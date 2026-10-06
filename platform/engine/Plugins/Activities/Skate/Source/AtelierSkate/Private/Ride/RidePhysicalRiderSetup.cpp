// URidePhysicalRider setup (RidePhysicalRider.cpp): building the body from the physics asset.
#include "RidePhysicalRider.h"
#include "RidePhysicalRiderDetail.h"
#include "SkateRider.h"
#include "RideClipPlayer.h"
#include "PhysicsControlComponent.h"
#include "PhysicsControlAsset.h"
#include "PhysicsControlRecord.h"
#include "Components/BoxComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Algo/Find.h"
#include "Chaos/ChaosEngineInterface.h"
#include "Physics/Experimental/PhysInterface_Chaos.h"
#include "PBDRigidsSolver.h"
#include "Chaos/Collision/CollisionConstraintFlags.h"
#include "PhysicsProxy/SingleParticlePhysicsProxy.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/PhysicsConstraintTemplate.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkeletalMeshRenderData.h"

using namespace RidePhysicalRiderDetail;

// ---------------------------------------------------------------------------------------------------------------
// Setup.

bool URidePhysicalRider::IsWanted() { return CVarRidePhysical.GetValueOnGameThread() != 0; }

FName URidePhysicalRider::Bone(const TCHAR* Contract) const
{
    const FName B = Api ? Api->GetSkateBone(FName(Contract)) : FName(Contract);
    const USkeletalMesh* Skeletal = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
    return !B.IsNone() && Skeletal && Skeletal->GetRefSkeleton().FindBoneIndex(B) != INDEX_NONE ? B : NAME_None;
}

void URidePhysicsControl::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    USkeletalMeshComponent* M = Posed.Get();
    if (TickType == LEVELTICK_All && M && M->GetSkeletalMeshAsset())
    {
        // What Physics Control's cache reads next (after the same wait for the mesh's evaluation).
        M->HandleExistingParallelEvaluationTask(true, true);
        if (M->GetEditableComponentSpaceTransforms().IsEmpty())
        {
            SkippedTime += DeltaTime;
            if (++Skipped <= 20)
                UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: no pose for Physics Control at frame %llu, its update skipped (%d)"),
                    GFrameCounter, Skipped);
            return;
        }
    }
    // A skipped frame's time goes into the next update, whose pose has moved over both frames.
    Super::TickComponent(DeltaTime + SkippedTime, TickType, ThisTickFunction);
    SkippedTime = 0;
    if (TickType == LEVELTICK_All) UpdatedFrame = GFrameCounter;
    // Its targets must reach the bodies before the physics step, or every body trails the board by a frame (RIDE.md,
    // tick order). A component the mesh waits on, ticking in a later group, carries the mesh and this after it.
    static bool bWarnedLate = false;
    if (TickType == LEVELTICK_All && ThisTickFunction && ThisTickFunction->GetActualTickGroup() > TG_PrePhysics && !bWarnedLate)
    {
        bWarnedLate = true;
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: Physics Control ticks after the physics step (group %d, mesh %d): the rider trails the board by a frame; whatever the mesh waits on must tick in TG_PrePhysics"),
            int32(ThisTickFunction->GetActualTickGroup()), M ? int32(M->PrimaryComponentTick.GetActualTickGroup()) : -1);
    }
}

void URidePhysicsControl::ForgetWidenedLimits(const USkeletalMeshComponent* SkeletalMesh)
{
    for (TPair<FName, FPhysicsControlRecord>& Record : ControlRecords)
        if (Record.Value.ChildComponent.Get() == SkeletalMesh) Record.Value.bJointLimitsWidened = false;
}

FRideJointEnvelope FRideJointEnvelope::Of(const FConstraintInstance& C)
{
    FRideJointEnvelope E;
    E.Frame1 = C.GetRefFrame(EConstraintFrame::Frame1);
    E.Frame2 = C.GetRefFrame(EConstraintFrame::Frame2);
    E.Swing1Motion = C.GetAngularSwing1Motion(); E.Swing2Motion = C.GetAngularSwing2Motion(); E.TwistMotion = C.GetAngularTwistMotion();
    E.Swing1 = C.GetAngularSwing1Limit(); E.Swing2 = C.GetAngularSwing2Limit(); E.Twist = C.GetAngularTwistLimit();
    const FConeConstraint& Cone = C.ProfileInstance.ConeLimit;
    const FTwistConstraint& Twist = C.ProfileInstance.TwistLimit;
    E.bSoftSwing = Cone.bSoftConstraint; E.SwingStiffness = Cone.Stiffness; E.SwingDamping = Cone.Damping;
    E.bSoftTwist = Twist.bSoftConstraint; E.TwistStiffness = Twist.Stiffness; E.TwistDamping = Twist.Damping;
    E.AngularProjection = C.ProfileInstance.ProjectionAngularAlpha;
    return E;
}

void FRideJointEnvelope::ApplyTo(FConstraintInstance& C, const FVector& Limits) const
{
    // The envelope's rotations at the live frames' positions: InitArticulated scaled those by each body's adjusted
    // scale (SkeletalMeshComponentPhysics.cpp, ScalePosition), which the asset's frames don't carry, so the asset's
    // positions would pull the limbs in toward the pelvis.
    const FTransform Place1(Frame1.GetRotation(), C.GetRefFrame(EConstraintFrame::Frame1).GetTranslation());
    const FTransform Place2(Frame2.GetRotation(), C.GetRefFrame(EConstraintFrame::Frame2).GetTranslation());
    C.SetRefFrame(EConstraintFrame::Frame1, Place1);
    C.SetRefFrame(EConstraintFrame::Frame2, Place2);
    // SetRefFrame hands Chaos the frame as given, but the constraint was made with its frames' positions scaled by the
    // mesh's scale (FConstraintInstance::InitConstraint_AssumesLocked): a scaled rider's joints would move off their
    // bones. Chaos gets the scaled frames, as it did then.
    const float Scale = C.GetLastKnownScale();
    if (!FMath::IsNearlyEqual(Scale, 1.f))
    {
        FTransform Scaled1 = Place1, Scaled2 = Place2;
        Scaled1.ScaleTranslation(FVector(Scale)); Scaled2.ScaleTranslation(FVector(Scale));
        FPhysicsInterface::ExecuteOnUnbrokenConstraintReadWrite(C.GetPhysicsConstraintRef(), [&](const FPhysicsConstraintHandle& Handle)
        {
            FPhysicsInterface::SetLocalPose(Handle, Scaled1, EConstraintFrame::Frame1);
            FPhysicsInterface::SetLocalPose(Handle, Scaled2, EConstraintFrame::Frame2);
        });
    }
    // The motions, limits and softness together, then one push to Chaos.
    FConeConstraint& Cone = C.ProfileInstance.ConeLimit;
    FTwistConstraint& Twisting = C.ProfileInstance.TwistLimit;
    Twisting.TwistMotion = TwistMotion; Twisting.TwistLimitDegrees = float(Limits.X);
    Cone.Swing1Motion = Swing1Motion; Cone.Swing1LimitDegrees = float(Limits.Y);
    Cone.Swing2Motion = Swing2Motion; Cone.Swing2LimitDegrees = float(Limits.Z);
    Cone.bSoftConstraint = bSoftSwing; Cone.Stiffness = SwingStiffness; Cone.Damping = SwingDamping;
    Twisting.bSoftConstraint = bSoftTwist; Twisting.Stiffness = TwistStiffness; Twisting.Damping = TwistDamping;
    C.UpdateAngularLimit();
}

bool FRideJointEnvelope::HasFrames(const FConstraintInstance& C) const
{
    constexpr double Tolerance = UE_PI / 1800.;
    return C.GetRefFrame(EConstraintFrame::Frame1).GetRotation().AngularDistance(Frame1.GetRotation()) < Tolerance
        && C.GetRefFrame(EConstraintFrame::Frame2).GetRotation().AngularDistance(Frame2.GetRotation()) < Tolerance;
}

bool URidePhysicalRider::Begin(ACharacter* InRider, const ISkateRider* InApi)
{
    USkeletalMeshComponent* NewMesh = InRider ? InRider->GetMesh() : nullptr;
    if (!NewMesh || !NewMesh->GetSkeletalMeshAsset()) return false;
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    if (Control && Rider == InRider && Mesh == NewMesh && (bBuiltAsset ? Mesh->GetPhysicsAsset() == Built && bBuiltFit == S->bFitBodiesToSkin : true))
    {
        // A dismount still fading out (or a placement): the new ride keeps the body, unless the fit was switched.
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
        if (!Built || BuiltFor != Skeletal || bBuiltFit != S->bFitBodiesToSkin)
        {
            Built = KeptPhysicsAsset(Skeletal, Api, S->bFitBodiesToSkin, BuiltFitted, BailEnvelopes);
            BuiltFor = Skeletal; bBuiltFit = S->bFitBodiesToSkin;
        }
        if (!Built) { Mesh = nullptr; Rider = nullptr; return false; }
        Mesh->SetPhysicsAsset(Built, true);
    }
    else if (Mesh->GetPhysicsAsset() != Own) Mesh->SetPhysicsAsset(Own, true);
    SavedProfile = Mesh->GetCollisionProfileName();
    Mesh->SetCollisionProfileName(TEXT("Ragdoll"));
    // A new physics state: no pair ignored yet (IgnoreRiderPairs).
    IgnoredPairs.Reset(); RiderPairs.Reset(); bIgnorePending = false;
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
    // The joints' riding envelopes, as the asset has them: a get-up or a remount puts them back after a bail's.
    RidingEnvelopes.Reset(); RampLimits.Reset(); bBailEnvelope = false; EnvelopeLostAtStart = 0; DriveFadeApplied = 1.f;
    if (const UPhysicsAsset* Physics = Mesh->GetPhysicsAsset())
    {
        for (const UPhysicsConstraintTemplate* Template : Physics->ConstraintSetup)
            if (Template) RidingEnvelopes.Add(Template->DefaultInstance.JointName, FRideJointEnvelope::Of(Template->DefaultInstance));
        // The pairs of bodies that may meet: Chaos ignores them while riding and lets them meet in a bail. The mesh's
        // response to its own object type stays as the Ragdoll profile has it, for whatever else is of that type.
        for (int32 I = 0; I < Mesh->Bodies.Num(); ++I)
            for (int32 J = I + 1; J < Mesh->Bodies.Num(); ++J)
                if (Physics->SkeletalBodySetups.IsValidIndex(J) && Physics->IsCollisionEnabled(I, J)) RiderPairs.Add(FIntPoint(I, J));
    }
    if (!bBuiltAsset) BailEnvelopes.Reset();

    PelvisBone = Bone(TEXT("pelvis")); HeadBone = Bone(TEXT("head"));
    FootBones[0] = Bone(TEXT("foot_L")); FootBones[1] = Bone(TEXT("foot_R"));
    ThighBones[0] = Bone(TEXT("thigh_L")); ThighBones[1] = Bone(TEXT("thigh_R"));

    // The controls: an authored asset from the settings, or one built from the profiles.
    UPhysicsControlAsset* Authored = S->ControlAsset.IsNull() ? nullptr : S->ControlAsset.LoadSynchronous();
    bOwnControlAsset = Authored == nullptr;
    Asset = Authored ? Authored : BuildControlAsset(Mesh->GetPhysicsAsset());
    URidePhysicsControl* Guarded = NewObject<URidePhysicsControl>(Rider, TEXT("RidePhysicsControl"), RF_Transient);
    Guarded->Posed = Mesh;
    Control = Guarded;
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
    bBail = bBailOffered = false; bBailMaterial = false; BailDragApplied = 0; HipsAboveGround = -1; GetUpTime = -1; GetUpWait = -1; LandingLeft = 0;
    LastMeshLocation = Mesh->GetComponentLocation();
    LastRiderVelocity = Rider->GetVelocity(); PlacedFrames = 0;
    BeganFrame = GFrameCounter;
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(ERidePhysicalPhase::OnFoot);
    // The physics state may have been made this frame, with the asset's own pairs waiting in Chaos's pending list,
    // which an add for the same body in the same frame replaces: the first list carries them too.
    PairsAddedFrame = PairsRemovedFrame = 0;
    IgnoreRiderPairs(true);
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
        // The rider's own asset keeps its bodies after the ride: they meet each other again as they did before it.
        if (!bBuiltAsset && Mesh->GetPhysicsAsset() == SavedPhysicsAsset) RemoveIgnoredPairs(IgnoredPairs.Array());
        IgnoredPairs.Reset(); RiderPairs.Reset(); bIgnorePending = false;
        ApplyBailMaterial(false);
        ApplyBailDrag(0.f);
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

// The physics asset built from the bone contract: a body per part, and joint limits wide enough for every riding pose.
// Fitted to the skin, a body is the convex hull of the vertices it carries (those whose strongest weight is on its
// bone or on a bone under it without a body of its own: fingers on the hand, neck and clavicles on the chest, hair on
// the head), as the physics asset editor's single convex hull fit makes it, at the mass of the contract's capsule so
// the drives and the bail's tuning see the same bodies. The contract's capsule goes from the part's bone toward the
// next contract bone (a sphere at the ends), radius in cm for a slim 1.7 m rider.
UPhysicsAsset* URidePhysicalRider::BuildPhysicsAsset(USkeletalMesh* Skeletal, const ISkateRider* RiderApi, UObject* Outer, bool bFitToSkin,
    int32* OutFitted, TMap<FName, FRideJointEnvelope>* OutBail)
{
    if (OutFitted) *OutFitted = 0;
    if (OutBail) OutBail->Reset();
    if (!Skeletal) return nullptr;
    const FReferenceSkeleton& Ref = Skeletal->GetRefSkeleton();
    auto Find = [&](const TCHAR* Contract)
    {
        if (!Contract) return int32(INDEX_NONE);
        const FName B = RiderApi ? RiderApi->GetSkateBone(FName(Contract)) : FName(Contract);
        return B.IsNone() ? int32(INDEX_NONE) : Ref.FindBoneIndex(B);
    };
    const TArray<FTransform> Bind = BindPose(Ref);
    // Each joint's range is a human's, in degrees. Flexion and extension turn the body about its flexion axis (as it
    // flexes, its far end moves toward Toward: forward for the trunk, neck, hip and elbow, back for the knee, down for
    // the ankle's plantar flexion); abduction and adduction turn it about the axis across that, away from and toward
    // the body's middle (bending sideways for the trunk and neck); twist turns it about itself. A shoulder swings
    // Flexion in any direction around a centre out to the side and a little forward (with the clavicle on the chest's
    // body), a wrist around its rest (the contract has no direction for the palm).
    enum class EToward : uint8 { None, Forward, Back, Down, ShoulderCone, Cone };
    struct FPart
    {
        const TCHAR* Bone; const TCHAR* To; const TCHAR* Parent; float Radius;
        EToward Toward; float Flexion, Extension, Abduction, Adduction, Twist;
    };
    static const FPart Parts[] = {
        {TEXT("pelvis"), TEXT("spine"), nullptr, 12.f, EToward::None, 0, 0, 0, 0, 0},
        {TEXT("spine"), TEXT("chest"), TEXT("pelvis"), 11.f, EToward::Forward, 40.f, 20.f, 20.f, 20.f, 15.f},
        {TEXT("chest"), TEXT("neck"), TEXT("spine"), 13.f, EToward::Forward, 40.f, 15.f, 20.f, 20.f, 25.f},
        {TEXT("head"), nullptr, TEXT("chest"), 10.f, EToward::Forward, 50.f, 55.f, 40.f, 40.f, 60.f},
        {TEXT("upperarm_L"), TEXT("forearm_L"), TEXT("chest"), 5.f, EToward::ShoulderCone, 110.f, 0, 0, 0, 60.f},
        {TEXT("forearm_L"), TEXT("hand_L"), TEXT("upperarm_L"), 4.f, EToward::Forward, 145.f, 5.f, 8.f, 8.f, 40.f},
        {TEXT("hand_L"), nullptr, TEXT("forearm_L"), 4.f, EToward::Cone, 70.f, 0, 0, 0, 45.f},
        {TEXT("upperarm_R"), TEXT("forearm_R"), TEXT("chest"), 5.f, EToward::ShoulderCone, 110.f, 0, 0, 0, 60.f},
        {TEXT("forearm_R"), TEXT("hand_R"), TEXT("upperarm_R"), 4.f, EToward::Forward, 145.f, 5.f, 8.f, 8.f, 40.f},
        {TEXT("hand_R"), nullptr, TEXT("forearm_R"), 4.f, EToward::Cone, 70.f, 0, 0, 0, 45.f},
        {TEXT("thigh_L"), TEXT("shin_L"), TEXT("pelvis"), 7.5f, EToward::Forward, 120.f, 25.f, 45.f, 30.f, 40.f},
        {TEXT("shin_L"), TEXT("foot_L"), TEXT("thigh_L"), 5.5f, EToward::Back, 140.f, 5.f, 8.f, 8.f, 15.f},
        {TEXT("foot_L"), TEXT("toe_L"), TEXT("shin_L"), 4.5f, EToward::Down, 50.f, 20.f, 15.f, 15.f, 25.f},
        {TEXT("thigh_R"), TEXT("shin_R"), TEXT("pelvis"), 7.5f, EToward::Forward, 120.f, 25.f, 45.f, 30.f, 40.f},
        {TEXT("shin_R"), TEXT("foot_R"), TEXT("thigh_R"), 5.5f, EToward::Back, 140.f, 5.f, 8.f, 8.f, 15.f},
        {TEXT("foot_R"), TEXT("toe_R"), TEXT("shin_R"), 4.5f, EToward::Down, 50.f, 20.f, 15.f, 15.f, 25.f},
    };
    // Radii are for a 1.7 m rider; scale them by this skeleton's head height in component space.
    const int32 Head = Find(TEXT("head")), Root = Find(TEXT("root"));
    const float Height = Head != INDEX_NONE ? float(Bind[Head].GetLocation().Z - (Root != INDEX_NONE ? Bind[Root].GetLocation().Z : 0.)) : 155.f;
    const float Size = FMath::Clamp(Height / 155.f, .2f, 5.f);
    // The body's own directions in the bind pose (component space): up from the pelvis to the head, forward along the
    // feet to the toes, right from the left thigh to the right.
    FVector Up = FVector::UpVector, Right = FVector::RightVector, Forward = FVector::ForwardVector;
    {
        const int32 Pelvis = Find(TEXT("pelvis")), ThighL = Find(TEXT("thigh_L")), ThighR = Find(TEXT("thigh_R"));
        if (Pelvis != INDEX_NONE && Head != INDEX_NONE)
            Up = (Bind[Head].GetLocation() - Bind[Pelvis].GetLocation()).GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
        if (ThighL != INDEX_NONE && ThighR != INDEX_NONE)
            Right = FVector::VectorPlaneProject(Bind[ThighR].GetLocation() - Bind[ThighL].GetLocation(), Up).GetSafeNormal(UE_SMALL_NUMBER, FVector::RightVector);
        FVector Toes = FVector::ZeroVector;
        const TCHAR* Feet[2][2] = {{TEXT("foot_L"), TEXT("toe_L")}, {TEXT("foot_R"), TEXT("toe_R")}};
        for (const auto& Foot : Feet)
            if (const int32 Ankle = Find(Foot[0]), Toe = Find(Foot[1]); Ankle != INDEX_NONE && Toe != INDEX_NONE)
                Toes += Bind[Toe].GetLocation() - Bind[Ankle].GetLocation();
        Forward = FVector::VectorPlaneProject(Toes, Up);
        if (Forward.SizeSquared() < 1e-6) Forward = FVector::CrossProduct(Right, Up);
        Forward.Normalize();
        Right = FVector::VectorPlaneProject(Right, Forward).GetSafeNormal(UE_SMALL_NUMBER, FVector::CrossProduct(Up, Forward));
    }
    // The bones that get a body: a contract that names one bone twice gets one.
    TArray<int32, TInlineAllocator<16>> Used;
    for (const FPart& Part : Parts) if (const int32 B = Find(Part.Bone); B != INDEX_NONE) Used.AddUnique(B);
    // The skin each body carries, in its bone's space, and the vertices left out as too far from it.
    TMap<int32, TArray<FVector>> Skin;
    TMap<int32, int32> Strays;
    if (bFitToSkin)
    {
        TArray<FVector> Positions; TArray<int32> Dominant;
        if (ReadSkin(Skeletal, Positions, Dominant))
        {
            const TArray<int32> Owner = SkinOwners(Ref, Dominant, [&](int32 I) { return Used.Contains(I); });
            for (int32 V = 0; V < Owner.Num(); ++V)
            {
                if (Owner[V] == INDEX_NONE) continue;
                if (FVector::Dist(Positions[V], Bind[Owner[V]].GetLocation()) > SkinReach * Size) { ++Strays.FindOrAdd(Owner[V]); continue; }
                Skin.FindOrAdd(Owner[V]).Add(Bind[Owner[V]].InverseTransformPosition(Positions[V]));
            }
        }
        else UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: %s keeps no CPU copy of its vertices, so its bodies are the contract's capsules"),
            *Skeletal->GetName());
    }
    const TArray<FVector> Directions = SphereDirections(HullDirections);
    const float MassPower = GEngine && GEngine->DefaultPhysMaterial ? GEngine->DefaultPhysMaterial->RaiseMassToPower : .75f;
    UPhysicsAsset* Physics = NewObject<UPhysicsAsset>(Outer, NAME_None, RF_Transient);
    auto NewBody = [&](int32 B)
    {
        USkeletalBodySetup* Body = NewObject<USkeletalBodySetup>(Physics, NAME_None, RF_Transient);
        Body->BoneName = Ref.GetBoneName(B);
        Body->PhysicsType = PhysType_Default;
        Body->CollisionTraceFlag = CTF_UseSimpleAsComplex;
        Body->DefaultInstance.LinearDamping = .05f;
        Body->DefaultInstance.AngularDamping = .8f;
        return Body;
    };
    int32 Bodies = 0, Fitted = 0;
    TArray<int32, TInlineAllocator<16>> Made;
    // The bodies each joint holds together (indices into the asset's bodies, the lower first).
    TSet<FIntPoint> Joined;
    // Each part's anatomical frame in component space at the bind pose, by contract name (the bail's centres are
    // relative to the parent part's).
    TMap<FString, FQuat> PartFrames;
    for (const FPart& Part : Parts)
    {
        const int32 B = Find(Part.Bone);
        if (B == INDEX_NONE || Made.Contains(B)) continue;
        Made.Add(B);
        const int32 To = Find(Part.To), Parent = Find(Part.Parent), BoneParent = Ref.GetParentIndex(B);
        // The body's long axis in the bone's space.
        FVector End = FVector::ZeroVector, Axis = FVector::UpVector;
        if (To != INDEX_NONE) { End = Bind[To].GetRelativeTransform(Bind[B]).GetLocation(); Axis = End.GetSafeNormal(); }
        else if (BoneParent >= 0) Axis = Bind[B].GetRotation().UnrotateVector((Bind[B].GetLocation() - Bind[BoneParent].GetLocation()).GetSafeNormal());
        if (Axis.IsNearlyZero()) Axis = FVector::UpVector;
        // Shapes are in the bone's space, which carries the bone's scale.
        const float Radius = Part.Radius * Size / FMath::Max(.01f, float(Bind[B].GetMaximumAxisScale()));
        const float Length = float(End.Size());
        const bool bCapsule = To != INDEX_NONE && Length > Radius * 1.2f;
        // Lengths are in the bone's units too: on a skeleton whose root carries its unit scale, one unit is a metre
        // or more.
        const float CapsuleLength = FMath::Max(Radius * .2f, Length - Radius);
        const double CapsuleVolume = UE_PI * Radius * Radius * (bCapsule ? CapsuleLength + Radius * 4. / 3. : Radius * 4. / 3.);
        USkeletalBodySetup* Body = nullptr;
        if (const TArray<FVector>* Points = Skin.Find(B); Points && Points->Num() >= MinSkinVertices)
        {
            USkeletalBodySetup* Hull = NewBody(B);
            FKConvexElem Convex;
            for (const int32 I : Extremes(*Points, Directions)) Convex.VertexData.Add((*Points)[I]);
            Convex.UpdateElemBox();
            Hull->AggGeom.ConvexElems.Add(Convex);
            Hull->CreatePhysicsMeshes();
            // The hull is the body's only shape (the element's own volume is not exported).
            const double Volume = Hull->AggGeom.ConvexElems.Num() ? Hull->AggGeom.GetScaledVolume(FVector::OneVector) : 0.;
            if (Volume > CapsuleVolume * MinHullShare)
            {
                Body = Hull;
                // Mass grows with the volume to the material's power: this scale gives the hull the capsule's mass.
                Body->DefaultInstance.MassScale = float(FMath::Pow(CapsuleVolume / Volume, double(MassPower)));
                ++Fitted;
            }
            const FVector Extent = Convex.ElemBox.GetSize() * Bind[B].GetMaximumAxisScale();
            const int32 Stray = Strays.FindRef(B);
            UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider body %s: %s (%d of %d vertices; %.0f x %.0f x %.0f cm, %.1fx the capsule's volume)%s"),
                *Ref.GetBoneName(B).ToString(), Body ? TEXT("fitted to the skin") : TEXT("capsule, too little skin"), Convex.VertexData.Num(),
                Points->Num(), Extent.X, Extent.Y, Extent.Z, Volume / FMath::Max(CapsuleVolume, 1e-9),
                Stray ? *FString::Printf(TEXT("; %d vertices further than %.0f cm from the bone left out"), Stray, SkinReach * Size) : TEXT(""));
        }
        if (!Body)
        {
            Body = NewBody(B);
            if (bCapsule)
            {
                FKSphylElem Capsule(Radius, CapsuleLength);
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
        }
        Physics->SkeletalBodySetups.Add(Body);
        ++Bodies;
        // The body's own directions at the bind pose (its anatomical frame): X its long axis, Y its flexion axis
        // (about which it bends toward Toward), Z across both. Every part has one, the pelvis too: a joint's bail
        // centre is its frame in its parent's.
        const FVector Long = Bind[B].TransformVectorNoScale(Axis).GetSafeNormal(UE_SMALL_NUMBER, Up);
        FVector Hinge = Long ^ (Part.Toward == EToward::Back ? -Forward : Part.Toward == EToward::Down ? -Up : Forward);
        if (Hinge.Size() < .2) Hinge = Long ^ (FMath::Abs(Long | Up) < .9 ? Up : Forward);
        const FQuat Frame = FRotationMatrix::MakeFromXY(Long, Hinge.GetSafeNormal()).ToQuat();
        PartFrames.Add(Part.Bone, Frame);
        if (Parent == INDEX_NONE) continue;
        if (const int32 ParentBody = Made.IndexOfByKey(Parent); ParentBody != INDEX_NONE)
            Joined.Add(FIntPoint(FMath::Min(ParentBody, Made.Num() - 1), FMath::Max(ParentBody, Made.Num() - 1)));
        // The joint at the bone's origin, in the body's own directions at the bind pose: the twist about the body's
        // long axis (X), Swing2 about its flexion axis (Y), Swing1 about the axis across both (Z). The parent's frame
        // is turned to the middle of each one-sided range (the physics asset editor's angular rotation offset), so
        // the limits hold a human's range around the bind pose: a knee and an elbow bend one way.
        const FVector Out = FString(Part.Bone).EndsWith(TEXT("_L")) ? -Right : Right;
        const FVector Across = Frame.GetAxisZ();
        FQuat Centre = FQuat::Identity;
        float Swing1 = Part.Flexion, Swing2 = Part.Flexion;
        if (Part.Toward == EToward::ShoulderCone) Centre = FQuat::FindBetweenNormals(Long, (Out + Forward * .5).GetSafeNormal());
        else if (Part.Toward != EToward::Cone)
        {
            // Swinging about Y by a positive angle flexes the joint; about Z, it swings the body toward Y, which is out
            // from the middle when Y points out.
            const float Side = (Frame.GetAxisY() | Out) >= 0. ? 1.f : -1.f;
            Centre = FQuat(Frame.GetAxisY(), FMath::DegreesToRadians((Part.Flexion - Part.Extension) * .5f))
                * FQuat(Across, FMath::DegreesToRadians((Part.Abduction - Part.Adduction) * .5f * Side));
            Swing2 = (Part.Flexion + Part.Extension) * .5f;
            Swing1 = (Part.Abduction + Part.Adduction) * .5f;
        }
        UPhysicsConstraintTemplate* Joint = NewObject<UPhysicsConstraintTemplate>(Physics, NAME_None, RF_Transient);
        FConstraintInstance& C = Joint->DefaultInstance;
        C.JointName = Body->BoneName;
        C.ConstraintBone1 = Body->BoneName;
        C.ConstraintBone2 = Ref.GetBoneName(Parent);
        C.SetRefFrame(EConstraintFrame::Frame1, FTransform(Bind[B].GetRotation().Inverse() * Frame));
        C.SetRefFrame(EConstraintFrame::Frame2, FTransform(Bind[Parent].GetRotation().Inverse() * Centre * Frame,
            Bind[B].GetRelativeTransform(Bind[Parent]).GetLocation()));
        C.SetLinearXMotion(ELinearConstraintMotion::LCM_Locked);
        C.SetLinearYMotion(ELinearConstraintMotion::LCM_Locked);
        C.SetLinearZMotion(ELinearConstraintMotion::LCM_Locked);
        C.SetAngularSwing1Limit(EAngularConstraintMotion::ACM_Limited, Swing1);
        C.SetAngularSwing2Limit(EAngularConstraintMotion::ACM_Limited, Swing2);
        C.SetAngularTwistLimit(EAngularConstraintMotion::ACM_Limited, Part.Twist);
        C.SetDisableCollision(true);
        Physics->ConstraintSetup.Add(Joint);
        // Where the bind pose sits in the range: inside it, or the first bail would snap the joint into it.
        const FVector Bound = JointAngles((Centre * Frame).Inverse() * Frame);
        UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider joint %s: swing limits %.0f (across) and %.0f (flexion), twist %.0f; the bind pose %.0f past them"),
            *Body->BoneName.ToString(), Swing1, Swing2, Part.Twist, PastLimits(Bound, Part.Twist, Swing1, Swing2));
        // The bail envelope: the same child frame, the parent's turned to Native's centre (the child's anatomical frame
        // in the parent part's at the centre), and Native's limits, hard. A part whose parent part has no body of its
        // own (two contract names on one bone) keeps the riding envelope in a bail.
        if (!OutBail) continue;
        const FBailJoint* Row = Algo::FindByPredicate(BailJoints, [&](const FBailJoint& R) { return FCString::Strcmp(R.Contract, Part.Bone) == 0; });
        const FQuat* ParentFrame = PartFrames.Find(Part.Parent);
        if (!Row || !ParentFrame)
        {
            UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider joint %s: no bail envelope (%s), the riding one holds in a bail"),
                *Body->BoneName.ToString(), !Row ? TEXT("not in Native's table") : TEXT("its parent part has no body"));
            continue;
        }
        FRideJointEnvelope Bail = FRideJointEnvelope::Of(C);
        const FQuat BailCentre = *ParentFrame * Row->Centre.GetNormalized();
        Bail.Frame2 = FTransform(Bind[Parent].GetRotation().Inverse() * BailCentre, Bail.Frame2.GetLocation());
        Bail.Twist = Row->Twist; Bail.Swing1 = Row->Swing1; Bail.Swing2 = Row->Swing2;
        Bail.TwistMotion = Bail.Swing1Motion = Bail.Swing2Motion = ACM_Limited;
        // Hard, as Native's are: a soft limit gives way to whatever pushes on it (a contact pinning the hand under the
        // body) by as much as the push needs.
        Bail.bSoftSwing = Bail.bSoftTwist = false;
        OutBail->Add(C.JointName, Bail);
        // Where the bind pose sits in it, as Chaos measures (the parent's frame to the child's).
        const FVector BindInBail = JointAngles(BailCentre.Inverse() * Frame);
        UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider joint %s in a bail: twist %.1f, swing limits %.1f (across) and %.1f (flexion) about Native's centre, %.0f degrees from the riding one; the bind pose %.0f past them"),
            *Body->BoneName.ToString(), Row->Twist, Row->Swing1, Row->Swing2, FMath::RadiansToDegrees((Centre * Frame).AngularDistance(BailCentre)),
            PastLimits(BindInBail, Row->Twist, Row->Swing1, Row->Swing2));
    }
    if (Bodies < MinBodies) { UE_LOG(LogTemp, Warning, TEXT("SKATE ride physical rider: only %d contract bones"), Bodies); return nullptr; }
    // Which bodies meet each other (in a bail: SetSelfCollision): every pair but a joint's two bodies and two that
    // overlap in the bind pose, which would be thrown apart on the first step. So an arm meets the torso and the
    // pelvis, and a leg the other leg.
    {
        const TArray<FVector> Around = SphereDirections(PairDirections);
        TArray<TArray<FVector2D>> Extent; Extent.SetNum(Bodies);
        for (int32 I = 0; I < Bodies; ++I)
        {
            TArray<FVector> Points;
            ShapePoints(Physics->SkeletalBodySetups[I]->AggGeom, Points);
            Extents(Points, Bind[Made[I]], Around, Extent[I]);
        }
        int32 Meet = 0;
        FString Overlapping;
        for (int32 I = 0; I < Bodies; ++I)
            for (int32 J = I + 1; J < Bodies; ++J)
            {
                if (Joined.Contains(FIntPoint(I, J))) { Physics->DisableCollision(I, J); continue; }
                const double Depth = Overlap(Extent[I], Extent[J]);
                if (Depth > -PairMargin * Size)
                {
                    Physics->DisableCollision(I, J);
                    Overlapping += FString::Printf(TEXT(" %s-%s (%.1f cm)"), *Ref.GetBoneName(Made[I]).ToString(), *Ref.GetBoneName(Made[J]).ToString(), Depth);
                }
                else ++Meet;
            }
        UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: %d pairs of bodies meet in a bail; %d joints' pairs and these, overlapping in the bind pose, never do:%s"),
            Meet, Joined.Num(), Overlapping.IsEmpty() ? TEXT(" none") : *Overlapping);
    }
    if (bFitToSkin) UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: %d of %d bodies fitted to %s's skin"), Fitted, Bodies, *Skeletal->GetName());
    if (OutFitted) *OutFitted = Fitted;
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
    // The root body touches nothing.
    for (int32 I = 0; I + 1 < Bodies; ++I) if (Bodies > Made.Num()) Physics->DisableCollision(I, Bodies - 1);
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
        Body.bEnablebEnableCCD = true; Body.bEnableCCD = F.bContinuousCollision;
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
