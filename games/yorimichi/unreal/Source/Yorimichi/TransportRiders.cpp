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

FTransportRider& FTransportRiders::Find(TArray<FTransportRider>& Riders, AWandererCharacter* Character)
{
    for (FTransportRider& R : Riders) if (R.Character.Get() == Character) return R;
    FTransportRider& R = Riders.AddDefaulted_GetRef(); R.Character = Character; return R;
}

void FTransportRiders::ApplyRemote(AActor& Service, TArray<FTransportRider>& Riders,
    const TArray<FTransportMembership>& Membership, int32 VehicleCount, ETransportVehicle Kind)
{
    for (const FTransportMembership& P : Membership)
        if (P.Character && !P.Character->IsLocallyControlled()) Find(Riders, P.Character);
    for (FTransportRider& R : Riders)
        if (AWandererCharacter* C = R.Character.Get(); C && !C->IsLocallyControlled())
        {
            const FTransportMembership* P = Membership.FindByPredicate(
                [C](const FTransportMembership& Item) { return Item.Character == C; });
            R.Vehicle = P && P->Vehicle >= 0 && P->Vehicle < VehicleCount ? P->Vehicle : INDEX_NONE;
            OrderTick(Service, R);
            SetAboard(R, R.Vehicle != INDEX_NONE, false, Kind);
        }
}
