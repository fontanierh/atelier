// USkateComponent getting on and off the board with the Ride backend (RIDE.md, "Transitions"): one continuous
// character. The actor is never moved to a new place: the capsule changes about its centre and settles onto the floor,
// the mesh keeps its world place across each switch and eases back onto the capsule, the pose switch is a standard
// inertialization (FAnimNode_SkateRider), the speed carries over both ways, and the board is always a real object
// that dissolves in and out rather than popping.
//
// Off the board the native clips play through the clip player's animator (FRideClipPlayer::Step) and are
// retargeted like a ride (PublishOffBoardPose): the board-carry locomotion on the character's own movement, and the
// mount and dismount clips, whose root motion moves the capsule through a root motion source. In the air no clip moves
// the capsule: CharacterMovement keeps the fall, and the clip's trajectory follows the capsule (a jump with the board in
// hand, the board thrown under the feet, a step off the board in the air), then a landing clip takes over.
//
// A bail can end on foot too: a slow one runs out (RUNOUT_*, the board rolling on), and a fallen body asked to stay
// on foot gets up where it lies (W_RECOVERY_*, blended out of the fallen pose). A board left lying can be stepped onto,
// and one kicked away in the air (BR_KICKOUT_*) flies on as a projectile.
#include "RideTransition.h"
#include "RideTransitionDetail.h"
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "RideClipPlayer.h"
#include "RideAnimator.h"
#include "RideAnimInstance.h"
#include "RidePhysicalRider.h"
#include "RideTuning.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameFramework/RootMotionSource.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/OverlapResult.h"
#include "PhysicsEngine/BodyInstance.h"

using namespace RideTransitionDetail;

namespace RideTransitionDetail
{
    TAutoConsoleVariable<int32> CVarRideTrace(TEXT("skate.RideTrace"), 0,
        TEXT("Log this many frames of the body after each switch between riding and on foot (a pose blend, the mode, the clip): ")
        TEXT("the actor, the mesh, and the pelvis and facing published and shown (0: off)."));
}

FRideTransition& USkateComponent::Transit()
{
    if (!Transition) Transition = MakeShared<FRideTransition>();
    return *Transition;
}

bool USkateComponent::WantsGetUpOnFoot() const { return Transition && Transition->bGetUpOnFoot; }

// ---------------------------------------------------------------------------------------------------------------
// The clips.

bool USkateComponent::PrepareRideClips()
{
    if (!Rider || USkateSettings::ActiveBackend() != ESkateBackend::Ride) return false;
    FRideTransition& T = Transit();
    if (!Clips) PreloadRide();
    FRideAnimator& Animator = Clips->GetAnimator();
    if (!Animator.HasClips()) Clips->Preload();
    if (!Animator.HasClips()) return false;
    // The pose mesh lives on the rider from now on (a ride keeps it).
    Animator.Attach(Rider);
    if (!Animator.HasRig()) return false;
    if (!T.bClipsTried)
    {
        // Load every transition clip now (while walking), not at the first mount, and the board's dissolve.
        T.bClipsTried = true; T.bClips = true;
        LoadBoardFade();
        for (int32 I = 0; I < 4; ++I)
        {
            T.Cycle[I] = Animator.Clip(CycleNames[I]);
            T.CycleLength[I] = FMath::Max(.05f, Length(T.Cycle[I]));
            T.CycleStride[I] = T.Cycle[I] ? float(FRideAnimator::RootMotion(T.Cycle[I], 0.f, T.CycleLength[I]).GetTranslation().Size2D()) : 0.f;
            T.CycleSpeed[I] = T.CycleStride[I] / T.CycleLength[I];
            T.bClips &= T.Cycle[I] != nullptr;
        }
        Animator.Clip(TEXT("BR_STAND_0_INTO_MOUNT"));
        for (int32 Gait = 1; Gait < 4; ++Gait)
            for (int32 Variant = 0; Variant < 4; ++Variant) Animator.Clip(*FString::Printf(TEXT("BR_%s_FWD_%d_INTO_MOUNT"), Gaits[Gait], Variant * 25));
        for (const TCHAR* Height : {TEXT("HI"), TEXT("LO")})
        {
            Animator.Clip(*FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_RUN_FWD"), Height));
            Animator.Clip(*FString::Printf(TEXT("BR_DISMOUNT_FAST_%s_INTO_RUN_FWD"), Height));
            Animator.Clip(*FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_STAND_0"), Height));
        }
        // In the air: the jumps with the board in hand, the landings, the board thrown under the feet, the steps off it.
        for (const TCHAR* Name : {TEXT("JBR_STAND_0_TO_SML_FWD_0"), TEXT("JBR_RUN_FWD_0_TO_SML_FWD_25"), TEXT("JBR_RUN_FWD_25_TO_SML_FWD_25"),
            TEXT("JBR_RUN_FWD_50_TO_SML_FWD_75"), TEXT("JBR_RUN_FWD_75_TO_SML_FWD_75"), TEXT("JBR_AIRDISMOUNT_TO_BIG_DN_0"),
            TEXT("BR_LF_AIR_INTO_MOUNT_BSGRAB"), TEXT("BR_RF_AIR_INTO_MOUNT_BSGRAB")})
            Animator.Clip(Name);
        for (const TCHAR* Grab : {TEXT("BS"), TEXT("FS"), TEXT("DBL"), TEXT("MUTE"), TEXT("STALE")})
            Animator.Clip(*FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_BR_AIR"), Grab));
        for (const TCHAR* Size : {TEXT("SML"), TEXT("BIG")})
            for (const TCHAR* Slope : {TEXT("DN"), TEXT("FWD"), TEXT("UP")})
            {
                Animator.Clip(*FString::Printf(TEXT("BR_LAND_%s_%s_0_INTO_STAND"), Size, Slope));
                if (Size[0] == 'B' && Slope[0] == 'D') { Animator.Clip(TEXT("BR_LAND_BIG_DN_0_INTO_RUN_FWD")); continue; }
                for (const int32 Step : {25, 75}) Animator.Clip(*FString::Printf(TEXT("BR_LAND_%s_%s_%d_INTO_RUN_FWD"), Size, Slope, Step));
            }
        // Bails on foot and the kick-out.
        for (const FRunOutWay& Way : RunOutWays)
            for (const TCHAR* Height : {TEXT("HI"), TEXT("LO")})
                for (const auto& Size : Way.Sizes)
                    for (const TCHAR* Variant : Size)
                        if (Variant) Animator.Clip(*FString::Printf(TEXT("RUNOUT_%s_%s_%s_TO_RUN_FWD"), Way.Way, Height, Variant));
        for (const TCHAR* Name : Recoveries) Animator.Clip(Name);
        for (const TCHAR* Name : {TEXT("BR_KICKOUT_HI_INTO_NB_AIR"), TEXT("BR_KICKOUT_LO_INTO_NB_AIR"), TEXT("JNB_KICKOUT_TO_SML_FWD_75")})
            Animator.Clip(Name);
        UE_LOG(LogTemp, Display, TEXT("SKATE ride transitions: carry strides %.0f/%.0f/%.0f cm, speeds %.0f/%.0f/%.0f cm/s%s"),
            T.CycleStride[1], T.CycleStride[2], T.CycleStride[3], T.CycleSpeed[1], T.CycleSpeed[2], T.CycleSpeed[3], T.bClips ? TEXT("") : TEXT(", clips missing"));
    }
    return T.bClips && T.CycleSpeed[1] > 1.f && T.CycleSpeed[2] > T.CycleSpeed[1] && T.CycleSpeed[3] > T.CycleSpeed[2];
}

FVector USkateComponent::OffBoardGround() const
{
    // The floor under the capsule: the off-board clips' trajectory is on it.
    const UCharacterMovementComponent* M = Movement();
    const float Gap = M && M->IsMovingOnGround() ? M->CurrentFloor.FloorDist : FloorGap;
    return Rider->GetActorLocation() - FVector(0, 0, Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + Gap);
}

void USkateComponent::TrackFeet(float Dt)
{
    // The character's own stride, read from its feet: the left foot's lead over the right along the facing.
    FRideTransition& T = Transit();
    const USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FName Left = RiderApi->GetSkateBone(TEXT("foot_L")), Right = RiderApi->GetSkateBone(TEXT("foot_R"));
    if (!Mesh || Dt <= 0.f || Left.IsNone() || Right.IsNone() || Mesh->GetBoneIndex(Left) == INDEX_NONE || Mesh->GetBoneIndex(Right) == INDEX_NONE)
    { T.bFeetKnown = false; return; }
    const float Lead = FVector::DotProduct(Mesh->GetBoneLocation(Left) - Mesh->GetBoneLocation(Right), Rider->GetActorForwardVector());
    if (T.bFeetKnown)
    {
        T.FootRate = FMath::Lerp(T.FootRate, (Lead - T.FootDiff) / Dt, .5f);
        T.SinceCross += Dt;
        if ((Lead > 0.f) != (T.FootDiff > 0.f) && T.SinceCross > .12f)
        {
            T.HalfPeriod = FMath::Clamp(FMath::Lerp(T.HalfPeriod, T.SinceCross, .5f), .15f, .8f);
            T.SinceCross = 0.f;
        }
    }
    T.FootDiff = Lead; T.bFeetKnown = true;
}

float USkateComponent::FeetPhase(bool bMirror) const
{
    // In the carry cycles the left foot's lead goes as -A sin(2 pi phase) (phase 0: the left foot down), so the
    // phase is the angle of (-lead, -lead rate / w). A mirrored clip swaps the feet: half a cycle on.
    const FRideTransition& T = *Transition;
    const float W = PI / FMath::Max(.1f, T.HalfPeriod);
    return FMath::Frac(FMath::Atan2(-T.FootDiff, -T.FootRate / W) / (2.f * PI) + (bMirror ? .5f : 0.f));
}

// ---------------------------------------------------------------------------------------------------------------
// Every frame, after the ride's step and before the mesh animates.

void USkateComponent::TickTransition(float Dt)
{
    if (!Rider) return;
    FRideTransition& T = Transit();
    // Off the board last frame: the stick is in for the next move.
    if (T.bReleasePending) ReleaseDrive();
    // The transition clips load on foot once the Ride backend is chosen (PreloadRetailRuntime preloads the session 2 s
    // after play; a backend chosen later loads it here), not at the first mount.
    if (bRetailPreloaded && Mode == ESkateMode::Off && !T.bClipsTried && USkateSettings::ActiveBackend() == ESkateBackend::Ride)
    {
        T.ClipsRetry -= Dt;
        if (T.ClipsRetry <= 0.f) { T.ClipsRetry = 5.f; PrepareRideClips(); }
    }
    const FRideTuning& Tune = FRideTuning::Get();
    OffBoardDeckBlend = FMath::Min(1.f, OffBoardDeckBlend + Dt / FMath::Max(.01f, Tune.ClipBlend));

    // Slow, upright bails are offered to the transition first (however the ride started).
    if (PhysicalRider && !PhysicalRider->OnBailStart.IsBound()) PhysicalRider->OnBailStart.BindUObject(this, &USkateComponent::TakeRunOut);
    // A bail handed over during the ride's frame: a run-out on foot, or a fallen body getting up where it lies.
    if (T.bRunOutPending) BeginRunOut();
    if (T.bRecoverPending) { T.bRecoverPending = false; BeginRecover(); }

    // A bail left on foot: the pose rises out of the fallen body, and the rider steps off once up.
    if (T.bGetUpOnFoot)
    {
        if (Mode == ESkateMode::Off) T.bGetUpOnFoot = false;
        else
        {
            if (PhysicalRider && PhysicalRider->IsGettingUp() && PhysicalRider->GetGetUpExit() == ERideGetUpExit::OnFoot && !RetailPose.IsEmpty())
                PhysicalRider->BlendFromSnapshot(RetailPose, PhysicalRider->GetGetUpAlpha());
            const bool bUp = Mode == ESkateMode::Ground && !(PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
            if (bUp) RideDismount();
        }
    }

    // On foot, the body eases back onto the capsule that moved under it (before the off-board
    // pose is published against the mesh's place).
    if (T.MeshSettleTime >= 0.f)
    {
        T.MeshSettleTime += Dt;
        const float A = FMath::SmoothStep(0.f, 1.f, T.MeshSettleTime / FMath::Max(.01f, Tune.MeshSettle));
        SetMeshOffset(T.MeshOffsetStart * (1.f - A), FQuat::Slerp(T.MeshTurnStart, FQuat::Identity, A).GetNormalized());
        if (A >= 1.f) T.MeshSettleTime = -1.f;
    }

    // Off the board: the clips, the carry, the character's own stride (for the next mount).
    if (Mode == ESkateMode::Off)
    {
        if (USkeletalMeshComponent* Mesh = Rider->GetMesh(); Mesh && !bRideClip && T.Foot == ERideFoot::Off)
            SavedMeshRotation = T.MeshTurn.Inverse() * Mesh->GetRelativeRotation().Quaternion();
        TrackFeet(Dt);
        if (T.Foot == ERideFoot::Carry) StepCarry(Dt);
        else if (T.Foot != ERideFoot::Off) StepRideClip(Dt);
    }

    // A board lying in the world follows its own body (flying, settling, tumbling), and dissolves once the rider has
    // been out of reach for a while.
    if (T.Board == ERideBoard::World)
    {
        StepLooseBoard(Dt);
        const bool bNear = FVector::Dist(BoardRoot->GetComponentLocation(), Rider->GetActorLocation()) < Tune.BoardReach;
        T.BoardTime = bNear ? 0.f : T.BoardTime + Dt;
        if (T.BoardTime > Tune.BoardLyingTime && T.ShownTarget > 0.f) ShowBoard(0.f, false);
    }

    // The dissolve. A lying board gone for good is dropped (and a recalled one comes back to the hand); a board put
    // away from the hand comes off it.
    if (T.Shown != T.ShownTarget)
    {
        T.Shown = FMath::FInterpConstantTo(T.Shown, T.ShownTarget, Dt, 1.f / FMath::Max(.01f, Tune.BoardDissolveTime));
        ApplyBoardShown();
        if (T.Shown <= 0.f && T.Board == ERideBoard::World)
        {
            DropLyingBoard();
            if (T.bRecall && Mode == ESkateMode::Off && !bRideClip && RiderApi->CanCarrySkateBoard()) BeginCarry(0.f);
            T.bRecall = false;
        }
        else if (T.Shown <= 0.f && T.Board == ERideBoard::Hand && T.Foot == ERideFoot::Off)
        {
            T.Board = ERideBoard::Away;
            UseWorldBoard();
        }
    }

    // The speed carried off the board fades, slowly while the stick keeps the way, fast without it. It follows the
    // character's travel, so turning takes it along.
    if (T.MomentumId)
    {
        UCharacterMovementComponent* M = Movement();
        const TSharedPtr<FRootMotionSource> Source = M ? M->GetRootMotionSourceByID(T.MomentumId) : nullptr;
        if (!Source.IsValid() || Source->GetScriptStruct() != FRootMotionSource_ConstantForce::StaticStruct() || Mode != ESkateMode::Off || bRideClip) StopMomentum();
        else
        {
            const FVector Travel = M->Velocity.GetSafeNormal2D();
            if (!Travel.IsNearlyZero()) T.MomentumDirection = Travel;
            const bool bHeld = FVector::DotProduct(M->GetCurrentAcceleration().GetSafeNormal2D(), T.MomentumDirection) > .5f;
            T.Momentum = FMath::Max(0.f, T.Momentum - (bHeld ? Tune.MomentumDecay : Tune.MomentumBrake) * Dt);
            if (T.Momentum <= 1.f) StopMomentum();
            else static_cast<FRootMotionSource_ConstantForce*>(Source.Get())->Force = T.MomentumDirection * T.Momentum;
        }
    }
    TraceTransition();
}

void USkateComponent::TraceTransition()
{
    // A line a frame from the frame before a switch to skate.RideTrace frames after it. "pub" is the pose published
    // this frame where the mesh is now; "shown" is the pose the mesh evaluated last frame (it animates after this
    // component), also where the mesh is now: a jump between a frame's pub and the next frame's shown is the graph's.
    FRideTransition& T = Transit();
    const int32 Frames = CVarRideTrace.GetValueOnGameThread();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (Frames <= 0 || !Mesh) { T.TraceLeft = 0; T.TraceLast.Reset(); return; }
    const bool bPose = !RetailPose.IsEmpty();
    const bool bSwitch = PoseBlendSerial != T.TraceSerial || uint8(Mode) != T.TraceMode || uint8(T.Foot) != T.TraceFoot || bPose != T.bTracePose ||
        T.Clip != T.TraceClip;
    T.TraceSerial = PoseBlendSerial; T.TraceMode = uint8(Mode); T.TraceFoot = uint8(T.Foot); T.bTracePose = bPose; T.TraceClip = T.Clip;
    const FTransform Actor = Rider->GetActorTransform();
    const FTransform MeshWorld = Mesh->GetRelativeTransform() * Actor;
    const FName Pelvis = RiderApi->GetSkateBone(TEXT("pelvis")), Left = RiderApi->GetSkateBone(TEXT("thigh_L")), Right = RiderApi->GetSkateBone(TEXT("thigh_R"));
    FVector PubHip = FVector::ZeroVector, PubL = FVector::ZeroVector, PubR = FVector::ZeroVector;
    const bool bPub = PoseBoneWorld(Mesh, MeshWorld, RetailPose, Pelvis, PubHip) && PoseBoneWorld(Mesh, MeshWorld, RetailPose, Left, PubL) &&
        PoseBoneWorld(Mesh, MeshWorld, RetailPose, Right, PubR);
    const bool bShown = !Pelvis.IsNone() && !Left.IsNone() && !Right.IsNone() && Mesh->GetBoneIndex(Pelvis) != INDEX_NONE &&
        Mesh->GetBoneIndex(Left) != INDEX_NONE && Mesh->GetBoneIndex(Right) != INDEX_NONE;
    const FVector ShownHip = bShown ? Mesh->GetBoneLocation(Pelvis) : FVector::ZeroVector;
    const float ShownFacing = bShown ? FacingYaw(Mesh->GetBoneLocation(Left), Mesh->GetBoneLocation(Right)) : 0.f;
    const FVector Loc = Actor.GetLocation();
    FString Line = FString::Printf(TEXT("SKATE trace f%llu t%.3f serial %u/%.2f mode %d foot %d %s@%.3f pose %d actor (%.1f %.1f %.1f) yaw %.1f ")
        TEXT("mesh yaw %.1f (cached %.1f) turn %.1f saved %.1f offset (%.1f %.1f %.1f) pub hip (%.1f %.1f %.1f) face %.1f shown hip (%.1f %.1f %.1f) face %.1f"),
        GFrameCounter, GetWorld()->GetTimeSeconds(), PoseBlendSerial, PoseBlendTime, int32(Mode), int32(T.Foot),
        T.Clip ? *T.Clip->GetName() : TEXT("-"), T.ClipTime, RetailPose.Num(), Loc.X, Loc.Y, Loc.Z, Actor.Rotator().Yaw,
        MeshWorld.Rotator().Yaw, Mesh->GetComponentTransform().Rotator().Yaw, T.MeshTurn.Rotator().Yaw, SavedMeshRotation.Rotator().Yaw,
        T.MeshOffset.X, T.MeshOffset.Y, T.MeshOffset.Z, PubHip.X, PubHip.Y, PubHip.Z, bPub ? FacingYaw(PubL, PubR) : 0.f,
        ShownHip.X, ShownHip.Y, ShownHip.Z, ShownFacing);
    // The speed: the character's velocity and acceleration, its own before the momentum is added, the drive, the
    // stick given to the next move and the speed it may run at.
    if (const UCharacterMovementComponent* M = Movement())
    {
        const FVector V = M->Velocity, A = M->GetCurrentAcceleration(), Pre = M->CurrentRootMotion.LastPreAdditiveVelocity;
        const FVector Stick = Rider->GetPendingMovementInputVector();
        Line += FString::Printf(TEXT(" vel (%.0f %.0f %.0f) acc (%.0f %.0f) pre (%.0f %.0f)%s mom %.0f drive %s(%.0f %.0f)%s in (%.2f %.2f) max %.0f mm %d"),
            V.X, V.Y, V.Z, A.X, A.Y, Pre.X, Pre.Y, M->CurrentRootMotion.bIsAdditiveVelocityApplied ? TEXT("+") : TEXT(""), T.Momentum,
            T.DriveId ? TEXT("") : TEXT("off "), T.DriveVelocity.X, T.DriveVelocity.Y, T.bReleasePending ? TEXT(" releasing") : TEXT(""),
            Stick.X, Stick.Y, M->GetMaxSpeed(), int32(M->MovementMode.GetValue()));
    }
    if (bSwitch)
    {
        if (T.TraceLeft <= 0 && !T.TraceLast.IsEmpty()) UE_LOG(LogTemp, Display, TEXT("%s (before)"), *T.TraceLast);
        T.TraceLeft = Frames;
    }
    if (T.TraceLeft > 0)
    {
        UE_LOG(LogTemp, Display, TEXT("%s%s"), *Line, bSwitch ? TEXT(" SWITCH") : TEXT(""));
        --T.TraceLeft;
    }
    T.TraceLast = Line;
}

void USkateComponent::ResetTransition()
{
    bRideClip = false; PendingPoseBlend = 0.f;
    if (!Transition) return;
    FRideTransition& T = *Transition;
    StopMomentum(); StopDrive();
    DropLyingBoard();
    if (Clips && T.Foot != ERideFoot::Off) Clips->GetAnimator().ClearOverride();
    T.Foot = ERideFoot::Off; T.Clip = nullptr; T.bCarryShown = false; T.bRecall = false;
    T.bRunOutPending = T.bRecoverPending = T.bKickOut = false; T.PendingClip = nullptr;
    if (Mode == ESkateMode::Off && !RetailPose.IsEmpty()) RetailPose.Reset();
    ReleaseBoardFromHand();
    T.Board = ERideBoard::Away; T.bGetUpOnFoot = false;
    T.Shown = T.ShownTarget = 0.f; ApplyBoardShown();
    T.MeshSettleTime = -1.f; SetMeshOffset(FVector::ZeroVector, FQuat::Identity);
}

void USkateComponent::SyncRootMotion()
{
    // A character whose anim instance takes root motion from everything has its graph updated by CharacterMovement
    // before it moves (UCharacterMovementComponent::PerformMovement), so before the ride steps and this component
    // publishes: the skate pose would show a frame late. While it shows there is no root motion to take, and the
    // graph updates in the mesh's own tick, after this component.
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    UAnimInstance* Anim = Mesh ? Mesh->GetAnimInstance() : nullptr;
    const bool bHold = Anim && !RetailPose.IsEmpty();
    if (bRootMotionHeld && (!bHold || RootMotionAnim.Get() != Anim)) ReleaseRootMotion();
    if (bHold && !bRootMotionHeld)
    {
        RootMotionAnim = Anim;
        SavedRootMotionMode = uint8(Anim->RootMotionMode.GetValue());
        Anim->RootMotionMode = ERootMotionMode::IgnoreRootMotion;
        bRootMotionHeld = true;
    }
}

void USkateComponent::ReleaseRootMotion()
{
    if (UAnimInstance* Anim = RootMotionAnim.Get(); Anim && bRootMotionHeld) Anim->RootMotionMode = ERootMotionMode::Type(SavedRootMotionMode);
    RootMotionAnim.Reset();
    bRootMotionHeld = false;
}

// ---------------------------------------------------------------------------------------------------------------
// The body and the speed.

void USkateComponent::SetMeshOffset(const FVector& Offset, const FQuat& Turn)
{
    FRideTransition& T = Transit();
    // Applied as a change, so whatever else places the mesh (a crouch) keeps its part.
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (Mesh && Mesh->GetAttachParent() == Rider->GetRootComponent())
    {
        if (!Offset.Equals(T.MeshOffset)) Mesh->SetRelativeLocation(Mesh->GetRelativeLocation() + Offset - T.MeshOffset);
        if (!Turn.Equals(T.MeshTurn, 1e-6f))
            Mesh->SetRelativeRotation((Turn * T.MeshTurn.Inverse() * Mesh->GetRelativeRotation().Quaternion()).GetNormalized());
    }
    T.MeshOffset = Offset; T.MeshTurn = Turn;
}

void USkateComponent::KeepMeshWorld(const FTransform& MeshWorld)
{
    // The actor moved or turned under the mesh: the offset and turn from the mesh's on-foot place that put it back
    // where it was in the world.
    FRideTransition& T = Transit();
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (!Mesh || Mesh->GetAttachParent() != Rider->GetRootComponent()) return;
    const FTransform Relative = MeshWorld.GetRelativeTransform(Rider->GetActorTransform());
    const FVector Home = Mesh->GetRelativeLocation() - T.MeshOffset;
    const FQuat HomeRotation = T.MeshTurn.Inverse() * Mesh->GetRelativeRotation().Quaternion();
    SetMeshOffset(Relative.GetLocation() - Home, (Relative.GetRotation() * HomeRotation.Inverse()).GetNormalized());
}

void USkateComponent::TurnActor(float Yaw)
{
    // Upright to Yaw (a clip's way): the mesh keeps its world place and rotation and eases back onto the capsule.
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (!Mesh) return;
    const FTransform MeshWorld = Mesh->GetRelativeTransform() * Rider->GetActorTransform();
    Rider->SetActorRotation(FRotator(0, Yaw, 0));
    KeepMeshWorld(MeshWorld);
    FRideTransition& T = Transit();
    T.MeshOffsetStart = T.MeshOffset; T.MeshTurnStart = T.MeshTurn; T.MeshSettleTime = 0.f;
}

void USkateComponent::StartMomentum(const FVector& Excess)
{
    StopMomentum();
    UCharacterMovementComponent* M = Movement();
    if (!M || Excess.Size() < 10.f) return;
    FRideTransition& T = Transit();
    // Additive: CharacterMovement steers and brakes the character's own velocity as usual, and adds this on top.
    TSharedPtr<FRootMotionSource_ConstantForce> Source = MakeShared<FRootMotionSource_ConstantForce>();
    Source->InstanceName = MomentumName;
    Source->AccumulateMode = ERootMotionAccumulateMode::Additive;
    Source->Priority = 5;
    Source->Force = Excess;
    Source->Duration = -1.f;                                 // until the momentum is spent (TickTransition)
    Source->Settings.SetFlag(ERootMotionSourceSettingsFlags::IgnoreZAccumulate);
    T.MomentumId = M->ApplyRootMotionSource(Source);
    T.Momentum = Excess.Size(); T.MomentumDirection = Excess.GetSafeNormal();
    // As after a move with it applied: the velocity read until the next move (the animation, the camera) is the whole
    // speed, and that move takes the character's own back first (RestorePreAdditiveRootMotionVelocity).
    const FVector Own = M->Velocity;
    M->Velocity = Own + FVector(Excess.X, Excess.Y, 0.f);
    M->CurrentRootMotion.LastPreAdditiveVelocity = Own;
    M->CurrentRootMotion.bIsAdditiveVelocityApplied = true;
}

void USkateComponent::StopMomentum()
{
    if (!Transition) return;
    FRideTransition& T = *Transition;
    if (T.MomentumId) if (UCharacterMovementComponent* M = Movement()) M->RemoveRootMotionSourceByID(T.MomentumId);
    T.MomentumId = 0; T.Momentum = 0.f;
}

// ---------------------------------------------------------------------------------------------------------------
// The board's dissolve: a masked material whose Dissolve parameter eats the parts away through a noise
// (USkateSettings::BoardDissolveMaterial). Whole or gone, the parts wear their own materials again.

void USkateComponent::ShowBoard(float Target, bool bInstant)
{
    FRideTransition& T = Transit();
    T.ShownTarget = Target;
    if (bInstant || FRideTuning::Get().BoardDissolveTime <= 0.f) T.Shown = Target;
    ApplyBoardShown();
}

void USkateComponent::LoadBoardFade()
{
    // Once (with the clips, before the first fade): a synchronous load in a fading frame would stall it.
    if (BoardFade || bBoardFadeTried) return;
    bBoardFadeTried = true;
    const FSoftObjectPath& Path = GetDefault<USkateSettings>()->BoardDissolveMaterial;
    if (UMaterialInterface* Base = Path.IsNull() ? nullptr : Cast<UMaterialInterface>(Path.TryLoad()))
        BoardFade = UMaterialInstanceDynamic::Create(Base, this);
    else UE_LOG(LogTemp, Warning, TEXT("SKATE ride: no board dissolve material (%s): the board shows whole until it is gone"), *Path.ToString());
}

void USkateComponent::ApplyBoardShown()
{
    FRideTransition& T = Transit();
    const bool bPartial = T.Shown > 0.f && T.Shown < 1.f;
    if (bPartial) LoadBoardFade();
    // Without the material the board shows whole until it is gone.
    const bool bFade = bPartial && BoardFade;
    if (bFade != T.bFadeMaterial)
    {
        TArray<UStaticMeshComponent*> Parts{Deck};
        for (UStaticMeshComponent* Part : Trucks) Parts.Add(Part);
        for (UStaticMeshComponent* Part : Wheels) Parts.Add(Part);
        for (UStaticMeshComponent* Part : Parts)
            if (Part) for (int32 I = 0; I < Part->GetNumMaterials(); ++I) Part->SetMaterial(I, bFade ? BoardFade.Get() : nullptr);
        T.bFadeMaterial = bFade;
    }
    if (bFade) BoardFade->SetScalarParameterValue(DissolveParameter, 1.f - T.Shown);
    BoardRoot->SetVisibility(T.Shown > 0.f, true);
}

void USkateComponent::DropLyingBoard()
{
    FRideTransition& T = Transit();
    if (UProjectileMovementComponent* Flight = T.Flight.Get()) Flight->DestroyComponent();
    if (UPrimitiveComponent* Loose = T.LooseBoard.Get()) Loose->DestroyComponent();
    T.Flight.Reset(); T.LooseBoard.Reset(); T.SettleTime = -1.f;
    if (T.Board == ERideBoard::World) T.Board = ERideBoard::Away;
}

FString USkateComponent::DescribeTransition() const
{
    if (!Transition || !Rider) return FString();
    const FRideTransition& T = *Transition;
    static const TCHAR* Places[] = {TEXT("away"), TEXT("ride"), TEXT("hand"), TEXT("world")};
    static const TCHAR* Feet[] = {TEXT("off"), TEXT("carry"), TEXT("mount"), TEXT("dismount"), TEXT("air"), TEXT("land"), TEXT("airmount"), TEXT("runout"), TEXT("recover")};
    FVector Hip = FVector::ZeroVector;
    const USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FName Pelvis = RiderApi ? RiderApi->GetSkateBone(TEXT("pelvis")) : NAME_None;
    if (Mesh && !Pelvis.IsNone() && Mesh->GetBoneIndex(Pelvis) != INDEX_NONE) Hip = Mesh->GetBoneLocation(Pelvis);
    const FVector Board = BoardRoot ? BoardRoot->GetComponentLocation() : FVector::ZeroVector;
    const UCharacterMovementComponent* M = Movement();
    const FVector V = M ? M->Velocity : FVector::ZeroVector;
    return FString::Printf(TEXT(" board=%s shown=%.2f vis=%d hip=%.1f,%.1f,%.1f deck=%.1f,%.1f,%.1f vel=%.0f,%.0f,%.0f offset=%.1f,%.1f,%.1f momentum=%.0f getup_on_foot=%d foot=%s clip=%s t=%.2f lift=%.2f phase=%.2f hold=%.1f hand=%s air=%.2f loose=%s deckup=%.2f turn=%.1f moves=mount,dismount,carry,jump,caveman,airdismount,runout,recover,kickout,stepon"),
        Places[uint8(T.Board)], T.Shown, BoardRoot && BoardRoot->IsVisible() ? 1 : 0, Hip.X, Hip.Y, Hip.Z, Board.X, Board.Y, Board.Z, V.X, V.Y, V.Z,
        T.MeshOffset.X, T.MeshOffset.Y, T.MeshOffset.Z, T.Momentum, T.bGetUpOnFoot ? 1 : 0, Feet[uint8(T.Foot)],
        T.Clip ? *T.Clip->GetName() : TEXT("-"), T.ClipTime, T.Lift, T.Phase, T.HoldTime, *T.HandBone.ToString(), T.AirTime,
        T.Flight.IsValid() ? TEXT("flying") : T.SettleTime >= 0.f ? TEXT("settling") : T.LooseBoard.IsValid() ? TEXT("body") : TEXT("-"),
        BoardRoot ? float(BoardRoot->GetUpVector().Z) : 0.f, FMath::RadiansToDegrees(T.MeshTurn.GetAngle()));
}
