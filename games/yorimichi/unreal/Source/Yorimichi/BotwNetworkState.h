#pragma once
#include "BotwMoveSet.h"
#include "JapanMovementNet.h"
#include "SprintStamina.h"

/** A value checkpoint: deserialization finishes and validates before any live pawn state is changed. */
struct FBotwNetworkState
{
#define BOTW_FIELD(Type, Name) Type Name{};
#include "BotwNetworkFields.inl"
#undef BOTW_FIELD
    uint32 ActionSerial = 0;
    float ActionBlendTime = 0.f, ActionTime = 0.f, ActionDuration = 0.f;
    float ActionSourceStartTime = 0.f, ActionPlayRate = 1.f;
    bool bActionLoops = false, bWantsToCrouch = false;
    FSprintStamina Stamina;
    bool bImpactClimbable = false;
    FVector ImpactPoint = FVector::ZeroVector, ImpactNormal = FVector::ZeroVector;
    FVector PendingLaunch = FVector::ZeroVector;
    void Capture(const UBotwMoveSet& Moves);
    void Apply(UBotwMoveSet& Moves, const FJapanMoveCheckpoint& Checkpoint) const;
    bool Serialize(FArchive& Ar);
};
