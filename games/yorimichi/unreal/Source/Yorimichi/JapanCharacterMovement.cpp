#include "JapanCharacterMovement.h"
#include "WandererCharacter.h"
#include "SkateboardComponent.h"
#include "SailboatComponent.h"
#include "SkateComponent.h"

float UJapanCharacterMovement::GetMaxSpeed() const
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) return 1400.f;
    return Rider && Rider->GetSkateboard() && Rider->GetSkateboard()->IsEquipped() ? USkateboardComponent::MaxSpeed : Super::GetMaxSpeed();
}

void UJapanCharacterMovement::CalcVelocity(float Dt,float Friction,bool bFluid,float BrakingDeceleration)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()) { Velocity = FVector::ZeroVector; return; }
    const auto* Skate = Rider ? Rider->GetSkateboard() : nullptr;
    if (!Skate || !Skate->IsEquipped() || !IsMovingOnGround())
    { Super::CalcVelocity(Dt,Friction,bFluid,BrakingDeceleration); return; }
    if (!Skate->CanRoll()) { Velocity.X = Velocity.Y = 0.f; return; }
    float Speed = Velocity.Size2D();
    const bool bBrake = Skate->IsStopping();
    // Steering uses board heading, independently of the free-look camera.
    const float TurnRate = 145.f/(1.f+Speed/700.f);
    const float ContactSteer = Skate->IsPushingGround() ? .25f : 1.f;
    const float Turn = Skate->GetSteering()*TurnRate*ContactSteer*FMath::Clamp(Speed/60.f,0.f,1.f)*Dt;
    const float Yaw = Rider->GetActorRotation().Yaw+Turn;
    const FVector Forward = FRotator(0,Yaw,0).Vector();
    const FVector GravityAlongFloor = FVector::VectorPlaneProject(FVector(0,0,GetGravityZ()),CurrentFloor.HitResult.ImpactNormal);
    const float Slope = FVector::DotProduct(GravityAlongFloor,Forward)*.35f;
    const float Push = Skate->IsPushingGround() && Skate->GetContactWeight() > 0.f && !bBrake ? 2200.f : 0.f;
    // Low rolling resistance preserves the speed earned on each stroke.
    // The contact-distance-driven push animation naturally adds less speed
    // per stroke as the board gets faster; braking remains deliberate and firm.
    const float Drag = bBrake ? 280.f+Speed*.65f : 6.f+Speed*.008f;
    Speed = FMath::Clamp(Speed+(Push+Slope-Drag)*Dt,0.f,USkateboardComponent::MaxSpeed);
    Velocity = Forward*Speed;
    MoveUpdatedComponent(FVector::ZeroVector,FRotator(0,Yaw,0),false);
}

void UJapanCharacterMovement::PhysicsRotation(float Dt)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && ((Rider->GetSkateboard() && Rider->GetSkateboard()->IsEquipped()) || (Rider->GetSailboat() && Rider->GetSailboat()->IsEquipped()))) return;
    if (Rider && Rider->GetSkate() && Rider->GetSkate()->IsOnBoard()) return;   // the board frame is the actor's rotation
    Super::PhysicsRotation(Dt);
}
