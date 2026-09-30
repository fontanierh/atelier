#include "JapanCharacterMovement.h"
#include "WandererCharacter.h"
#include "SailboatComponent.h"
#include "SkateComponent.h"

float UJapanCharacterMovement::GetMaxSpeed() const
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) return 1400.f;
    return Super::GetMaxSpeed();
}

void UJapanCharacterMovement::CalcVelocity(float Dt, float Friction, bool bFluid, float BrakingDeceleration)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) { Velocity = FVector::ZeroVector; return; }
    Super::CalcVelocity(Dt, Friction, bFluid, BrakingDeceleration);
}

void UJapanCharacterMovement::PhysicsRotation(float Dt)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) return;
    if (Rider && Rider->GetSkate() && Rider->GetSkate()->IsRiding()) return;   // the board frame is the actor's rotation
    Super::PhysicsRotation(Dt);
}

void UJapanCharacterMovement::PhysCustom(float Dt, int32 Iterations)
{
    if (CustomMovementMode == USkateComponent::MovementMode)
    {
        if (auto* Rider = Cast<AWandererCharacter>(CharacterOwner); Rider && Rider->GetSkate()) Rider->GetSkate()->PhysSkate(Dt);
        return;
    }
    Super::PhysCustom(Dt, Iterations);
}
