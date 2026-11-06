#include "HairSpringComponent.h"
#include "WandererCharacter.h"
#include "Components/SkeletalMeshComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

UHairSpringComponent::UHairSpringComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    // Before physics, right after its character's own tick (AMoverCharacter makes the character a prerequisite).
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void UHairSpringComponent::TickComponent(float Dt, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(Dt, TickType, ThisTickFunction);
    const AWandererCharacter* Owner = Cast<AWandererCharacter>(GetOwner());
    USkeletalMeshComponent* Mesh = Owner ? Owner->GetMesh() : nullptr;
    if (Morphs.Num() != 2 || Dt <= SMALL_NUMBER || !Mesh || !Mesh->GetSkeletalMeshAsset()) return;
    const FVector Position = Mesh->GetSocketTransform(TEXT("head")).GetLocation();
    // Teleports and long suspended frames must not kick the spring.
    if (!bInitialized || Dt > .1f || FVector::DistSquared(Position, PreviousHead) > 2500.f)
    {
        bInitialized = true; PreviousHead = Position; PreviousVelocity = FVector::ZeroVector;
        Flex = FlexVelocity = FVector2D::ZeroVector;
    }
    const FVector Velocity = (Position - PreviousHead) / Dt;
    const FVector Acceleration = Owner->GetActorTransform().InverseTransformVectorNoScale((Velocity - PreviousVelocity) / Dt);
    PreviousHead = Position; PreviousVelocity = Velocity;
    const bool bContact = ContactActions.Contains(Owner->GetAnimationAction());
    ContactFade = FMath::FInterpConstantTo(ContactFade, bContact ? 0.f : 1.f, Dt, 8.f);
    // The character's +X forward / +Y lateral frame, independent of the FBX's bone axes: the tips follow the skinned head.
    FVector2D Target = bContact ? FVector2D::ZeroVector : FVector2D(-(Acceleration.X + .45 * Acceleration.Z) / 1800., -Acceleration.Y / 1800.);
    if (Target.SizeSquared() > 1.) Target.Normalize();
    const int32 Steps = FMath::Max(1, FMath::CeilToInt(Dt * 120.f));
    const float H = Dt / Steps, Omega = 18.f, Damping = .8f;
    for (int32 I = 0; I < Steps; ++I)
    {
        FlexVelocity += (Omega * Omega * (Target - Flex) - 2.f * Damping * Omega * FlexVelocity) * H;
        Flex += FlexVelocity * H;
        if (Flex.SizeSquared() > 1.) { Flex.Normalize(); FlexVelocity = FVector2D::ZeroVector; }
    }
    const float Enabled = (FParse::Param(FCommandLine::Get(), TEXT("statichair")) || FParse::Param(FCommandLine::Get(), TEXT("cairostatichair"))) ? 0.f : ContactFade;
    Mesh->SetMorphTarget(Morphs[0], Flex.X * Enabled);
    Mesh->SetMorphTarget(Morphs[1], Flex.Y * Enabled);
}
