#pragma once
// Helpers shared by the RidePhysicalRider*.cpp files (one source, split by section).
#include "RidePhysicalRider.h"
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

namespace RidePhysicalRiderDetail
{
    extern TAutoConsoleVariable<int32> CVarRidePhysical;

    extern TAutoConsoleVariable<int32> CVarRideSkinCheck;

    extern TAutoConsoleVariable<int32> CVarRideJointCheck;

    extern TAutoConsoleVariable<int32> CVarRideSelfCollision;

    extern TAutoConsoleVariable<int32> CVarRideBailTighten;

    extern TAutoConsoleVariable<float> CVarRideBailTightenRate;

    extern TAutoConsoleVariable<float> CVarRideBailProjection;
    extern TAutoConsoleVariable<float> CVarRideBailDriveFade;

    extern TAutoConsoleVariable<int32> CVarRideBailApplyNow;

    extern TAutoConsoleVariable<int32> CVarRideBailTrace;

    inline TArray<TWeakObjectPtr<URidePhysicalRider>> GRiders;

    // The physics assets built from the bone contract, by mesh (one map per fit), kept for the session: a character
    // switch or a new ride takes its mesh's again rather than building it (and cooking the hulls) on that frame.
    struct FBuiltAsset { TWeakObjectPtr<UPhysicsAsset> Asset; int32 Fitted = 0; TMap<FName, FRideJointEnvelope> Bail; };
    inline TMap<TWeakObjectPtr<USkeletalMesh>, FBuiltAsset> GBuiltAssets[2];

    inline UPhysicsAsset* KeptPhysicsAsset(USkeletalMesh* Skeletal, const ISkateRider* RiderApi, bool bFitToSkin, int32& Fitted,
        TMap<FName, FRideJointEnvelope>& Bail)
    {
        TMap<TWeakObjectPtr<USkeletalMesh>, FBuiltAsset>& Kept = GBuiltAssets[bFitToSkin ? 1 : 0];
        for (auto It = Kept.CreateIterator(); It; ++It)
            if (!It->Key.IsValid() || !It->Value.Asset.IsValid())
            {
                if (UPhysicsAsset* Old = It->Value.Asset.Get()) Old->RemoveFromRoot();
                It.RemoveCurrent();
            }
        if (const FBuiltAsset* Found = Kept.Find(Skeletal)) { Fitted = Found->Fitted; Bail = Found->Bail; return Found->Asset.Get(); }
        const double Start = FPlatformTime::Seconds();
        UPhysicsAsset* Built = URidePhysicalRider::BuildPhysicsAsset(Skeletal, RiderApi, GetTransientPackage(), bFitToSkin, &Fitted, &Bail);
        if (!Built) return nullptr;
        Built->AddToRoot();
        Kept.Add(Skeletal, FBuiltAsset{Built, Fitted, Bail});
        UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: physics asset for %s built in %.1f ms, kept for the session"),
            *Skeletal->GetName(), (FPlatformTime::Seconds() - Start) * 1000.);
        return Built;
    }
    inline FAutoConsoleCommand ReloadCommand(TEXT("skate.RidePhysicalReload"),
        TEXT("Ride: rebuild the physical rider's profiles from Project Settings > Skate Physical Rider and apply them."),
        FConsoleCommandDelegate::CreateLambda([]
        {
            for (const TWeakObjectPtr<URidePhysicalRider>& R : GRiders) if (R.IsValid()) R->ReloadProfiles();
        }));
    inline FAutoConsoleCommand DumpCommand(TEXT("skate.RidePhysicalDump"),
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

    inline FName PhaseName(ERidePhysicalPhase Phase)
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
    inline FPhysicsControlSparseData Strengths(float Linear, float Angular, float Damping)
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
    inline FPhysicsControlModifierSparseData Modifier()
    {
        FPhysicsControlModifierSparseData D;
        D.bEnableMovementType = D.bEnableCollisionType = D.bEnableGravityMultiplier = D.bEnablePhysicsBlendWeight = false;
        D.bEnableKinematicTargetSpace = D.bEnablebUpdateKinematicFromSimulation = D.bEnablebEnableCCD = false;
        return D;
    }

    // The loose board's box: the deck, trucks and wheels, centred this far below the deck bone (cm at board scale 1).
    const FVector LooseBoardExtent(40.f, 10.5f, 5.f);
    constexpr float LooseBoardDrop = 4.f;
    // GuardBoards: the box swept is this much smaller all round (cm); a move longer than BoardGuardReach (cm) in a
    // frame is a placement, not a flight; a face it would have passed sends it back with this restitution.
    constexpr float BoardGuardInset = 1.5f, BoardGuardReach = 500.f, BoardGuardBounce = .3f;
    // The surfaces made physical follow the body once it has moved this far, and let go beyond twice the radius.
    constexpr float PhysicalFollow = 600.f;
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
    // A pelvis crossing a face in a bail: one that ends this close to the face (cm) only touches it, and is checked again
    // from where it was while that is this near (cm); a crossing counts when the pelvis is cut off from this high over
    // the bail's floor (cm).
    constexpr float ThroughTouch = 2.f, ThroughKeep = 30.f, ThroughFloorUp = 30.f;
    // A body fitted to the skin is the convex hull of its vertices furthest out in this many directions, from at
    // least this many vertices; a hull under this share of the capsule's volume (a bone that carries little skin of
    // its own) leaves the capsule. With 64 directions the hull cut up to 3 cm off a limb's side (none of them
    // reached the calf's widest ring); 256 leave under 1 cm, about 47 vertices a hull.
    constexpr int32 HullDirections = 256;
    // A vertex further than this from its body's bone (cm, for a 1.7 m rider) is not that body's skin: a part bound
    // in its bone's own space, imported at the mesh's origin, would stretch the hull to the feet.
    constexpr float SkinReach = 80.f;
    constexpr int32 MinSkinVertices = 24;
    constexpr double MinHullShare = .05;
    // The skin depth samples each body's vertices furthest out in this many directions and about this many more
    // spread over the mesh, each traced this far above and below it (cm).
    constexpr int32 SkinDirections = 26;
    constexpr int32 SkinSpread = 256;
    constexpr float SkinProbe = 30.f;
    // Two bodies are tested for overlap along this many directions (the separating-axis test, sampled), and count as
    // overlapping when they come within this distance (cm, for a 1.7 m rider).
    constexpr int32 PairDirections = 128;
    constexpr float PairMargin = .5f;
    // A pair kept apart as a bail began meets again once this far apart (cm): more than PairMargin, so a pair that
    // only grazes isn't released and caught again frame after frame.
    constexpr float ReleaseMargin = 1.f;
    // A bail's limits start this far past the pose it began in (degrees), so the first step holds the joint where it is.
    constexpr float RampMargin = 2.f;
    // Chaos's swing limit stays under a half turn (4 atan2(.., 1 + w) reaches 360 at the far pole).
    constexpr float MaxLimit = 179.f;

    // Native's bail envelope on the contract's joints. In a bail (wipeout ragdoll modes 7 to 9, WipeoutRagdoll.cpp:20)
    // Native holds each of its joints within a circular cone of max(0.01, skel x bail mult x 0.5) about its parent
    // frame's X and a twist of +-max(0.01, skel x bail mult x 0.6), centred where its two frames meet; mode 10 and a
    // restored joint take max(0.01, skel x mult), the riding range, which here stays the asset's. Centre is the child's
    // anatomical frame (BuildPhysicsAsset's: X along the body, Y its flexion axis, both from the bind pose) in its
    // parent's at Native's centres, worked out on Native's RIG_TPOSE with the same rule; the limits are the largest twist,
    // Swing1 and Swing2 Chaos measures over Native's envelope, the parent's frame to the child's (the box that holds it,
    // Chaos's limits being a pyramid). A contract joint that spans several of Native's sums them: the spine is
    // HIPS-SPINE, the chest SPINE-SPINE1 to SPINE2-SPINE3, the head SPINE3-NECK and NECK-NECK1, an upper arm the
    // clavicle's and the shoulder's. Each side keeps Native's own values: its left and right differ (the left ankle's
    // cone is 9.4 degrees, the right's 13.5), so a side's centre is up to 20 degrees from the mirror of the other's. From
    // Native's physics_skeleton_joints records.
    struct FBailJoint { const TCHAR* Contract; FQuat Centre; float Twist, Swing1, Swing2; };
    const FBailJoint BailJoints[] = {
        {TEXT("spine"), FQuat(0.0495f, 0.1839f, 0.0005f, 0.9817f), 16.0f, 12.8f, 14.0f},
        {TEXT("chest"), FQuat(0.1145f, 0.3301f, 0.0874f, 0.9329f), 35.1f, 34.8f, 31.1f},
        {TEXT("head"), FQuat(0.0709f, 0.0917f, 0.0406f, 0.9924f), 11.3f, 9.8f, 12.2f},
        {TEXT("upperarm_L"), FQuat(0.0308f, -0.0057f, -0.8321f, 0.5537f), 42.1f, 37.6f, 42.1f},
        {TEXT("forearm_L"), FQuat(-0.1695f, 0.4058f, 0.1936f, 0.8770f), 33.2f, 16.8f, 16.2f},
        {TEXT("hand_L"), FQuat(0.2187f, -0.1036f, -0.0550f, 0.9687f), 42.8f, 37.6f, 34.2f},
        {TEXT("upperarm_R"), FQuat(-0.1620f, 0.0743f, 0.7673f, 0.6160f), 42.1f, 30.3f, 42.8f},
        {TEXT("forearm_R"), FQuat(0.0572f, 0.4629f, -0.0734f, 0.8815f), 36.4f, 19.8f, 19.5f},
        {TEXT("hand_R"), FQuat(-0.1789f, -0.1244f, 0.0590f, 0.9742f), 48.0f, 48.5f, 42.8f},
        {TEXT("thigh_L"), FQuat(0.4546f, -0.1547f, -0.8551f, 0.1956f), 41.3f, 38.2f, 45.9f},
        {TEXT("shin_L"), FQuat(0.7509f, -0.0141f, 0.6566f, 0.0694f), 32.9f, 38.2f, 41.4f},
        {TEXT("foot_L"), FQuat(0.0357f, -0.6381f, 0.1092f, 0.7613f), 11.4f, 11.3f, 23.6f},
        {TEXT("thigh_R"), FQuat(-0.4887f, -0.0742f, 0.8568f, 0.1471f), 35.1f, 33.9f, 39.3f},
        {TEXT("shin_R"), FQuat(-0.7697f, -0.0039f, -0.6350f, 0.0655f), 44.7f, 37.4f, 46.1f},
        {TEXT("foot_R"), FQuat(-0.0488f, -0.5546f, -0.0947f, 0.8253f), 30.6f, 21.4f, 34.1f},
    };

    // The reference skeleton's bind pose in component space.
    inline TArray<FTransform> BindPose(const FReferenceSkeleton& Ref)
    {
        TArray<FTransform> Bind; Bind.SetNum(Ref.GetNum());
        for (int32 I = 0; I < Ref.GetNum(); ++I)
        {
            const int32 Parent = Ref.GetParentIndex(I);
            Bind[I] = Parent >= 0 ? Ref.GetRefBonePose()[I] * Bind[Parent] : Ref.GetRefBonePose()[I];
        }
        return Bind;
    }

    // LOD0's vertices in the bind pose (component space) and the bone of each one's strongest weight (INDEX_NONE
    // outside every section). False when the mesh keeps no CPU copy of them.
    inline bool ReadSkin(const USkeletalMesh* Skeletal, TArray<FVector>& Positions, TArray<int32>& Dominant)
    {
        const FSkeletalMeshRenderData* Render = Skeletal ? Skeletal->GetResourceForRendering() : nullptr;
        if (!Render || Render->LODRenderData.Num() == 0) return false;
        const FSkeletalMeshLODRenderData& LOD = Render->LODRenderData[0];
        const FPositionVertexBuffer& Points = LOD.StaticVertexBuffers.PositionVertexBuffer;
        const FSkinWeightVertexBuffer& Weights = LOD.SkinWeightVertexBuffer;
        const uint32 Count = Points.GetNumVertices();
        if (Count == 0 || !Points.GetVertexData() || Weights.GetNumVertices() != Count || !Weights.GetDataVertexBuffer()->GetWeightData())
            return false;
        Positions.SetNumZeroed(Count);
        Dominant.Init(INDEX_NONE, Count);
        const uint32 Influences = Weights.GetMaxBoneInfluences();
        for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
            for (uint32 V = Section.BaseVertexIndex; V < FMath::Min(Count, Section.BaseVertexIndex + Section.NumVertices); ++V)
            {
                Positions[V] = FVector(Points.VertexPosition(V));
                uint32 Best = 0; uint16 Most = 0;
                for (uint32 I = 0; I < Influences; ++I)
                    if (const uint16 W = Weights.GetBoneWeight(V, I); W > Most) { Most = W; Best = Weights.GetBoneIndex(V, I); }
                if (Most > 0 && Section.BoneMap.IsValidIndex(int32(Best))) Dominant[V] = Section.BoneMap[Best];
            }
        return true;
    }

    // Each vertex's body: the nearest bone at or above its strongest bone that has one (INDEX_NONE: none).
    inline TArray<int32> SkinOwners(const FReferenceSkeleton& Ref, const TArray<int32>& Dominant, TFunctionRef<bool(int32)> HasBody)
    {
        TArray<int32> Owner; Owner.Init(INDEX_NONE, Ref.GetNum());
        // Parents come before their children.
        for (int32 I = 0; I < Ref.GetNum(); ++I)
        {
            const int32 Parent = Ref.GetParentIndex(I);
            Owner[I] = HasBody(I) ? I : Parent >= 0 ? Owner[Parent] : INDEX_NONE;
        }
        TArray<int32> Of; Of.Init(INDEX_NONE, Dominant.Num());
        for (int32 V = 0; V < Dominant.Num(); ++V)
            if (Owner.IsValidIndex(Dominant[V])) Of[V] = Owner[Dominant[V]];
        return Of;
    }

    // The skin depth's groups, by the contract bone of the body that carries a vertex (others: the torso).
    const TCHAR* const SkinGroupNames[] = { TEXT("torso"), TEXT("head"), TEXT("upperarms"), TEXT("forearms"), TEXT("hands"),
        TEXT("legs"), TEXT("feet") };
    static_assert(UE_ARRAY_COUNT(SkinGroupNames) == URidePhysicalRider::SkinGroupCount);
    struct FSkinGroupBone { const TCHAR* Contract; uint8 Group; };
    const FSkinGroupBone SkinGroupBones[] = {
        {TEXT("pelvis"), 0}, {TEXT("spine"), 0}, {TEXT("chest"), 0}, {TEXT("head"), 1}, {TEXT("upperarm_L"), 2}, {TEXT("upperarm_R"), 2},
        {TEXT("forearm_L"), 3}, {TEXT("forearm_R"), 3}, {TEXT("hand_L"), 4}, {TEXT("hand_R"), 4}, {TEXT("thigh_L"), 5}, {TEXT("thigh_R"), 5},
        {TEXT("shin_L"), 5}, {TEXT("shin_R"), 5}, {TEXT("foot_L"), 6}, {TEXT("foot_R"), 6} };

    // Directions spread evenly over the sphere (a Fibonacci lattice).
    inline TArray<FVector> SphereDirections(int32 Count)
    {
        TArray<FVector> Out;
        const double Golden = UE_PI * (3. - FMath::Sqrt(5.));
        for (int32 I = 0; I < Count; ++I)
        {
            const double Z = 1. - (2. * I + 1.) / Count, R = FMath::Sqrt(FMath::Max(0., 1. - Z * Z)), A = Golden * I;
            Out.Add(FVector(R * FMath::Cos(A), R * FMath::Sin(A), Z));
        }
        return Out;
    }

    // The points furthest out along each direction, each once (indices into Points).
    inline TArray<int32> Extremes(const TArray<FVector>& Points, const TArray<FVector>& Directions)
    {
        TArray<int32> Out;
        if (Points.IsEmpty()) return Out;
        for (const FVector& D : Directions)
        {
            int32 Best = 0; double Most = -UE_DOUBLE_BIG_NUMBER;
            for (int32 I = 0; I < Points.Num(); ++I)
                if (const double S = Points[I] | D; S > Most) { Most = S; Best = I; }
            Out.AddUnique(Best);
        }
        return Out;
    }

    // A shape's extent along each direction (its lowest and highest point), its points placed by Place.
    inline void Extents(const TArray<FVector>& Points, const FTransform& Place, const TArray<FVector>& Directions, TArray<FVector2D>& Out)
    {
        Out.Init(FVector2D(UE_DOUBLE_BIG_NUMBER, -UE_DOUBLE_BIG_NUMBER), Directions.Num());
        for (const FVector& Point : Points)
        {
            const FVector W = Place.TransformPosition(Point);
            for (int32 D = 0; D < Directions.Num(); ++D)
            {
                const double X = W | Directions[D];
                Out[D].X = FMath::Min(Out[D].X, X); Out[D].Y = FMath::Max(Out[D].Y, X);
            }
        }
    }

    // How deep two convex shapes go into each other (below 0: how far apart): the smallest overlap of their extents
    // over the directions. Sampled axes make it a slight overestimate of the depth.
    inline double Overlap(const TArray<FVector2D>& A, const TArray<FVector2D>& B)
    {
        if (A.IsEmpty() || A.Num() != B.Num()) return -UE_DOUBLE_BIG_NUMBER;
        double Depth = UE_DOUBLE_BIG_NUMBER;
        for (int32 D = 0; D < A.Num(); ++D) Depth = FMath::Min(Depth, FMath::Min(A[D].Y - B[D].X, B[D].Y - A[D].X));
        return Depth;
    }

    // A joint's rotation (the child's frame in the parent's) as Chaos measures it against the limits, in degrees:
    // the twist about X, then the swing about Z (Swing1) and about Y (Swing2).
    inline FVector JointAngles(const FQuat& Relative)
    {
        FQuat Swing, Twist;
        Relative.ToSwingTwist(FVector::ForwardVector, Swing, Twist);
        if (Swing.W < 0) Swing = FQuat(-Swing.X, -Swing.Y, -Swing.Z, -Swing.W);
        return FVector(FMath::RadiansToDegrees(Relative.GetTwistAngle(FVector::ForwardVector)),
            FMath::RadiansToDegrees(4. * FMath::Atan2(Swing.Z, 1. + Swing.W)), FMath::RadiansToDegrees(4. * FMath::Atan2(Swing.Y, 1. + Swing.W)));
    }

    // A joint's rotation as Chaos measures it against its limits, R01 = R0^-1 R1 (FPBDJointUtilities::
    // DecomposeSwingTwistLocal): the solver takes the container's bodies in reverse (PBDJointContainerSolver's
    // GetJointParticle), so body 0 is the parent (Frame2) and body 1 the child (Frame1). Physics Control's ClampExact
    // takes the same order. Measured the other way a joint inside its limits reads past them once it twists.
    inline FQuat ChaosRelative(const FBodyInstance& Child, const FBodyInstance& Parent, const FQuat& Frame1, const FQuat& Frame2)
    {
        return (Parent.GetUnrealWorldTransform().GetRotation() * Frame2).Inverse() * (Child.GetUnrealWorldTransform().GetRotation() * Frame1);
    }

    // A live joint's limits (twist, Swing1, Swing2; degrees), a free axis unbounded and a locked one at 0.
    inline FVector LiveLimits(const FConstraintInstance& C)
    {
        const auto Limit = [](EAngularConstraintMotion Motion, float Degrees)
        {
            return Motion == ACM_Free ? UE_BIG_NUMBER : Motion == ACM_Locked ? 0.f : Degrees;
        };
        return FVector(Limit(C.GetAngularTwistMotion(), C.GetAngularTwistLimit()), Limit(C.GetAngularSwing1Motion(), C.GetAngularSwing1Limit()),
            Limit(C.GetAngularSwing2Motion(), C.GetAngularSwing2Limit()));
    }

    // How far a joint goes past its limits (degrees; below 0 inside them): the furthest of its twist and two swings
    // past their own limits. Chaos's linear joint solver (the default) holds two limited swings as a pyramid, each
    // about its own axis (FPBDJointCachedSolver::InitPyramidSwingConstraint), not as the ellipse they would draw, so a
    // joint at both swing limits at once is inside them.
    inline double PastLimits(const FVector& Angles, double Twist, double Swing1, double Swing2)
    {
        return FMath::Max3(FMath::Abs(Angles.X) - Twist, FMath::Abs(Angles.Y) - Swing1, FMath::Abs(Angles.Z) - Swing2);
    }

    // A body's shapes as points in its bone's space: a hull's vertices, a capsule's or sphere's surface in 26
    // directions (their lowest point within a fifth of the radius).
    inline void ShapePoints(const FKAggregateGeom& Geom, TArray<FVector>& Out)
    {
        for (const FKConvexElem& C : Geom.ConvexElems)
        {
            const FTransform T = C.GetTransform();
            for (const FVector& V : C.VertexData) Out.Add(T.TransformPosition(V));
        }
        static const TArray<FVector> Around = SphereDirections(26);
        for (const FKSphereElem& S : Geom.SphereElems)
            for (const FVector& D : Around) Out.Add(S.Center + D * S.Radius);
        for (const FKSphylElem& S : Geom.SphylElems)
        {
            const FVector Axis = S.Rotation.Quaternion().GetAxisZ() * (S.Length * .5f);
            for (const FVector& D : Around) { Out.Add(S.Center + Axis + D * S.Radius); Out.Add(S.Center - Axis + D * S.Radius); }
        }
    }
}
