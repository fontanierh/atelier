#include "SkiPhysicalBody.h"
#include "SkiSettings.h"
#include "Components/SkeletalMeshComponent.h"
#include "PhysicsControlComponent.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/BodyInstance.h"

namespace
{
const FName JointsSet(TEXT("SkiJoints")), AnchorsSet(TEXT("SkiAnchors")), RootSet(TEXT("SkiRoot")), LimbsSet(TEXT("SkiLimbs"));

FPhysicsControlData Drive(float Hz, bool bLinear)
{
    FPhysicsControlData Data;
    Data.bEnabled = true;
    Data.AngularStrength = Hz;
    Data.AngularDampingRatio = 1.f;
    Data.LinearStrength = bLinear ? Hz : 0.f;
    Data.LinearDampingRatio = 1.f;
    Data.bUseSkeletalAnimation = true;
    return Data;
}
}

bool USkiPhysicalBody::Begin(USkeletalMeshComponent* InMesh, FName Pelvis, const FName (&Feet)[2], const FName (&Hands)[2])
{
    End();
    if (!InMesh || !InMesh->GetPhysicsAsset() || InMesh->GetPhysicsAsset()->SkeletalBodySetups.Num() < 6) return false;
    Mesh = InMesh;
    const USkiSettings* S = GetDefault<USkiSettings>();

    // The highest body: the pelvis's own, or the first under the root.
    Root = Mesh->GetBodyInstance(Pelvis) ? Pelvis : NAME_None;
    if (Root.IsNone())
        for (const USkeletalBodySetup* Setup : Mesh->GetPhysicsAsset()->SkeletalBodySetups)
            if (Setup && (Root.IsNone() || Mesh->GetBoneIndex(Setup->BoneName) < Mesh->GetBoneIndex(Root))) Root = Setup->BoneName;
    if (Root.IsNone()) { Mesh = nullptr; return false; }

    SavedProfile = Mesh->GetCollisionProfileName();
    SavedUpdateMode = uint8(Mesh->PhysicsTransformUpdateMode.GetValue());
    Mesh->PhysicsTransformUpdateMode = EPhysicsTransformUpdateMode::ComponentTransformIsKinematic;
    Mesh->SetCollisionProfileName(TEXT("Ragdoll"));
    Mesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);

    Control = NewObject<UPhysicsControlComponent>(Mesh->GetOwner(), TEXT("SkiPhysicsControl"), RF_Transient);
    Control->RegisterComponent();
    Control->AddTickPrerequisiteComponent(Mesh);

    FPhysicsControlModifierData Kinematic;
    Kinematic.MovementType = EPhysicsMovementType::Kinematic;
    Kinematic.CollisionType = ECollisionEnabled::QueryOnly;
    Kinematic.GravityMultiplier = 0.f;
    Control->CreateBodyModifier(Mesh, Root, RootSet, Kinematic);
    FPhysicsControlModifierData Simulated = Kinematic;
    Simulated.MovementType = EPhysicsMovementType::Simulated;
    Control->CreateBodyModifiersFromSkeletalMeshBelow(Mesh, Root, false, LimbsSet, Simulated);

    Control->CreateControlsFromSkeletalMeshBelow(Mesh, Root, false, EPhysicsControlType::ParentSpace, Drive(S->JointStrength, false), JointsSet);
    // The feet and hands held from the pelvis: the skis carry the feet wherever the pelvis goes.
    for (int32 Side = 0; Side < 2; ++Side)
    {
        if (Mesh->GetBodyInstance(Feet[Side]))
            Control->CreateControl(Mesh, Root, Mesh, Feet[Side], Drive(S->FeetStrength, true), FPhysicsControlTarget(), AnchorsSet, TEXT("SkiFoot"));
        if (Mesh->GetBodyInstance(Hands[Side]))
            Control->CreateControl(Mesh, Root, Mesh, Hands[Side], Drive(S->HandStrength, true), FPhysicsControlTarget(), AnchorsSet, TEXT("SkiHand"));
    }
    bCrashed = false;
    ApplyRiding();
    UE_LOG(LogTemp, Display, TEXT("SKI physical body on %s: %d bodies, %d controls, root %s"), *Mesh->GetName(),
        Mesh->Bodies.Num(), Control->GetAllControlNames().Num(), *Root.ToString());
    return true;
}

void USkiPhysicalBody::End()
{
    if (Control)
    {
        Control->DestroyAllControlsAndBodyModifiers();
        Control->DestroyComponent();
        Control = nullptr;
    }
    if (Mesh)
    {
        Mesh->SetAllBodiesSimulatePhysics(false);
        Mesh->SetAllBodiesPhysicsBlendWeight(0.f);
        Mesh->PhysicsTransformUpdateMode = EPhysicsTransformUpdateMode::Type(SavedUpdateMode);
        if (!SavedProfile.IsNone()) Mesh->SetCollisionProfileName(SavedProfile);
        Mesh = nullptr;
    }
    bCrashed = false;
    PendingFrames = 0;
}

void USkiPhysicalBody::ApplyRiding()
{
    const USkiSettings* S = GetDefault<USkiSettings>();
    Control->SetBodyModifiersInSetMovementType(RootSet, EPhysicsMovementType::Kinematic);
    Control->SetBodyModifiersInSetGravityMultiplier(TEXT("All"), 0.f);
    Control->SetBodyModifiersInSetCollisionType(TEXT("All"), ECollisionEnabled::QueryOnly);
    Control->SetControlDatasInSet(JointsSet, Drive(S->JointStrength, false));
    Control->SetControlsInSetEnabled(AnchorsSet, true);
}

void USkiPhysicalBody::ApplyCrash()
{
    const USkiSettings* S = GetDefault<USkiSettings>();
    Control->SetBodyModifiersInSetMovementType(RootSet, EPhysicsMovementType::Simulated);
    Control->SetBodyModifiersInSetGravityMultiplier(TEXT("All"), 1.f);
    Control->SetBodyModifiersInSetCollisionType(TEXT("All"), ECollisionEnabled::QueryAndPhysics);
    Control->SetControlDatasInSet(JointsSet, Drive(S->JointStrength * S->CrashTone, false));
    Control->SetControlsInSetEnabled(AnchorsSet, false);
}

void USkiPhysicalBody::Crash(const FVector& Velocity)
{
    if (!Control || bCrashed) return;
    bCrashed = true;
    ApplyCrash();
    // The modifiers reach the bodies on Physics Control's next update: the velocity follows once they simulate.
    PendingVelocity = Velocity;
    PendingFrames = 2;
}

void USkiPhysicalBody::Recover()
{
    if (!Control || !bCrashed) return;
    bCrashed = false;
    PendingFrames = 0;
    ApplyRiding();
}

void USkiPhysicalBody::Update()
{
    if (!Mesh || PendingFrames <= 0) return;
    if (--PendingFrames == 0 || Mesh->IsSimulatingPhysics(Root))
    {
        Mesh->SetAllPhysicsLinearVelocity(PendingVelocity);
        PendingFrames = 0;
    }
}

FVector USkiPhysicalBody::GetPelvisLocation() const
{
    return Mesh ? Mesh->GetBoneLocation(Root) : FVector::ZeroVector;
}

FVector USkiPhysicalBody::GetPelvisVelocity() const
{
    return Mesh ? Mesh->GetPhysicsLinearVelocity(Root) : FVector::ZeroVector;
}
