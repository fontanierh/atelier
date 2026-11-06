#pragma once
#include "CoreMinimal.h"
#include "BelmonteTrainRules.h"

class UWorld;
class AActor;
class UPrimitiveComponent;

/**
 * The world half of the train's safe recovery (BelmonteTrainRules::AcceptStand decides): where someone put off the
 * train may stand. Tested on real collision in BelmonteTrainServiceTests.cpp.
 */
namespace BelmonteTrainRecovery
{
/** The standing capsule and the floor it may stand on. */
struct FStander
{
    float Radius = 34.f, HalfHeight = 88.f;
    /** CharacterMovementComponent::GetWalkableFloorZ. */
    double WalkableZ = .71;
    /** Not part of the world here (the player themself). */
    const AActor* Ignore = nullptr;
};

/**
 * Probes a candidate: the first surface down from MaxOff above Near (a world z) at Point's x and y, the standing capsule
 * a step above it (overlapping nothing: the world, the train, other people) and that capsule swept down onto its floor.
 * IsTrain marks the train's own parts. Feet: where the feet would stand (the floor), valid when accepted.
 */
YORIMICHI_API BelmonteTrainRules::FStandProbe Probe(const UWorld* World, const FVector& Point, double Near, double MaxOff,
    const FStander& Stander, TFunctionRef<bool(const UPrimitiveComponent*)> IsTrain, FVector& Feet);

/** Probe, then AcceptStand. */
YORIMICHI_API bool SafeStand(const UWorld* World, const FVector& Point, double Near, double MaxOff, const FStander& Stander,
    TFunctionRef<bool(const UPrimitiveComponent*)> IsTrain, FVector& Feet);
}
