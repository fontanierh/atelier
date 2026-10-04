#pragma once
#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "JapanCharacterMovement.generated.h"

/** The player's movement: ordinary CharacterMovement, the sailboat holding its own velocity, the skate plugin's custom
 *  movement mode (USkateComponent::MovementMode) handed to the board, and a BOTW move set's (UBotwMoveSet::MovementMode:
 *  gliding, climbing, swimming), which also sets the velocity of its hops and driven attacks, turns the character and
 *  hears what the capsule runs into. */
UCLASS()
class YORIMICHI_API UJapanCharacterMovement : public UCharacterMovementComponent
{
    GENERATED_BODY()
public:
    virtual void CalcVelocity(float Dt, float Friction, bool bFluid, float BrakingDeceleration) override;
    virtual void PhysicsRotation(float Dt) override;
    virtual float GetMaxSpeed() const override;
    virtual void PhysCustom(float Dt, int32 Iterations) override;
    virtual void HandleImpact(const FHitResult& Hit, float TimeSlice = 0.f, const FVector& MoveDelta = FVector::ZeroVector) override;
};
