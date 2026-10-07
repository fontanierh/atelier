#include "JapanDefenceTimeline.h"

void FJapanDefenceTimeline::Trace(double Time, const TCHAR* Reason) const
{
#if !UE_BUILD_SHIPPING
    for (const FWindow& W : Windows)
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence window reason=%s time=%.6f edge=%u kind=%u press=%.6f start=%.6f end=%.6f cutoff=%.6f consumed=%d serial=%u live_start=%.6f"),
            Reason, Time, W.Edge, uint32(W.Kind), W.Press, W.Start, W.End,
            W.SelfCutoff, W.bConsumed, W.ActionSerial, W.LiveStart);
    for (const FReaction& R : Reactions)
        UE_LOG(LogTemp, Display, TEXT("NETWORK defence reaction reason=%s time=%.6f contact=%.6f recovery_end=%.6f guard_end=%.6f"),
            Reason, Time, R.Time, R.RecoveryEnd, R.GuardEnd);
#endif
}

void FJapanDefenceTimeline::Record(const FJapanDefenceSample& Sample)
{
    if (!FMath::IsFinite(Sample.Time) || Sample.Location.ContainsNaN() || Sample.Forward.ContainsNaN()) return;
    if (!Samples.IsEmpty() && Sample.Time < Samples.Last().Time) return;
    if (!Samples.IsEmpty() && Sample.Time == Samples.Last().Time) Samples.Last() = Sample;
    else Samples.Add(Sample);
    const double PruneBefore = FMath::Min(Sample.Time, OldestPending) - MaximumHistory;
    while (Samples.Num() > 128 || (Samples.Num() > 1 && Samples[1].Time < PruneBefore)) Samples.RemoveAt(0);
    Reactions.RemoveAll([&](const FReaction& R) { return FMath::Max(R.RecoveryEnd, R.GuardEnd) < PruneBefore; });
    Windows.RemoveAll([&](const FWindow& W) { return W.End < PruneBefore; });
    // Keep the last older hold so a continuous guard survives without repeated edges.
    while (Holds.Num() > 1 && Holds[1].Time < PruneBefore) Holds.RemoveAt(0);
}

const FJapanDefenceSample* FJapanDefenceTimeline::At(double Time) const
{
    for (int32 I = Samples.Num() - 1; I >= 0; --I)
        if (Samples[I].Time <= Time)
        {
            const bool Recent = Time - Samples[I].Time <= MaximumSampleGap;
            const bool Bracketed = I + 1 < Samples.Num() && Samples[I + 1].Time - Samples[I].Time <= .15;
            return Recent || Bracketed ? &Samples[I] : nullptr;
        }
    return nullptr;
}

bool FJapanDefenceTimeline::GuardHeld(double Time, const FJapanDefenceSample& Sample) const
{
    bool bHeld = Sample.bGuardHeld;
    for (const FHold& H : Holds)
        if (H.Time <= Time && int16(H.Edge - Sample.ThroughEdge) > 0) bHeld = H.bHeld;
    return bHeld;
}

void FJapanDefenceTimeline::Hold(uint16 Edge, double Time, bool bHeld)
{
    if (!FMath::IsFinite(Time)) return;
    if (Holds.Num() >= 64) { ++HoldOverflows; return; }
    for (const FHold& H : Holds) if (H.Edge == Edge) return;
    if (!Holds.IsEmpty() && (int16(Edge - Holds.Last().Edge) <= 0 || Time < Holds.Last().Time)) return;
    Holds.Add({Edge, Time, bHeld});
}

bool FJapanDefenceTimeline::Add(uint16 Edge, double Press, EJapanDefence Kind,
    double StartAfterPress, double EndAfterPress, double PerfectAfterPress)
{
    const FJapanDefenceSample* Sample = At(Press);
    if (!Sample || !FMath::IsFinite(Press) || !FMath::IsFinite(StartAfterPress) || !FMath::IsFinite(EndAfterPress) ||
        !FMath::IsFinite(PerfectAfterPress) || StartAfterPress < 0. || EndAfterPress <= StartAfterPress ||
        EndAfterPress > 2. || Windows.Num() >= 32) return false;
    for (const FReaction& R : Reactions)
        if (Press >= R.Time && (Press < R.RecoveryEnd || (Kind == EJapanDefence::Parry && Press < R.GuardEnd))) return false;
    const bool bParry = Kind == EJapanDefence::Parry;
    if (Kind != EJapanDefence::Dodge && !bParry) return false;
    if (bParry ? (!Sample->bCanParry || !Sample->bArmed || Sample->bGuardBroken || !GuardHeld(Press, *Sample)) : !Sample->bCanDodge) return false;
    // One original edge can carry multiple authored parry intervals, but a retransmit
    // cannot recreate an identical interval or erase its consumed state.
    for (const FWindow& W : Windows)
        if (W.Edge == Edge && (W.bConsumed || W.Press != Press || W.Kind != Kind ||
            (W.Start == Press + StartAfterPress && W.End == Press + EndAfterPress))) return false;
    Windows.Add({Edge, Press, Press + StartAfterPress, Press + EndAfterPress,
        Press + FMath::Clamp(PerfectAfterPress, 0., EndAfterPress), Kind, false});
    return true;
}

void FJapanDefenceTimeline::Reaction(double Contact, double RecoverySeconds, double GuardBrokenSeconds)
{
    if (!FMath::IsFinite(Contact) || !FMath::IsFinite(RecoverySeconds) || !FMath::IsFinite(GuardBrokenSeconds)) return;
    if (RecoverySeconds <= 0. && GuardBrokenSeconds <= 0.) return;
    // At most 8 queued contacts per victim; this also holds ample live history.
    if (Reactions.Num() >= 32) Reactions.RemoveAt(0);
    Reactions.Add({Contact, Contact + FMath::Max(0., RecoverySeconds), Contact + FMath::Max(0., GuardBrokenSeconds)});
}

void FJapanDefenceTimeline::BindAction(uint16 Edge, uint32 Serial, double LiveStart)
{
    if (!Serial || !FMath::IsFinite(LiveStart)) return;
    for (FWindow& W : Windows)
        if (W.Edge == Edge && !W.ActionSerial && LiveStart >= W.Press)
        { W.ActionSerial = Serial; W.LiveStart = LiveStart; }
}

void FJapanDefenceTimeline::SelfCutoff(uint32 Serial, double LiveTime)
{
    if (!Serial || !FMath::IsFinite(LiveTime)) return;
    for (FWindow& W : Windows)
        if (W.ActionSerial == Serial && LiveTime >= W.LiveStart)
            W.SelfCutoff = FMath::Min(W.SelfCutoff, W.Press + LiveTime - W.LiveStart);
}

void FJapanDefenceTimeline::CancelByInput(uint32 Serial, double OriginalTime)
{
    if (!Serial || !FMath::IsFinite(OriginalTime)) return;
    for (FWindow& W : Windows)
        if (W.ActionSerial == Serial && OriginalTime >= W.Press)
            W.SelfCutoff = FMath::Min(W.SelfCutoff, OriginalTime);
}

EJapanDefence FJapanDefenceTimeline::Resolve(double Contact, const FVector& From, float GuardCosine, uint16& UsedEdge)
{
    UsedEdge = 0;
    if (!FMath::IsFinite(Contact) || From.ContainsNaN() || !FMath::IsFinite(GuardCosine)) return EJapanDefence::None;
    bool Broken = false;
    for (const FReaction& R : Reactions)
        if (Contact >= R.Time)
        {
            if (Contact < R.RecoveryEnd) return EJapanDefence::Recovering;
            Broken |= Contact < R.GuardEnd;
        }
    // Parry precedes dodge and recovery, matching IncomingStrike's authored priority.
    for (EJapanDefence Kind : {EJapanDefence::Parry, EJapanDefence::Dodge})
        for (FWindow& W : Windows)
            if (W.Kind == Kind && !(Broken && Kind == EJapanDefence::Parry) && !W.bConsumed && W.Start <= Contact && Contact <= W.End &&
                (Kind == EJapanDefence::Dodge || Contact < W.SelfCutoff))
            {
                UsedEdge = W.Edge;
                if (!W.ActionSerial) ++AuthoredFallbacks;
                // Landing ends the hop, not its remaining invulnerability. Live
                // IncomingStrike calls this recovery, so it cannot trigger a flurry.
                if (Kind == EJapanDefence::Dodge && Contact >= W.SelfCutoff) return EJapanDefence::Recovering;
                if (Kind == EJapanDefence::Parry)
                    for (FWindow& Same : Windows) if (Same.Edge == UsedEdge) Same.bConsumed = true;
                return Kind == EJapanDefence::Dodge && W.PerfectEnd > W.Press && Contact <= W.PerfectEnd ? EJapanDefence::PerfectDodge : Kind;
            }
    const FJapanDefenceSample* Sample = At(Contact);
    if (!Sample) { ++MissingSamples; return EJapanDefence::None; }
    if (Sample->bRecovering) return EJapanDefence::Recovering;
    if (!Broken && !Sample->bGuardBroken && Sample->bGround && Sample->bArmed && GuardHeld(Contact, *Sample) &&
        (Sample->Forward.GetSafeNormal2D() | (From - Sample->Location).GetSafeNormal2D()) >= GuardCosine)
        return EJapanDefence::Guard;
    return EJapanDefence::None;
}
