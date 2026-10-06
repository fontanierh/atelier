// URidePhysicalRider bails and the get-up (RidePhysicalRider.cpp).
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
