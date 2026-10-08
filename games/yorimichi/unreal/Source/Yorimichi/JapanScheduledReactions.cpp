#include "JapanCharacterMovement.h"
#include "BotwMoveSet.h"
#include "BotwMovementReaction.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "JapanNetwork.h"
#include "JapanReactionDeliveryQA.h"
#include "JapanCombatQA.h"
#include "Engine/NetConnection.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"
#include "TimerManager.h"

void AWandererCharacter::ClientReceiveMovementReaction_Implementation(const TArray<uint8>& Encoded)
{
    if (GetLocalRole() == ROLE_AutonomousProxy)
        CastChecked<UJapanCharacterMovement>(GetCharacterMovement())->ReceiveScheduledReaction(Encoded);
}

void AWandererCharacter::ServerRecoverMovementReactions_Implementation(uint32 Epoch)
{
    CastChecked<UJapanCharacterMovement>(GetCharacterMovement())->RecoverScheduledReactions(Epoch);
}

void UJapanCharacterMovement::ResetScheduledReactions()
{
    if (!ReactionJournal.Reset(GetActivityEpoch())) { ++ReactionStats.RejectedResets; return; }
    // Called only by ResetActivityPrediction, which deletes both CMC prediction
    // data objects. Their real prior timestamp and wrap generation are now zero.
    ReactionPrevious = ReactionCurrent = ReactionOwnerEnd = FJapanReactionStamp();
    ReactionOrigins.Reset(); ReactionAcceptedCheckpoint = ReactionDisposed = 0;
    ReactionDeadlines.Reset(); ReactionLastRecoveredThrough = 0; ReactionLastRecovery = -1.;
    ReactionWindows.Reset(); bLethalReactionQueued = false;
    auto Waiting = MoveTemp(FutureReactions); FutureReactions.Reset();
    for (const auto& Encoded : Waiting) ReceiveScheduledReaction(Encoded);
}

bool UJapanCharacterMovement::QueueScheduledReaction(const FJapanReactionValue& Value)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (!Rider || !JapanNetwork::IsOnline(GetWorld()) || !Rider->HasAuthority() ||
        Rider->GetRemoteRole() != ROLE_AutonomousProxy || Rider->IsNpc() || !PredictsMoves() ||
        Rider->GetNetworkActivity() != EJapanActivity::OnFoot || bImmediateMovementReaction ||
        !Rider->GetSword() || Rider->GetSword()->GetHealth() <= 0.f) return false;
    FBotwMovementReaction Payload;
    if (!FBotwMovementReaction::Decode(Value, Payload)) { ++ReactionStats.InvalidPayloads; return false; }
    FJapanScheduledReaction Event;
    if (!ReactionJournal.Issue(ReactionCurrent, Value, Event))
    {
        ++ReactionStats.Forced;
        ApplyScheduledThrough(ReactionJournal.Known()); QueueReactionCheckpoint();
        return false; // Never drop damage/reaction; caller applies the new value immediately.
    }
    TArray<uint8> Encoded;
    FMemoryWriter Writer(Encoded, true);
    if (!Event.Serialize(Writer))
    {
        ++ReactionStats.InvalidPayloads; ++ReactionStats.Forced;
        ApplyScheduledThrough(Event.Sequence); QueueReactionCheckpoint(); return true;
    }
    ++ReactionStats.Issued;
    JapanReactionDeliveryQA::Scheduled(this, TEXT("reaction_issued"), Event);
    AddReactionWindow(Event);
    CastChecked<AWandererCharacter>(CharacterOwner)->ClientReceiveMovementReaction(Encoded);
    {
        const auto* Controller = Cast<APlayerController>(CharacterOwner->Controller);
        const auto* Connection = Controller ? Controller->GetNetConnection() : nullptr;
        const double RTT = Connection ? Connection->RawPingInSeconds : 0.;
        const double Jitter = Connection ? Connection->GetAverageJitterInMS() * .001 : 0.;
        if (Event.Sequence > ReactionJournal.Applied())
            ScheduleReactionDeadline(Event.Sequence, FPlatformTime::Seconds(), RTT, Jitter);
    }
    return true;
}

void UJapanCharacterMovement::AddReactionWindow(const FJapanScheduledReaction& Event)
{
    if (ReactionWindows.Num() == 32)
    {
        int32 Closed = ReactionWindows.IndexOfByPredicate([](const FReactionWindow& W) { return W.bClosed; });
        if (!ensureMsgf(Closed != INDEX_NONE, TEXT("Reaction window capacity cannot fill with pending journal events")))
        {
            ++ReactionStats.Forced; ApplyScheduledThrough(ReactionJournal.Known()); QueueReactionCheckpoint();
            Closed = ReactionWindows.IndexOfByPredicate([](const FReactionWindow& W) { return W.bClosed; });
        }
        if (Closed == INDEX_NONE) return; // Named forced error; never evict an open eligibility interval.
        ReactionWindows.RemoveAt(Closed, 1, EAllowShrinking::No);
    }
    const bool Applied = Event.Sequence <= ReactionJournal.Applied();
    ReactionWindows.Add({Event.Sequence, Event.Resolved, Applied ? ReactionCurrent : FJapanReactionStamp{},
        Applied, ProcessedEdge, Applied ? ProcessedEdge : uint16(0)});
}

bool UJapanCharacterMovement::QueueLethalReaction(const FJapanReactionValue& Value)
{
    auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (!Rider || !JapanNetwork::IsOnline(GetWorld()) || !Rider->HasAuthority() ||
        Rider->GetRemoteRole() != ROLE_AutonomousProxy || Rider->IsNpc() ||
        Rider->GetNetworkActivity() != EJapanActivity::OnFoot || bImmediateMovementReaction ||
        !Rider->GetSword() || Rider->GetSword()->GetHealth() > 0.f) return false;
    if (bLethalReactionQueued) return true;
    FBotwMovementReaction Payload;
    if (!FBotwMovementReaction::Decode(Value, Payload)) { ++ReactionStats.InvalidPayloads; return false; }
    bLethalReactionQueued = true;
    const uint32 Epoch = GetActivityEpoch();
    // Health/cues are already committed. End the epoch at the next safe CMC
    // boundary, without running another old-epoch move or damaging twice.
    GetWorld()->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this, [this, Epoch, Payload]()
    {
        if (Epoch != GetActivityEpoch())
        {
            ++ReactionStats.LethalSuperseded;
            UE_LOG(LogJapanMovementQA, Error, TEXT("Lethal reaction superseded before epoch replacement old=%u current=%u"), Epoch, GetActivityEpoch());
            return;
        }
        if (ReactionJournal.Applied() < ReactionJournal.Known())
        { ++ReactionStats.Forced; ApplyScheduledThrough(ReactionJournal.Known()); }
        JapanReactionDeliveryQA::State(this, TEXT("lethal_before_epoch"), ReactionJournal.HasPending(), false, ReactionCurrent.Time);
        auto* Victim = CastChecked<AWandererCharacter>(CharacterOwner);
        Victim->BeginNetworkActivity(EJapanActivity::OnFoot, IsFalling(), 0,
            [Victim, Payload]() { Victim->GetMoves()->ApplyMovementReaction(Payload); });
    }));
    return true;
}

bool UJapanCharacterMovement::ReactionEdgeEligible(TOptional<uint16> Edge, bool bContinuousHold) const
{
    // Zero is a real wrapped sequence, never a missing-origin sentinel.
    if (!Edge.IsSet()) return true;
    for (const FReactionWindow& Window : ReactionWindows)
        if ((!bContinuousHold || !Window.bClosed) && int16(Edge.GetValue() - Window.ResolvedEdge) > 0 &&
            (!Window.bClosed || int16(Window.AcknowledgedEdge - Edge.GetValue()) >= 0)) return false;
    return true;
}

bool UJapanCharacterMovement::AllowScheduledAttack(TOptional<uint16> Edge)
{
    if (ReactionEdgeEligible(Edge)) return true;
    ++ReactionStats.SuppressedAttacks;
    return false;
}

void UJapanCharacterMovement::ReceiveScheduledReaction(const TArray<uint8>& Encoded)
{
    if (!CharacterOwner || CharacterOwner->GetLocalRole() != ROLE_AutonomousProxy) return;
    if (Encoded.IsEmpty() || Encoded.Num() > FJapanReactionValue::MaximumBytes + 32)
    { ++ReactionStats.InvalidPayloads; return; }
    FMemoryReader Reader(Encoded, true);
    FJapanScheduledReaction Event;
    FBotwMovementReaction Payload;
    if (!Event.Serialize(Reader) || !Reader.AtEnd() || !FBotwMovementReaction::Decode(Event.Value, Payload))
    { ++ReactionStats.InvalidPayloads; return; }
    if (Event.Epoch > GetActivityEpoch())
    {
        // Property replication and the reliable actor RPC may arrive in separate
        // bunches. Keep only a bounded next-epoch delivery until OnRep resets.
        if (GetActivityEpoch() != MAX_uint32 && Event.Epoch == GetActivityEpoch() + 1 &&
            FutureReactions.Num() < FJapanReactionJournal::RetainedCapacity) FutureReactions.Add(Encoded);
        else ++ReactionStats.InvalidPayloads;
        return;
    }
    // Recovering extends the required prefix without another RPC. The host's
    // bounded deadline/periodic checkpoints cover later in-flight events.
    using E = FJapanReactionJournal::EReceive;
    const E Result = ReactionJournal.Receive(Event);
    if (Result == E::WrongEpoch)
        JapanReactionDeliveryQA::Scheduled(this, TEXT("reaction_wrong_epoch"), Event);
    if (Result == E::Added)
    { ++ReactionStats.Received; JapanReactionDeliveryQA::Scheduled(this, TEXT("reaction_received"), Event); }
    if (Result == E::Invalid) ++ReactionStats.InvalidPayloads;
    if (Result == E::Full || Result == E::Gap)
    {
        ++ReactionStats.Recoveries;
        CastChecked<AWandererCharacter>(CharacterOwner)->ServerRecoverMovementReactions(GetActivityEpoch());
    }
}

void UJapanCharacterMovement::PrepareReactionMove(FJapanMoveInput& Input, float Timestamp, float Dt)
{
    if (!PredictsMoves() || !CharacterOwner || CharacterOwner->GetLocalRole() != ROLE_AutonomousProxy) return;
    FJapanReactionStamp End = ReactionOwnerEnd;
    if (End.Generation == 0 && End.Time == 0.f)
        JapanReactionDeliveryQA::FirstMove(this, Timestamp, Dt, CharacterOwner->GetActorLocation());
    if (Timestamp < End.Time) ++End.Generation; // UE has already performed its periodic reset.
    End.Time = Timestamp;
    if (!ReactionJournal.NeedsRecovery())
        for (uint32 Sequence = ReactionJournal.Applied(); Sequence < ReactionJournal.Known();)
        {
            ++Sequence;
            if (!ReactionOrigins.ContainsByPredicate([&](const FJapanReactionMarker& M) { return M.Sequence == Sequence; }))
            {
                ReactionOrigins.Add({Sequence, {ReactionOwnerEnd, End, Dt}, ProcessedEdge,
                    Input.Edges.IsEmpty() ? ProcessedEdge : uint16(Input.FirstEdge + Input.Edges.Num() - 1)});
                if (const auto* Event = ReactionJournal.Find(Sequence))
                    JapanReactionDeliveryQA::Scheduled(this, TEXT("reaction_prepared"), *Event, &ReactionOrigins.Last());
            }
        }
    Input.ReactionThrough = ReactionJournal.NeedsRecovery() ? ReactionJournal.Applied() : ReactionJournal.Known();
    for (const auto& Marker : ReactionOrigins)
        if (Marker.Sequence <= Input.ReactionThrough) Input.ReactionOrigins.Add(Marker);
    ReactionOwnerEnd = End;
}

void UJapanCharacterMovement::AcceptReactionMove(float Timestamp)
{
    ReactionPrevious = ReactionCurrent;
    if (Timestamp < ReactionCurrent.Time) ++ReactionCurrent.Generation;
    ReactionCurrent.Time = Timestamp;
}

void UJapanCharacterMovement::ApplyScheduledThrough(uint32 Through)
{
    // A callback must not fail after the journal advances its marker. Validate
    // the complete retained suffix before applying any movement side effects.
    for (uint32 Sequence = ReactionJournal.Applied(); Sequence < Through && Sequence < ReactionJournal.Known();)
    {
        const auto* Event = ReactionJournal.Find(++Sequence);
        FBotwMovementReaction Payload;
        if (Event && !FBotwMovementReaction::Decode(Event->Value, Payload))
        {
            ++ReactionStats.InvalidPayloads; ++ReactionStats.FailedApply;
            UE_LOG(LogJapanMovementQA, Error, TEXT("Invalid retained reaction payload epoch=%u sequence=%u"), GetActivityEpoch(), Sequence);
            return;
        }
    }
    if (!ReactionJournal.Apply(Through, [&](const FJapanScheduledReaction& Event)
    {
        FBotwMovementReaction Payload;
        if (!FBotwMovementReaction::Decode(Event.Value, Payload))
        { ++ReactionStats.InvalidPayloads; return; }
        CastChecked<AWandererCharacter>(CharacterOwner)->GetMoves()->ApplyMovementReaction(Payload);
        if (CharacterOwner->HasAuthority())
            for (auto& Window : ReactionWindows)
                if (Window.Sequence == Event.Sequence && !Window.bClosed)
                { Window.Acknowledged = ReactionCurrent; Window.AcknowledgedEdge = ProcessedEdge; Window.bClosed = true; }
        if (bReplaying) ++ReactionStats.Replayed; else ++ReactionStats.Applied;
        const auto* Marker = ActiveInput.ReactionOrigins.FindByPredicate([&](const FJapanReactionMarker& M) { return M.Sequence == Event.Sequence; });
        JapanReactionDeliveryQA::Scheduled(this, TEXT("reaction_applied"), Event, Marker);
        JapanCombatQA::ReactionApplied(this, Event.Epoch, Event.Sequence);
    }))
    {
        ++ReactionStats.FailedApply;
        UE_LOG(LogJapanMovementQA, Error, TEXT("Scheduled reaction replay is missing retained payloads epoch=%u through=%u"), GetActivityEpoch(), Through);
        if (CharacterOwner->GetLocalRole() == ROLE_AutonomousProxy)
            CastChecked<AWandererCharacter>(CharacterOwner)->ServerRecoverMovementReactions(GetActivityEpoch());
    }
    ReactionDeadlines.RemoveAll([&](const FReactionDeadline& Deadline) { return Deadline.Sequence <= ReactionJournal.Applied(); });
}

void UJapanCharacterMovement::ScheduleReactionDeadline(uint32 Sequence, double Now, double RTT, double Jitter)
{
    static_assert(MaximumReactionWait < FBotwMovementReaction::HitImmunitySeconds,
        "A heavy hit must reach physical down before its contact-time immunity ends");
    ReactionDeadlines.Add({Sequence, Now + (RTT > 0. ?
        FMath::Clamp(3. * RTT + Jitter + .03, .25, MaximumReactionWait) : MaximumReactionWait)});
}

bool UJapanCharacterMovement::ReactionDeadlineExpired(double Now) const
{
    return ReactionDeadlines.ContainsByPredicate([&](const FReactionDeadline& Deadline) { return Now >= Deadline.At; });
}

bool UJapanCharacterMovement::AllowReactionRecoveryRequest(double Now, double RTT)
{
    const double Interval = FMath::Clamp(RTT, .05, MaximumReactionWait);
    if ((!ReactionJournal.HasPending() && ReactionJournal.Known() <= ReactionLastRecoveredThrough) ||
        (ReactionLastRecovery >= 0. && Now - ReactionLastRecovery < Interval)) return false;
    ReactionLastRecovery = Now; ReactionLastRecoveredThrough = ReactionJournal.Known();
    return true;
}

void UJapanCharacterMovement::RecoverScheduledReactions(uint32 Epoch, bool bClientRequest)
{
    if (!CharacterOwner || !CharacterOwner->HasAuthority() || CharacterOwner->GetRemoteRole() != ROLE_AutonomousProxy ||
        Epoch != GetActivityEpoch() || !PredictsMoves()) return;
    const double Now = FPlatformTime::Seconds();
    const auto* Controller = Cast<APlayerController>(CharacterOwner->Controller);
    const auto* Connection = Controller ? Controller->GetNetConnection() : nullptr;
    // One request may repair owner retention after the host already applied it.
    // Repeated requests for the same covered prefix cannot force fresh work.
    if (bClientRequest && !AllowReactionRecoveryRequest(Now, Connection ? Connection->RawPingInSeconds : .1))
    { ++ReactionStats.RejectedRecoveries; return; }
    if (!bClientRequest) { ReactionLastRecovery = Now; ReactionLastRecoveredThrough = ReactionJournal.Known(); }
    ++ReactionStats.Recoveries; ++ReactionStats.Forced;
    ApplyScheduledThrough(ReactionJournal.Known());
    QueueReactionCheckpoint(); // Next captured state explicitly carries Through=Known.
}

void UJapanCharacterMovement::TickScheduledReactions()
{
    if (CharacterOwner && CharacterOwner->HasAuthority() && ReactionDeadlineExpired(FPlatformTime::Seconds()))
        RecoverScheduledReactions(GetActivityEpoch(), false);
}

void UJapanCharacterMovement::RetireReactionOrigins()
{
    ReactionOrigins.RemoveAll([&](const FJapanReactionMarker& M) { return M.Sequence <= ReactionJournal.Retired(); });
}

void UJapanCharacterMovement::DisposeReactionMoves(uint32 Through)
{
    ReactionDisposed = FMath::Max(ReactionDisposed, Through);
    ReactionJournal.Retire(ReactionDisposed, ReactionAcceptedCheckpoint); RetireReactionOrigins();
}

void UJapanCharacterMovement::AcceptReactionCheckpoint(const FJapanMoveCheckpoint& State, uint32 Disposed, bool bAuthoritative)
{
    // Only after CMC accepted and the move-set state successfully restored.
    if ((bAuthoritative && State.ReactionThrough < ReactionAcceptedCheckpoint) || !ReactionJournal.Restore(State.ReactionThrough))
    {
        ++ReactionStats.FailedRestore;
        UE_LOG(LogJapanMovementQA, Error, TEXT("Accepted movement checkpoint cannot restore reaction journal epoch=%u through=%u"),
            GetActivityEpoch(), State.ReactionThrough);
        CastChecked<AWandererCharacter>(CharacterOwner)->ServerRecoverMovementReactions(GetActivityEpoch()); return;
    }
    if (bAuthoritative) ReactionAcceptedCheckpoint = State.ReactionThrough;
    DisposeReactionMoves(Disposed);
}

void UJapanCharacterMovement::SimulateReactionMove(float Dt, TFunctionRef<void(float, float, TOptional<uint16>)> Step)
{
    const uint32 Through = ActiveInput.ReactionThrough;
    if (Through <= ReactionJournal.Applied()) { Step(Dt, 0.f, {}); return; }
    if (!CharacterOwner->HasAuthority())
    { ApplyScheduledThrough(Through); Step(Dt, 0.f, {}); return; }
    if (Through > ReactionJournal.Known())
    { ++ReactionStats.InvalidOrigins; Step(Dt, 0.f, {}); return; }
    const auto* Server = GetPredictionData_Server_Character();
    const auto* Scalar = IConsoleManager::Get().FindConsoleVariable(TEXT("p.NetServerMaxMoveDeltaTimeScalar"));
    const float Dilation = CharacterOwner->GetActorTimeDilation();
    const float MaximumDt = Server->MaxMoveDeltaTime * (Scalar ? Scalar->GetFloat() : 1.f) * Dilation;
    const bool StampDelta = !Server->bResolvingTimeDiscrepancy && Dilation == 1.f;
    struct FCut { float At; uint32 Through; uint16 EdgeThrough; };
    TArray<FCut, TInlineAllocator<2 * FJapanReactionJournal::RetainedCapacity>> Cuts;
    float LastStart = 0.f;
    for (uint32 Sequence = ReactionJournal.Applied(); Sequence < Through;)
    {
        ++Sequence;
        const auto* Event = ReactionJournal.Find(Sequence);
        const auto* Marker = ActiveInput.ReactionOrigins.FindByPredicate([&](const FJapanReactionMarker& M) { return M.Sequence == Sequence; });
        const auto Plan = Event && Marker ? JapanReactionTiming::Plan(ReactionPrevious, Event->Resolved, ReactionCurrent,
            Dt, MaximumDt, MinTimeBetweenTimeStampResets, Marker->Origin, StampDelta) : JapanReactionTiming::FPlan();
        const uint16 LastEdge = ActiveInput.Edges.IsEmpty() ? ProcessedEdge : uint16(ActiveInput.FirstEdge + ActiveInput.Edges.Num() - 1);
        const bool EdgeBounds = Marker && int16(Marker->EdgeBefore - ProcessedEdge) >= 0 &&
            int16(LastEdge - Marker->EdgeAfter) >= 0 && uint16(Marker->EdgeAfter - Marker->EdgeBefore) <= FJapanMoveInput::MaximumEdges;
        if (Plan.Result != JapanReactionTiming::EResult::Exact || Plan.Before < LastStart || !EdgeBounds)
        {
            ++ReactionStats.InvalidOrigins;
            ApplyScheduledThrough(Through); QueueReactionCheckpoint(); Step(Dt, 0.f, {}); return;
        }
        if (Plan.bFolded) ++ReactionStats.FoldedSlices;
        Cuts.Add({Plan.Before, Sequence, Marker->EdgeBefore});
        if (Plan.After >= MIN_TICK_TIME) Cuts.Add({Plan.Before + Plan.Reaction, 0, Marker->EdgeAfter});
        LastStart = Plan.Before;
    }
    Cuts.StableSort([](const FCut& A, const FCut& B) { return A.At < B.At; });
    float Elapsed = 0.f;
    for (const FCut& Cut : Cuts)
    {
        if (Cut.At - Elapsed >= MIN_TICK_TIME)
        { Step(Cut.At - Elapsed, Dt - Cut.At, Cut.EdgeThrough); Elapsed = Cut.At; }
        else if (int16(Cut.EdgeThrough - ProcessedEdge) > 0)
            Step(0.f, Dt - Elapsed, Cut.EdgeThrough); // Consume boundary edges without advancing physics.
        if (Cut.Through)
        {
            // The acknowledged boundary is the owner's original saved move,
            // even when a later packet carries its lost marker and merged time.
            const auto* Marker = ActiveInput.ReactionOrigins.FindByPredicate([&](const FJapanReactionMarker& M) { return M.Sequence == Cut.Through; });
            for (auto& Window : ReactionWindows)
                if (Marker && Window.Sequence == Cut.Through && !Window.bClosed)
                { Window.Acknowledged = Marker->Origin.Previous; Window.AcknowledgedEdge = Marker->EdgeBefore; Window.bClosed = true; }
            ApplyScheduledThrough(Cut.Through);
        }
    }
    if (Dt > Elapsed) Step(Dt - Elapsed, 0.f, {});
    QueueReactionCheckpoint();
}
