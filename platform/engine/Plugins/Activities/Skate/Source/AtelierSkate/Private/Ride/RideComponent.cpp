// USkateComponent's side of the Ride backend: starting and stepping the session, its sounds, and the bail's ragdoll
// and loose board. SkateRuntime.cpp copies the session's outputs into RetailRuntime, so the board placement,
// retargeting, modes and HUD after the step are the same code for both backends.
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateRails.h"
#include "RideSession.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "PhysicsEngine/PhysicsConstraintTemplate.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/OverlapResult.h"

namespace
{
    FRideWorld RideWorld(ACharacter* Rider, USkateRailSubsystem* Rails)
    {
        FRideWorld W; W.World = Rider ? Rider->GetWorld() : nullptr; W.Ignore = Rider; W.Rails = Rails; return W;
    }
    FRidePreferences RidePreferences()
    {
        const USkateSettings* S = GetDefault<USkateSettings>();
        FRidePreferences P;
        P.Pop = S->PopHeightScale; P.Spin = S->AirSpinScale; P.PushSpeed = S->PushSpeedScale; P.PushPower = S->PushPowerScale; P.VertAssist = S->VertAssist;
        return P;
    }
    // The loose board's box: the deck, trucks and wheels, centred this far below the deck bone (cm at board scale 1).
    const FVector LooseBoardExtent(40.f, 10.5f, 5.f);
    constexpr float LooseBoardDrop = 4.f;
    // The reach of the surfaces made physical around a fallen body, and how far it may move before they follow.
    constexpr float PhysicalRadius = 1200.f, PhysicalFollow = 600.f;
    // Instanced meshes with more instances than this stay query-only (switching them all would hitch).
    constexpr int32 PhysicalMaxInstances = 64;
}

void USkateComponent::PreloadRide()
{
    if (!Ride) Ride = MakeShared<FRideSession>();
    Ride->Preload();
}

bool USkateComponent::StartRide()
{
    if (!Rider) return false;
    if (!Ride) Ride = MakeShared<FRideSession>();
    EndRagdoll();
    Ride->SetRagdoll(Rider->GetMesh() != nullptr && Rider->GetMesh()->GetSkeletalMeshAsset() != nullptr);
    Ride->Activate(RideWorld(Rider, RailSystem), Pos, Rot, Vel, bGoofy, RidePreferences());
    UE_LOG(LogTemp, Display, TEXT("SKATE ride started at (%.0f, %.0f, %.0f) speed %.0f, %s"), Pos.X, Pos.Y, Pos.Z, Vel.Size(),
        Ride->HasRig() ? TEXT("rider clips") : TEXT("board only"));
    return true;
}

void USkateComponent::StopRide()
{
    EndRagdoll();
}

bool USkateComponent::StepRide(float Dt)
{
    // The deliberate bail: both sticks clicked with both triggers held (scripted input sets bBail itself).
    if (!bScripted && Rider)
    {
        In.bBail = false;
        if (APlayerController* PC = Cast<APlayerController>(Rider->GetController()))
            In.bBail = PC->IsInputKeyDown(EKeys::Gamepad_LeftThumbstick) && PC->IsInputKeyDown(EKeys::Gamepad_RightThumbstick) &&
                PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis) > .5f && PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > .5f;
    }
    Ride->Step(Dt, In, RideWorld(Rider, RailSystem));
    for (const ERideCue Cue : Ride->Cues)
        switch (Cue)
        {
        case ERideCue::Push: PlayCue(TEXT("push"), .7f); break;
        case ERideCue::Flick: PlayCue(TEXT("flick"), .6f); break;
        case ERideCue::Catch: PlayCue(TEXT("catch"), .7f); break;
        case ERideCue::Fall: PlayCue(TEXT("fall"), 1.f); break;
        }
    return true;
}

void USkateComponent::AfterRideFrame(float Dt)
{
    if (!Ride) return;
    if (Ride->IsBailing() && !bRagdoll && !LooseBoard && Ride->BailTime() < .25f && !StartRagdoll()) Ride->SetRagdoll(false);
    if (bRagdoll || LooseBoard) UpdateRagdoll(Dt);
}

// ---------------------------------------------------------------------------------------------------------------
// Bails: the rider's own physics asset (or one built from its skeleton) goes limp with the board's velocity, the
// board tumbles as its own body, and when the body has settled the rider gets up where it lies, the pose blending
// from the fallen body to the stance.

UPhysicsAsset* USkateComponent::BuildRagdollAsset()
{
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (!Mesh || !Mesh->GetSkeletalMeshAsset()) return nullptr;
    const FReferenceSkeleton& Ref = Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    auto Bone = [&](const TCHAR* Contract)
    {
        if (!Contract) return int32(INDEX_NONE);
        const FName B = RiderApi ? RiderApi->GetSkateBone(FName(Contract)) : FName(Contract);
        return B.IsNone() ? int32(INDEX_NONE) : Ref.FindBoneIndex(B);
    };
    TArray<FTransform> Bind; Bind.SetNum(Ref.GetNum());
    for (int32 I = 0; I < Ref.GetNum(); ++I)
    {
        const int32 Parent = Ref.GetParentIndex(I);
        Bind[I] = Parent >= 0 ? Ref.GetRefBonePose()[I] * Bind[Parent] : Ref.GetRefBonePose()[I];
    }
    // Each body is a capsule from its bone toward the next contract bone (a sphere at the ends), radius in cm at the
    // rider's height; each joint limits swing and twist like a loose body.
    struct FPart { const TCHAR* Bone; const TCHAR* To; const TCHAR* Parent; float Radius; float Swing; float Twist; };
    static const FPart Parts[] = {
        {TEXT("pelvis"), TEXT("spine"), nullptr, 12.f, 0, 0},
        {TEXT("spine"), TEXT("chest"), TEXT("pelvis"), 11.f, 20.f, 15.f},
        {TEXT("chest"), TEXT("neck"), TEXT("spine"), 13.f, 20.f, 15.f},
        {TEXT("head"), nullptr, TEXT("chest"), 10.f, 35.f, 35.f},
        {TEXT("upperarm_L"), TEXT("forearm_L"), TEXT("chest"), 5.f, 70.f, 35.f},
        {TEXT("forearm_L"), TEXT("hand_L"), TEXT("upperarm_L"), 4.f, 60.f, 15.f},
        {TEXT("hand_L"), nullptr, TEXT("forearm_L"), 4.f, 30.f, 15.f},
        {TEXT("upperarm_R"), TEXT("forearm_R"), TEXT("chest"), 5.f, 70.f, 35.f},
        {TEXT("forearm_R"), TEXT("hand_R"), TEXT("upperarm_R"), 4.f, 60.f, 15.f},
        {TEXT("hand_R"), nullptr, TEXT("forearm_R"), 4.f, 30.f, 15.f},
        {TEXT("thigh_L"), TEXT("shin_L"), TEXT("pelvis"), 7.5f, 45.f, 15.f},
        {TEXT("shin_L"), TEXT("foot_L"), TEXT("thigh_L"), 5.5f, 60.f, 8.f},
        {TEXT("foot_L"), TEXT("toe_L"), TEXT("shin_L"), 4.5f, 25.f, 8.f},
        {TEXT("thigh_R"), TEXT("shin_R"), TEXT("pelvis"), 7.5f, 45.f, 15.f},
        {TEXT("shin_R"), TEXT("foot_R"), TEXT("thigh_R"), 5.5f, 60.f, 8.f},
        {TEXT("foot_R"), TEXT("toe_R"), TEXT("shin_R"), 4.5f, 25.f, 8.f},
    };
    // Radii are for a 1.7 m rider; scale them by this skeleton's head height in component space.
    const int32 Head = Bone(TEXT("head")), Root = Bone(TEXT("root"));
    const float Height = Head != INDEX_NONE ? float(Bind[Head].GetLocation().Z - (Root != INDEX_NONE ? Bind[Root].GetLocation().Z : 0.)) : 155.f;
    const float Size = FMath::Clamp(Height / 155.f, .2f, 5.f);
    UPhysicsAsset* Asset = NewObject<UPhysicsAsset>(this, TEXT("RideRagdoll"), RF_Transient);
    int32 Bodies = 0;
    TArray<int32, TInlineAllocator<16>> Used;
    for (const FPart& Part : Parts)
    {
        const int32 B = Bone(Part.Bone);
        // A contract that names one bone twice gets one body.
        if (B == INDEX_NONE || Used.Contains(B)) continue;
        Used.Add(B);
        const int32 To = Bone(Part.To), Parent = Bone(Part.Parent), BoneParent = Ref.GetParentIndex(B);
        // The body's long axis in the bone's space.
        FVector End = FVector::ZeroVector, Axis = FVector::UpVector;
        if (To != INDEX_NONE) { End = Bind[To].GetRelativeTransform(Bind[B]).GetLocation(); Axis = End.GetSafeNormal(); }
        else if (BoneParent >= 0) Axis = Bind[B].GetRotation().UnrotateVector((Bind[B].GetLocation() - Bind[BoneParent].GetLocation()).GetSafeNormal());
        if (Axis.IsNearlyZero()) Axis = FVector::UpVector;
        // Shapes are in the bone's space, which carries the bone's scale.
        const float Radius = Part.Radius * Size / FMath::Max(.01f, float(Bind[B].GetMaximumAxisScale()));
        USkeletalBodySetup* Body = NewObject<USkeletalBodySetup>(Asset, NAME_None, RF_Transient);
        Body->BoneName = Ref.GetBoneName(B);
        Body->PhysicsType = PhysType_Default;
        Body->CollisionTraceFlag = CTF_UseSimpleAsComplex;
        Body->DefaultInstance.LinearDamping = .05f;
        Body->DefaultInstance.AngularDamping = .8f;
        const float Length = float(End.Size());
        if (To != INDEX_NONE && Length > Radius * 1.2f)
        {
            FKSphylElem Capsule(Radius, FMath::Max(1.f, Length - Radius));
            Capsule.Center = End * .5f;
            Capsule.Rotation = FRotationMatrix::MakeFromZ(Axis).Rotator();
            Body->AggGeom.SphylElems.Add(Capsule);
        }
        else
        {
            FKSphereElem Sphere(Radius);
            Sphere.Center = Axis * Radius * .7f;
            Body->AggGeom.SphereElems.Add(Sphere);
        }
        Body->CreatePhysicsMeshes();
        Asset->SkeletalBodySetups.Add(Body);
        ++Bodies;
        if (Parent == INDEX_NONE) continue;
        // The joint at the bone's origin, its twist axis along the body.
        UPhysicsConstraintTemplate* Joint = NewObject<UPhysicsConstraintTemplate>(Asset, NAME_None, RF_Transient);
        FConstraintInstance& C = Joint->DefaultInstance;
        C.JointName = Body->BoneName;
        C.ConstraintBone1 = Body->BoneName;
        C.ConstraintBone2 = Ref.GetBoneName(Parent);
        const FTransform Frame1(FRotationMatrix::MakeFromX(Axis).ToQuat());
        C.SetRefFrame(EConstraintFrame::Frame1, Frame1);
        C.SetRefFrame(EConstraintFrame::Frame2, Frame1 * Bind[B].GetRelativeTransform(Bind[Parent]));
        C.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
        C.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
        C.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
        C.SetAngularSwing1Limit(EAngularConstraintMotion::ACM_Limited, Part.Swing);
        C.SetAngularSwing2Limit(EAngularConstraintMotion::ACM_Limited, Part.Swing);
        C.SetAngularTwistLimit(EAngularConstraintMotion::ACM_Limited, Part.Twist);
        C.SetDisableCollision(true);
        Asset->ConstraintSetup.Add(Joint);
    }
    if (Bodies < 6) { UE_LOG(LogTemp, Warning, TEXT("SKATE ride ragdoll: only %d contract bones, no ragdoll"), Bodies); return nullptr; }
    Asset->UpdateBodySetupIndexMap();
    Asset->UpdateBoundsBodiesArray();
    // The bodies only meet the world: built capsules overlap their neighbours in any pose, and overlapping bodies in
    // one ragdoll push each other apart violently.
    for (int32 I = 0; I < Bodies; ++I)
        for (int32 J = I + 1; J < Bodies; ++J) Asset->DisableCollision(I, J);
    return Asset;
}

bool USkateComponent::StartRagdoll()
{
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (!Mesh || !Ride) return false;
    const FVector Velocity = Ride->GetBailVelocity();
    const float Scale = BoardScale();
    // The loose board: a box the size of the board, thrown with its velocity and spin; the board's meshes follow it.
    LooseBoard = NewObject<UBoxComponent>(Rider, NAME_None, RF_Transient);
    LooseBoard->SetBoxExtent(LooseBoardExtent * Scale);
    LooseBoard->SetCollisionProfileName(TEXT("PhysicsActor"));
    LooseBoard->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
    // It starts inside the rider's feet: the two bodies pass through each other rather than push apart.
    LooseBoard->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Ignore);
    LooseBoard->SetHiddenInGame(true);
    LooseBoard->SetUsingAbsoluteLocation(true); LooseBoard->SetUsingAbsoluteRotation(true); LooseBoard->SetUsingAbsoluteScale(true);
    LooseBoard->RegisterComponent();
    const FQuat DeckRotation = BoardRoot->GetComponentQuat();
    LooseBoard->SetWorldLocationAndRotation(BoardRoot->GetComponentLocation() - DeckRotation.GetUpVector() * LooseBoardDrop * Scale, DeckRotation);
    LooseBoard->SetMassOverrideInKg(NAME_None, 3.5f, true);
    LooseBoard->SetLinearDamping(.15f);
    LooseBoard->SetAngularDamping(.4f);
    LooseBoard->SetSimulatePhysics(true);
    LooseBoard->SetPhysicsLinearVelocity(Velocity * .85f + FVector(0, 0, 90.f));
    LooseBoard->SetPhysicsAngularVelocityInRadians(Ride->GetBailSpin() +
        DeckRotation.GetForwardVector() * FMath::FRandRange(-7.f, 7.f) + DeckRotation.GetRightVector() * FMath::FRandRange(-4.f, 4.f));
    MakeWorldPhysical(BoardRoot->GetComponentLocation());
    // The rider: its own physics asset when it has a usable one, otherwise one built from the bone contract.
    UPhysicsAsset* Own = Mesh->GetSkeletalMeshAsset() ? Mesh->GetSkeletalMeshAsset()->GetPhysicsAsset() : nullptr;
    bOwnPhysicsAsset = Own && Own->SkeletalBodySetups.Num() >= 6;
    if (!bOwnPhysicsAsset)
    {
        if (!RagdollAsset) RagdollAsset = BuildRagdollAsset();
        if (!RagdollAsset) { UE_LOG(LogTemp, Warning, TEXT("SKATE ride ragdoll unavailable; the rider slides instead")); return false; }
        Mesh->SetPhysicsAsset(RagdollAsset, true);
    }
    SavedMeshProfile = Mesh->GetCollisionProfileName();
    Mesh->SetCollisionProfileName(TEXT("Ragdoll"));
    Mesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
    Mesh->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
    if (Mesh->Bodies.Num() == 0) Mesh->RecreatePhysicsState();
    if (Mesh->Bodies.Num() == 0)
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride ragdoll has no bodies; the rider slides instead"));
        Mesh->SetCollisionProfileName(SavedMeshProfile);
        if (!bOwnPhysicsAsset) Mesh->SetPhysicsAsset(Own, true);
        return false;
    }
    Mesh->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
    Mesh->SetAllBodiesSimulatePhysics(true);
    Mesh->SetSimulatePhysics(true);
    Mesh->SetPhysicsBlendWeight(1.f);
    Mesh->bBlendPhysics = true;
    Mesh->WakeAllRigidBodies();
    // The body leaves the board with its speed, a little lift, and its upper half pitched along the travel.
    Mesh->SetAllPhysicsLinearVelocity(Velocity * .9f + FVector(0, 0, 60.f));
    const FName Head = RiderApi ? RiderApi->GetSkateBone(TEXT("head")) : FName(TEXT("head"));
    if (!Head.IsNone()) Mesh->AddImpulse(Velocity.GetSafeNormal2D() * 25.f, Head, true);
    bRagdoll = true; RagdollTime = 0; RagdollQuiet = 0; GetUpBlend = -1;
    RagdollStart = Mesh->GetBoneLocation(RiderApi ? RiderApi->GetSkateBone(TEXT("pelvis")) : FName(TEXT("pelvis")));
    RagdollLimit = FMath::Max(2500.f, Velocity.Size() * 1.5f + 800.f);
    {
        // The floor the body starts over: a body found well below it, under a floor, has fallen through the world.
        FHitResult Hit;
        FCollisionQueryParams Params(TEXT("RideFloor"), false, Rider);
        RagdollFloor = GetWorld()->LineTraceSingleByChannel(Hit, RagdollStart + FVector(0, 0, 50.f), RagdollStart - FVector(0, 0, 300.f), ECC_Pawn, Params)
            ? FVector(Hit.ImpactPoint) : RagdollStart - FVector(0, 0, 100.f);
    }
    UE_LOG(LogTemp, Display, TEXT("SKATE ride ragdoll (%s physics asset, %d bodies) at %.0f cm/s"),
        bOwnPhysicsAsset ? TEXT("rider's") : TEXT("contract"), Mesh->Bodies.Num(), Velocity.Size());
    return true;
}

void USkateComponent::UpdateRagdoll(float Dt)
{
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    const FRideTuning& Tune = FRideTuning::Get();
    // The board's meshes follow the loose body until the rider stands again.
    if (LooseBoard && Ride && Ride->GetMode() != ERideState::Ground)
    {
        const FTransform Body = LooseBoard->GetComponentTransform();
        const float Scale = BoardScale();
        BoardRoot->SetWorldTransform(FTransform(Body.GetRotation(), Body.GetLocation() + Body.GetRotation().GetUpVector() * LooseBoardDrop * Scale, FVector(Scale)));
    }
    if (!Mesh || !Ride) { EndRagdoll(); return; }
    if (bRagdoll && GetUpBlend < 0)
    {
        RagdollTime += Dt;
        const FName PelvisBone = RiderApi ? RiderApi->GetSkateBone(TEXT("pelvis")) : FName(TEXT("pelvis"));
        const FVector Hips = Mesh->GetBoneLocation(PelvisBone);
        const float Speed = Mesh->GetPhysicsLinearVelocity(PelvisBone).Size();
        RagdollQuiet = Speed < 40.f ? RagdollQuiet + Dt : 0.f;
        // A body that gains speed or height it was never given has met something it cannot resolve: stop simulating
        // it and let the session slide the rider to a stop instead.
        bool bThrough = false;
        if (Hips.Z < RagdollFloor.Z - 120.f)
        {
            FHitResult Above;
            FCollisionQueryParams Params(TEXT("RideThrough"), false, Rider);
            bThrough = GetWorld()->LineTraceSingleByChannel(Above, Hips, Hips + FVector(0, 0, 400.f), ECC_Pawn, Params) && Above.ImpactNormal.Z < -.5f;
        }
        if (Speed > RagdollLimit || Hips.Z > RagdollStart.Z + 400.f || bThrough || Hips.ContainsNaN())
        {
            UE_LOG(LogTemp, Warning, TEXT("SKATE ride ragdoll unstable (%.0f cm/s, %.0f cm from the start%s); the rider slides instead"),
                Speed, Hips.Z - RagdollStart.Z, bThrough ? TEXT(", under the floor") : TEXT(""));
            Ride->SetRagdoll(false);
            EndRagdoll();
            return;
        }
        // The root and the camera follow the ground under the body.
        FHitResult Hit;
        FCollisionQueryParams Params(TEXT("RideBody"), false, Rider);
        FVector Ground = Hips - FVector(0, 0, 15.f);
        if (GetWorld()->LineTraceSingleByChannel(Hit, Hips + FVector(0, 0, 40.f), Hips - FVector(0, 0, 250.f), ECC_Pawn, Params)) Ground = Hit.ImpactPoint;
        Ride->FollowBody(Ground);
        if (FVector::Dist(Hips, PhysicalCentre) > PhysicalFollow) MakeWorldPhysical(Hips);
        const bool bSettled = RagdollTime > 1.6f && (RagdollQuiet > .4f || RagdollTime > Tune.BailSettle + 2.f);
        if (bSettled || !Ride->IsBailing())
        {
            // Stand up where the body lies, facing the way the body points (head from hips).
            const FName HeadBone = RiderApi ? RiderApi->GetSkateBone(TEXT("head")) : FName(TEXT("head"));
            const FVector Flat = (Mesh->GetBoneLocation(HeadBone) - Hips).GetSafeNormal2D();
            const float Yaw = Flat.IsNearlyZero() ? float(Rider->GetActorRotation().Yaw) : float(Flat.Rotation().Yaw);
            if (Ride->IsBailing()) Ride->GetUp(Ground, Yaw);
            // The mesh goes back on the capsule while the bodies keep lying where they are; the physics weight then
            // fades so the stance rises out of the fallen body.
            Mesh->AttachToComponent(Rider->GetCapsuleComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
            SetMeshForRiding(true);
            GetUpBlend = 0;
            UE_LOG(LogTemp, Display, TEXT("SKATE ride get up after %.1f s"), RagdollTime);
        }
        return;
    }
    if (bRagdoll && GetUpBlend >= 0)
    {
        GetUpBlend += Dt / FMath::Max(.1f, Tune.GetUpTime);
        const float Weight = 1.f - FMath::SmoothStep(0.f, 1.f, GetUpBlend);
        if (GetUpBlend < 1.f) { Mesh->bBlendPhysics = false; Mesh->SetAllBodiesPhysicsBlendWeight(Weight); return; }
    }
    EndRagdoll();
}

void USkateComponent::MakeWorldPhysical(const FVector& Centre)
{
    PhysicalCentre = Centre;
    TArray<FOverlapResult> Hits;
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_WorldStatic); Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
    FCollisionQueryParams Params(TEXT("RideWorld"), false, Rider);
    GetWorld()->OverlapMultiByObjectType(Hits, Centre, FQuat::Identity, Objects, FCollisionShape::MakeSphere(PhysicalRadius), Params);
    for (const FOverlapResult& Hit : Hits)
    {
        UPrimitiveComponent* C = Hit.GetComponent();
        if (!C || C == LooseBoard || C->GetCollisionEnabled() != ECollisionEnabled::QueryOnly) continue;
        if (C->GetCollisionResponseToChannel(ECC_PhysicsBody) != ECR_Block || C->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block) continue;
        if (const UInstancedStaticMeshComponent* Instanced = Cast<UInstancedStaticMeshComponent>(C); Instanced && Instanced->GetInstanceCount() > PhysicalMaxInstances) continue;
        if (MadePhysical.Contains(C)) continue;
        C->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        MadePhysical.Add(C);
    }
}

void USkateComponent::RestoreWorld()
{
    for (const TWeakObjectPtr<UPrimitiveComponent>& C : MadePhysical)
        if (C.IsValid()) C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    MadePhysical.Reset();
}

void USkateComponent::EndRagdoll()
{
    if (LooseBoard)
    {
        LooseBoard->SetSimulatePhysics(false);
        LooseBoard->DestroyComponent();
        LooseBoard = nullptr;
    }
    GetUpBlend = -1;
    RestoreWorld();
    if (!bRagdoll) return;
    bRagdoll = false;
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (!Mesh) return;
    Mesh->SetAllBodiesSimulatePhysics(false);
    Mesh->SetSimulatePhysics(false);
    Mesh->bBlendPhysics = false;
    Mesh->SetAllBodiesPhysicsBlendWeight(0.f);
    if (!SavedMeshProfile.IsNone()) Mesh->SetCollisionProfileName(SavedMeshProfile);
    if (!bOwnPhysicsAsset) Mesh->SetPhysicsAsset(Mesh->GetSkeletalMeshAsset() ? Mesh->GetSkeletalMeshAsset()->GetPhysicsAsset() : nullptr, true);
    if (Mesh->GetAttachParent() != Rider->GetCapsuleComponent())
        Mesh->AttachToComponent(Rider->GetCapsuleComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
    SetMeshForRiding(IsRiding());
}
