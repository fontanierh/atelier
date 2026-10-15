#pragma once
#include "CoreMinimal.h"
#include "JapanHorseState.generated.h"

/** The horse ride's simulation at a CMC timestamp (UHorseComponent::AdvanceSimulation), also carried by an activity
 * handoff. Presentation (ground pitch, bank, torso spring, the horse's clip blend, hoofsteps) never feeds it.
 * Phase follows UHorseComponent::EPhase and Role/ForcedIdle index the fixed EHorseRole order, never a process-local name. */
USTRUCT()
struct FJapanHorseState
{
    GENERATED_BODY()
    static constexpr int32 CheckpointBytes = 36;
    /** EHorseRole::Count; the first IdleRoles roles are Idle and its variants, then the gaits, Mount and Dismount. */
    static constexpr uint8 RoleCount = 13;
    static constexpr uint8 IdleRoles = 6;
    static constexpr uint8 SprintRole = 10;
    static constexpr uint8 MountRole = 11;
    static constexpr uint8 DismountRole = 12;
    /** 0 Stowed, 1 Mounting, 2 Riding, 3 Dismounting. */
    UPROPERTY() uint8 Phase = 0;
    UPROPERTY() uint8 Role = 0;
    /** An idle variant playing out, or 0 (Idle) for none. */
    UPROPERTY() uint8 ForcedIdle = 0;
    UPROPERTY() uint32 Serial = 0;
    UPROPERTY() float Yaw = 0.f;
    UPROPERTY() float Speed = 0.f;
    UPROPERTY() float Steering = 0.f;
    UPROPERTY() float PhaseTime = 0.f;
    UPROPERTY() float GaitPhase = 0.f;
    /** Seconds left of the idle variant (at most its clip's length) and until the next one. */
    UPROPERTY() float IdleTimer = 0.f;
    UPROPERTY() float IdleCooldown = 0.f;
    UPROPERTY() bool Sprint = false;
    /** The dismount has ended: the host stows the horse and starts the on-foot epoch. Only while dismounting. */
    UPROPERTY() bool Terminal = false;
    UPROPERTY() bool ReinIn = false;
    bool IsValid() const;
    /** Fixed vocabulary and LE 32-bit scalars; out-of-range bytes are rejected before any lookup. */
    bool SerializeCheckpoint(FArchive& Ar);
    /** The rider clip's name for a role (the movement checkpoint's action); NAME_None out of range. */
    static FName RoleName(uint8 Index);
};
