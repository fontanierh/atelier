#pragma once
#include "JapanReactionJournal.h"
#include "GameFramework/CharacterMovementComponent.h"

/** Original saved-move boundaries survive retransmission independently of UE's
 * OldMove choice. Previous is stored, never reconstructed by float subtraction. */
struct FJapanReactionOrigin
{
    FJapanReactionStamp Previous, End;
    float DeltaTime = 0.f;
};

namespace JapanReactionTiming
{
enum class EResult : uint8 { InvalidMove, Exact, Clamped };
struct FPlan
{
    EResult Result = EResult::InvalidMove;
    float Before = 0.f, Reaction = 0.f, After = 0.f;
    bool bFolded = false;
};

/** Relative timestamps use only one adjacent accepted reset generation. The
 * reaction timeout is much shorter than a CMC timestamp-reset period. */
inline bool Relative(const FJapanReactionStamp& Stamp, const FJapanReactionStamp& End,
    float ResetPeriod, double& Out)
{
    if (!Stamp.IsValid() || !End.IsValid()) return false;
    const int64 Generations = int64(Stamp.Generation) - int64(End.Generation);
    if (Generations < -1 || Generations > 1) return false;
    // Match CMC's float timestamp subtraction, including rebasing Current at
    // reset. A double subtraction here can place an otherwise identical start
    // one ulp outside the float Dt that CMC admitted.
    const float Rebased = Stamp.Time + float(Generations) * ResetPeriod;
    Out = double(Rebased - End.Time);
    return FMath::IsFinite(Out);
}

/** Call only after ordinary CMC timestamp/epoch/budget admission. Never grants
 * simulation time: the three slices sum to the already accepted Dt. A forged,
 * stale or clipped origin gets a counted immediate fallback, not an exemption
 * from the strict correction gate. The caller validates the reaction sequence. */
inline FPlan Plan(const FJapanReactionStamp& Current, const FJapanReactionStamp& Resolved,
    const FJapanReactionStamp& End, float AcceptedDt, float MaximumDt, float ResetPeriod,
    const FJapanReactionOrigin& Origin, bool bStampDelta, float MinimumTick = UCharacterMovementComponent::MIN_TICK_TIME)
{
    FPlan Out;
    double CurrentAt = 0., ResolvedAt = 0.;
    if (!FMath::IsFinite(AcceptedDt) || !FMath::IsFinite(MaximumDt) ||
        !FMath::IsFinite(ResetPeriod) || AcceptedDt <= 0.f || MaximumDt <= 0.f ||
        AcceptedDt > MaximumDt || ResetPeriod <= MaximumDt || !FMath::IsFinite(MinimumTick) || MinimumTick <= 0.f ||
        !Relative(Current, End, ResetPeriod, CurrentAt) || CurrentAt >= 0. ||
        !Relative(Resolved, End, ResetPeriod, ResolvedAt) || ResolvedAt > 0.) return Out;

    Out.Result = EResult::Clamped; Out.Reaction = AcceptedDt;
    // CMC discrepancy resolution and actor dilation do not map simulation Dt
    // onto this timestamp interval. The caller supplies the actual effective
    // cap and explicitly marks these regimes; the fallback must be counted.
    if (!bStampDelta) return Out;
    double PreviousAt = 0., OriginEndAt = 0.;
    if (!FMath::IsFinite(Origin.DeltaTime) || Origin.DeltaTime <= 0.f || Origin.DeltaTime > MaximumDt ||
        !Relative(Origin.Previous, End, ResetPeriod, PreviousAt) ||
        !Relative(Origin.End, End, ResetPeriod, OriginEndAt) ||
        PreviousAt >= OriginEndAt || OriginEndAt > 0. ||
        OriginEndAt <= FMath::Max(CurrentAt, ResolvedAt)) return Out;

    // Capped owner frames can contain timestamp time that was never simulated.
    // Ordinary frames use the actual prior stamp, avoiding end-Dt roundoff at
    // the current/resolve boundary. Only a capped gap needs reconstruction.
    double StartAt = PreviousAt;
    if (OriginEndAt - PreviousAt > MaximumDt)
        StartAt = OriginEndAt - Origin.DeltaTime;
    const double Earliest = FMath::Max(-double(AcceptedDt), FMath::Max(CurrentAt, ResolvedAt));
    if (StartAt < Earliest || StartAt > 0.) return Out;

    Out.Before = FMath::Clamp(float(StartAt + double(AcceptedDt)), 0.f, AcceptedDt);
    const float Remaining = AcceptedDt - Out.Before;
    Out.Reaction = FMath::Min(Origin.DeltaTime, Remaining);
    Out.After = FMath::Max(0.f, Remaining - Out.Reaction);
    if (Out.Before > 0.f && Out.Before < MinimumTick)
    { Out.Reaction += Out.Before; Out.Before = 0.f; Out.bFolded = true; }
    if (Out.After > 0.f && Out.After < MinimumTick)
    { Out.Reaction += Out.After; Out.After = 0.f; Out.bFolded = true; }
    if (Out.Reaction < MinimumTick)
    {
        // There is no valid reaction simulation slice. Do not consume input
        // edges in an extra tiny MoveSet::Advance call.
        Out.Before = Out.After = 0.f; Out.Reaction = AcceptedDt;
        return Out;
    }
    Out.Result = EResult::Exact;
    return Out;
}
}
