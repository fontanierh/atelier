#include "JapanCameraArm.h"
#include "JapanWorld.h"
#include "SeeThrough.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"

UJapanCameraArm::UJapanCameraArm(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
}

bool UJapanCameraArm::PassesHouse() const
{
    const AJapanWorld* World = House.Get();
    return World && World->IsSeeThroughProbeIgnored() && World->SeeThroughGroups.Num() > 0;
}

void UJapanCameraArm::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    // The floor under Cairo while he is on the tree house (and through a jump or fall from it), faded in and out
    // over 0.4 s so stepping on or off the house does not jolt the camera.
    float Target = 0.f;
    if (const ACharacter* Owner = Cast<ACharacter>(GetOwner()))
    {
        const float Feet = Owner->GetActorLocation().Z - (Owner->GetCapsuleComponent() ? Owner->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 0.f);
        const UPrimitiveComponent* Base = Owner->GetMovementBase();
        if (PassesHouse() && Base && Base->ComponentHasTag(JapanSeeThrough::Tag))
        {
            FloorZ = Feet; Target = 1.f;
        }
        else
        {
            FloorZ = FMath::Min(FloorZ, Feet);
            const UCharacterMovementComponent* Move = Owner->GetCharacterMovement();
            if (FloorWeight > 0.f && PassesHouse() && Move && Move->IsFalling()) Target = 1.f;
        }
    }
    FloorWeight = FMath::FInterpConstantTo(FloorWeight, Target, DeltaTime, 2.5f);
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
}

FVector UJapanCameraArm::BlendLocations(const FVector& DesiredArmLocation, const FVector& TraceHitLocation, bool bHitSomething, float DeltaTime)
{
    // The sweep ran from the arm's origin (PreviousArmOrigin, set just before it) to the desired camera location.
    const FVector Origin = PreviousArmOrigin;
    const FVector Offset = DesiredArmLocation - Origin;
    const float Full = Offset.Size();
    if (Full < UE_KINDA_SMALL_NUMBER) return DesiredArmLocation;
    const FVector Dir = Offset / Full;
    FVector Hit = TraceHitLocation;
    if (bHitSomething && PassesHouse())
    {
        // Sweep again without the tree house: only the terrain and the rest of the world stop the camera there.
        FCollisionQueryParams Params(SCENE_QUERY_STAT(JapanCameraArm), false, GetOwner());
        for (const UHierarchicalInstancedStaticMeshComponent* Group : House->SeeThroughGroups) Params.AddIgnoredComponent(Group);
        FHitResult Result;
        GetWorld()->SweepSingleByChannel(Result, Origin, DesiredArmLocation, FQuat::Identity, ProbeChannel, FCollisionShape::MakeSphere(ProbeSize), Params);
        bHitSomething = Result.bBlockingHit; Hit = Result.Location;
    }
    float Allowed = bHitSomething ? FMath::Min(Full, float(FVector::Dist(Hit, Origin))) : Full;
    if (FloorWeight > 0.f && Dir.Z < -.01f)
    {
        // Looking up from below: stop the arm FloorClearance above the floor he stands on.
        const float Room = FMath::Max(0.f, float(Origin.Z) - (FloorZ + FloorClearance));
        Allowed = FMath::Lerp(Allowed, FMath::Min(Allowed, Room / float(-Dir.Z)), FloorWeight);
    }
    // In at once, out gently. A gap of frames (the arm did not sweep: a cut, the zeppelin's free camera) starts afresh.
    const uint64 Frame = GFrameCounter;
    if (Length < 0.f || Frame > LastBlendFrame + 2 || Allowed <= Length) Length = Allowed;
    else Length = FMath::FInterpTo(Length, Allowed, DeltaTime, RecoverSpeed);
    LastBlendFrame = Frame;
    return Length >= Full - .01f ? DesiredArmLocation : Origin + Dir * Length;
}
