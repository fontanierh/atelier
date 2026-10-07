#include "JapanCharacterMovement.h"
#include "WandererCharacter.h"
#include "SailboatComponent.h"
#include "BikeComponent.h"
#include "JapanNetwork.h"
#include "SkateComponent.h"
#include "BotwMoveSet.h"

float UJapanCharacterMovement::GetMaxSpeed() const
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) return 1400.f;
    if (Rider && JapanNetwork::IsOnline(GetWorld()) && Rider->GetNetworkActivity() == EJapanActivity::Bike) return 1200.f;
    return Super::GetMaxSpeed();
}

void UJapanCharacterMovement::CalcVelocity(float Dt, float Friction, bool bFluid, float BrakingDeceleration)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) { Velocity = FVector::ZeroVector; return; }
    Super::CalcVelocity(Dt, Friction, bFluid, BrakingDeceleration);
    // A move set's hop, driven attack or plunge sets the velocity across the ground (falling keeps its own vertical).
    if (Rider && Rider->GetMoves() && (!JapanNetwork::IsOnline(GetWorld()) || Rider->GetNetworkActivity() == EJapanActivity::OnFoot)) Rider->GetMoves()->OverrideVelocity(Velocity);
}

void UJapanCharacterMovement::PhysicsRotation(float Dt)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && JapanNetwork::IsOnline(GetWorld()) && Rider->GetNetworkActivity() == EJapanActivity::Bike) return;
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) return;
    if (Rider && Rider->GetSkate() && Rider->GetSkate()->IsRiding()) return;   // the board frame is the actor's rotation
    if (Rider && Rider->GetMoves() && Rider->GetMoves()->ControlsRotation()) return;   // lock-on, gliding, climbing, attacks
    Super::PhysicsRotation(Dt);
}

void UJapanCharacterMovement::PhysCustom(float Dt, int32 Iterations)
{
    if (CustomMovementMode == USkateComponent::MovementMode)
    {
        if (auto* Rider = Cast<AWandererCharacter>(CharacterOwner); Rider && Rider->GetSkate()) Rider->GetSkate()->PhysSkate(Dt);
        return;
    }
    if (UBotwMoveSet::IsTraversalMode(CustomMovementMode))
    {
        if (auto* Rider = Cast<AWandererCharacter>(CharacterOwner); Rider && Rider->GetMoves()) Rider->GetMoves()->Phys(Dt, Iterations);
        else SetMovementMode(MOVE_Falling);
        return;
    }
    Super::PhysCustom(Dt, Iterations);
}

void UJapanCharacterMovement::HandleImpact(const FHitResult& Hit, float TimeSlice, const FVector& MoveDelta)
{
    Super::HandleImpact(Hit, TimeSlice, MoveDelta);
    if (auto* Rider = Cast<AWandererCharacter>(CharacterOwner); Rider && Rider->GetMoves()) Rider->GetMoves()->Impact(Hit);
}
