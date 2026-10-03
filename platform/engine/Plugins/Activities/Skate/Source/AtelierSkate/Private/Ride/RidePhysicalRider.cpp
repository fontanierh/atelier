// The physical rider: see RidePhysicalRider.h and RIDE.md, "Physical rider".
#include "RidePhysicalRider.h"
#include "SkateRider.h"
#include "PhysicsControlComponent.h"
#include "PhysicsControlAsset.h"
#include "Components/BoxComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/OverlapResult.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/PhysicsConstraintTemplate.h"
#include "PhysicsEngine/SkeletalBodySetup.h"

namespace
{
    TAutoConsoleVariable<int32> CVarRidePhysical(TEXT("skate.RidePhysical"), 1,
        TEXT("Ride: 1 (the default) makes the rider an active ragdoll while riding (Physics Control drives its bodies toward the ")
        TEXT("animation); 0 animates it, with a ragdoll for bails only."));

    TArray<TWeakObjectPtr<URidePhysicalRider>> GRiders;
    FAutoConsoleCommand ReloadCommand(TEXT("skate.RidePhysicalReload"),
        TEXT("Ride: rebuild the physical rider's profiles from Project Settings > Skate Physical Rider and apply them."),
        FConsoleCommandDelegate::CreateLambda([]
        {
            for (const TWeakObjectPtr<URidePhysicalRider>& R : GRiders) if (R.IsValid()) R->ReloadProfiles();
        }));
    FAutoConsoleCommand DumpCommand(TEXT("skate.RidePhysicalDump"),
        TEXT("Ride: log every body of the physical rider (scale, body, bone and target positions, bounds, what it touches)."),
        FConsoleCommandDelegate::CreateLambda([]
        {
            for (const TWeakObjectPtr<URidePhysicalRider>& R : GRiders) if (R.IsValid()) R->Dump();
        }));

    // Control and body modifier sets. The limbs' own sets (WorldSpace_FootLeft, ParentSpace_Spine, FootLeft, ...)
    // come from Physics Control; these group them.
    const FName AllSet(TEXT("All")), WorldSet(TEXT("WorldSpace")), ParentSet(TEXT("ParentSpace"));
    const FName AnchorPelvis(TEXT("Anchor_Pelvis")), AnchorFeet(TEXT("Anchor_Feet")), AnchorHands(TEXT("Anchor_Hands"));
    const FName JointsSpine(TEXT("Joints_Spine")), JointsArms(TEXT("Joints_Arms")), JointsLegs(TEXT("Joints_Legs"));
    const FName FeetBodies(TEXT("Feet"));

    FName PhaseName(ERidePhysicalPhase Phase)
    {
        switch (Phase)
        {
        case ERidePhysicalPhase::Riding: return TEXT("Riding");
        case ERidePhysicalPhase::Air: return TEXT("Air");
        case ERidePhysicalPhase::Landing: return TEXT("Landing");
        case ERidePhysicalPhase::Grind: return TEXT("Grind");
        case ERidePhysicalPhase::Manual: return TEXT("Manual");
        case ERidePhysicalPhase::Bail: return TEXT("Bail");
        case ERidePhysicalPhase::GetUp: return TEXT("GetUp");
        case ERidePhysicalPhase::OnFoot: return TEXT("OnFoot");
        default: return NAME_None;
        }
    }
    constexpr ERidePhysicalPhase Phases[] = { ERidePhysicalPhase::Riding, ERidePhysicalPhase::Air, ERidePhysicalPhase::Landing,
        ERidePhysicalPhase::Grind, ERidePhysicalPhase::Manual, ERidePhysicalPhase::Bail, ERidePhysicalPhase::GetUp, ERidePhysicalPhase::OnFoot };

    // A sparse control update that sets only strengths and damping, leaving collision, targets and enabling alone.
    FPhysicsControlSparseData Strengths(float Linear, float Angular, float Damping)
    {
        FPhysicsControlSparseData D;
        D.bEnableLinearExtraDamping = D.bEnableMaxForce = D.bEnableAngularExtraDamping = D.bEnableMaxTorque = false;
        D.bEnableLinearTargetVelocityMultiplier = D.bEnableAngularTargetVelocityMultiplier = D.bEnableCustomControlPoint = false;
        D.bEnablebEnabled = D.bEnablebUseCustomControlPoint = D.bEnablebUseSkeletalAnimation = D.bEnablebDisableCollision = false;
        D.bEnablebOnlyControlChildObject = D.bEnablebUseAccelerationDriveMode = false;
        D.LinearStrength = Linear; D.AngularStrength = Angular;
        D.LinearDampingRatio = D.AngularDampingRatio = Damping;
        return D;
    }
    FPhysicsControlModifierSparseData Modifier()
    {
        FPhysicsControlModifierSparseData D;
        D.bEnableMovementType = D.bEnableCollisionType = D.bEnableGravityMultiplier = D.bEnablePhysicsBlendWeight = false;
        D.bEnableKinematicTargetSpace = D.bEnablebUpdateKinematicFromSimulation = D.bEnablebEnableCCD = false;
        return D;
    }

    // The loose board's box: the deck, trucks and wheels, centred this far below the deck bone (cm at board scale 1).
    const FVector LooseBoardExtent(40.f, 10.5f, 5.f);
    constexpr float LooseBoardDrop = 4.f;
    // The surfaces made physical follow the body once it has moved this far, and let go beyond twice the radius.
    constexpr float PhysicalFollow = 600.f;
    // Instanced meshes with more instances than this stay query-only (switching them all would hitch).
    constexpr int32 PhysicalMaxInstances = 64;
    constexpr int32 MinBodies = 6;
    // A mesh that moves further than this in one frame was placed, not ridden (60 m/s at 60 fps).
    constexpr float PlacedDistance = 100.f;
    // For this many frames after a placement, a change of the rider's speed above LaunchStep in one frame (12 g at
    // 60 fps: a scripted launch, not riding) is given to the body as well.
    constexpr int32 PlacedLaunchFrames = 3;
    constexpr float LaunchStep = 200.f;
    // The get-up hands the bodies to the animation once Physics Control's copy of it shows the snapshot this closely
    // (cm), or after this many frames.
    constexpr float SnapshotShown = 10.f;
    constexpr int32 MaxGetUpWait = 4;
    // How far below the pelvis a bail looks for the ground it lies on (cm): a body sliding down a wall can be metres
    // above the floor.
    constexpr float HipsGroundRange = 1000.f;
    // A fallen pelvis this close to the ground under it is down, and the body slides (cm).
    constexpr float SlideHeight = 50.f;
}

// ---------------------------------------------------------------------------------------------------------------
// Settings.

URidePhysicalSettings::URidePhysicalSettings()
{
    // Riding keeps the defaults. In the air the hands hold grabs; a landing lets the legs absorb; a grind holds the
    // feet harder on the deck; a bail lets go of everything but a muscle tone, and falls; on foot the feet follow the
    // steps more loosely.
    Air.Hands = 8.f;
    Landing.Legs = .8f; Landing.Feet = 14.f;
    Grind.Feet = 14.f;
    Bail.Joints = 3.f; Bail.Body = 0.f; Bail.Pelvis = 0.f; Bail.Feet = 0.f; Bail.Hands = 0.f; Bail.Gravity = 1.f;
    Bail.bFeetTouchWorld = true;
    OnFoot.Feet = 6.f;
}

const FRidePhysicalProfile& URidePhysicalSettings::Profile(ERidePhysicalPhase Phase) const
{
    switch (Phase)
    {
    case ERidePhysicalPhase::Air: return Air;
    case ERidePhysicalPhase::Landing: return Landing;
    case ERidePhysicalPhase::Grind: return Grind;
    case ERidePhysicalPhase::Manual: return Manual;
    case ERidePhysicalPhase::Bail: return Bail;
    case ERidePhysicalPhase::GetUp: return GetUp;
    case ERidePhysicalPhase::OnFoot: return OnFoot;
    default: return Riding;
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Setup.

bool URidePhysicalRider::IsWanted() { return CVarRidePhysical.GetValueOnGameThread() != 0; }

FName URidePhysicalRider::Bone(const TCHAR* Contract) const
{
    const FName B = Api ? Api->GetSkateBone(FName(Contract)) : FName(Contract);
    const USkeletalMesh* Skeletal = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
    return !B.IsNone() && Skeletal && Skeletal->GetRefSkeleton().FindBoneIndex(B) != INDEX_NONE ? B : NAME_None;
}

bool URidePhysicalRider::Begin(ACharacter* InRider, const ISkateRider* InApi)
{
    USkeletalMeshComponent* NewMesh = InRider ? InRider->GetMesh() : nullptr;
    if (!NewMesh || !NewMesh->GetSkeletalMeshAsset()) return false;
    if (Control && Rider == InRider && Mesh == NewMesh && (bBuiltAsset ? Mesh->GetPhysicsAsset() == Built : true))
    {
        // A dismount still fading out: the new ride keeps the body.
        bEndWhenOut = false;
        return true;
    }
    if (Control) End();
    Rider = InRider; Api = InApi; Mesh = NewMesh;
    TickWorld = Rider->GetWorld();
    USkeletalMesh* Skeletal = Mesh->GetSkeletalMeshAsset();

    // The bodies: the rider's own physics asset when it has a usable one, otherwise one built from the bone contract.
    UPhysicsAsset* Own = Skeletal->GetPhysicsAsset();
    SavedPhysicsAsset = Mesh->GetPhysicsAsset();
    bBuiltAsset = !(Own && Own->SkeletalBodySetups.Num() >= MinBodies);
    if (bBuiltAsset)
    {
        if (!Built || BuiltFor != Skeletal) { Built = BuildPhysicsAsset(Skeletal, Api, this); BuiltFor = Skeletal; }
        if (!Built) { Mesh = nullptr; Rider = nullptr; return false; }
        Mesh->SetPhysicsAsset(Built, true);
    }
    else if (Mesh->GetPhysicsAsset() != Own) Mesh->SetPhysicsAsset(Own, true);
    SavedProfile = Mesh->GetCollisionProfileName();
    Mesh->SetCollisionProfileName(TEXT("Ragdoll"));
    Mesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
    Mesh->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
    if (Mesh->Bodies.Num() == 0) Mesh->RecreatePhysicsState();
    if (Mesh->Bodies.Num() == 0)
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: no bodies on %s"), *Skeletal->GetName());
        Mesh->SetCollisionProfileName(SavedProfile);
        if (bBuiltAsset) Mesh->SetPhysicsAsset(SavedPhysicsAsset, true);
        Mesh = nullptr; Rider = nullptr;
        return false;
    }
    // The mesh stays on the capsule: the bodies simulate in the world while the component keeps its place.
    SavedUpdateMode = uint8(Mesh->PhysicsTransformUpdateMode.GetValue());
    Mesh->PhysicsTransformUpdateMode = EPhysicsTransformUpdateMode::ComponentTransformIsKinematic;
    Mesh->bBlendPhysics = false;

    PelvisBone = Bone(TEXT("pelvis")); HeadBone = Bone(TEXT("head"));
    FootBones[0] = Bone(TEXT("foot_L")); FootBones[1] = Bone(TEXT("foot_R"));
    ThighBones[0] = Bone(TEXT("thigh_L")); ThighBones[1] = Bone(TEXT("thigh_R"));

    // The controls: an authored asset from the settings, or one built from the profiles.
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    UPhysicsControlAsset* Authored = S->ControlAsset.IsNull() ? nullptr : S->ControlAsset.LoadSynchronous();
    bOwnControlAsset = Authored == nullptr;
    Asset = Authored ? Authored : BuildControlAsset(Mesh->GetPhysicsAsset());
    Control = NewObject<UPhysicsControlComponent>(Rider, TEXT("RidePhysicsControl"), RF_Transient);
    Control->PhysicsControlAsset = Asset.Get();
    // A jump of the mesh this far in a frame is a placement: no target velocities from it (see Update).
    Control->TeleportDistanceThreshold = PlacedDistance;
    Control->RegisterComponent();
    Control->AddTickPrerequisiteComponent(Mesh);
    // The anchors (Physics Control's "world-space" controls) hold each body toward the animation in the board's
    // frame: relative to the kinematic body on the skeleton's root, which the actor carries with the board. Anchors
    // in the world trail a target that moves with the board by about a frame (12 cm at 10 m/s). Without a root
    // body, they are in the world.
    RootBone = Skeletal->GetRefSkeleton().GetBoneName(0);
    bBoardFrame = RootBone != PelvisBone && Mesh->GetBodyInstance(RootBone) != nullptr;
    if (!Control->CreateControlsAndBodyModifiersFromPhysicsControlAsset(Mesh, bBoardFrame ? Mesh.Get() : nullptr, bBoardFrame ? RootBone : NAME_None))
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: no controls for %s"), *Skeletal->GetName());
        End();
        return false;
    }
    // The pelvis's anchor already holds it to the root body: its joint control to the root goes.
    if (bBoardFrame && !PelvisBone.IsNone())
    {
        const FString Joint = RootBone.ToString() + TEXT("_") + PelvisBone.ToString();
        TArray<FName> Drop;
        for (const FName Name : Control->GetControlNamesInSet(TEXT("ParentSpace_Pelvis")))
            if (Name.ToString() == Joint || Name.ToString().StartsWith(Joint + TEXT("_"))) Drop.Add(Name);
        if (Drop.Num()) Control->DestroyControls(Drop, true, false);
    }
    Control->SetControlsInSetEnabled(AllSet, false);
    bSimulating = false; bEndWhenOut = false; Weight = WeightTarget = 0; AppliedWeight = -1;
    bBail = bBailOffered = false; bBailMaterial = bBailDrag = false; HipsAboveGround = -1; GetUpTime = -1; GetUpWait = -1; LandingLeft = 0;
    LastMeshLocation = Mesh->GetComponentLocation();
    LastRiderVelocity = Rider->GetVelocity(); PlacedFrames = 0;
    BeganFrame = GFrameCounter;
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(ERidePhysicalPhase::OnFoot);
    ApplyJointLimits(true, true);
    ApplyWeight();
    GRiders.AddUnique(this);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider on %s: %s physics asset, %d bodies, %d controls"), *Skeletal->GetName(),
        bBuiltAsset ? TEXT("contract") : TEXT("rider's"), Mesh->Bodies.Num(), Control->GetAllControlNames().Num());
    UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider anchors in the %s's frame"), bBoardFrame ? TEXT("board") : TEXT("world"));
    return true;
}

void URidePhysicalRider::End()
{
    GRiders.Remove(this);
    if (LooseBoard) DropLooseBoard();
    if (Control)
    {
        Control->DestroyAllControlsAndBodyModifiers();
        Control->DestroyComponent();
        Control = nullptr;
    }
    RestoreWorld();
    if (Mesh)
    {
        ApplyBailMaterial(false);
        ApplyBailDrag(false);
        Mesh->SetAllBodiesSimulatePhysics(false);
        Mesh->SetAllBodiesPhysicsBlendWeight(0.f);
        Mesh->bBlendPhysics = false;
        Mesh->PhysicsTransformUpdateMode = EPhysicsTransformUpdateMode::Type(SavedUpdateMode);
        if (!SavedProfile.IsNone()) Mesh->SetCollisionProfileName(SavedProfile);
        if (bBuiltAsset || Mesh->GetPhysicsAsset() != SavedPhysicsAsset) Mesh->SetPhysicsAsset(SavedPhysicsAsset, true);
    }
    // A running get-up keeps its clock (the self-tick) and its snapshot for BlendFromSnapshot.
    Mesh = nullptr; Rider = nullptr; Asset = nullptr; SavedPhysicsAsset = nullptr;
    bSimulating = false; bEndWhenOut = false; bBail = false; GetUpWait = -1;
    Weight = WeightTarget = 0; Phase = ERidePhysicalPhase::Off;
}

void URidePhysicalRider::Release(float Seconds)
{
    if (!Control) return;
    // A get-up still waiting to hand the bodies over keeps them until it has (Update), then ends.
    if (GetUpWait >= 0) { bEndWhenOut = true; return; }
    if (!bSimulating || Weight <= 0.f || Seconds <= 0.f || bBail) { End(); return; }
    bEndWhenOut = true;
    if (WeightTarget > 0.f) BlendOut(Seconds);
}

// The physics asset built from the bone contract: one capsule per part from its bone toward the next contract bone (a
// sphere at the ends), radius in cm for a 1.7 m rider, and joint limits wide enough for every riding pose.
UPhysicsAsset* URidePhysicalRider::BuildPhysicsAsset(USkeletalMesh* Skeletal, const ISkateRider* RiderApi, UObject* Outer)
{
    if (!Skeletal) return nullptr;
    const FReferenceSkeleton& Ref = Skeletal->GetRefSkeleton();
    auto Find = [&](const TCHAR* Contract)
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
    struct FPart { const TCHAR* Bone; const TCHAR* To; const TCHAR* Parent; float Radius; float Swing; float Twist; };
    static const FPart Parts[] = {
        {TEXT("pelvis"), TEXT("spine"), nullptr, 12.f, 0, 0},
        {TEXT("spine"), TEXT("chest"), TEXT("pelvis"), 11.f, 35.f, 30.f},
        {TEXT("chest"), TEXT("neck"), TEXT("spine"), 13.f, 35.f, 30.f},
        {TEXT("head"), nullptr, TEXT("chest"), 10.f, 50.f, 45.f},
        {TEXT("upperarm_L"), TEXT("forearm_L"), TEXT("chest"), 5.f, 100.f, 60.f},
        {TEXT("forearm_L"), TEXT("hand_L"), TEXT("upperarm_L"), 4.f, 120.f, 30.f},
        {TEXT("hand_L"), nullptr, TEXT("forearm_L"), 4.f, 60.f, 30.f},
        {TEXT("upperarm_R"), TEXT("forearm_R"), TEXT("chest"), 5.f, 100.f, 60.f},
        {TEXT("forearm_R"), TEXT("hand_R"), TEXT("upperarm_R"), 4.f, 120.f, 30.f},
        {TEXT("hand_R"), nullptr, TEXT("forearm_R"), 4.f, 60.f, 30.f},
        {TEXT("thigh_L"), TEXT("shin_L"), TEXT("pelvis"), 7.5f, 100.f, 35.f},
        {TEXT("shin_L"), TEXT("foot_L"), TEXT("thigh_L"), 5.5f, 120.f, 10.f},
        {TEXT("foot_L"), TEXT("toe_L"), TEXT("shin_L"), 4.5f, 45.f, 15.f},
        {TEXT("thigh_R"), TEXT("shin_R"), TEXT("pelvis"), 7.5f, 100.f, 35.f},
        {TEXT("shin_R"), TEXT("foot_R"), TEXT("thigh_R"), 5.5f, 120.f, 10.f},
        {TEXT("foot_R"), TEXT("toe_R"), TEXT("shin_R"), 4.5f, 45.f, 15.f},
    };
    // Radii are for a 1.7 m rider; scale them by this skeleton's head height in component space.
    const int32 Head = Find(TEXT("head")), Root = Find(TEXT("root"));
    const float Height = Head != INDEX_NONE ? float(Bind[Head].GetLocation().Z - (Root != INDEX_NONE ? Bind[Root].GetLocation().Z : 0.)) : 155.f;
    const float Size = FMath::Clamp(Height / 155.f, .2f, 5.f);
    UPhysicsAsset* Physics = NewObject<UPhysicsAsset>(Outer, NAME_None, RF_Transient);
    int32 Bodies = 0;
    TArray<int32, TInlineAllocator<16>> Used;
    for (const FPart& Part : Parts)
    {
        const int32 B = Find(Part.Bone);
        // A contract that names one bone twice gets one body.
        if (B == INDEX_NONE || Used.Contains(B)) continue;
        Used.Add(B);
        const int32 To = Find(Part.To), Parent = Find(Part.Parent), BoneParent = Ref.GetParentIndex(B);
        // The body's long axis in the bone's space.
        FVector End = FVector::ZeroVector, Axis = FVector::UpVector;
        if (To != INDEX_NONE) { End = Bind[To].GetRelativeTransform(Bind[B]).GetLocation(); Axis = End.GetSafeNormal(); }
        else if (BoneParent >= 0) Axis = Bind[B].GetRotation().UnrotateVector((Bind[B].GetLocation() - Bind[BoneParent].GetLocation()).GetSafeNormal());
        if (Axis.IsNearlyZero()) Axis = FVector::UpVector;
        // Shapes are in the bone's space, which carries the bone's scale.
        const float Radius = Part.Radius * Size / FMath::Max(.01f, float(Bind[B].GetMaximumAxisScale()));
        USkeletalBodySetup* Body = NewObject<USkeletalBodySetup>(Physics, NAME_None, RF_Transient);
        Body->BoneName = Ref.GetBoneName(B);
        Body->PhysicsType = PhysType_Default;
        Body->CollisionTraceFlag = CTF_UseSimpleAsComplex;
        Body->DefaultInstance.LinearDamping = .05f;
        Body->DefaultInstance.AngularDamping = .8f;
        const float Length = float(End.Size());
        if (To != INDEX_NONE && Length > Radius * 1.2f)
        {
            // Lengths are in the bone's units too: on a skeleton whose root carries its unit scale, one unit is
            // a metre or more.
            FKSphylElem Capsule(Radius, FMath::Max(Radius * .2f, Length - Radius));
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
        Physics->SkeletalBodySetups.Add(Body);
        ++Bodies;
        if (Parent == INDEX_NONE) continue;
        // The joint at the bone's origin, its twist axis along the body.
        UPhysicsConstraintTemplate* Joint = NewObject<UPhysicsConstraintTemplate>(Physics, NAME_None, RF_Transient);
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
        Physics->ConstraintSetup.Add(Joint);
    }
    if (Bodies < MinBodies) { UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: only %d contract bones"), Bodies); return nullptr; }
    // A kinematic body on the skeleton's root that follows the animation and touches nothing. The skeletal mesh's
    // physics blend expects a body there when the root bone is scaled (an FBX armature carries its unit scale on
    // it): it takes that body as the frame of the simulated bodies below the root. Without one, the pelvis lands at
    // the root, 1/scale of the way from it, and the rider sinks into the ground. It is also the board's frame for the
    // anchors (Begin).
    if (!Used.Contains(0))
    {
        USkeletalBodySetup* RootBody = NewObject<USkeletalBodySetup>(Physics, NAME_None, RF_Transient);
        RootBody->BoneName = Ref.GetBoneName(0);
        RootBody->PhysicsType = PhysType_Kinematic;
        RootBody->CollisionReponse = EBodyCollisionResponse::BodyCollision_Disabled;
        RootBody->CollisionTraceFlag = CTF_UseSimpleAsComplex;
        RootBody->AggGeom.SphereElems.Add(FKSphereElem(2.f / FMath::Max(.01f, float(Bind[0].GetMaximumAxisScale()))));
        RootBody->CreatePhysicsMeshes();
        Physics->SkeletalBodySetups.Add(RootBody);
    }
    Bodies = Physics->SkeletalBodySetups.Num();
    Physics->UpdateBodySetupIndexMap();
    Physics->UpdateBoundsBodiesArray();
    // The bodies only meet the world: built capsules overlap their neighbours in any pose, and overlapping bodies in
    // one ragdoll push each other apart violently.
    for (int32 I = 0; I < Bodies; ++I)
        for (int32 J = I + 1; J < Bodies; ++J) Physics->DisableCollision(I, J);
    return Physics;
}

// The control asset built from the bone contract. Physics Control gives each body to the first limb that reaches it,
// so the limbs go from the hands and feet in to the pelvis, which takes whatever is left (tails, skirts).
UPhysicsControlAsset* URidePhysicalRider::BuildControlAsset(const UPhysicsAsset* Physics)
{
    UPhysicsControlAsset* Target = NewObject<UPhysicsControlAsset>(this, NAME_None, RF_Transient);
    const FReferenceSkeleton& Ref = Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    struct FLimb { const TCHAR* Name; const TCHAR* Start; const TCHAR* Fallback; };
    static const FLimb Limbs[] = {
        {TEXT("FootLeft"), TEXT("foot_L"), nullptr}, {TEXT("FootRight"), TEXT("foot_R"), nullptr},
        {TEXT("LegLeft"), TEXT("thigh_L"), nullptr}, {TEXT("LegRight"), TEXT("thigh_R"), nullptr},
        {TEXT("HandLeft"), TEXT("hand_L"), nullptr}, {TEXT("HandRight"), TEXT("hand_R"), nullptr},
        {TEXT("ArmLeft"), TEXT("clavicle_L"), TEXT("upperarm_L")}, {TEXT("ArmRight"), TEXT("clavicle_R"), TEXT("upperarm_R")},
        {TEXT("Head"), TEXT("head"), nullptr}, {TEXT("Spine"), TEXT("spine"), nullptr}, {TEXT("Pelvis"), TEXT("pelvis"), nullptr},
    };
    TSet<int32> Claimed;
    TSet<FName> Present;
    FPhysicsControlCharacterSetupData& Setup = Target->CharacterSetupData;
    for (const FLimb& Limb : Limbs)
    {
        FName Start = Bone(Limb.Start);
        if (Start.IsNone() && Limb.Fallback) Start = Bone(Limb.Fallback);
        if (Start.IsNone()) continue;
        TArray<int32> Below;
        Physics->GetBodyIndicesBelow(Below, Start, Ref);
        bool bAny = false;
        for (const int32 I : Below) if (!Claimed.Contains(I)) { Claimed.Add(I); bAny = true; }
        if (!bAny) continue;
        FPhysicsControlLimbSetupData& Data = Setup.LimbSetupData.AddDefaulted_GetRef();
        Data.LimbName = Limb.Name;
        Data.StartBone = Start;
        Present.Add(Limb.Name);
    }
    // Controls start with no strength (the profiles set it); joints do not collide parent to child; every body
    // starts kinematic and unseen, following the animation.
    Setup.DefaultWorldSpaceControlData.LinearStrength = Setup.DefaultWorldSpaceControlData.AngularStrength = 0.f;
    Setup.DefaultParentSpaceControlData.LinearStrength = Setup.DefaultParentSpaceControlData.AngularStrength = 0.f;
    Setup.DefaultParentSpaceControlData.bDisableCollision = true;
    Setup.DefaultBodyModifierData.MovementType = EPhysicsMovementType::Kinematic;
    Setup.DefaultBodyModifierData.PhysicsBlendWeight = 0.f;

    auto AddSet = [&](TArray<FPhysicsControlSetUpdate>& Sets, FName Name, const TCHAR* Prefix, std::initializer_list<const TCHAR*> LimbNames)
    {
        FPhysicsControlSetUpdate Set; Set.SetName = Name;
        for (const TCHAR* L : LimbNames)
            if (Present.Contains(FName(L))) Set.Names.Add(FName(FString(Prefix) + L));
        if (Set.Names.Num()) Sets.Add(Set);
    };
    TArray<FPhysicsControlSetUpdate>& ControlSets = Target->AdditionalSets.ControlSetUpdates;
    AddSet(ControlSets, AnchorPelvis, TEXT("WorldSpace_"), {TEXT("Pelvis")});
    AddSet(ControlSets, AnchorFeet, TEXT("WorldSpace_"), {TEXT("FootLeft"), TEXT("FootRight")});
    AddSet(ControlSets, AnchorHands, TEXT("WorldSpace_"), {TEXT("HandLeft"), TEXT("HandRight")});
    AddSet(ControlSets, JointsSpine, TEXT("ParentSpace_"), {TEXT("Spine"), TEXT("Head")});
    AddSet(ControlSets, JointsArms, TEXT("ParentSpace_"), {TEXT("ArmLeft"), TEXT("ArmRight"), TEXT("HandLeft"), TEXT("HandRight")});
    AddSet(ControlSets, JointsLegs, TEXT("ParentSpace_"), {TEXT("LegLeft"), TEXT("LegRight"), TEXT("FootLeft"), TEXT("FootRight")});
    AddSet(Target->AdditionalSets.ModifierSetUpdates, FeetBodies, TEXT(""), {TEXT("FootLeft"), TEXT("FootRight")});
    FillProfiles(Target);
    return Target;
}

// Each phase's profile, in order: every world-space control at the Body strength, then the anchors over it; every
// joint at the Joints strength, then the spine, arms and legs scaled; gravity and world collision on every body,
// then the feet's collision.
void URidePhysicalRider::FillProfiles(UPhysicsControlAsset* Target) const
{
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    Target->Profiles.Reset();
    for (const ERidePhysicalPhase P : Phases)
    {
        const FRidePhysicalProfile& F = S->Profile(P);
        FPhysicsControlControlAndModifierUpdates& U = Target->Profiles.Add(PhaseName(P));
        U.ControlUpdates.Emplace(WorldSet, Strengths(F.Body, F.Body, F.AnchorDamping));
        U.ControlUpdates.Emplace(AnchorPelvis, Strengths(F.Pelvis, F.Pelvis, F.AnchorDamping));
        U.ControlUpdates.Emplace(AnchorFeet, Strengths(F.Feet, F.Feet, F.AnchorDamping));
        U.ControlUpdates.Emplace(AnchorHands, Strengths(F.Hands, F.Hands, F.AnchorDamping));
        U.ControlUpdates.Emplace(ParentSet, Strengths(0.f, F.Joints, F.JointDamping));
        U.ControlUpdates.Emplace(JointsSpine, Strengths(0.f, F.Joints * F.Spine, F.JointDamping));
        U.ControlUpdates.Emplace(JointsArms, Strengths(0.f, F.Joints * F.Arms, F.JointDamping));
        U.ControlUpdates.Emplace(JointsLegs, Strengths(0.f, F.Joints * F.Legs, F.JointDamping));
        FPhysicsControlModifierSparseData Body = Modifier();
        Body.bEnableGravityMultiplier = true; Body.GravityMultiplier = F.Gravity;
        Body.bEnableCollisionType = true;
        Body.CollisionType = F.bBodyTouchesWorld ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::QueryOnly;
        U.ModifierUpdates.Emplace(AllSet, Body);
        FPhysicsControlModifierSparseData Feet = Modifier();
        Feet.bEnableCollisionType = true; Feet.CollisionType = F.bFeetTouchWorld ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::QueryOnly;
        U.ModifierUpdates.Emplace(FeetBodies, Feet);
    }
}

void URidePhysicalRider::ReloadProfiles()
{
    if (!Control || !Asset) return;
    if (bOwnControlAsset) FillProfiles(Asset);
    const ERidePhysicalPhase Current = Phase;
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(Current);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: profiles reloaded (%s)"), *PhaseName(Current).ToString());
}

// ---------------------------------------------------------------------------------------------------------------
// Each frame.

void URidePhysicalRider::ApplyPhase(ERidePhysicalPhase NewPhase)
{
    if (!Control || NewPhase == Phase || NewPhase == ERidePhysicalPhase::Off) return;
    Phase = NewPhase;
    Control->InvokeControlProfile(PhaseName(NewPhase));
}

void URidePhysicalRider::SetSimulating(bool bSimulate, const FVector* Velocity)
{
    if (!Control || bSimulate == bSimulating) return;
    bSimulating = bSimulate;
    Control->SetControlsInSetEnabled(AllSet, bSimulate);
    Control->SetBodyModifiersInSetMovementType(AllSet, bSimulate ? EPhysicsMovementType::Simulated : EPhysicsMovementType::Kinematic);
    if (!bSimulate) return;
    if (Velocity)
    {
        // Switched now so the bodies leave with this velocity; the body modifiers keep them simulating.
        // From the pelvis down: a kinematic root body stays with the animation.
        if (PelvisBone.IsNone()) Mesh->SetAllBodiesSimulatePhysics(true);
        else Mesh->SetAllBodiesBelowSimulatePhysics(PelvisBone, true, true);
        Mesh->SetAllPhysicsLinearVelocity(*Velocity);
        Mesh->WakeAllRigidBodies();
    }
    // Otherwise they start where the animation is (they were following it, unseen), at the rider's speed. Physics
    // Control's own reset would give each body its cached velocity, which a placement in the same frame makes the
    // jump's.
    else ResetToAnimation();
}

void URidePhysicalRider::ApplyWeight()
{
    if (!Control || Weight == AppliedWeight) return;
    AppliedWeight = Weight;
    Control->SetBodyModifiersInSetPhysicsBlendWeight(AllSet, Weight);
}

void URidePhysicalRider::ApplyBailMaterial(bool bBailing)
{
    if (!Mesh || bBailing == bBailMaterial) return;
    bBailMaterial = bBailing;
    if (!bBailing) { Mesh->SetPhysMaterialOverride(SavedMaterial); SavedMaterial = nullptr; return; }
    const float Friction = GetDefault<URidePhysicalSettings>()->BailFriction;
    // Chaos copies a material's values when it first meets it: a changed setting takes a new one.
    if (!BailMaterial || BailMaterial->Friction != Friction)
    {
        BailMaterial = NewObject<UPhysicalMaterial>(this, NAME_None, RF_Transient);
        BailMaterial->Friction = Friction;
        BailMaterial->bOverrideFrictionCombineMode = true;
        BailMaterial->FrictionCombineMode = EFrictionCombineMode::Min;
    }
    SavedMaterial = Mesh->BodyInstance.GetPhysMaterialOverride();
    Mesh->SetPhysMaterialOverride(BailMaterial);
}

void URidePhysicalRider::ApplyBailDrag(bool bSliding)
{
    if (!Mesh || bSliding == bBailDrag) return;
    bBailDrag = bSliding;
    const float Drag = bSliding ? GetDefault<URidePhysicalSettings>()->BailDrag : 0.f;
    for (FBodyInstance* Body : Mesh->Bodies)
    {
        const UBodySetup* Setup = Body ? Body->GetBodySetup() : nullptr;
        if (!Setup) continue;
        Body->LinearDamping = Setup->DefaultInstance.LinearDamping + Drag;
        Body->UpdateDampingProperties();
    }
}

// Riding: the rider's constraint profile, with limits that widen to the animation. Bailing: the bail profile and the
// limits as authored. The built asset has one set of limits for both. Physics Control reads the response from the
// live constraints each update, so it is set after the profile (which would copy the template's over it).
void URidePhysicalRider::ApplyJointLimits(bool bRidingProfile, bool bWiden)
{
    if (!Mesh) return;
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    if (!bBuiltAsset) Mesh->SetConstraintProfileForAll(bRidingProfile ? S->RideConstraintProfile : S->BailConstraintProfile, true);
    const EAngularDriveLimitViolationResponse Response = bWiden && S->bWidenLimitsWhileRiding
        ? EAngularDriveLimitViolationResponse::WidenLimits : EAngularDriveLimitViolationResponse::None;
    for (FConstraintInstance* C : Mesh->Constraints)
        if (C) C->ProfileInstance.AngularDrive.LimitViolationResponse = Response;
}

void URidePhysicalRider::BlendIn(float Seconds)
{
    if (!Control || bBail) return;
    bEndWhenOut = false;
    GetUpTime = -1; GetUpWait = -1;
    SetSimulating(true);
    WeightTarget = 1.f;
    WeightRate = 1.f / FMath::Max(Seconds, .01f);
    if (Seconds <= 0.f) { Weight = 1.f; ApplyWeight(); }
}

void URidePhysicalRider::BlendOut(float Seconds)
{
    if (!Control) return;
    WeightTarget = 0.f;
    WeightRate = 1.f / FMath::Max(Seconds, .01f);
    if (Seconds <= 0.f) { Weight = 0.f; ApplyWeight(); SetSimulating(false); if (bEndWhenOut) End(); }
}

void URidePhysicalRider::Update(float Dt, ERidePhysicalPhase NewPhase)
{
    if (!Control || !Mesh) return;
    DrivenFrame = GFrameCounter;
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    // A touchdown holds the Landing profile for a moment.
    if (NewPhase == ERidePhysicalPhase::Riding || NewPhase == ERidePhysicalPhase::Manual)
    {
        if (Phase == ERidePhysicalPhase::Air) LandingLeft = S->LandingTime;
        if (LandingLeft > 0.f) { LandingLeft -= Dt; NewPhase = ERidePhysicalPhase::Landing; }
    }
    else LandingLeft = 0.f;
    // The bail and the get-up choose their own profiles.
    if (!bBail && GetUpTime < 0.f) ApplyPhase(NewPhase);

    // A get-up hands the bodies over once the animation shows the snapshot.
    if (GetUpWait >= 0 && (AnimationShowsSnapshot() || ++GetUpWait > MaxGetUpWait))
    {
        HandOverGetUp();
        if (bEndWhenOut) { End(); return; }
    }

    if (Weight != WeightTarget)
    {
        Weight = FMath::FInterpConstantTo(Weight, WeightTarget, Dt, WeightRate);
        ApplyWeight();
        if (Weight <= 0.f && WeightTarget <= 0.f)
        {
            SetSimulating(false);
            if (bEndWhenOut) { End(); return; }
        }
    }

    AdvanceGetUp(Dt);

    const FVector MeshAt = Mesh->GetComponentLocation();
    const bool bPlaced = FVector::DistSquared(MeshAt, LastMeshLocation) > FMath::Square(PlacedDistance);
    const FVector RiderVelocity = Rider->GetVelocity();
    const FVector Launch = RiderVelocity - LastRiderVelocity;
    LastMeshLocation = MeshAt; LastRiderVelocity = RiderVelocity;
    if (!bSimulating || GetUpWait >= 0) PelvisError = WorstError = FootError = 0.f;
    else if (bPlaced && !bBail)
    {
        // Placed: the bodies go with the animation rather than being pulled there by the controls.
        ResetToAnimation();
        PlacedFrames = PlacedLaunchFrames;
        PelvisError = WorstError = FootError = 0.f;
    }
    else
    {
        // Set moving just after a placement: the body leaves with the rider.
        if (PlacedFrames > 0 && !bBail)
        {
            --PlacedFrames;
            if (Launch.SizeSquared() > FMath::Square(LaunchStep)) Mesh->SetAllPhysicsLinearVelocity(Launch, true);
        }
        const FVector Centre = GetPelvisLocation();
        if (FVector::Dist(Centre, PhysicalCentre) > PhysicalFollow) MakeWorldPhysical(Centre);
        // A body far from where the animation wants it while riding has been carried off by something it could not
        // resolve (or the rider was moved without a teleport): back onto Physics Control's copy of the animation.
        if (Measure() && !bBail && PelvisError > 300.f)
        {
            UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: body %.0f cm from the animation, reset"), PelvisError);
            Control->ResetBodyModifiersInSetToCachedBoneTransforms(AllSet, EResetToCachedTargetBehavior::ResetDuringUpdateControls);
        }
    }
}

void URidePhysicalRider::ResetToAnimation()
{
    // The skeletal mesh's own teleport: every body goes to its bone in the mesh's last pose, carried to where the
    // component is now, as a moved component with ETeleportType::TeleportPhysics does (with the bodies seen, that pose
    // is theirs: they move with the component). Physics Control's reset to its cached targets would instead give
    // each body the velocity of the jump (the placement's distance over one frame). The bodies leave at the rider's
    // speed.
    Mesh->UpdateKinematicBonesToAnim(Mesh->GetComponentSpaceTransforms(), ETeleportType::TeleportPhysics, false, EAllowKinematicDeferral::DisallowDeferral);
    Mesh->SetAllPhysicsLinearVelocity(Rider->GetVelocity());
    Mesh->SetAllPhysicsAngularVelocityInRadians(FVector::ZeroVector);
}

void URidePhysicalRider::AdvanceGetUp(float Dt)
{
    // The blend starts when the bodies are handed over.
    if (GetUpTime < 0.f || GetUpWait >= 0) return;
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    GetUpTime += Dt;
    if (GetUpTime < S->GetUpBlend) return;
    GetUpTime = -1.f;
    UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: up (%s)"), GetUpExit == ERideGetUpExit::Board ? TEXT("board") : TEXT("on foot"));
    if (Control && GetUpExit == ERideGetUpExit::Board && IsWanted()) BlendIn(S->MountBlend);
}

void URidePhysicalRider::Tick(float DeltaTime)
{
    // Ticks itself only when no ride drove it this frame: mount and dismount blends on foot, and a get-up that
    // outlives the ride.
    if (DrivenFrame == GFrameCounter) return;
    if (Control) Update(DeltaTime, ERidePhysicalPhase::OnFoot);
    else AdvanceGetUp(DeltaTime);
}

ETickableTickType URidePhysicalRider::GetTickableTickType() const
{
    return HasAnyFlags(RF_ClassDefaultObject) ? ETickableTickType::Never : ETickableTickType::Conditional;
}

TStatId URidePhysicalRider::GetStatId() const { RETURN_QUICK_DECLARE_CYCLE_STAT(URidePhysicalRider, STATGROUP_Tickables); }
UWorld* URidePhysicalRider::GetTickableGameObjectWorld() const { return TickWorld.Get(); }

bool URidePhysicalRider::Measure()
{
    PelvisError = WorstError = FootError = 0.f;
    // Physics Control has no copy of the pose until its first update after Begin, and none for a frame in which the
    // mesh had no transforms; its lookups then answer the world's origin.
    if (GFrameCounter < BeganFrame + 2) return false;
    if (!PelvisBone.IsNone() && Control->GetCachedBonePosition(Mesh, PelvisBone).IsZero()) return false;
    // In a bail the pose is measured where a root that follows the body would put it: carried as far as the ground
    // under the pelvis has gone since the bail began. The ride's root gets there some frames late (it follows the
    // body's ground through the session's interpolated step) and Physics Control's copy of the pose a frame later
    // still: measured where they are, a fall at 6 m/s reads 25 cm off the clip from its third frame.
    FVector Shift = FVector::ZeroVector;
    if (bBail)
    {
        const FVector CachedRoot = RootBone.IsNone() ? FVector::ZeroVector : Control->GetCachedBonePosition(Mesh, RootBone);
        Shift = CachedRoot.IsZero() || BailRoot.IsZero() ? BodyGround - LastBodyGround : BailRoot + (BodyGround - BailFloor) - CachedRoot;
    }
    int32 Feet = 0;
    for (const FBodyInstance* Body : Mesh->Bodies)
    {
        if (!Body || !Body->IsInstanceSimulatingPhysics() || !Body->BodySetup.IsValid()) continue;
        const FName B = Body->BodySetup->BoneName;
        const float Error = float(FVector::Dist(Body->GetUnrealWorldTransform().GetLocation(), Control->GetCachedBonePosition(Mesh, B) + Shift));
        WorstError = FMath::Max(WorstError, Error);
        if (B == PelvisBone) PelvisError = Error;
        if (B == FootBones[0] || B == FootBones[1]) { FootError += Error; ++Feet; }
    }
    if (Feet) FootError /= Feet;
    return true;
}

// ---------------------------------------------------------------------------------------------------------------
// Body queries.

FVector URidePhysicalRider::GetPelvisLocation() const
{
    if (!Mesh) return FVector::ZeroVector;
    if (const FBodyInstance* Body = Mesh->GetBodyInstance(PelvisBone)) return Body->GetUnrealWorldTransform().GetLocation();
    return Mesh->GetBoneLocation(PelvisBone);
}

float URidePhysicalRider::GetBodyYaw() const
{
    if (!Mesh) return 0.f;
    const FVector Flat = (Mesh->GetBoneLocation(HeadBone) - Mesh->GetBoneLocation(PelvisBone)).GetSafeNormal2D();
    return Flat.IsNearlyZero() ? float(Mesh->GetComponentRotation().Yaw) : float(Flat.Rotation().Yaw);
}

// The body's front is right x up (Unreal's axes are left-handed: Y right, Z up, X forward).
bool URidePhysicalRider::IsFaceUp() const
{
    if (!Mesh) return true;
    const FVector Up = Mesh->GetBoneLocation(HeadBone) - Mesh->GetBoneLocation(PelvisBone);
    const FVector Right = Mesh->GetBoneLocation(ThighBones[1]) - Mesh->GetBoneLocation(ThighBones[0]);
    return FVector::CrossProduct(Right, Up).Z > 0.;
}

FVector URidePhysicalRider::TraceGround(const FVector& At) const
{
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBodyGround), false, Rider);
    if (LooseBoard) Params.AddIgnoredComponent(LooseBoard.Get());
    if (Rider && Rider->GetWorld()->LineTraceSingleByChannel(Hit, At + FVector(0, 0, 40.f), At - FVector(0, 0, 250.f), ECC_Pawn, Params))
        return Hit.ImpactPoint;
    return At - FVector(0, 0, 15.f);
}

void URidePhysicalRider::Dump() const
{
    if (!Mesh || !Control || !Rider) { UE_LOG(LogTemp, Display, TEXT("SKATE ride physical dump: no rider")); return; }
    const FReferenceSkeleton& Ref = Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    const TArray<FTransform>& Local = Mesh->GetBoneSpaceTransforms();
    UE_LOG(LogTemp, Display, TEXT("SKATE ride physical dump: mesh at %s scale %s; root %s, reference scale %s, pose scale %s"),
        *Mesh->GetComponentLocation().ToString(), *Mesh->GetComponentScale().ToString(), *Ref.GetBoneName(0).ToString(),
        *Ref.GetRefBonePose()[0].GetScale3D().ToString(), Local.Num() ? *Local[0].GetScale3D().ToString() : TEXT("-"));
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideDump), false);
    Params.AddIgnoredComponent(Mesh.Get());
    for (const FBodyInstance* Body : Mesh->Bodies)
    {
        if (!Body || !Body->BodySetup.IsValid()) continue;
        const FName B = Body->BodySetup->BoneName;
        const FBox Box = Body->GetBodyBounds();
        FString Touching;
        if (Body->IsInstanceSimulatingPhysics() && Box.IsValid)
        {
            TArray<FOverlapResult> Hits;
            Rider->GetWorld()->OverlapMultiByObjectType(Hits, Box.GetCenter(), FQuat::Identity,
                FCollisionObjectQueryParams(FCollisionObjectQueryParams::AllObjects), FCollisionShape::MakeBox(Box.GetExtent()), Params);
            for (const FOverlapResult& H : Hits)
                if (const UPrimitiveComponent* C = H.GetComponent(); C && CollisionEnabledHasPhysics(C->GetCollisionEnabled()))
                    Touching += FString::Printf(TEXT(" %s.%s(type %d)"), *GetNameSafe(C->GetOwner()), *C->GetName(), int32(C->GetCollisionObjectType()));
        }
        UE_LOG(LogTemp, Display, TEXT("SKATE ride physical dump: %s sim=%d scale=%s body=%s bone=%s target=%s bounds=%s..%s near:%s"),
            *B.ToString(), Body->IsInstanceSimulatingPhysics() ? 1 : 0, *Body->Scale3D.ToString(),
            *Body->GetUnrealWorldTransform().GetLocation().ToString(), *Mesh->GetBoneLocation(B).ToString(),
            *Control->GetCachedBonePosition(Mesh, B).ToString(), *Box.Min.ToString(), *Box.Max.ToString(), *Touching);
    }
}

FString URidePhysicalRider::Describe() const
{
    if (!Control) return TEXT("phys=off");
    const FVector Hips = GetPelvisLocation();
    return FString::Printf(TEXT("phys=%s sim=%d w=%.2f pelvis_err=%.1f foot_err=%.1f worst_err=%.1f hips=%.1f,%.1f,%.1f lie=%.1f drag=%d getup=%.2f bail_kind=%s bodies=%d pa=%s frame=%s"),
        *PhaseName(Phase).ToString(), bSimulating, Weight, PelvisError, FootError, WorstError, Hips.X, Hips.Y, Hips.Z, bBail ? HipsAboveGround : -1.f, int(bBailDrag), GetGetUpAlpha(),
        !bBailOffered ? TEXT("none") : LastBailKind == ERideBailKind::RunOut ? TEXT("runout") : TEXT("fall"),
        Mesh ? Mesh->Bodies.Num() : 0, bBuiltAsset ? TEXT("contract") : TEXT("rider"), bBoardFrame ? TEXT("board") : TEXT("world"));
}

// ---------------------------------------------------------------------------------------------------------------
// Bails.

ERideBailKind URidePhysicalRider::ClassifyBail(const FVector& BoardVelocity, const FVector& BoardSpin) const
{
    if (!Mesh) return ERideBailKind::Fall;
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    const FVector Hips = Mesh->GetBoneLocation(PelvisBone);
    const FVector Trunk = (Mesh->GetBoneLocation(HeadBone) - Hips).GetSafeNormal();
    const float Tilt = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(Trunk.Z), -1.f, 1.f)));
    const bool bFeetBelow = FMath::Max(Mesh->GetBoneLocation(FootBones[0]).Z, Mesh->GetBoneLocation(FootBones[1]).Z) < Hips.Z - 20.;
    const bool bRunOut = Tilt < S->RunOutTilt && bFeetBelow && BoardVelocity.Size2D() < S->RunOutSpeed &&
        FMath::Abs(BoardVelocity.Z) < S->RunOutImpact && FMath::RadiansToDegrees(BoardSpin.Size()) < S->RunOutSpin;
    return bRunOut ? ERideBailKind::RunOut : ERideBailKind::Fall;
}

bool URidePhysicalRider::OfferBail(const FVector& BoardVelocity, const FVector& BoardSpin)
{
    bBailOffered = true;
    LastBailKind = ClassifyBail(BoardVelocity, BoardSpin);
    const bool bTaken = OnBailStart.IsBound() && OnBailStart.Execute(LastBailKind);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride bail is a %s%s"), LastBailKind == ERideBailKind::RunOut ? TEXT("run-out") : TEXT("fall"),
        bTaken ? TEXT(", taken on foot") : TEXT(""));
    return bTaken;
}

bool URidePhysicalRider::StartBail(const FVector& Velocity, const FVector& BoardSpin, const FTransform& BoardTransform, float Scale)
{
    if (!Control || !Mesh || bBail) return false;
    UWorld* World = Rider->GetWorld();
    // The loose board: a box the size of the board, thrown with its velocity and spin; the board's meshes follow it.
    BoardScale = Scale;
    if (LooseBoard) DropLooseBoard();
    LooseBoard = NewObject<UBoxComponent>(Rider, NAME_None, RF_Transient);
    LooseBoard->SetBoxExtent(LooseBoardExtent * Scale);
    LooseBoard->SetCollisionProfileName(TEXT("PhysicsActor"));
    LooseBoard->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
    // It starts inside the rider's feet: the two pass through each other rather than push apart.
    LooseBoard->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Ignore);
    LooseBoard->SetHiddenInGame(true);
    LooseBoard->SetUsingAbsoluteLocation(true); LooseBoard->SetUsingAbsoluteRotation(true); LooseBoard->SetUsingAbsoluteScale(true);
    LooseBoard->RegisterComponent();
    const FQuat Deck = BoardTransform.GetRotation();
    LooseBoard->SetWorldLocationAndRotation(BoardTransform.GetLocation() - Deck.GetUpVector() * LooseBoardDrop * Scale, Deck);
    LooseBoard->SetMassOverrideInKg(NAME_None, 3.5f, true);
    LooseBoard->SetLinearDamping(.15f);
    LooseBoard->SetAngularDamping(.4f);
    LooseBoard->SetSimulatePhysics(true);
    LooseBoard->SetPhysicsLinearVelocity(Velocity * .85f + FVector(0, 0, 90.f));
    LooseBoard->SetPhysicsAngularVelocityInRadians(BoardSpin +
        Deck.GetForwardVector() * FMath::FRandRange(-7.f, 7.f) + Deck.GetRightVector() * FMath::FRandRange(-4.f, 4.f));

    // The body: an active ragdoll keeps the momentum its bodies have; an animated one leaves with the board's.
    const bool bWasSimulating = bSimulating;
    if (!bSimulating)
    {
        const FVector Thrown = Velocity * .9f + FVector(0, 0, 60.f);
        SetSimulating(true, &Thrown);
    }
    else
    {
        Mesh->WakeAllRigidBodies();
        // A body moving much faster than the board was flung by something the riding could not resolve: the bail
        // starts from the board's momentum instead.
        const FBodyInstance* Pelvis = Mesh->GetBodyInstance(PelvisBone);
        if (Pelvis && Pelvis->GetUnrealWorldVelocity().Size() > Velocity.Size() + 1000.f)
        {
            Mesh->SetAllPhysicsLinearVelocity(Velocity * .9f + FVector(0, 0, 60.f));
            Mesh->SetAllPhysicsAngularVelocityInRadians(FVector::ZeroVector);
        }
    }
    bEndWhenOut = false; GetUpTime = -1.f; GetUpWait = -1;
    Weight = WeightTarget = 1.f; ApplyWeight();
    bBail = true; BailTime = 0.f; Quiet = 0.f;
    // Limp at once: the Bail profile lets go of every anchor and turns gravity on, and the joints keep only its tone
    // toward the clip (their limits as authored). The anchors hold the bodies in the frame of the kinematic root body,
    // and in a bail the ride stops the root on the bail's frame, then carries it to the ground under the body a frame
    // late (on a quarter, from the board on the wall to whatever lies below the hips): held to that frame even for a
    // moment, the body is braked to a stop or flung.
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(ERidePhysicalPhase::Bail);
    ApplyJointLimits(false, false);
    ApplyBailMaterial(true);

    BailStart = GetPelvisLocation();
    BailLimit = FMath::Max(2500.f, float(Velocity.Size()) * 1.5f + 800.f);
    // The highest a thrown body can rise (out of a quarter pipe at speed), with a margin.
    BailRise = FMath::Max(400.f, FMath::Square(FMath::Max(0.f, float(Velocity.Z))) / (2.f * 980.f) + 200.f);
    {
        // The floor the body starts over: a body found well below it, under a floor, has fallen through the world.
        FHitResult Hit;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideFloor), false, Rider);
        Params.AddIgnoredComponent(LooseBoard.Get());
        BailFloor = World->LineTraceSingleByChannel(Hit, BailStart + FVector(0, 0, 50.f), BailStart - FVector(0, 0, 300.f), ECC_Pawn, Params)
            ? FVector(Hit.ImpactPoint) : BailStart - FVector(0, 0, 100.f);
    }
    BodyGround = LastBodyGround = BailFloor;
    BailRoot = RootBone.IsNone() ? FVector::ZeroVector : Control->GetCachedBonePosition(Mesh, RootBone);
    HipsAboveGround = float(BailStart.Z - BailFloor.Z);
    MakeWorldPhysical(BailStart);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride ragdoll (%s physics asset, %d bodies, %s) at %.0f cm/s"),
        bBuiltAsset ? TEXT("contract") : TEXT("rider's"), Mesh->Bodies.Num(), bWasSimulating ? TEXT("active") : TEXT("from animation"), Velocity.Size());
    return true;
}

ERideBodyState URidePhysicalRider::UpdateBail(float Dt, float SettleTime)
{
    if (!bBail || !Mesh || !Control) return ERideBodyState::Unstable;
    BailTime += Dt;
    const FVector Hips = GetPelvisLocation();
    const FBodyInstance* Pelvis = Mesh->GetBodyInstance(PelvisBone);
    const float Speed = Pelvis ? float(Pelvis->GetUnrealWorldVelocity().Size()) : 0.f;
    Quiet = Speed < 40.f ? Quiet + Dt : 0.f;
    // A body that gains speed or height it was never given has met something it cannot resolve.
    bool bThrough = false;
    if (Hips.Z < BailFloor.Z - 120.f)
    {
        FHitResult Above;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideThrough), false, Rider);
        bThrough = Rider->GetWorld()->LineTraceSingleByChannel(Above, Hips, Hips + FVector(0, 0, 400.f), ECC_Pawn, Params) && Above.ImpactNormal.Z < -.5f;
    }
    if (Speed > BailLimit || Hips.Z > BailStart.Z + BailRise || bThrough || Hips.ContainsNaN())
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride ragdoll unstable (%.0f cm/s, %.0f cm from the start%s)"),
            Speed, Hips.Z - BailStart.Z, bThrough ? TEXT(", under the floor") : TEXT(""));
        return ERideBodyState::Unstable;
    }
    LastBodyGround = BodyGround;
    BodyGround = TraceGround(Hips);
    {
        FHitResult Below;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideHipsGround), false, Rider);
        if (LooseBoard) Params.AddIgnoredComponent(LooseBoard.Get());
        HipsAboveGround = Rider->GetWorld()->LineTraceSingleByChannel(Below, Hips + FVector(0, 0, 10.f), Hips - FVector(0, 0, HipsGroundRange), ECC_Pawn, Params)
            ? float(Hips.Z - Below.ImpactPoint.Z) : -1.f;
    }
    // Down near the ground the body slides, and drags (BailDrag): a body still in the air falls and flies freely.
    ApplyBailDrag(HipsAboveGround >= 0.f && HipsAboveGround < SlideHeight);
    return BailTime > 1.6f && (Quiet > .4f || BailTime > SettleTime + 2.f) ? ERideBodyState::Settled : ERideBodyState::Tumbling;
}

void URidePhysicalRider::Abort()
{
    if (!Control) return;
    DropLooseBoard();
    bBail = false; GetUpTime = -1.f; GetUpWait = -1;
    Weight = WeightTarget = 0.f; ApplyWeight();
    SetSimulating(false);
    ApplyBailMaterial(false);
    ApplyBailDrag(false);
    ApplyJointLimits(true, true);
    Phase = ERidePhysicalPhase::Off;
}

// ---------------------------------------------------------------------------------------------------------------
// Get-up.

void URidePhysicalRider::StartGetUp(ERideGetUpExit Exit)
{
    if (!Control || !Mesh) return;
    // The fallen pose in world space, every bone (those without bodies sit on their simulated parents).
    const TArray<FTransform>& Pose = Mesh->GetComponentSpaceTransforms();
    const FTransform Component = Mesh->GetComponentTransform();
    SnapshotWorld.SetNum(Pose.Num());
    for (int32 I = 0; I < Pose.Num(); ++I) SnapshotWorld[I] = Pose[I] * Component;
    SnapshotMesh = Mesh->GetSkeletalMeshAsset();
    SnapshotComponent = Mesh;
    // From here the pose is the blend, held at the snapshot until the bodies are handed over. The mesh shows the pose
    // the ride hands it a frame late, and Physics Control's copy of it (the kinematic bodies' targets) a frame later
    // still: weight 0 now would show the clip's pose for a frame, and the bodies would jump to it the next. So the
    // bodies stay seen, lying where they are, until Physics Control's copy shows the snapshot (Update).
    bBail = false;
    GetUpExit = Exit;
    GetUpTime = 0.f;
    GetUpWait = bSimulating && Weight > 0.f ? 0 : -1;
    if (GetUpWait < 0) HandOverGetUp();
    UE_LOG(LogTemp, Display, TEXT("SKATE ride get up after %.1f s, %s, %s"), BailTime, IsFaceUp() ? TEXT("face up") : TEXT("face down"),
        Exit == ERideGetUpExit::Board ? TEXT("onto the board") : TEXT("on foot"));
}

bool URidePhysicalRider::AnimationShowsSnapshot() const
{
    if (!Control || !Mesh || SnapshotComponent.Get() != Mesh) return false;
    for (const FName B : {PelvisBone, HeadBone})
    {
        const int32 I = B.IsNone() ? INDEX_NONE : Mesh->GetBoneIndex(B);
        if (!SnapshotWorld.IsValidIndex(I)) continue;
        const FVector Shown = Control->GetCachedBonePosition(Mesh, B);
        if (Shown.IsZero() || FVector::DistSquared(Shown, SnapshotWorld[I].GetLocation()) > FMath::Square(SnapshotShown)) return false;
    }
    return true;
}

void URidePhysicalRider::HandOverGetUp()
{
    if (GetUpWait >= 0) UE_LOG(LogTemp, Display, TEXT("SKATE ride get-up: bodies handed to the animation after %d frames"), GetUpWait);
    GetUpWait = -1;
    Weight = WeightTarget = 0.f; ApplyWeight();
    SetSimulating(false);
    ApplyBailMaterial(false);
    ApplyBailDrag(false);
    ApplyJointLimits(true, true);
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(ERidePhysicalPhase::GetUp);
}

float URidePhysicalRider::GetGetUpAlpha() const
{
    return GetUpTime >= 0.f ? FMath::Clamp(GetUpTime / FMath::Max(.05f, GetDefault<URidePhysicalSettings>()->GetUpBlend), 0.f, 1.f) : 1.f;
}

// The snapshot as a local pose of the current component: bones under the root keep their place in the world at
// alpha 0, the root itself is the pose's, so the body moves straight from where it lay to the clip.
bool URidePhysicalRider::BlendFromSnapshot(TArray<FTransform>& LocalPose, float Alpha) const
{
    const USkeletalMeshComponent* Target = SnapshotComponent.Get();
    if (Alpha >= 1.f || !Target || !SnapshotMesh.IsValid() || Target->GetSkeletalMeshAsset() != SnapshotMesh.Get()) return false;
    const FReferenceSkeleton& Ref = SnapshotMesh->GetRefSkeleton();
    if (LocalPose.Num() != Ref.GetNum() || SnapshotWorld.Num() != Ref.GetNum()) return false;
    const FTransform Component = Target->GetComponentTransform();
    const float A = FMath::SmoothStep(0.f, 1.f, FMath::Clamp(Alpha, 0.f, 1.f));
    // The pose's root in the world, which the root's children are measured from.
    for (int32 I = 1; I < Ref.GetNum(); ++I)
    {
        const int32 Parent = Ref.GetParentIndex(I);
        if (Parent < 0) continue;
        const FTransform ParentWorld = Parent == 0 ? LocalPose[0] * Component : SnapshotWorld[Parent];
        const FTransform Snap = SnapshotWorld[I].GetRelativeTransform(ParentWorld);
        FTransform& Out = LocalPose[I];
        Out.SetTranslation(FMath::Lerp(Snap.GetTranslation(), Out.GetTranslation(), A));
        Out.SetRotation(FQuat::Slerp(Snap.GetRotation(), Out.GetRotation(), A).GetNormalized());
    }
    return true;
}

// ---------------------------------------------------------------------------------------------------------------
// The loose board.

FTransform URidePhysicalRider::GetLooseBoardDeck() const
{
    if (!LooseBoard) return FTransform::Identity;
    const FTransform Body = LooseBoard->GetComponentTransform();
    return FTransform(Body.GetRotation(), Body.GetLocation() + Body.GetRotation().GetUpVector() * LooseBoardDrop * BoardScale, FVector(BoardScale));
}

UBoxComponent* URidePhysicalRider::TakeLooseBoard()
{
    UBoxComponent* Board = LooseBoard;
    LooseBoard = nullptr;
    TakenBoard = Board;
    return Board;
}

void URidePhysicalRider::DropLooseBoard()
{
    if (!LooseBoard) return;
    LooseBoard->SetSimulatePhysics(false);
    LooseBoard->DestroyComponent();
    LooseBoard = nullptr;
}

// ---------------------------------------------------------------------------------------------------------------
// The world around the body. Surfaces that only answer queries (the character walks on those) become physical near
// the body so its bodies and the loose board can touch them, and go back when the body has left.

void URidePhysicalRider::MakeWorldPhysical(const FVector& Centre)
{
    if (!Rider) return;
    const float Radius = GetDefault<URidePhysicalSettings>()->WorldRadius;
    PhysicalCentre = Centre;
    // Let go of the surfaces far behind, unless a taken board still lies near them.
    const UPrimitiveComponent* Board = TakenBoard.Get();
    for (int32 I = MadePhysical.Num() - 1; I >= 0; --I)
    {
        UPrimitiveComponent* C = MadePhysical[I].Get();
        if (!C) { MadePhysical.RemoveAtSwap(I); continue; }
        const FBoxSphereBounds Bounds = C->Bounds;
        const double Away = FMath::Max(0., FVector::Dist(Bounds.Origin, Centre) - Bounds.SphereRadius);
        const double FromBoard = Board ? FMath::Max(0., FVector::Dist(Bounds.Origin, Board->GetComponentLocation()) - Bounds.SphereRadius) : 1e30;
        if (Away > Radius * 2. && FromBoard > Radius) { C->SetCollisionEnabled(ECollisionEnabled::QueryOnly); MadePhysical.RemoveAtSwap(I); }
    }
    TArray<FOverlapResult> Hits;
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_WorldStatic); Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideWorld), false, Rider);
    Rider->GetWorld()->OverlapMultiByObjectType(Hits, Centre, FQuat::Identity, Objects, FCollisionShape::MakeSphere(Radius), Params);
    for (const FOverlapResult& Hit : Hits)
    {
        UPrimitiveComponent* C = Hit.GetComponent();
        if (!C || C == LooseBoard || C->GetCollisionEnabled() != ECollisionEnabled::QueryOnly) continue;
        if (C->GetCollisionResponseToChannel(ECC_PhysicsBody) != ECR_Block || C->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block) continue;
        if (const UInstancedStaticMeshComponent* Instanced = Cast<UInstancedStaticMeshComponent>(C); Instanced && Instanced->GetInstanceCount() > PhysicalMaxInstances) continue;
        C->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        MadePhysical.Add(C);
    }
}

void URidePhysicalRider::RestoreWorld()
{
    // A taken board keeps the ground it lies on.
    const UPrimitiveComponent* Board = TakenBoard.Get();
    const float Radius = GetDefault<URidePhysicalSettings>()->WorldRadius;
    for (int32 I = MadePhysical.Num() - 1; I >= 0; --I)
    {
        UPrimitiveComponent* C = MadePhysical[I].Get();
        if (!C) { MadePhysical.RemoveAtSwap(I); continue; }
        if (Board && Board->IsSimulatingPhysics() && FVector::Dist(C->Bounds.Origin, Board->GetComponentLocation()) - C->Bounds.SphereRadius < Radius) continue;
        C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        MadePhysical.RemoveAtSwap(I);
    }
    PhysicalCentre = FVector(1e30);
}
