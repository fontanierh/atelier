#include "TrainPassengerView.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Controller.h"

bool FTrainPassengerView::Toggle(bool bPassenger, bool& bPreference)
{
    if (!bPassenger) return false;
    if (!bWasPassenger) bFirstPerson = bPreference;
    bFirstPerson = !bFirstPerson;
    bPreference = bFirstPerson;
    bWasPassenger = true;
    return true;
}

void FTrainPassengerView::Update(bool bPassenger, bool bPreference, float DeltaSeconds, float Rate)
{
    if (!bPassenger) bFirstPerson = false;
    else if (!bWasPassenger) bFirstPerson = bPreference;
    bWasPassenger = bPassenger;
    Blend = FMath::FInterpConstantTo(Blend, bFirstPerson ? 1.f : 0.f, DeltaSeconds, Rate);
    if (Blend <= 0.f) Eye = FVector::ZeroVector;
}

void FTrainPassengerView::Apply(const AWandererCharacter& Rider, float DeltaSeconds, FMinimalViewInfo& View)
{
    if (Blend <= 0.f) return;
    const FTransform Actor = Rider.GetActorTransform();
    FVector Head = Actor.GetLocation() + FVector(0, 0, Rider.GetCapsuleComponent()->GetScaledCapsuleHalfHeight() * .82f);
    const FName Bone = Rider.GetSkateBone(TEXT("head"));
    if (Rider.GetMesh() && Rider.GetMesh()->DoesSocketExist(Bone)) Head = Rider.GetMesh()->GetSocketLocation(Bone) + FVector(0, 0, 8.f);
    const FVector Local = Actor.InverseTransformPositionNoScale(Head);
    Eye = Eye.IsZero() ? Local : FMath::VInterpTo(Eye, Local, DeltaSeconds, 12.f);
    FRotator Look = Rider.GetController() ? Rider.GetController()->GetControlRotation() : View.Rotation;
    if (Rider.IsGondolaSeated())
    {
        const float BaseYaw = float(Actor.Rotator().Yaw);
        const float RelYaw = FMath::Clamp(float(FRotator::NormalizeAxis(Look.Yaw - BaseYaw)), -100.f, 100.f);
        const float ClampedPitch = FMath::Clamp(float(FRotator::NormalizeAxis(Look.Pitch)), -60.f, 60.f);
        Look = FRotator(ClampedPitch, FRotator::NormalizeAxis(BaseYaw + RelYaw), 0.f);
        if (Rider.GetController()) Rider.GetController()->SetControlRotation(Look);
    }
    const FVector Where = Actor.TransformPositionNoScale(Eye) + FRotator(0, Look.Yaw, 0).Vector() * 10.f;
    const float Weight = FMath::SmoothStep(0.f, 1.f, Blend);
    View.Location = FMath::Lerp(View.Location, Where, Weight);
    View.Rotation = FQuat::Slerp(View.Rotation.Quaternion(), Look.Quaternion(), Weight).Rotator();
}

void FTrainPassengerView::AddHiddenBodyComponents(const AWandererCharacter& Rider, TSet<FPrimitiveComponentId>& Hidden)
{
    TArray<AActor*> Actors;
    Rider.GetAttachedActors(Actors, true, true);
    auto Add = [&](const AActor* Actor)
    {
        TInlineComponentArray<UPrimitiveComponent*> Parts(Actor, true);
        for (const UPrimitiveComponent* Part : Parts)
            if (Part != Rider.GetCapsuleComponent() && Part->GetPrimitiveSceneId().IsValid()) Hidden.Add(Part->GetPrimitiveSceneId());
    };
    Add(&Rider);
    for (const AActor* Actor : Actors) Add(Actor);
}
