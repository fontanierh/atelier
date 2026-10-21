#include "TransportRiders.h"
#include "WandererCharacter.h"
#include "JapanNetwork.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/SpringArmComponent.h"

void FTransportRiders::OrderTick(AActor& Service, FTransportRider& Rider)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || Rider.bTickOrdered) return;
    // The vehicles move first; the rider's movement then follows its base without a frame of lag.
    C->PrimaryActorTick.AddPrerequisite(&Service, Service.PrimaryActorTick);
    C->GetCharacterMovement()->PrimaryComponentTick.AddPrerequisite(&Service, Service.PrimaryActorTick);
    Rider.bTickOrdered = true;
}

bool FTransportRiders::SetAboard(FTransportRider& Rider, bool bAboard, bool bVehiclesOnly, ETransportVehicle Kind)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || Rider.bAboard == bAboard) return false;
    if (bAboard && C->bTrainAboard && C->AboardVehicle != Kind) return false;
    Rider.bAboard = bAboard;
    C->bTrainAboard = bAboard;
    UCapsuleComponent* Capsule = C->GetCapsuleComponent();
    if (bAboard)
    {
        C->AboardVehicle = Kind;
        if (bVehiclesOnly)
        {
            Rider.Responses = Capsule->GetCollisionResponseToChannels();
            Rider.bCollisionOverridden = true;
            for (const ECollisionChannel Channel : {ECC_WorldStatic, ECC_WorldDynamic, ECC_PhysicsBody, ECC_Destructible})
                Capsule->SetCollisionResponseToChannel(Channel, ECR_Ignore);
            Capsule->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Block);
        }
        Rider.bCameraLag = C->CameraArm->bEnableCameraLag;
        C->CameraArm->bEnableCameraLag = false;   // world-space lag would trail the moving vehicle
    }
    else
    {
        if (Rider.bCollisionOverridden) Capsule->SetCollisionResponseToChannels(Rider.Responses);
        Rider.bCollisionOverridden = false;
        C->AboardVehicle = ETransportVehicle::None;
        C->CameraArm->bEnableCameraLag = Rider.bCameraLag;
        C->bNoSprint = false;
        C->bTrainAboard = false;
    }
    return true;
}

void FTransportRiders::Carry(FTransportRider& Rider, const AActor& Service, UPrimitiveComponent* Body, const FTransform& Previous, bool bMoved)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || !Body) return;
    // Standing on its floor the character movement follows the vehicle as its base; when it does not (a moment off the
    // floor), offline the vehicle's move this frame is applied to the rider here, before the character's own movement.
    const UPrimitiveComponent* Base = C->GetMovementBase();
    if (Base && Base->GetOwner() == &Service) return;
    if (!JapanNetwork::IsOnline(Service.GetWorld()) && bMoved)
    {
        const FTransform Now = Body->GetComponentTransform();
        const FVector At = Now.TransformPosition(Previous.InverseTransformPosition(C->GetActorLocation()));
        const double Turn = FRotator::NormalizeAxis(Now.Rotator().Yaw - Previous.Rotator().Yaw);
        C->SetActorLocationAndRotation(At, C->GetActorRotation() + FRotator(0., Turn, 0.), false, nullptr, ETeleportType::TeleportPhysics);
        if (C->IsLocallyControlled() && C->Controller && !FMath::IsNearlyZero(Turn))
            C->Controller->SetControlRotation(C->Controller->GetControlRotation() + FRotator(0., Turn, 0.));
    }
    if (C->GetCharacterMovement()->IsMovingOnGround()) C->SetBase(Body);
}
