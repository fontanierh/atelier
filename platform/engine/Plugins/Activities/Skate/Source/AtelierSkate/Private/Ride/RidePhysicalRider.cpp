// The physical rider: see RidePhysicalRider.h and RIDE.md, "Physical rider".
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

namespace RidePhysicalRiderDetail
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
