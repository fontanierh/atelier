#include "JapanCameraArm.h"
#include "JapanWorld.h"
#include "SeeThrough.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"

namespace
{
    // Moves Current toward Target, critically damped, arriving in about three times SmoothTime without overshooting
    // (Game Programming Gems 4, 1.10). Velocity carries from frame to frame.
    float SmoothDamp(float Current, float Target, float& Velocity, float SmoothTime, float DeltaTime)
    {
        if (DeltaTime <= 0.f) return Current;
        const float Omega = 2.f / FMath::Max(SmoothTime, .0001f);
        const float X = Omega * DeltaTime;
        const float Exp = 1.f / (1.f + X + .48f * X * X + .235f * X * X * X);
        const float Change = Current - Target;
        const float Temp = (Velocity + Omega * Change) * DeltaTime;
        Velocity = (Velocity - Omega * Temp) * Exp;
        float Out = Target + (Change + Temp) * Exp;
        if ((Target > Current) == (Out > Target)) { Out = Target; Velocity = 0.f; }
        return Out;
    }
    // A gap of more frames than this in the arm's updates (a camera cut, the zeppelin's free camera) starts it afresh.
    constexpr uint64 GapFrames = 2;
    // The camera itself stays at least this far off anything solid (cm); the probe keeps it ProbeRadius off at rest.
    constexpr float ArmBodyClearance = 14.f;
    // The thin sweep used when Cairo's head is already within ProbeRadius of something (cm).
    constexpr float ThinRadius = 4.f;
    // How fast the squeezed camera rises over him and settles back (1/s).
    constexpr float LiftSpeed = 5.f;
}

UJapanCameraArm::UJapanCameraArm(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
}

bool UJapanCameraArm::PassesHouse() const
{
    const AJapanWorld* World = House.Get();
    return World && World->IsSeeThroughProbeIgnored() && World->SeeThroughGroups.Num() > 0;
}

float UJapanCameraArm::Free(const FVector& From, const FVector& Dir, float Dist, float Radius, const FCollisionQueryParams& Params) const
{
    FHitResult Hit;
    if (!GetWorld()->SweepSingleByChannel(Hit, From, From + Dir * Dist, FQuat::Identity, ProbeChannel, FCollisionShape::MakeSphere(Radius), Params))
        return Dist;
    return Hit.bStartPenetrating ? -1.f : Hit.Time * Dist;
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
        if (Base && Base->ComponentHasTag(JapanSeeThrough::Tag))
        {
            FloorZ = Feet; Target = 1.f;
        }
        else
        {
            FloorZ = FMath::Min(FloorZ, Feet);
            const UCharacterMovementComponent* Move = Owner->GetCharacterMovement();
            if (FloorWeight > 0.f && Move && Move->IsFalling()) Target = 1.f;
        }
    }
    FloorWeight = FMath::FInterpConstantTo(FloorWeight, Target, DeltaTime, 2.5f);
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
}

void UJapanCameraArm::UpdateDesiredArmLocation(bool bDoTrace, bool bDoLocationLag, bool bDoRotationLag, float DeltaTime)
{
    // The engine places the camera where it wants to be (lag, rotation, socket offset) without its own probe; this
    // arm then keeps it in front of what is solid.
    Super::UpdateDesiredArmLocation(false, bDoLocationLag, bDoRotationLag, DeltaTime);
    UWorld* World = GetWorld();
    const FTransform Desired = FTransform(RelativeSocketRotation, RelativeSocketLocation) * GetComponentTransform();
    const FVector Origin = PreviousArmOrigin;
    const FVector Want = Desired.GetLocation();
    const float Full = float(FVector::Dist(Want, Origin));
    if (!bDoTrace || TargetArmLength == 0.f || !World || Full < 1.f)
    {
        Length = -1.f; Speed = 0.f; Lift = 0.f;
        return;
    }
    const FVector Dir = (Want - Origin) / Full;

    FCollisionQueryParams Params(SCENE_QUERY_STAT(JapanCameraArm), false, GetOwner());
    if (PassesHouse())
        for (const UHierarchicalInstancedStaticMeshComponent* Group : House->SeeThroughGroups) Params.AddIgnoredComponent(Group);

    // The hard limit: how far out the camera can be before something solid. Thin things ignore the camera channel,
    // so only the terrain, walls, roofs, decks, rocks and houses count.
    float Hard = Free(Origin, Dir, Full, ProbeRadius, Params);
    if (Hard < 0.f)
    {
        // Something is already within ProbeRadius of his head (a low beam): sweep thin and keep as far off it.
        const float Thin = Free(Origin, Dir, Full, ThinRadius, Params);
        if (Thin >= Full) Hard = Full;
        else if (Thin >= 0.f) Hard = FMath::Max(0.f, Thin - (ProbeRadius - ThinRadius));
        else Hard = FMath::Max(Length, 0.f);
    }
    if (FloorWeight > 0.f && Dir.Z < -.01f)
    {
        // Looking up from below on the tree house: stop FloorClearance above the floor he stands on, never under it.
        const float Room = FMath::Max(0.f, float(Origin.Z) - (FloorZ + FloorClearance));
        Hard = FMath::Lerp(Hard, FMath::Min(Hard, Room / float(-Dir.Z)), FloorWeight);
    }

    // Pull in fast, ease out gently. Never further than the hard limit, give or take the few cm the probe keeps spare.
    const uint64 Frame = GFrameCounter;
    if (Length < 0.f || Frame > LastFrame + GapFrames) { Length = Hard; Speed = 0.f; }
    else Length = SmoothDamp(Length, Hard, Speed, Hard < Length ? PullInTime : EaseOutTime, DeltaTime);
    LastFrame = Frame;
    const float Limit = Hard + FMath::Max(ProbeRadius - ArmBodyClearance, 0.f);
    if (Length > Limit) { Length = Limit; Speed = FMath::Min(Speed, 0.f); }
    Length = FMath::Clamp(Length, 0.f, Full);

    // Squeezed (pulled in short, the camera level with him or above): rise over him and look down at him rather than
    // going into his head. Not when looking up from below, where rising would bring the camera into him.
    const float Pulled = FMath::Clamp((Full - Length) / 50.f, 0.f, 1.f);
    const float Squeeze = (1.f - FMath::SmoothStep(.4f * SqueezeLength, SqueezeLength, Length)) * Pulled;
    Lift = FMath::FInterpTo(Lift, Dir.Z > -.4f ? Squeeze * LiftHeight : 0.f, DeltaTime, LiftSpeed);
    FVector Camera = Origin + Dir * Length;
    if (Lift > .5f)
    {
        // Only as high as the ceiling allows.
        const float Up = Free(Camera, FVector::UpVector, Lift, .6f * ProbeRadius, Params);
        Lift = FMath::Min(Lift, FMath::Max(Up, 0.f));
    }
    FQuat Rotation = Desired.GetRotation();
    if (Lift > .5f)
    {
        const FVector Look = Camera + Rotation.GetForwardVector() * FMath::Max(Length, 100.f);
        Camera.Z += Lift;
        FRotator Aim = (Look - Camera).Rotation();
        Aim.Roll = Desired.Rotator().Roll;
        Rotation = Aim.Quaternion();
    }
    else if (Length >= Full - .01f) Camera = Want;

    UnfixedCameraPosition = Want;
    bIsCameraFixed = Length < Full - .5f || Lift > .5f;
    const FTransform Relative = FTransform(Rotation, Camera).GetRelativeTransform(GetComponentTransform());
    RelativeSocketLocation = Relative.GetLocation();
    RelativeSocketRotation = Relative.GetRotation();
    UpdateChildTransforms();
}
