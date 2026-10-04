// The physical rider: see RidePhysicalRider.h and RIDE.md, "Physical rider".
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

namespace
{
    TAutoConsoleVariable<int32> CVarRidePhysical(TEXT("skate.RidePhysical"), 1,
        TEXT("Ride: 1 (the default) makes the rider an active ragdoll while riding (Physics Control drives its bodies toward the ")
        TEXT("animation); 0 animates it, with a ragdoll for bails only."));

    TAutoConsoleVariable<int32> CVarRideSkinCheck(TEXT("skate.RideSkinCheck"), 0,
        TEXT("Ride: 1 adds skin=, skin_bone= and skin_groups= to the physical rider's state: how far its skin goes under the ")
        TEXT("ground (cm, the deepest of a sample of the mesh's vertices skinned on the CPU; below 0 it stays above), the body ")
        TEXT("that carries that vertex and the deepest of each group of bodies; and hand_gap=: how far each hand's skin stays ")
        TEXT("from the torso's and thighs' bodies (cm, below 0 inside one). For QA: a few milliseconds a frame."));

    TAutoConsoleVariable<int32> CVarRideJointCheck(TEXT("skate.RideJointCheck"), 0,
        TEXT("Ride: 1 adds joint_past=, joint= and joint_angles= to the physical rider's state: how far the joint furthest past ")
        TEXT("its range goes (degrees, below 0 inside every range), which joint, and its twist and two swings (degrees, from ")
        TEXT("the bodies' rotations, as Chaos measures them against the live limits), with joint_limits= and joint_soft=, those ")
        TEXT("limits and whether they are soft; joint_env= (bail, riding or mixed: the envelope the live joints hold), joint_lost= ")
        TEXT("(joints whose limits are not the ones the rider set), joint_ramp= (how far the bail's limits still stand open past ")
        TEXT("its envelope, degrees) and joint_tighten=; and pair_depth= and pair=: how deep the two bodies that may meet go into ")
        TEXT("each other (cm, below 0 apart). For QA: about a millisecond a frame."));

    TAutoConsoleVariable<int32> CVarRideSelfCollision(TEXT("skate.RideSelfCollision"), 1,
        TEXT("Ride: 1 (the default) lets the physical rider's bodies meet each other in a bail (the arms the torso, a leg the ")
        TEXT("other); 0 lets them pass through each other, as they do riding. Read as a bail starts."));

    TAutoConsoleVariable<int32> CVarRideBailTighten(TEXT("skate.RideBailTighten"), 1,
        TEXT("Ride: 1 (the default) holds the built asset's joints in a bail within Native's bail envelope (each joint's own ")
        TEXT("centre, hard limits a half to a third of the riding ones, the drives' targets clamped to them); 0 keeps the riding ")
        TEXT("limits in a bail. Read as a bail starts."));

    TAutoConsoleVariable<float> CVarRideBailTightenRate(TEXT("skate.RideBailTightenRate"), 120.f,
        TEXT("Ride: how fast a bail's joint limits close from the pose the bail began in to Native's envelope (degrees a second; ")
        TEXT("0 closes them at the bail's first update)."));

    TAutoConsoleVariable<float> CVarRideBailProjection(TEXT("skate.RideBailProjection"), .8f,
        TEXT("Ride: how much of a bail joint's error past its hard limits Chaos's angular projection takes back each step (0 to 1; ")
        TEXT("the asset has 0). Without it a hard hit puts a knee or a hand 12 to 24 degrees past Native's bail envelope. Read as a bail starts."));
    TAutoConsoleVariable<float> CVarRideBailDriveFade(TEXT("skate.RideBailDriveFade"), 0.f,
        TEXT("Ride: N > 0 fades the Bail profile's joint drives (its tone toward the clip) to nothing over N seconds, as the ")
        TEXT("square of the time left, as Native's wipeout fades its drives (1.5 s); 0 (the default) keeps the tone through the bail."));

    TAutoConsoleVariable<int32> CVarRideBailApplyNow(TEXT("skate.RideBailApplyNow"), 1,
        TEXT("Ride: 1 (the default) applies the Bail profile to the bodies as the bail begins, so that frame's physics already ")
        TEXT("lets go of the anchors; 0 leaves it to Physics Control's next update."));

    TAutoConsoleVariable<int32> CVarRideBailTrace(TEXT("skate.RideBailTrace"), 0,
        TEXT("Ride: N > 0 logs each bail's first N frames: the pelvis's and the bodies' velocities, the root body and the actor."));

    TArray<TWeakObjectPtr<URidePhysicalRider>> GRiders;

    // The physics assets built from the bone contract, by mesh (one map per fit), kept for the session: a character
    // switch or a new ride takes its mesh's again rather than building it (and cooking the hulls) on that frame.
    struct FBuiltAsset { TWeakObjectPtr<UPhysicsAsset> Asset; int32 Fitted = 0; TMap<FName, FRideJointEnvelope> Bail; };
    TMap<TWeakObjectPtr<USkeletalMesh>, FBuiltAsset> GBuiltAssets[2];

    UPhysicsAsset* KeptPhysicsAsset(USkeletalMesh* Skeletal, const ISkateRider* RiderApi, bool bFitToSkin, int32& Fitted,
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
    TArray<FTransform> BindPose(const FReferenceSkeleton& Ref)
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
    bool ReadSkin(const USkeletalMesh* Skeletal, TArray<FVector>& Positions, TArray<int32>& Dominant)
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
    TArray<int32> SkinOwners(const FReferenceSkeleton& Ref, const TArray<int32>& Dominant, TFunctionRef<bool(int32)> HasBody)
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
    TArray<FVector> SphereDirections(int32 Count)
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
    TArray<int32> Extremes(const TArray<FVector>& Points, const TArray<FVector>& Directions)
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
    void Extents(const TArray<FVector>& Points, const FTransform& Place, const TArray<FVector>& Directions, TArray<FVector2D>& Out)
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
    double Overlap(const TArray<FVector2D>& A, const TArray<FVector2D>& B)
    {
        if (A.IsEmpty() || A.Num() != B.Num()) return -UE_DOUBLE_BIG_NUMBER;
        double Depth = UE_DOUBLE_BIG_NUMBER;
        for (int32 D = 0; D < A.Num(); ++D) Depth = FMath::Min(Depth, FMath::Min(A[D].Y - B[D].X, B[D].Y - A[D].X));
        return Depth;
    }

    // A joint's rotation (the child's frame in the parent's) as Chaos measures it against the limits, in degrees:
    // the twist about X, then the swing about Z (Swing1) and about Y (Swing2).
    FVector JointAngles(const FQuat& Relative)
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
    FQuat ChaosRelative(const FBodyInstance& Child, const FBodyInstance& Parent, const FQuat& Frame1, const FQuat& Frame2)
    {
        return (Parent.GetUnrealWorldTransform().GetRotation() * Frame2).Inverse() * (Child.GetUnrealWorldTransform().GetRotation() * Frame1);
    }

    // A live joint's limits (twist, Swing1, Swing2; degrees), a free axis unbounded and a locked one at 0.
    FVector LiveLimits(const FConstraintInstance& C)
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
    double PastLimits(const FVector& Angles, double Twist, double Swing1, double Swing2)
    {
        return FMath::Max3(FMath::Abs(Angles.X) - Twist, FMath::Abs(Angles.Y) - Swing1, FMath::Abs(Angles.Z) - Swing2);
    }

    // A body's shapes as points in its bone's space: a hull's vertices, a capsule's or sphere's surface in 26
    // directions (their lowest point within a fifth of the radius).
    void ShapePoints(const FKAggregateGeom& Geom, TArray<FVector>& Out)
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
    Bail.bFeetTouchWorld = true; Bail.bContinuousCollision = true;
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

void URidePhysicalRider::ApplyBailDrag(float Drag)
{
    if (!Mesh || Drag == BailDragApplied || (Drag > 0.f && BailDragApplied > 0.f && FMath::Abs(Drag - BailDragApplied) < .01f)) return;
    BailDragApplied = Drag;
    for (FBodyInstance* Body : Mesh->Bodies)
    {
        const UBodySetup* Setup = Body ? Body->GetBodySetup() : nullptr;
        if (!Setup) continue;
        Body->LinearDamping = Setup->DefaultInstance.LinearDamping + Drag;
        Body->UpdateDampingProperties();
    }
}

// Riding: the rider's constraint profile, with limits that widen to the animation, and the bodies pass through each
// other. Bailing: the bail profile and the bodies meet. The built asset's joints take their riding envelope (the
// asset's) or, in a bail, Native's (ApplyEnvelopes), with the drives' targets clamped into it; skate.RideBailTighten 0
// keeps the riding envelope in a bail. Physics Control reads the response from the live constraints each update, so
// it is set after the profile (which would copy the template's over it).
void URidePhysicalRider::ApplyJointLimits(bool bRidingProfile, bool bWiden)
{
    if (!Mesh) return;
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    if (!bBuiltAsset) Mesh->SetConstraintProfileForAll(bRidingProfile ? S->RideConstraintProfile : S->BailConstraintProfile, true);
    const bool bTighten = !bRidingProfile && bBuiltAsset && !BailEnvelopes.IsEmpty() && CVarRideBailTighten.GetValueOnGameThread() != 0;
    // In the bail's envelope a drive aimed outside it is aimed at its edge (ClampExact, which holds the swing's
    // direction): a target past a hard limit would only press the body against it.
    const EAngularDriveLimitViolationResponse Response = bWiden && S->bWidenLimitsWhileRiding ? EAngularDriveLimitViolationResponse::WidenLimits
        : bTighten ? EAngularDriveLimitViolationResponse::ClampExact : EAngularDriveLimitViolationResponse::None;
    for (FConstraintInstance* C : Mesh->Constraints)
        if (C) C->ProfileInstance.AngularDrive.LimitViolationResponse = Response;
    // Until a bail's envelope goes on, the live joints hold the asset's riding one.
    if (bBuiltAsset && (bTighten || bBailEnvelope)) ApplyEnvelopes(bTighten);
    else if (const UPhysicsAsset* Physics = Mesh->GetPhysicsAsset(); Physics && !bWiden)
    {
        // Riding widened the live limits to fit the animation's pose. Physics Control puts them back only for a
        // control it still drives, and a bail lets every control go limp first, so the bail would keep the riding
        // pose's widened limits. Each joint goes back to the asset's limits here.
        for (FConstraintInstance* C : Mesh->Constraints)
        {
            if (!C) continue;
            for (const UPhysicsConstraintTemplate* Template : Physics->ConstraintSetup)
                if (Template && Template->DefaultInstance.JointName == C->JointName)
                {
                    C->RestoreAngularLimitsToDefault(Template->DefaultInstance);
                    break;
                }
        }
    }
    SetSelfCollision(!bRidingProfile);
}

// Chaos takes back this share of a hard limit's angular error each step (its semi-physical projection).
static void SetAngularProjection(FConstraintInstance& C, float Alpha)
{
    if (C.ProfileInstance.ProjectionAngularAlpha == Alpha && C.ProfileInstance.bEnableProjection) return;
    float LinearAlpha, AngularAlpha, LinearTolerance, AngularTolerance;
    C.GetProjectionParams(LinearAlpha, AngularAlpha, LinearTolerance, AngularTolerance);
    C.SetProjectionParams(true, LinearAlpha, Alpha, LinearTolerance, AngularTolerance);
}

// The envelope goes onto the live constraints only: the asset is shared by every rider on the mesh (and by the next
// ride), and Physics Control's widening measures against it. A bail's limits start open to the pose the body is in,
// each axis to where the joint stands now (plus RampMargin) where that is past the envelope, and close at
// skate.RideBailTightenRate (UpdateRamp): limits snapped shut on a deeply bent grab would throw the bodies apart in one
// step, and no bone is moved to fit them.
void URidePhysicalRider::ApplyEnvelopes(bool bTighten)
{
    RampLimits.Reset();
    bBailEnvelope = bTighten;
    for (FConstraintInstance* C : Mesh->Constraints)
    {
        if (!C) continue;
        const FRideJointEnvelope* Bail = bTighten ? BailEnvelopes.Find(C->JointName) : nullptr;
        if (!Bail)
        {
            if (const FRideJointEnvelope* Riding = RidingEnvelopes.Find(C->JointName))
            {
                Riding->ApplyTo(*C);
                SetAngularProjection(*C, Riding->AngularProjection);
            }
            continue;
        }
        FVector Limits(Bail->Twist, Bail->Swing1, Bail->Swing2);
        const FBodyInstance* Child = Mesh->GetBodyInstance(C->ConstraintBone1);
        const FBodyInstance* Parent = Mesh->GetBodyInstance(C->ConstraintBone2);
        if (Child && Parent)
        {
            const FVector Now = JointAngles(ChaosRelative(*Child, *Parent, Bail->Frame1.GetRotation(), Bail->Frame2.GetRotation())).GetAbs();
            Limits = Limits.ComponentMax(Now + FVector(RampMargin)).ComponentMin(FVector(MaxLimit));
        }
        Bail->ApplyTo(*C, Limits);
        SetAngularProjection(*C, FMath::Clamp(CVarRideBailProjection.GetValueOnGameThread(), 0.f, 1.f));
        RampLimits.Add(C->JointName, Limits);
    }
    // Physics Control would put the asset's limits back over these on its next update (URidePhysicsControl).
    if (URidePhysicsControl* Guarded = Cast<URidePhysicsControl>(Control)) Guarded->ForgetWidenedLimits(Mesh);
}

void URidePhysicalRider::UpdateRamp(float Dt)
{
    if (!bBailEnvelope || RampLimits.IsEmpty() || !Mesh) return;
    const float Rate = CVarRideBailTightenRate.GetValueOnGameThread();
    for (FConstraintInstance* C : Mesh->Constraints)
    {
        FVector* Limits = C ? RampLimits.Find(C->JointName) : nullptr;
        const FRideJointEnvelope* Bail = C ? BailEnvelopes.Find(C->JointName) : nullptr;
        if (!Limits || !Bail) continue;
        const FVector Envelope(Bail->Twist, Bail->Swing1, Bail->Swing2);
        if (*Limits == Envelope) continue;
        *Limits = Rate <= 0.f ? Envelope : (*Limits - FVector(Rate * Dt)).ComponentMax(Envelope);
        FConeConstraint& Cone = C->ProfileInstance.ConeLimit;
        C->ProfileInstance.TwistLimit.TwistLimitDegrees = float(Limits->X);
        Cone.Swing1LimitDegrees = float(Limits->Y); Cone.Swing2LimitDegrees = float(Limits->Z);
        C->UpdateAngularLimit();
    }
}

// Native fades its wipeout's drives over 1.5 s by the square of the time left (WipeoutResponse.cpp:44): here the Bail
// profile's joint drives, through Physics Control's multipliers, which the profiles never set. An authored control
// asset keeps its own.
void URidePhysicalRider::ApplyDriveFade(float Multiplier)
{
    if (!Control || !bOwnControlAsset || Multiplier == DriveFadeApplied) return;
    if (Multiplier > 0.f && Multiplier < 1.f && FMath::Abs(Multiplier - DriveFadeApplied) < .01f) return;
    DriveFadeApplied = Multiplier;
    FPhysicsControlSparseMultiplier Fade;
    Fade.bEnableLinearStrengthMultiplier = Fade.bEnableLinearDampingRatioMultiplier = Fade.bEnableLinearExtraDampingMultiplier = false;
    Fade.bEnableMaxForceMultiplier = Fade.bEnableAngularDampingRatioMultiplier = Fade.bEnableAngularExtraDampingMultiplier = false;
    Fade.bEnableMaxTorqueMultiplier = false;
    Fade.bEnableAngularStrengthMultiplier = true;
    Fade.AngularStrengthMultiplier = Multiplier;
    Control->SetControlSparseMultiplier(ParentSet, Fade, false, false, true);
}

// Which envelope the live joints hold, and whether their limits are the ones the rider set.
void URidePhysicalRider::CheckEnvelope(int32& OnBail, int32& OnRiding, int32& Lost, float& Ramp) const
{
    OnBail = OnRiding = Lost = 0; Ramp = 0.f;
    if (!Mesh || !bBuiltAsset) return;
    for (const FConstraintInstance* C : Mesh->Constraints)
    {
        if (!C) continue;
        const FRideJointEnvelope* Bail = BailEnvelopes.Find(C->JointName);
        const FRideJointEnvelope* Riding = RidingEnvelopes.Find(C->JointName);
        const FVector Live(C->GetAngularTwistLimit(), C->GetAngularSwing1Limit(), C->GetAngularSwing2Limit());
        const bool bSoft = C->ProfileInstance.ConeLimit.bSoftConstraint || C->ProfileInstance.TwistLimit.bSoftConstraint;
        if (Bail && Bail->HasFrames(*C))
        {
            ++OnBail;
            const FVector* Set = RampLimits.Find(C->JointName);
            if (!bBailEnvelope || !Set || !Live.Equals(*Set, .01) || bSoft) ++Lost;
            if (Set) Ramp = FMath::Max(Ramp, float((*Set - FVector(Bail->Twist, Bail->Swing1, Bail->Swing2)).GetMax()));
        }
        else if (Riding && Riding->HasFrames(*C))
        {
            ++OnRiding;
            if (Live.X < Riding->Twist - .01 || Live.Y < Riding->Swing1 - .01 || Live.Z < Riding->Swing2 - .01) ++Lost;
        }
        else ++Lost;
    }
}

// The bodies meet each other through Chaos's ignore list, pair by pair: riding, Chaos ignores every pair of the
// rider's bodies (the animation puts a hand on a thigh and the bodies follow it); in a bail, the pairs meet, less any
// that overlaps in the pose the bail starts from: a hand resting inside a thigh would be thrown out of it on the first
// step. Those pairs stay apart until they come apart (ReleaseKeptPairs). The mesh's response to its own object type
// is left as the Ragdoll profile has it, so other bodies of that type (another rider's, props) still meet the rider.
void URidePhysicalRider::SetSelfCollision(bool bOn)
{
    if (!Mesh) return;
    bOn = bOn && CVarRideSelfCollision.GetValueOnGameThread() != 0;
    PairsReleased = 0;
    if (!bOn)
    {
        IgnoreRiderPairs(false);
        return;
    }
    // A bail just after the pairs were ignored (a mount, a get-up) waits for them to reach the physics before letting
    // any go: until then they count as kept apart and ReleaseKeptPairs lets each go once apart.
    if (bIgnorePending || IgnoredPairs.Num() < RiderPairs.Num()) IgnoreRiderPairs(false);
    if (GFrameCounter < PairsAddedFrame + 3) return;
    TArray<TArray<FVector2D>> Extent;
    BodyExtents(Extent);
    TArray<FIntPoint> Meet;
    FString Names;
    for (const FIntPoint& P : IgnoredPairs)
    {
        if (!Extent.IsValidIndex(P.X) || !Extent.IsValidIndex(P.Y) || Extent[P.X].IsEmpty() || Extent[P.Y].IsEmpty()) continue;
        const double Depth = Overlap(Extent[P.X], Extent[P.Y]);
        if (Depth <= -PairMargin) { Meet.Add(P); continue; }
        Names += FString::Printf(TEXT(" %s-%s (%.1f cm)"), *Mesh->Bodies[P.X]->BodySetup->BoneName.ToString(), *Mesh->Bodies[P.Y]->BodySetup->BoneName.ToString(), Depth);
    }
    for (const FIntPoint& P : Meet) IgnoredPairs.Remove(P);
    RemoveIgnoredPairs(Meet);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride ragdoll: %d pairs of bodies meet; overlapping as the bail starts, kept apart until they come apart:%s"),
        Meet.Num(), Names.IsEmpty() ? TEXT(" none") : *Names);
}

void URidePhysicalRider::IgnoreRiderPairs(bool bWithAsset)
{
    // A pair let go in the last frames may still be waiting to leave Chaos's list: adding it back now could cross that
    // on the physics thread and leave it meeting. Update tries again.
    if (GFrameCounter < PairsRemovedFrame + 3) { bIgnorePending = true; return; }
    bIgnorePending = false;
    const UPhysicsAsset* Physics = Mesh ? Mesh->GetPhysicsAsset() : nullptr;
    if (!Physics) return;
    TMap<FPhysicsActorHandle, TArray<FPhysicsActorHandle>> Ignore;
    const auto Actor = [&](int32 I) { return Mesh->Bodies.IsValidIndex(I) && Mesh->Bodies[I] ? Mesh->Bodies[I]->GetPhysicsActor() : FPhysicsActorHandle(); };
    for (const FIntPoint& P : RiderPairs)
    {
        if (IgnoredPairs.Contains(P)) continue;
        FPhysicsActorHandle A = Actor(P.X), B = Actor(P.Y);
        if (!A || !B) continue;
        Ignore.FindOrAdd(A).Add(B);
        IgnoredPairs.Add(P);
    }
    if (Ignore.IsEmpty()) return;
    // Chaos keeps one pending list per body and frame: a second add for a body in the frame its physics state was made
    // replaces the asset's own (InitArticulated's), so each listed body carries those pairs as well.
    if (bWithAsset)
        for (auto& Entry : Ignore)
            for (int32 I = 0; I < Mesh->Bodies.Num(); ++I)
                if (Mesh->Bodies[I] && Mesh->Bodies[I]->GetPhysicsActor() == Entry.Key)
                {
                    for (int32 J = 0; J < Mesh->Bodies.Num(); ++J)
                        if (J != I && Physics->SkeletalBodySetups.IsValidIndex(FMath::Max(I, J)) && !Physics->IsCollisionEnabled(I, J))
                            if (FPhysicsActorHandle Other = Actor(J)) Entry.Value.AddUnique(Other);
                    break;
                }
    FPhysicsCommand::ExecuteWrite(Mesh.Get(), [&]() { FChaosEngineInterface::AddDisabledCollisionsFor_AssumesLocked(Ignore); });
    PairsAddedFrame = GFrameCounter;
}

// Takes pairs off Chaos's ignore list on the physics thread (the game thread's API only adds, or drops a body's whole
// list).
void URidePhysicalRider::RemoveIgnoredPairs(const TArray<FIntPoint>& Pairs)
{
    for (const FIntPoint& P : Pairs)
    {
        if (!Mesh->Bodies.IsValidIndex(P.X) || !Mesh->Bodies.IsValidIndex(P.Y) || !Mesh->Bodies[P.X] || !Mesh->Bodies[P.Y]) continue;
        FPhysicsActorHandle A = Mesh->Bodies[P.X]->GetPhysicsActor(), B = Mesh->Bodies[P.Y]->GetPhysicsActor();
        Chaos::FPBDRigidsSolver* Solver = A ? A->GetSolver<Chaos::FPBDRigidsSolver>() : nullptr;
        if (!Solver || !B) continue;
        const Chaos::FUniqueIdx IdA = A->GetGameThreadAPI().UniqueIdx(), IdB = B->GetGameThreadAPI().UniqueIdx();
        Solver->EnqueueCommandImmediate([Solver, IdA, IdB]()
        {
            Chaos::FSingleParticlePhysicsProxy* ProxyA = Solver->GetParticleProxy_PT(IdA);
            Chaos::FSingleParticlePhysicsProxy* ProxyB = Solver->GetParticleProxy_PT(IdB);
            if (ProxyA && ProxyB)
                Solver->GetEvolution()->GetBroadPhase().GetIgnoreCollisionManager().RemoveIgnoreCollisions(ProxyA->GetHandle_LowLevel(), ProxyB->GetHandle_LowLevel());
        });
        PairsRemovedFrame = GFrameCounter;
    }
}

// A pair kept apart as the bail began meets again once it has come ReleaseMargin apart, so a hand that started inside
// a thigh can't pass through it for the rest of the tumble. Never within three frames of the pairs being ignored,
// while their entries may still be waiting to be added.
void URidePhysicalRider::ReleaseKeptPairs()
{
    if (!Mesh || IgnoredPairs.IsEmpty() || GFrameCounter < PairsAddedFrame + 3) return;
    TArray<TArray<FVector2D>> Extent;
    BodyExtents(Extent);
    TArray<FIntPoint> Released;
    FString Names;
    for (const FIntPoint& P : IgnoredPairs)
    {
        if (!Extent.IsValidIndex(P.X) || !Extent.IsValidIndex(P.Y) || Extent[P.X].IsEmpty() || Extent[P.Y].IsEmpty()) continue;
        const double Depth = Overlap(Extent[P.X], Extent[P.Y]);
        if (Depth > -ReleaseMargin) continue;
        Released.Add(P);
        Names += FString::Printf(TEXT(" %s-%s (%.1f cm apart)"), *Mesh->Bodies[P.X]->BodySetup->BoneName.ToString(),
            *Mesh->Bodies[P.Y]->BodySetup->BoneName.ToString(), -Depth);
    }
    for (const FIntPoint& P : Released) IgnoredPairs.Remove(P);
    RemoveIgnoredPairs(Released);
    PairsReleased += Released.Num();
    if (Released.Num())
        UE_LOG(LogTemp, Display, TEXT("SKATE ride ragdoll: kept apart as the bail began, meet again %.2f s in:%s"), BailTime, *Names);
}

// Each body's extent along PairDirections where it is now (empty for a body that touches nothing).
void URidePhysicalRider::BodyExtents(TArray<TArray<FVector2D>>& Extent) const
{
    Extent.Reset();
    const UPhysicsAsset* Physics = Mesh ? Mesh->GetPhysicsAsset() : nullptr;
    if (!Physics) return;
    if (BodyPointsFor != Physics)
    {
        BodyPointsFor = Physics;
        BodyPoints.Reset(); BodyPoints.SetNum(Physics->SkeletalBodySetups.Num());
        for (int32 I = 0; I < BodyPoints.Num(); ++I)
            if (const USkeletalBodySetup* Setup = Physics->SkeletalBodySetups[I]; Setup && Setup->CollisionReponse != EBodyCollisionResponse::BodyCollision_Disabled
                && Setup->PhysicsType != PhysType_Kinematic)
                ShapePoints(Setup->AggGeom, BodyPoints[I]);
    }
    static const TArray<FVector> Around = SphereDirections(PairDirections);
    Extent.SetNum(FMath::Min(BodyPoints.Num(), Mesh->Bodies.Num()));
    for (int32 I = 0; I < Extent.Num(); ++I)
    {
        const FBodyInstance* Body = Mesh->Bodies[I];
        if (!Body || BodyPoints[I].IsEmpty()) continue;
        const int32 Index = Mesh->GetBoneIndex(Physics->SkeletalBodySetups[I]->BoneName);
        if (Index == INDEX_NONE) continue;
        // The body where the physics has it, at its bone's scale (the shapes are in the bone's units).
        FTransform Place = Body->GetUnrealWorldTransform();
        Place.SetScale3D(Mesh->GetBoneTransform(Index).GetScale3D());
        Extents(BodyPoints[I], Place, Around, Extent[I]);
    }
}

// The joint furthest past its range and the two bodies that may meet deepest in each other, as the bodies are now:
// the live constraints' frames and limits (a bail's envelope, Physics Control's widening), measured as Chaos does.
bool URidePhysicalRider::MeasureJoints(float& Past, FName& Joint, FVector& Angles, float& Depth, FName Pair[2], FVector* Limits, bool* bSoft) const
{
    const UPhysicsAsset* Physics = Mesh ? Mesh->GetPhysicsAsset() : nullptr;
    if (!Physics) return false;
    Past = -UE_BIG_NUMBER; Joint = NAME_None; Angles = FVector::ZeroVector;
    if (Limits) *Limits = FVector::ZeroVector;
    if (bSoft) *bSoft = false;
    for (const FConstraintInstance* C : Mesh->Constraints)
    {
        if (!C) continue;
        const FBodyInstance* Child = Mesh->GetBodyInstance(C->ConstraintBone1);
        const FBodyInstance* Parent = Mesh->GetBodyInstance(C->ConstraintBone2);
        if (!Child || !Parent) continue;
        const FVector A = JointAngles(ChaosRelative(*Child, *Parent, C->GetRefFrame(EConstraintFrame::Frame1).GetRotation(),
            C->GetRefFrame(EConstraintFrame::Frame2).GetRotation()));
        const FVector Live = LiveLimits(*C);
        const float P = float(PastLimits(A, Live.X, Live.Y, Live.Z));
        if (P <= Past) continue;
        Past = P; Joint = C->ConstraintBone1; Angles = A;
        if (Limits) *Limits = Live;
        if (bSoft) *bSoft = C->ProfileInstance.ConeLimit.bSoftConstraint || C->ProfileInstance.TwistLimit.bSoftConstraint;
    }
    Depth = -UE_BIG_NUMBER; Pair[0] = Pair[1] = NAME_None;
    TArray<TArray<FVector2D>> Extent;
    BodyExtents(Extent);
    for (int32 I = 0; I < Extent.Num(); ++I)
        for (int32 J = I + 1; J < Extent.Num(); ++J)
        {
            if (Extent[I].IsEmpty() || Extent[J].IsEmpty() || !Physics->IsCollisionEnabled(I, J) || IgnoredPairs.Contains(FIntPoint(I, J))) continue;
            if (const float D = float(Overlap(Extent[I], Extent[J])); D > Depth)
            {
                Depth = D;
                Pair[0] = Physics->SkeletalBodySetups[I]->BoneName; Pair[1] = Physics->SkeletalBodySetups[J]->BoneName;
            }
        }
    return Joint != NAME_None;
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
    GuardBoards();
    if (!Control || !Mesh) return;
    DrivenFrame = GFrameCounter;
    if (bIgnorePending && !bBail) IgnoreRiderPairs(false);
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
        const UBodySetup* Setup = Body->GetBodySetup();
        const FKAggregateGeom Geom = Setup ? Setup->AggGeom : FKAggregateGeom();
        UE_LOG(LogTemp, Display, TEXT("SKATE ride physical dump: %s sim=%d scale=%s body=%s bone=%s target=%s bounds=%s..%s mass=%.1f kg collision=%d type=%d static=%d dynamic=%d ccd=%d shapes=%d sphere %d capsule %d convex near:%s"),
            *B.ToString(), Body->IsInstanceSimulatingPhysics() ? 1 : 0, *Body->Scale3D.ToString(),
            *Body->GetUnrealWorldTransform().GetLocation().ToString(), *Mesh->GetBoneLocation(B).ToString(),
            *Control->GetCachedBonePosition(Mesh, B).ToString(), *Box.Min.ToString(), *Box.Max.ToString(), Body->GetBodyMass(),
            int32(Body->GetCollisionEnabled()), int32(Body->GetObjectType()), int32(Body->GetResponseToChannel(ECC_WorldStatic)),
            int32(Body->GetResponseToChannel(ECC_WorldDynamic)), Body->bUseCCD ? 1 : 0, Geom.SphereElems.Num(), Geom.SphylElems.Num(),
            Geom.ConvexElems.Num(), *Touching);
    }
}

const TCHAR* URidePhysicalRider::SkinGroupName(int32 Group)
{
    return Group >= 0 && Group < SkinGroupCount ? SkinGroupNames[Group] : TEXT("-");
}

bool URidePhysicalRider::MeasureSkinDepth(float& Depth, FName& Bone, float* Groups) const
{
    Depth = -SkinProbe; Bone = NAME_None;
    if (Groups) for (int32 G = 0; G < SkinGroupCount; ++G) Groups[G] = -SkinProbe;
    USkeletalMeshComponent* Skinned = Mesh.Get();
    const USkeletalMesh* Skeletal = Skinned ? Skinned->GetSkeletalMeshAsset() : nullptr;
    const UPhysicsAsset* Physics = Skinned ? Skinned->GetPhysicsAsset() : nullptr;
    if (!Skeletal || !Physics || !Rider) return false;
    // The samples: each body's vertices furthest out (in its bone's space, so in any pose: where a body meets the
    // ground), and a spread of the rest, for the skin that a bent joint pushes out between two bodies.
    if (SkinSamplesFor != Physics)
    {
        SkinSamplesFor = Physics; SkinSamples.Reset(); SkinSampleBones.Reset(); SkinSampleGroups.Reset();
        TArray<FVector> Positions; TArray<int32> Dominant;
        if (ReadSkin(Skeletal, Positions, Dominant))
        {
            const FReferenceSkeleton& Ref = Skeletal->GetRefSkeleton();
            const TArray<FTransform> Bind = BindPose(Ref);
            TSet<int32> Bodies;
            for (const USkeletalBodySetup* Setup : Physics->SkeletalBodySetups)
                if (Setup && Setup->PhysicsType != PhysType_Kinematic) Bodies.Add(Ref.FindBoneIndex(Setup->BoneName));
            const TArray<int32> Owner = SkinOwners(Ref, Dominant, [&](int32 I) { return Bodies.Contains(I); });
            TMap<int32, TArray<int32>> Carried;
            for (int32 V = 0; V < Owner.Num(); ++V) if (Owner[V] != INDEX_NONE) Carried.FindOrAdd(Owner[V]).Add(V);
            const TArray<FVector> Directions = SphereDirections(SkinDirections);
            TSet<int32> Taken;
            for (const TPair<int32, TArray<int32>>& Part : Carried)
            {
                TArray<FVector> Local;
                for (const int32 V : Part.Value) Local.Add(Bind[Part.Key].InverseTransformPosition(Positions[V]));
                for (const int32 I : Extremes(Local, Directions))
                    if (!Taken.Contains(Part.Value[I])) { Taken.Add(Part.Value[I]); SkinSamples.Add(Part.Value[I]); SkinSampleBones.Add(Ref.GetBoneName(Part.Key)); }
            }
            const int32 Stride = FMath::Max(1, Owner.Num() / SkinSpread);
            for (int32 V = 0; V < Owner.Num(); V += Stride)
                if (Owner[V] != INDEX_NONE && !Taken.Contains(V)) { Taken.Add(V); SkinSamples.Add(V); SkinSampleBones.Add(Ref.GetBoneName(Owner[V])); }
            TMap<FName, uint8> GroupOf;
            for (const FSkinGroupBone& G : SkinGroupBones) if (const FName B = this->Bone(G.Contract); !B.IsNone()) GroupOf.Add(B, G.Group);
            for (const FName B : SkinSampleBones) SkinSampleGroups.Add(GroupOf.FindRef(B));
            UE_LOG(LogTemp, Display, TEXT("SKATE ride physical rider: the skin depth samples %d of %s's %d vertices"), SkinSamples.Num(),
                *Skeletal->GetName(), Owner.Num());
        }
    }
    const FSkeletalMeshRenderData* Render = Skeletal->GetResourceForRendering();
    const FSkinWeightVertexBuffer* Weights = Skinned->GetSkinWeightBuffer(0);
    if (SkinSamples.IsEmpty() || !Render || Render->LODRenderData.Num() == 0 || !Weights) return false;
    const FSkeletalMeshLODRenderData& LOD = Render->LODRenderData[0];
    TArray<FMatrix44f> RefToLocals;
    Skinned->CacheRefToLocalMatrices(RefToLocals);
    const FTransform ToWorld = Skinned->GetComponentTransform();
    UWorld* World = Rider->GetWorld();
    // The ground as it shows: its complex collision (the render mesh's triangles), which the bodies' simple shapes
    // may stand off from.
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideSkin), true, Rider);
    if (LooseBoard) Params.AddIgnoredComponent(LooseBoard.Get());
    for (int32 I = 0; I < SkinSamples.Num(); ++I)
    {
        const FVector P = ToWorld.TransformPosition(FVector(USkeletalMeshComponent::GetSkinnedVertexPosition(Skinned, SkinSamples[I], LOD, *Weights, RefToLocals)));
        FHitResult Hit;
        if (!World->LineTraceSingleByChannel(Hit, P + FVector(0, 0, SkinProbe), P - FVector(0, 0, SkinProbe), ECC_Pawn, Params) || Hit.bStartPenetrating)
            continue;
        const float Below = float((FVector(Hit.ImpactPoint) - P) | Hit.ImpactNormal);
        if (Below > Depth) { Depth = Below; Bone = SkinSampleBones[I]; }
        if (Groups && SkinSampleGroups.IsValidIndex(I)) Groups[SkinSampleGroups[I]] = FMath::Max(Groups[SkinSampleGroups[I]], Below);
    }
    return true;
}

bool URidePhysicalRider::MeasureHandGap(float Gap[2], FName Near[2]) const
{
    Gap[0] = Gap[1] = SkinProbe; Near[0] = Near[1] = NAME_None;
    USkeletalMeshComponent* Skinned = Mesh.Get();
    const USkeletalMesh* Skeletal = Skinned ? Skinned->GetSkeletalMeshAsset() : nullptr;
    const UPhysicsAsset* Physics = Skinned ? Skinned->GetPhysicsAsset() : nullptr;
    if (!Skeletal || !Physics) return false;
    const FReferenceSkeleton& Ref = Skeletal->GetRefSkeleton();
    const FName Hands[2] = { Bone(TEXT("hand_L")), Bone(TEXT("hand_R")) };
    if (HandSamplesFor != Physics)
    {
        HandSamplesFor = Physics; HandSamples[0].Reset(); HandSamples[1].Reset();
        TArray<FVector> Positions; TArray<int32> Dominant;
        if (ReadSkin(Skeletal, Positions, Dominant))
        {
            TSet<int32> Bodies;
            for (const USkeletalBodySetup* Setup : Physics->SkeletalBodySetups)
                if (Setup && Setup->PhysicsType != PhysType_Kinematic) Bodies.Add(Ref.FindBoneIndex(Setup->BoneName));
            const TArray<int32> Owner = SkinOwners(Ref, Dominant, [&](int32 I) { return Bodies.Contains(I); });
            for (int32 H = 0; H < 2; ++H)
            {
                const int32 HandIndex = Hands[H].IsNone() ? INDEX_NONE : Ref.FindBoneIndex(Hands[H]);
                for (int32 V = 0; V < Owner.Num(); ++V) if (HandIndex != INDEX_NONE && Owner[V] == HandIndex) HandSamples[H].Add(V);
            }
        }
    }
    const FSkeletalMeshRenderData* Render = Skeletal->GetResourceForRendering();
    const FSkinWeightVertexBuffer* Weights = Skinned->GetSkinWeightBuffer(0);
    if ((HandSamples[0].IsEmpty() && HandSamples[1].IsEmpty()) || !Render || Render->LODRenderData.Num() == 0 || !Weights) return false;
    const FSkeletalMeshLODRenderData& LOD = Render->LODRenderData[0];
    TArray<FMatrix44f> RefToLocals;
    Skinned->CacheRefToLocalMatrices(RefToLocals);
    const FTransform ToWorld = Skinned->GetComponentTransform();
    // The bodies a resting hand may reach: their shapes in their bones' spaces (which carry the bones' scale).
    struct FNearBody { FName Name; FTransform Bone; float Scale; const FKAggregateGeom* Geom; TArray<TArray<FPlane>> Planes; };
    TArray<FNearBody> Reach;
    for (const TCHAR* Contract : { TEXT("pelvis"), TEXT("spine"), TEXT("chest"), TEXT("thigh_L"), TEXT("thigh_R") })
    {
        const FName B = Bone(Contract);
        const int32 Body = B.IsNone() ? INDEX_NONE : Physics->FindBodyIndex(B);
        const int32 Index = B.IsNone() ? INDEX_NONE : Skinned->GetBoneIndex(B);
        if (Body == INDEX_NONE || Index == INDEX_NONE || !Physics->SkeletalBodySetups[Body]) continue;
        FNearBody& N = Reach.AddDefaulted_GetRef();
        N.Name = B; N.Bone = Skinned->GetBoneTransform(Index); N.Scale = float(FMath::Max(N.Bone.GetMaximumAxisScale(), 1e-4));
        N.Geom = &Physics->SkeletalBodySetups[Body]->AggGeom;
        for (const FKConvexElem& Convex : N.Geom->ConvexElems) Convex.GetPlanes(N.Planes.AddDefaulted_GetRef());
    }
    // Signed distance (bone units) from a point in the bone's space to a body's shapes: below 0 inside.
    const auto Distance = [](const FNearBody& N, const FVector& Q)
    {
        double D = TNumericLimits<double>::Max();
        for (int32 E = 0; E < N.Geom->ConvexElems.Num(); ++E)
        {
            const FVector P = N.Geom->ConvexElems[E].GetTransform().InverseTransformPosition(Q);
            double Out = -TNumericLimits<double>::Max();
            for (const FPlane& Plane : N.Planes[E]) Out = FMath::Max(Out, double(Plane.PlaneDot(P)));
            if (N.Planes[E].Num()) D = FMath::Min(D, Out);
        }
        for (const FKSphylElem& Capsule : N.Geom->SphylElems)
        {
            const FVector P = Capsule.GetTransform().InverseTransformPosition(Q);
            const double Half = Capsule.Length * .5;
            D = FMath::Min(D, (P - FVector(0, 0, FMath::Clamp(P.Z, -Half, Half))).Size() - Capsule.Radius);
        }
        for (const FKSphereElem& Sphere : N.Geom->SphereElems) D = FMath::Min(D, (Q - Sphere.Center).Size() - Sphere.Radius);
        return D;
    };
    for (int32 H = 0; H < 2; ++H)
        for (const int32 V : HandSamples[H])
        {
            const FVector P = ToWorld.TransformPosition(FVector(USkeletalMeshComponent::GetSkinnedVertexPosition(Skinned, V, LOD, *Weights, RefToLocals)));
            for (const FNearBody& N : Reach)
            {
                const float D = float(Distance(N, N.Bone.InverseTransformPosition(P)) * N.Scale);
                if (D < Gap[H]) { Gap[H] = D; Near[H] = N.Name; }
            }
        }
    return true;
}

FString URidePhysicalRider::Describe() const
{
    if (!Control) return TEXT("phys=off");
    const FVector Hips = GetPelvisLocation();
    FString Skin;
    if (CVarRideSkinCheck.GetValueOnGameThread() != 0)
    {
        float Depth, Groups[SkinGroupCount]; FName Bone;
        if (MeasureSkinDepth(Depth, Bone, Groups))
        {
            Skin = FString::Printf(TEXT(" skin=%.1f skin_bone=%s skin_groups="), Depth, Bone.IsNone() ? TEXT("-") : *Bone.ToString());
            for (int32 G = 0; G < SkinGroupCount; ++G) Skin += FString::Printf(TEXT("%s%s:%.1f"), G ? TEXT(",") : TEXT(""), SkinGroupNames[G], Groups[G]);
        }
        float Gap[2]; FName Near[2];
        if (MeasureHandGap(Gap, Near))
            Skin += FString::Printf(TEXT(" hand_gap=%.1f,%.1f hand_near=%s,%s"), Gap[0], Gap[1], *Near[0].ToString(), *Near[1].ToString());
    }
    if (CVarRideJointCheck.GetValueOnGameThread() != 0)
    {
        float Past, Depth; FName Joint, Pair[2]; FVector Angles, Limits; bool bSoft = false;
        if (MeasureJoints(Past, Joint, Angles, Depth, Pair, &Limits, &bSoft))
        {
            const auto Shown = [](double L) { return L >= UE_BIG_NUMBER ? -1. : L; };
            Skin += FString::Printf(TEXT(" joint_past=%.1f joint=%s joint_angles=%.0f,%.0f,%.0f joint_limits=%.1f,%.1f,%.1f joint_soft=%d"), Past,
                *Joint.ToString(), Angles.X, Angles.Y, Angles.Z, Shown(Limits.X), Shown(Limits.Y), Shown(Limits.Z), bSoft ? 1 : 0);
            if (bBuiltAsset)
            {
                int32 OnBail, OnRiding, Lost; float Ramp;
                CheckEnvelope(OnBail, OnRiding, Lost, Ramp);
                Skin += FString::Printf(TEXT(" joint_env=%s joint_on=%d,%d joint_lost=%d joint_ramp=%.1f joint_tighten=%d"),
                    OnBail && !OnRiding ? TEXT("bail") : OnRiding && !OnBail ? TEXT("riding") : TEXT("mixed"), OnBail, OnRiding, Lost, Ramp,
                    CVarRideBailTighten.GetValueOnGameThread() != 0 ? 1 : 0);
            }
            if (!Pair[0].IsNone()) Skin += FString::Printf(TEXT(" pair_depth=%.1f pair=%s-%s"), Depth, *Pair[0].ToString(), *Pair[1].ToString());
            Skin += FString::Printf(TEXT(" pairs_kept=%d pairs_released=%d"), IgnoredPairs.Num(), PairsReleased);
        }
    }
    const FBodyInstance* Pelvis = Mesh ? Mesh->GetBodyInstance(PelvisBone) : nullptr;
    const FVector HipsVelocity = Pelvis ? Pelvis->GetUnrealWorldVelocity() : FVector::ZeroVector;
    return FString::Printf(TEXT("phys=%s sim=%d w=%.2f pelvis_err=%.1f foot_err=%.1f worst_err=%.1f hips=%.1f,%.1f,%.1f hips_vel=%.0f,%.0f,%.0f lie=%.1f drag=%.2f getup=%.2f bail_kind=%s bodies=%d pa=%s frame=%s skipped=%d"),
        *PhaseName(Phase).ToString(), bSimulating, Weight, PelvisError, FootError, WorstError, Hips.X, Hips.Y, Hips.Z,
        HipsVelocity.X, HipsVelocity.Y, HipsVelocity.Z, bBail ? HipsAboveGround : -1.f, BailDragApplied, GetGetUpAlpha(),
        !bBailOffered ? TEXT("none") : LastBailKind == ERideBailKind::RunOut ? TEXT("runout") : TEXT("fall"),
        Mesh ? Mesh->Bodies.Num() : 0, !bBuiltAsset ? TEXT("rider") : BuiltFitted > 0 ? TEXT("skin") : TEXT("contract"), bBoardFrame ? TEXT("board") : TEXT("world"),
        Cast<URidePhysicsControl>(Control) ? Cast<URidePhysicsControl>(Control)->Skipped : 0) + Skin;
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
    // Thrown at riding speed it moves more than its own thickness in a step: swept, not stepped, through physics.
    LooseBoard->SetUseCCD(true);
    LooseBoard->SetSimulatePhysics(true);
    LooseLast = LooseBoard->GetComponentTransform();
    LooseBoard->SetPhysicsLinearVelocity(Velocity * .85f + FVector(0, 0, 90.f));
    // A tumble of its own, drawn from the bail's velocity so a replay throws it the same way.
    FRandomStream Tumble{int32(GetTypeHash(FIntVector(Velocity)))};
    LooseBoard->SetPhysicsAngularVelocityInRadians(BoardSpin +
        Deck.GetForwardVector() * Tumble.FRandRange(-7.f, 7.f) + Deck.GetRightVector() * Tumble.FRandRange(-4.f, 4.f));

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
    // toward the clip, within the bail's envelope (ApplyJointLimits). The anchors hold the bodies in the frame of the kinematic root body,
    // and in a bail the ride stops the root on the bail's frame, then carries it to the ground under the body a frame
    // late (on a quarter, from the board on the wall to whatever lies below the hips): held to that frame even for a
    // moment, the body is braked to a stop or flung.
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(ERidePhysicalPhase::Bail);
    ApplyJointLimits(false, false);
    ApplyBailMaterial(true);
    // The profile reaches the bodies at Physics Control's next update. One that already ran this frame left the
    // riding anchors on for this frame's physics, toward a root the ride holds still as it bails: applied now, the
    // bodies are let go in this frame's step.
    const URidePhysicsControl* Guarded = Cast<URidePhysicsControl>(Control);
    const bool bUpdatedBefore = Guarded && Guarded->UpdatedFrame == GFrameCounter;
    const bool bApplyNow = CVarRideBailApplyNow.GetValueOnGameThread() != 0;
    if (bApplyNow) Control->UpdateControls(0.f);
    // The limits as Physics Control left them: every joint should hold what ApplyEnvelopes set.
    {
        int32 OnBail, OnRiding; float Ramp;
        CheckEnvelope(OnBail, OnRiding, EnvelopeLostAtStart, Ramp);
        if (bBuiltAsset)
            UE_LOG(LogTemp, Display, TEXT("SKATE ride ragdoll joints: %d in the bail's envelope, %d in the riding one, %d not as set; limits open up to %.1f degrees past the envelope for the pose the bail began in"),
                OnBail, OnRiding, EnvelopeLostAtStart, Ramp);
    }

    BailStart = BailHips = GetPelvisLocation();
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
    const FBodyInstance* PelvisBody = Mesh->GetBodyInstance(PelvisBone);
    BailFrame = GFrameCounter; BailTraced = 0;
    BailPelvisVelocity = PelvisBody ? PelvisBody->GetUnrealWorldVelocity() : FVector::ZeroVector;
    UE_LOG(LogTemp, Display, TEXT("SKATE ride ragdoll (%s physics asset, %d bodies, %s) at %.0f cm/s, the pelvis at %.0f cm/s (frame %llu; controls updated %s this frame, %s)"),
        bBuiltAsset ? TEXT("contract") : TEXT("rider's"), Mesh->Bodies.Num(), bWasSimulating ? TEXT("active") : TEXT("from animation"), Velocity.Size(),
        BailPelvisVelocity.Size(), GFrameCounter, bUpdatedBefore ? TEXT("before the bail") : TEXT("not yet"),
        bApplyNow ? TEXT("the bail's applied now") : TEXT("the bail's left to the next update"));
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
    if (BailTraced < CVarRideBailTrace.GetValueOnGameThread())
    {
        // Before this frame's physics: the first line is the bail's own frame, the next shows what its step did.
        ++BailTraced;
        FVector Momentum = FVector::ZeroVector; double Mass = 0;
        for (const FBodyInstance* B : Mesh->Bodies)
            if (B && B->IsInstanceSimulatingPhysics()) { const float M = B->GetBodyMass(); Momentum += B->GetUnrealWorldVelocity() * M; Mass += M; }
        const FVector Bodies = Mass > 0 ? Momentum / Mass : FVector::ZeroVector;
        const FVector PV = Pelvis ? Pelvis->GetUnrealWorldVelocity() : FVector::ZeroVector;
        const FBodyInstance* RootBody = RootBone.IsNone() ? nullptr : Mesh->GetBodyInstance(RootBone);
        const FVector RootAt = RootBody ? RootBody->GetUnrealWorldTransform().GetLocation() : FVector::ZeroVector;
        const FVector Actor = Rider->GetActorLocation();
        const URidePhysicsControl* Guarded = Cast<URidePhysicsControl>(Control);
        UE_LOG(LogTemp, Display, TEXT("SKATE ride bail trace +%llu: pelvis (%.0f, %.0f, %.0f) cm/s (%.0f at the bail), bodies (%.0f, %.0f, %.0f); ")
            TEXT("hips (%.1f, %.1f, %.1f), root body (%.1f, %.1f, %.1f), actor (%.1f, %.1f, %.1f); controls updated at +%lld"),
            GFrameCounter - BailFrame, PV.X, PV.Y, PV.Z, BailPelvisVelocity.Size(), Bodies.X, Bodies.Y, Bodies.Z,
            Hips.X, Hips.Y, Hips.Z, RootAt.X, RootAt.Y, RootAt.Z, Actor.X, Actor.Y, Actor.Z,
            Guarded ? int64(Guarded->UpdatedFrame) - int64(BailFrame) : int64(-999));
    }
    // A body that gains speed or height it was never given has met something it cannot resolve; one whose pelvis
    // crossed a face since the last update, and is cut off from the floor it was thrown over, went through it (a floor
    // it was pressed under, a wall it tunnelled), and the ride would follow it there. A face is hit from either side
    // (Chaos turns a triangle's normal toward the ray), so the crossing alone does not tell going in from coming out: a
    // pelvis the solver pushes back out of a wall crosses it too, onto the floor's side. A pelvis that only reaches a
    // face is checked again from where it was, next update (while that is near: a pelvis rounding a corner moves on).
    bool bThrough = false, bTouch = false;
    FString Crossed;
    {
        FHitResult Hit, Cut;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideThrough), false, Rider);
        if (LooseBoard) Params.AddIgnoredComponent(LooseBoard.Get());
        UWorld* World = Rider->GetWorld();
        if (!Hips.ContainsNaN() && World->LineTraceSingleByChannel(Hit, BailHips, Hips, ECC_Pawn, Params) && !Hit.bStartPenetrating)
        {
            if (Hit.Distance > FVector::Dist(BailHips, Hips) - ThroughTouch) bTouch = FVector::Dist(BailHips, Hips) < ThroughKeep;
            else if (World->LineTraceSingleByChannel(Cut, BailFloor + FVector(0, 0, ThroughFloorUp), Hips, ECC_Pawn, Params))
            {
                bThrough = true;
                const UPrimitiveComponent* Face = Hit.GetComponent();
                Crossed = FString::Printf(TEXT(", through %s/%s at (%.0f, %.0f, %.0f)"), Face && Face->GetOwner() ? *Face->GetOwner()->GetName() : TEXT("?"),
                    Face ? *Face->GetName() : TEXT("?"), Hit.ImpactPoint.X, Hit.ImpactPoint.Y, Hit.ImpactPoint.Z);
            }
        }
        if (!bThrough && !bTouch && Hips.Z < BailFloor.Z - 120.f)
        {
            bThrough = World->LineTraceSingleByChannel(Hit, Hips, Hips + FVector(0, 0, 400.f), ECC_Pawn, Params) && Hit.ImpactNormal.Z < -.5f;
            if (bThrough) Crossed = TEXT(", under the floor");
        }
    }
    if (!bTouch) BailHips = Hips;
    if (Speed > BailLimit || Hips.Z > BailStart.Z + BailRise || bThrough || Hips.ContainsNaN())
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride ragdoll unstable (%.0f cm/s, %.0f cm from the start%s)"), Speed, Hips.Z - BailStart.Z, *Crossed);
        return ERideBodyState::Unstable;
    }
    if (!IgnoredPairs.IsEmpty() && CVarRideSelfCollision.GetValueOnGameThread() != 0) ReleaseKeptPairs();
    UpdateRamp(Dt);
    {
        const float Fade = CVarRideBailDriveFade.GetValueOnGameThread();
        ApplyDriveFade(Fade > 0.f ? FMath::Square(FMath::Clamp(1.f - BailTime / Fade, 0.f, 1.f)) : 1.f);
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
    // Down near the ground the body slides, and drags (BailDrag, coming in over BailDragFrom..BailDragFull): a body
    // still in the air falls and flies freely.
    const URidePhysicalSettings* S = GetDefault<URidePhysicalSettings>();
    const bool bSliding = HipsAboveGround >= 0.f && HipsAboveGround < SlideHeight;
    ApplyBailDrag(bSliding ? S->BailDrag * FMath::SmoothStep(S->BailDragFrom, S->BailDragFull, BailTime) : 0.f);
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
    ApplyBailDrag(0.f);
    ApplyDriveFade(1.f);
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
    // The bodies' shapes, and how low each one lay.
    GetUpShapes.Reset();
    if (const UPhysicsAsset* Physics = Mesh->GetPhysicsAsset())
        for (const USkeletalBodySetup* Body : Physics->SkeletalBodySetups)
        {
            const int32 Bone = Body ? Mesh->GetBoneIndex(Body->BoneName) : INDEX_NONE;
            if (!SnapshotWorld.IsValidIndex(Bone) || Bone == 0 || Body->CollisionReponse == EBodyCollisionResponse::BodyCollision_Disabled) continue;
            FGetUpShape Shape; Shape.Bone = Bone;
            ShapePoints(Body->AggGeom, Shape.Points);
            if (Shape.Points.IsEmpty()) continue;
            Shape.SnapshotLow = UE_DOUBLE_BIG_NUMBER;
            for (const FVector& P : Shape.Points) Shape.SnapshotLow = FMath::Min(Shape.SnapshotLow, SnapshotWorld[Bone].TransformPosition(P).Z);
            GetUpShapes.Add(MoveTemp(Shape));
        }
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
    ApplyBailDrag(0.f);
    ApplyDriveFade(1.f);
    ApplyJointLimits(true, true);
    Phase = ERidePhysicalPhase::Off;
    ApplyPhase(ERidePhysicalPhase::GetUp);
}

float URidePhysicalRider::GetGetUpAlpha() const
{
    return GetUpTime >= 0.f ? FMath::Clamp(GetUpTime / FMath::Max(.05f, GetDefault<URidePhysicalSettings>()->GetUpBlend), 0.f, 1.f) : 1.f;
}

FTransform URidePhysicalRider::ShownTransform(const USceneComponent* Component)
{
    // Inside CharacterMovement's move the actor's children keep the transform they had until the move ends
    // (FScopedMovementUpdate): measured from the parent, the transform they take this frame.
    const USceneComponent* Parent = Component ? Component->GetAttachParent() : nullptr;
    if (!Parent || Component->IsUsingAbsoluteLocation() || Component->IsUsingAbsoluteRotation() || Component->IsUsingAbsoluteScale())
        return Component ? Component->GetComponentTransform() : FTransform::Identity;
    return Component->GetRelativeTransform() * Parent->GetSocketTransform(Component->GetAttachSocketName());
}

// The snapshot as a local pose of the current component: bones under the root keep their place in the world at
// alpha 0, the root itself is the pose's, so the body moves straight from where it lay to the clip.
bool URidePhysicalRider::BlendFromSnapshot(TArray<FTransform>& LocalPose, float Alpha) const
{
    const USkeletalMeshComponent* Target = SnapshotComponent.Get();
    if (Alpha >= 1.f || !Target || !SnapshotMesh.IsValid() || Target->GetSkeletalMeshAsset() != SnapshotMesh.Get()) return false;
    const FReferenceSkeleton& Ref = SnapshotMesh->GetRefSkeleton();
    if (LocalPose.Num() != Ref.GetNum() || SnapshotWorld.Num() != Ref.GetNum()) return false;
    const FTransform Component = ShownTransform(Target);
    const float A = FMath::SmoothStep(0.f, 1.f, FMath::Clamp(Alpha, 0.f, 1.f));
    // Each bone's height, and each body shape's lowest point, at the blend's two ends: where it lay, and in the pose
    // it rises to.
    const auto Heights = [&](TArray<double>& Out, TArray<double>& Low)
    {
        TArray<FTransform> Space; Space.SetNum(LocalPose.Num()); Out.SetNum(LocalPose.Num());
        for (int32 I = 0; I < LocalPose.Num(); ++I)
        {
            const int32 Parent = Ref.GetParentIndex(I);
            Space[I] = Parent >= 0 ? LocalPose[I] * Space[Parent] : LocalPose[I];
            Out[I] = Component.TransformPosition(Space[I].GetLocation()).Z;
        }
        Low.SetNum(GetUpShapes.Num());
        for (int32 S = 0; S < GetUpShapes.Num(); ++S)
        {
            const FTransform World = Space.IsValidIndex(GetUpShapes[S].Bone) ? Space[GetUpShapes[S].Bone] * Component : Component;
            Low[S] = UE_DOUBLE_BIG_NUMBER;
            for (const FVector& P : GetUpShapes[S].Points) Low[S] = FMath::Min(Low[S], World.TransformPosition(P).Z);
        }
    };
    TArray<double> Risen, Shown, RisenLow, ShownLow;
    Heights(Risen, RisenLow);
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
    // Joint by joint, the rotations swing a limb through the floor on its way from lying to standing (a foot 15 cm
    // under it half way up). No bone, and no body's shape, goes lower than the lower of its two ends: the root rises
    // by the deepest shortfall. The shapes carry the skin past the bones (a toe 4 cm under the floor while its ankle
    // stayed above).
    Heights(Shown, ShownLow);
    double Lift = 0.;
    for (int32 I = 1; I < Shown.Num(); ++I) Lift = FMath::Max(Lift, FMath::Min(SnapshotWorld[I].GetLocation().Z, Risen[I]) - Shown[I]);
    for (int32 S = 0; S < GetUpShapes.Num(); ++S) Lift = FMath::Max(Lift, FMath::Min(GetUpShapes[S].SnapshotLow, RisenLow[S]) - ShownLow[S]);
    if (Lift > 0.) LocalPose[0].AddToTranslation(Component.InverseTransformVector(FVector(0, 0, Lift)));
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
    TakenLast = LooseLast;
    return Board;
}

void URidePhysicalRider::GuardBoards()
{
    GuardBoard(LooseBoard, LooseLast);
    GuardBoard(TakenBoard.Get(), TakenLast);
}

void URidePhysicalRider::GuardBoard(UPrimitiveComponent* Board, FTransform& Last)
{
    // The board's own world and owner: a handed-over board outlives the body (End clears Rider).
    UWorld* World = Board ? Board->GetWorld() : nullptr;
    if (!World) return;
    const FTransform Now(Board->GetComponentQuat(), Board->GetComponentLocation());
    // Not simulating (held, lying still), barely moved or turned, or placed (a first frame, a teleport): nothing to sweep.
    const double Moved = FVector::DistSquared(Last.GetLocation(), Now.GetLocation());
    const bool bTurned = Last.GetRotation().AngularDistance(Now.GetRotation()) > 1e-3;
    if (!Board->IsSimulatingPhysics() || (Moved < .01 && !bTurned) || Moved > FMath::Square(BoardGuardReach)) { Last = Now; return; }
    // A little inside the box, so the ground physics already holds it on is not a hit.
    const UBoxComponent* Box = Cast<UBoxComponent>(Board);
    const FVector Extent = ((Box ? Box->GetScaledBoxExtent() : FVector(Board->Bounds.SphereRadius)) - FVector(BoardGuardInset)).ComponentMax(FVector(.5f));
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardGuard), false, Board->GetOwner());
    Params.AddIgnoredComponent(Board);
    const FTransform From(Last.GetRotation(), Last.GetLocation());
    for (int32 Try = 0; Try < 3; ++Try)
    {
        FHitResult Hit; FTransform Reached;
        if (!FRideClipPlayer::SweepBox(*World, From, Now, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, Hit, &Reached)) break;
        // What moves is physics' own to push.
        UPrimitiveComponent* Other = Hit.GetComponent();
        if (Other && Other->IsSimulatingPhysics()) { Params.AddIgnoredComponent(Other); continue; }
        FTransform Back;
        if (!Hit.bStartPenetrating) Back = FTransform(Reached.GetRotation(), Reached.GetLocation() + Hit.Normal * .2f);
        else if (Hit.Time > 0.f)
            Back = FTransform(FQuat::Slerp(From.GetRotation(), Now.GetRotation(), Hit.Time).GetNormalized(), FMath::Lerp(From.GetLocation(), Now.GetLocation(), double(Hit.Time)));
        else
        {
            // It was already inside something where it was last (it started there): physics taking it out to a free
            // pose, by a way its centre can go, is left alone; otherwise it stays.
            FHitResult There, Between;
            if (!FRideClipPlayer::SweepBox(*World, Now, Now, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, There) &&
                !World->LineTraceSingleByChannel(Between, From.GetLocation(), Now.GetLocation(), ECC_Pawn, Params))
                break;
            Back = From;
        }
        // Physics passed or turned into this face (it does not see it, or stepped over it): back to the last pose found
        // free, the velocity into the face turned back as a bounce; a turn into it stops.
        Board->SetWorldLocationAndRotation(Back.GetLocation(), Back.GetRotation(), false, nullptr, ETeleportType::TeleportPhysics);
        const FVector Normal = Hit.Normal;
        const FVector Velocity = Board->GetPhysicsLinearVelocity();
        const float Into = float(FVector::DotProduct(Velocity, Normal));
        if (Normal.IsNearlyZero()) Board->SetPhysicsLinearVelocity(FVector::ZeroVector);
        else if (Into < 0.f) Board->SetPhysicsLinearVelocity(Velocity - Normal * Into * (1.f + BoardGuardBounce));
        if (Hit.bStartPenetrating) Board->SetPhysicsAngularVelocityInRadians(FVector::ZeroVector);
        Last = Back;
        return;
    }
    Last = Now;
}

void URidePhysicalRider::DropLooseBoard()
{
    if (!LooseBoard) return;
    LooseBoard->SetSimulatePhysics(false);
    LooseBoard->DestroyComponent();
    LooseBoard = nullptr;
}

void URidePhysicalRider::PlaceLooseBoard(const FTransform& Deck)
{
    if (!LooseBoard) return;
    if (LooseBoard->IsSimulatingPhysics()) LooseBoard->SetSimulatePhysics(false);
    const FQuat Rotation = Deck.GetRotation();
    LooseBoard->SetWorldLocationAndRotation(Deck.GetLocation() - Rotation.GetUpVector() * LooseBoardDrop * BoardScale, Rotation,
        false, nullptr, ETeleportType::TeleportPhysics);
    LooseLast = LooseBoard->GetComponentTransform();
}

void URidePhysicalRider::ReleaseLooseBoard(const FVector& Velocity, const FVector& Spin)
{
    if (!LooseBoard || LooseBoard->IsSimulatingPhysics()) return;
    // The box's centre is below the deck it was placed by: it moves with the deck's velocity and the turn about it.
    const FVector Arm = LooseBoard->GetComponentLocation() - GetLooseBoardDeck().GetLocation();
    // Native's board (a deck, trucks and wheels) fits where the box may not: lifted out of what it would start inside,
    // which the guard (GuardBoard) would otherwise hold it in.
    if (UWorld* World = LooseBoard->GetWorld())
    {
        const FVector Extent = (LooseBoard->GetScaledBoxExtent() - FVector(BoardGuardInset)).ComponentMax(FVector(.5f));
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardRelease), false, LooseBoard->GetOwner());
        Params.AddIgnoredComponent(LooseBoard.Get());
        const FTransform At(LooseBoard->GetComponentQuat(), LooseBoard->GetComponentLocation());
        for (int32 Step = 0, Tries = 0; Step <= 10 && Tries < 20; ++Tries)
        {
            const FTransform Try(At.GetRotation(), At.GetLocation() + FVector(0, 0, 3.f * Step));
            FHitResult Hit;
            if (!FRideClipPlayer::SweepBox(*World, Try, Try, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, Hit))
            {
                if (Step > 0) LooseBoard->SetWorldLocationAndRotation(Try.GetLocation(), Try.GetRotation(), false, nullptr, ETeleportType::TeleportPhysics);
                break;
            }
            // What moves is physics' own to push.
            UPrimitiveComponent* Other = Hit.GetComponent();
            if (Other && Other->IsSimulatingPhysics()) Params.AddIgnoredComponent(Other); else ++Step;
        }
    }
    LooseBoard->SetSimulatePhysics(true);
    LooseBoard->SetPhysicsLinearVelocity(Velocity + FVector::CrossProduct(Spin, Arm));
    LooseBoard->SetPhysicsAngularVelocityInRadians(Spin);
    LooseLast = LooseBoard->GetComponentTransform();
}

// ---------------------------------------------------------------------------------------------------------------
// The world around the body. Surfaces that only answer queries (the character walks on those) become physical near
// the body so its bodies and the loose board can touch them, and go back when the body has left.

// An instance's own body: none for an index out of range (GetBodyInstance falls back to the component's template).
static FBodyInstance* InstanceBody(UInstancedStaticMeshComponent* Mesh, int32 Index)
{
    if (!Mesh || Index < 0 || Index >= Mesh->GetInstanceCount()) return nullptr;
    FBodyInstance* Body = Mesh->GetBodyInstance(NAME_None, false, Index);
    return Body && Body != &Mesh->BodyInstance && Body->InstanceBodyIndex == Index ? Body : nullptr;
}

// How far an instance's bounds are from At (0 within them).
static double InstanceAway(const UInstancedStaticMeshComponent& Mesh, int32 Index, const FVector& At)
{
    FTransform Where;
    if (!Mesh.GetStaticMesh() || !Mesh.GetInstanceTransform(Index, Where, true)) return 0.;
    const FBoxSphereBounds Bounds = Mesh.GetStaticMesh()->GetBounds().TransformBy(Where);
    return FMath::Max(0., FVector::Dist(Bounds.Origin, At) - Bounds.SphereRadius);
}

// An instance's collision (its body is made again, by itself, when physics comes or goes).
// An instance body's switch rebuilds the body (FInstancedMeshComponentBodies::Recreate), which copies its responses and
// profile but not its object type: the new body is put back to the old one's type, or a WorldDynamic instance would come
// back WorldStatic.
static void SetInstanceCollision(UInstancedStaticMeshComponent* Mesh, int32 Index, ECollisionEnabled::Type Type)
{
    FBodyInstance* Body = InstanceBody(Mesh, Index);
    if (!Body) return;
    const ECollisionChannel Type0 = Body->GetObjectType();
    Body->SetCollisionEnabled(Type);
    if (FBodyInstance* Made = InstanceBody(Mesh, Index); Made && Made->GetObjectType() != Type0) Made->SetObjectType(Type0);
}

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
    for (int32 I = MadeInstances.Num() - 1; I >= 0; --I)
    {
        UInstancedStaticMeshComponent* M = MadeInstances[I].Mesh.Get();
        const int32 Index = MadeInstances[I].Index;
        if (!M) { MadeInstances.RemoveAtSwap(I); continue; }
        const double FromBoard = Board ? InstanceAway(*M, Index, Board->GetComponentLocation()) : 1e30;
        if (InstanceAway(*M, Index, Centre) > Radius * 2. && FromBoard > Radius) { SetInstanceCollision(M, Index, ECollisionEnabled::QueryOnly); MadeInstances.RemoveAtSwap(I); }
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
        // An instanced mesh (a village's houses and lots, a forest): each instance near, by itself; switching a whole
        // one would hitch, and the component's own switch never reaches its instances' bodies anyway.
        if (UInstancedStaticMeshComponent* Instanced = Cast<UInstancedStaticMeshComponent>(C))
        {
            const int32 Index = Hit.ItemIndex;
            const FBodyInstance* Body = InstanceBody(Instanced, Index);
            if (Body && Body->GetCollisionEnabled() == ECollisionEnabled::QueryOnly)
            {
                SetInstanceCollision(Instanced, Index, ECollisionEnabled::QueryAndPhysics);
                MadeInstances.Add({Instanced, Index});
            }
            continue;
        }
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
    for (int32 I = MadeInstances.Num() - 1; I >= 0; --I)
    {
        UInstancedStaticMeshComponent* M = MadeInstances[I].Mesh.Get();
        if (!M) { MadeInstances.RemoveAtSwap(I); continue; }
        if (Board && Board->IsSimulatingPhysics() && InstanceAway(*M, MadeInstances[I].Index, Board->GetComponentLocation()) < Radius) continue;
        SetInstanceCollision(M, MadeInstances[I].Index, ECollisionEnabled::QueryOnly);
        MadeInstances.RemoveAtSwap(I);
    }
    PhysicalCentre = FVector(1e30);
}
