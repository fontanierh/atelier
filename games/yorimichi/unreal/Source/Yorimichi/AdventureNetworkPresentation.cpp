#include "AdventureMoveSet.h"
#include "JapanAvatarState.h"
#include "WandererCharacter.h"
#include "JapanCharacterMovement.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/GameStateBase.h"
#include "Engine/World.h"

FJapanAvatarState UAdventureMoveSet::CapturePresentation() const
{
    FJapanAvatarState State;
    if (!Character) return State;
    State.ServerTime = Character->GetWorld()->GetTimeSeconds();
    State.Action = Character->AnimationAction; State.ActionSerial = Character->ActionSerial;
    State.ActionTime = Character->ActionTime; State.SourceStart = Character->ActionSourceStartTime;
    State.PlayRate = Character->ActionPlayRate; State.Duration = Character->ActionDuration; State.Blend = Character->ActionBlendTime;
    State.Mode = uint8(Mode);
    State.Flags = (Character->bActionLoops ? FJapanAvatarState::Loop : 0) | (bArmed ? FJapanAvatarState::Armed : 0) |
        (bGuardHeld ? FJapanAvatarState::Guard : 0) | (bDown ? FJapanAvatarState::Down : 0) |
        (bGliderShown ? FJapanAvatarState::Glider : 0) | (bLocked ? FJapanAvatarState::Locked : 0);
    State.MeshLocation = Character->GetMesh()->GetRelativeLocation();
    State.MeshRotation = Character->GetMesh()->GetRelativeRotation();
    State.Intent = FVector(Character->MoveIntent.X, Character->MoveIntent.Y, 0);
    State.FlinchTime = FlinchTime; State.FlinchAngle = FlinchAngle; State.FlinchPeak = FlinchPeak;
    State.FlinchTwist = FlinchTwist; State.FlinchAxis = FlinchAxis;
    State.GuardBroken = GuardBroken; State.GlideTurn = GlideTurn; State.SwimYaw = SwimYaw;
    return State;
}

void UAdventureMoveSet::ApplyPresentation(const FJapanAvatarState& State, float Dt)
{
    if (!Character || State.Mode > uint8(EAdventureMoveMode::Swim)) return;
    const AGameStateBase* GameState = Character->GetWorld()->GetGameState();
    const float Now = GameState ? GameState->GetServerWorldTimeSeconds() : State.ServerTime;
    // Bound extrapolation during a stalled connection. Ordinary CMC smoothing handles the replicated capsule.
    const float Age = FMath::Clamp(Now - State.ServerTime, 0.f, .2f);
    Character->AnimationAction = State.Action; Character->ActionSerial = State.ActionSerial;
    Character->ActionTime = State.ActionTime + Age;
    Character->ActionSourceStartTime = State.SourceStart; Character->ActionPlayRate = State.PlayRate;
    Character->ActionDuration = State.Duration; Character->ActionBlendTime = State.Blend;
    Character->bActionLoops = (State.Flags & FJapanAvatarState::Loop) != 0;
    Character->MoveIntent = FVector2D(State.Intent.X, State.Intent.Y);
    const FVector MeshLocation = FMath::VInterpTo(Character->GetBaseTranslationOffset(), FVector(State.MeshLocation), Dt, 20.f);
    const FQuat MeshRotation = FQuat::Slerp(Character->GetBaseRotationOffset(), State.MeshRotation.Quaternion(),
        FMath::Clamp(Dt * 20.f, 0.f, 1.f)).GetNormalized();
    const FVector SmoothingLocation = Character->GetMesh()->GetRelativeLocation() - Character->GetBaseTranslationOffset();
    const FQuat SmoothingRotation = Character->GetMesh()->GetRelativeRotation().Quaternion() * Character->GetBaseRotationOffset().Inverse();
    Character->CacheInitialMeshOffset(MeshLocation, MeshRotation.Rotator());
    Character->GetMesh()->SetRelativeLocationAndRotation(MeshLocation + SmoothingLocation,
        (SmoothingRotation * MeshRotation).GetNormalized());
    Mode = EAdventureMoveMode(State.Mode);
    bArmed = (State.Flags & FJapanAvatarState::Armed) != 0;
    bGuardHeld = (State.Flags & FJapanAvatarState::Guard) != 0;
    bDown = (State.Flags & FJapanAvatarState::Down) != 0;
    bLocked = (State.Flags & FJapanAvatarState::Locked) != 0;
    for (auto& Pair : Slots)
    {
        const bool Hand = bArmed && !Pair.Value.Hand.IsNone();
        if (Pair.Value.bInHand != Hand) { Pair.Value.bInHand = Hand; Attach(Pair.Key); }
    }
    ShowGlider((State.Flags & FJapanAvatarState::Glider) != 0);
    FlinchTime = State.FlinchTime < 0.f ? -1.f : State.FlinchTime + Age;
    FlinchAngle = State.FlinchAngle; FlinchPeak = State.FlinchPeak; FlinchTwist = State.FlinchTwist;
    FlinchAxis = State.FlinchAxis; GuardBroken = FMath::Max(0.f, State.GuardBroken - Age);
    GlideTurn = State.GlideTurn; SwimYaw = State.SwimYaw;
    // Only derive visual carry/grip layers. Never call Advance, Phys, sweeps, stamina or action transitions here.
    AdvanceEquipment(Dt);
    AdvanceGliderGrip(Dt);
}
