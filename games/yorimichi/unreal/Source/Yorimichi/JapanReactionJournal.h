#pragma once
#include "CoreMinimal.h"

/** A CMC timestamp together with its accepted reset generation. Generations
 * belong to the movement clock, not to a wall clock supplied by the owner. */
struct FJapanReactionStamp
{
    uint32 Generation = 0;
    float Time = 0.f;
    bool IsValid() const { return FMath::IsFinite(Time) && Time >= 0.f; }
    bool operator==(const FJapanReactionStamp& Other) const
    { return Generation == Other.Generation && Time == Other.Time; }
    bool operator<(const FJapanReactionStamp& Other) const
    { return Generation < Other.Generation || (Generation == Other.Generation && Time < Other.Time); }
};

/** Value-only movement delta. Its codec and action validation belong to the
 * move set; the journal neither calls combat nor stores actor references. */
struct FJapanReactionValue
{
    static constexpr int32 MaximumBytes = 256;
    FName Action;
    TArray<uint8> Bytes;
    bool IsValid() const { return !Bytes.IsEmpty() && Bytes.Num() <= MaximumBytes; }
    bool operator==(const FJapanReactionValue& Other) const
    { return Action == Other.Action && Bytes == Other.Bytes; }
};

struct FJapanScheduledReaction
{
    uint32 Epoch = 0, Sequence = 0;
    FJapanReactionStamp Resolved;
    FJapanReactionValue Value;
    /** Reliable owner delivery uses this same codec as the native roundtrip test.
     * Epoch, generation and float timestamp are exact; no quantization. */
    bool Serialize(FArchive& Ar);
    bool IsValid() const { return Epoch && Sequence && Resolved.IsValid() && Value.IsValid(); }
    bool operator==(const FJapanScheduledReaction& Other) const
    {
        return Epoch == Other.Epoch && Sequence == Other.Sequence &&
            Resolved == Other.Resolved && Value == Other.Value;
    }
};

/** Bounded retained payloads, shared by authority and owner. Application is
 * deliberately separate from health, cues, transport and timestamp admission.
 * A good ACK alone cannot retire a payload needed by a pending replay. */
class FJapanReactionJournal
{
public:
    static constexpr int32 Capacity = 8, RetainedCapacity = Capacity + 1;
    enum class EReceive : uint8 { Added, Duplicate, Covered, WrongEpoch, Invalid, Gap, Full, Recovering };

    bool Reset(uint32 InEpoch)
    {
        if (!InEpoch || InEpoch <= Epoch) { ++RejectedResets; return false; }
        Epoch = InEpoch; KnownThrough = AppliedThrough = RetiredThrough = 0;
        DisposedThrough = CheckpointThrough = 0; Entries.Reset();
        bRecovery = false; RecoveryThrough = 0; return true;
    }
    // Lifetime counters survive epoch replacement. Recovery is a named failure,
    // never a strict-pass exemption; the runtime must request host reconciliation.
    uint32 RecoveryRequests = 0, FailedRestores = 0, RejectedResets = 0;
    bool NeedsRecovery() const { return bRecovery; }
    uint32 Known() const { return KnownThrough; }
    uint32 Applied() const { return AppliedThrough; }
    uint32 Retired() const { return RetiredThrough; }
    int32 Num() const { return Entries.Num(); }
    bool HasPending() const { return bRecovery || KnownThrough > AppliedThrough; }
    const FJapanScheduledReaction* Find(uint32 Sequence) const
    {
        return Entries.FindByPredicate([&](const FJapanScheduledReaction& Item) { return Item.Sequence == Sequence; });
    }

    /** Failure leaves the journal unchanged; the caller owns the counted
     * overflow/epoch fallback, including an ordinary authoritative correction. */
    bool Issue(const FJapanReactionStamp& Resolved, const FJapanReactionValue& Value, FJapanScheduledReaction& Out)
    {
        if (bRecovery || !Epoch || KnownThrough == MAX_uint32 || KnownThrough - AppliedThrough >= Capacity ||
            Entries.Num() >= RetainedCapacity || !Resolved.IsValid() || !Value.IsValid()) return false;
        FJapanScheduledReaction Item{Epoch, KnownThrough + 1, Resolved, Value};
        Entries.Add(Item); KnownThrough = Item.Sequence; Out = MoveTemp(Item); return true;
    }

    EReceive Receive(const FJapanScheduledReaction& Item)
    {
        if (!Item.IsValid()) return EReceive::Invalid;
        if (Item.Epoch != Epoch) return EReceive::WrongEpoch;
        if (const auto* Existing = Find(Item.Sequence))
            return *Existing == Item ? EReceive::Duplicate : EReceive::Invalid;
        // A checkpoint can overtake the reliable payload. Its committed state
        // already includes the reaction; late delivery must not apply it again.
        if (Item.Sequence <= RetiredThrough || Item.Sequence <= AppliedThrough) return EReceive::Covered;
        // The authority may have freed a serialized checkpoint that the owner
        // has not accepted yet. A reliable Full must not become a silent gap:
        // latch recovery through every missed sequence until a checkpoint covers
        // them (or an authoritative epoch replacement cancels them).
        if (bRecovery) { RequireRecovery(Item.Sequence); return EReceive::Recovering; }
        if (KnownThrough == MAX_uint32 || Item.Sequence != KnownThrough + 1)
        { RequireRecovery(Item.Sequence); return EReceive::Gap; }
        if (KnownThrough - AppliedThrough >= Capacity || Entries.Num() >= RetainedCapacity)
        { RequireRecovery(Item.Sequence); return EReceive::Full; }
        Entries.Add(Item); KnownThrough = Item.Sequence; return EReceive::Added;
    }

    /** Validate the whole range before invoking any movement callback. The
     * callback applies only a validated immutable movement delta, never damage,
     * and must not mutate this journal or replace its epoch. */
    bool Apply(uint32 Through, TFunctionRef<void(const FJapanScheduledReaction&)> ApplyValue)
    {
        // Recovery blocks new delivery, not replay of retained known history.
        // A CMC correction can require those values before recovery completes.
        if (Through > KnownThrough) return false;
        if (Through <= AppliedThrough) return true;
        uint32 Sequence = AppliedThrough;
        while (Sequence < Through)
            if (!Find(++Sequence)) return false;
        while (AppliedThrough < Through)
        {
            const auto* Item = Find(AppliedThrough + 1);
            ApplyValue(*Item); ++AppliedThrough;
        }
        return true;
    }

    /** Restore only after CMC accepts this checkpoint. Saved moves keep their
     * original Through value, so replay applies every subsequent value once. */
    bool Restore(uint32 Through)
    {
        if (Through < RetiredThrough)
        { ++FailedRestores; RequireRecovery(KnownThrough); return false; }
        AppliedThrough = Through;
        KnownThrough = FMath::Max(KnownThrough, Through);
        if (bRecovery && Through >= RecoveryThrough) { bRecovery = false; RecoveryThrough = 0; }
        return true;
    }

    /** Owner: actual saved-move disposal plus an accepted checkpoint. Authority:
     * accepted moves plus a successfully serialized matching checkpoint. */
    void Retire(uint32 Disposed, uint32 Checkpoint)
    {
        DisposedThrough = FMath::Max(DisposedThrough, FMath::Min(Disposed, AppliedThrough));
        CheckpointThrough = FMath::Max(CheckpointThrough, FMath::Min(Checkpoint, AppliedThrough));
        RetiredThrough = FMath::Max(RetiredThrough, FMath::Min(DisposedThrough, CheckpointThrough));
        Entries.RemoveAll([&](const FJapanScheduledReaction& Item) { return Item.Sequence <= RetiredThrough; });
    }
private:
    void RequireRecovery(uint32 Through)
    {
        if (!bRecovery) ++RecoveryRequests;
        bRecovery = true; RecoveryThrough = FMath::Max(RecoveryThrough, Through);
    }
    uint32 Epoch = 0, KnownThrough = 0, AppliedThrough = 0, RetiredThrough = 0;
    uint32 DisposedThrough = 0, CheckpointThrough = 0;
    uint32 RecoveryThrough = 0;
    bool bRecovery = false;
    TArray<FJapanScheduledReaction, TInlineAllocator<RetainedCapacity>> Entries;
};
