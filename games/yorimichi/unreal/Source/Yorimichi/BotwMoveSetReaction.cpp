#include "BotwMoveSet.h"
#include "BotwMovementReaction.h"
#include "WandererCharacter.h"
#include "GameFramework/CharacterMovementComponent.h"

void UBotwMoveSet::FreezeReactionAction(FBotwMovementReaction& Reaction, FName Name, float Blend) const
{
    if (const FBotwMove* Move = Find(Name))
    {
        Reaction.Action = Name; Reaction.Blend = Blend;
        Reaction.SourceStart = Move->Start; Reaction.PlayRate = Move->Rate;
    }
}

void UBotwMoveSet::FreezeReactionFlinch(FBotwMovementReaction& Reaction, const FVector& Away,
    float Degrees, float Peak, float Side) const
{
    Reaction.Flags |= FBotwMovementReaction::Flinch;
    Reaction.FlinchAxis = FVector::CrossProduct(FVector::UpVector, Away.GetSafeNormal2D());
    if (Reaction.FlinchAxis.IsNearlyZero()) Reaction.FlinchAxis = -Character->GetActorRightVector();
    Reaction.FlinchAngle = Degrees * GetParam(TEXT("FlinchScale"), 1.f);
    Reaction.FlinchPeak = FMath::Max(Peak, .02f);
    Reaction.FlinchTwist = FMath::Sign(Side) * .45f;
}

void UBotwMoveSet::SubmitMovementReaction(const FBotwMovementReaction& Reaction)
{
    // The transport layer will schedule only eligible remote on-foot reactions.
    // This extraction keeps the immediate path shared with offline/NPC/host play.
    const bool Draw = (Reaction.Flags & FBotwMovementReaction::PerfectDodge) && !bArmed;
    ApplyMovementReaction(Reaction);
    if (Draw && bArmed) ArmedFeedback(true); // Resolve only; replayed Apply never publishes a second cue.
}

void UBotwMoveSet::ApplyMovementReaction(const FBotwMovementReaction& Reaction)
{
    if (!Character || !ensure(Reaction.IsValid())) return;
    using R = FBotwMovementReaction;
    const uint16 Flags = Reaction.Flags;
    TGuardValue<bool> ExternalChange(bExternalDefenceChange, true);
    auto* Movement = Character->GetCharacterMovement();
    if (Flags & R::ClearHop) bHopInvulnerability = false;
    if (Flags & R::Immunity) Invulnerable = FMath::Max(Invulnerable, Reaction.Invulnerable);
    if (Flags & R::ClearCharge) { bCharging = false; AttackBuffer = 0.f; }
    if (Flags & R::ClearLunge) LungeTime = 0.f;
    if (Flags & R::ResetCombo) Combo = 0;
    if (Flags & R::LeaveGlide) CloseGlider(false);
    if (Flags & R::LeaveClimb)
    {
        // The direction/parameter are frozen at resolution, not recomputed
        // from whatever wall the owner happens to face when delivery arrives.
        const float PreviousNoClimb = NoClimb;
        LeaveClimb(true);
        Movement->Velocity = Reaction.ClimbRelease;
        NoClimb = FMath::Max(PreviousNoClimb, Reaction.NoClimb);
    }
    if (Flags & R::Down) { bDown = true; DownTime = 0.f; }
    if (Flags & R::BreakGuard) GuardBroken = Reaction.GuardBroken;
    if (Flags & R::PerfectDodge)
    {
        FlurryTime = Reaction.FlurryTime;
        FlurryPoint = Reaction.FlurryPoint; bFlurryPoint = (Flags & R::HasFlurryPoint) != 0;
        Invulnerable = Reaction.Invulnerable;
        if (!bArmed) SetArmed(true, false);
    }
    // None explicitly means no Play: an unavailable authored clip must not
    // stop the owner's current action merely because this reaction arrived.
    if (!Reaction.Action.IsNone())
        if (const auto* Move = Find(Reaction.Action))
            Play(Reaction.Action, Reaction.Blend, Reaction.SourceStart, Reaction.PlayRate / Move->Rate);
    if (Flags & R::Flinch)
    {
        FlinchAxis = Reaction.FlinchAxis; FlinchAngle = Reaction.FlinchAngle;
        FlinchPeak = Reaction.FlinchPeak; FlinchTwist = Reaction.FlinchTwist; FlinchTime = 0.f;
    }
    if (Flags & R::SetVelocity) Movement->Velocity = Reaction.Impulse;
    if (Flags & R::Launch) Character->LaunchCharacter(Reaction.Impulse, true, true);
}
