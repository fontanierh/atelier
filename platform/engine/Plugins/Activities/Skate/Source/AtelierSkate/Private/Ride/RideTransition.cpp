// USkateComponent getting on and off the board with the Ride backend (RIDE.md, "Transitions"): one continuous
// character. The actor is never moved to a new place: the capsule changes about its centre and settles onto the floor,
// the mesh keeps its world place across each switch and eases back onto the capsule, the pose switch is a standard
// inertialization (FAnimNode_SkateRider), the speed carries over both ways, and the board is always a real object
// that dissolves in and out rather than popping.
//
// Off the board the native clips play through the Ride session's animator (FRideSession::StepOffBoard) and are
// retargeted like a ride (PublishOffBoardPose): the board-carry locomotion on the character's own movement, and the
// mount and dismount clips, whose root motion moves the capsule through a root motion source. In the air no clip moves
// the capsule: CharacterMovement keeps the fall, and the clip's trajectory follows the capsule (a jump with the board in
// hand, the board thrown under the feet, a step off the board in the air), then a landing clip takes over.
//
// A bail can end on foot too: a slow one runs out (RUNOUT_*, the board rolling on), and a fallen body asked to stay
// on foot gets up where it lies (W_RECOVERY_*, blended out of the fallen pose). A board left lying can be stepped onto,
// and one kicked away in the air (BR_KICKOUT_*) flies on as a projectile.
#include "RideTransition.h"
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "RideSession.h"
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

namespace
{
    TAutoConsoleVariable<int32> CVarRideTrace(TEXT("skate.RideTrace"), 0,
        TEXT("Log this many frames of the body after each switch between riding and on foot (a pose blend, the mode, the clip): ")
        TEXT("the actor, the mesh, and the pelvis and facing published and shown (0: off)."));
    // The riding capsule (SkateComponent.cpp): the board carries the body, the capsule only holds the camera.
    constexpr float RidingRadius = 22.f, RidingHalf = 55.f;
    // Stepping off settles the standing capsule on a floor up to this far above or below where its centre was.
    constexpr float SettleUp = 25.f, SettleDown = 60.f;
    // Where CharacterMovement keeps a walking capsule above its floor (between MIN_FLOOR_DIST and MAX_FLOOR_DIST).
    constexpr float FloorGap = 2.15f;
    // The loose board's box sits this far below its deck (RidePhysicalRider.cpp), at board scale 1.
    constexpr float LooseBoardDrop = 4.f;
    // The deck's pivot above the ground contact (SkateRuntime.cpp).
    constexpr float DeckPivot = 9.05f;
    // The mount clip's gait by the character's speed (cm/s): between the carry cycles' own speeds (stand 0, walk
    // ~170, run ~540, sprint ~910), the sprint's from just under the character's own sprint (637), which it reaches.
    constexpr float WalkMount = 80.f, RunMount = 350.f, SprintMount = 620.f;
    // The ride starts on the floor under its deck: a sweep down the deck's normal from this far above finds it (cm).
    constexpr float HandOffReach = 30.f;
    // An air kick-out stands on a floor only when coming down onto it within this time (s).
    constexpr float KickFloorTime = .1f;
    // Stepping off: the fast clip above FastDismount; the run-out above RunDismount or with the stick held; otherwise
    // the step off to a stand.
    constexpr float FastDismount = 600.f, RunDismount = 150.f;
    // The clips' board is held above this height over their trajectory (cm), and on the ground below it.
    constexpr float HeldHeight = 15.f;
    const FName MomentumName(TEXT("SkateMomentum"));
    const FName DriveName(TEXT("SkateDrive"));
    const FName DissolveParameter(TEXT("Dissolve"));
    const FName DeckBone(TEXT("SKATEBOARD_ROOT"));
    const FName CadenceCurve(TEXT("CADENCEENDPERCENT"));
    const FName Trajectory(TEXT("TRAJECTORY"));
    // In the air: the board thrown under the feet finishes in the air above this height (the ride starts airborne),
    // and below it waits for the landing. A jump with less time left than AirChain holds its last frame.
    constexpr float AirMountHeight = 70.f, AirChain = .25f;
    // A take-off this fast upward is a jump (slower is a step off a ledge); a landing this fast or after this long in
    // the air is a big one, and this far below or above the take-off a landing down or up.
    constexpr float JumpSpeed = 150.f, BigFall = -700.f, BigAirTime = .9f, LandDown = -60.f, LandUp = 30.f;
    // The board-carry locomotion, slowest first; the mount clips come from the same gaits at four phases of the step.
    const TCHAR* const CycleNames[4] = {TEXT("BR_STAND_0_CYC"), TEXT("BR_WALK_FWD_CYC"), TEXT("BR_RUN_FWD_CYC"), TEXT("BR_SPRINT_FWD_CYC")};
    const TCHAR* const Gaits[4] = {TEXT("STAND"), TEXT("WALK"), TEXT("RUN"), TEXT("SPRINT")};
    // The drive follows the clip's travel averaged over this long either side of the time shown (s): the native
    // trajectories step unevenly from frame to frame.
    constexpr float DriveWindow = .1f;
    // A trajectory held in the world (a step onto a lying board, a get-up) pulls the capsule after it at this rate
    // (1/s), up to AnchorSpeed (cm/s).
    constexpr float AnchorGain = 5.f, AnchorSpeed = 350.f;
    // A kicked or run-out board's launch is its motion over this long (s) at least.
    constexpr float KickWindow = .05f;
    // A lying board can be stepped onto when the character is this close to it (cm), slower than RunMount, and the board
    // lies wheels down (its up this close to vertical) and still.
    constexpr float StepOnReach = 130.f, StepOnUp = .85f, StepOnBlend = .35f;
    // A kicked board: the sphere it flies as (cm at board scale 1), how it bounces, and how long it may fly before it
    // settles wherever it is. It settles flat over BoardSettle (s); upside down its deck lies this far above the ground.
    constexpr float FlightRadius = 5.f, FlightBounce = .3f, FlightFriction = .5f, FlightStop = 60.f, FlightLimit = 4.f;
    // On the ground it slows by this much each second (cm/s).
    constexpr float FlightRoll = 250.f;
    constexpr float BoardSettle = .2f, UpsideDownDeck = 1.5f;
    // The kick: at least this fast away from the rider (cm/s).
    constexpr float KickSpeed = 250.f;
    // A get-up on foot waits at most this long (s) for the physical rider to hand its bodies to the animation.
    constexpr float RecoverWait = .3f;
    // The run-outs (RUNOUT_<way>_<HI|LO>_<size><n>_TO_RUN_FWD) by the way the board was going and the bail's energy:
    // small, medium and big variants of each.
    struct FRunOutWay { const TCHAR* Way; const TCHAR* Sizes[3][3]; };
    const FRunOutWay RunOutWays[4] = {
        {TEXT("FWD"), {{TEXT("S1"), TEXT("S2")}, {TEXT("M1"), TEXT("M2"), TEXT("M3")}, {TEXT("B1")}}},
        {TEXT("BWD"), {{TEXT("S2"), TEXT("S3")}, {TEXT("M1"), TEXT("M3")}, {TEXT("B1"), TEXT("B2")}}},
        {TEXT("FF"), {{TEXT("S2")}, {TEXT("M1"), TEXT("M2")}, {}}},
        {TEXT("BF"), {{TEXT("S2")}, {TEXT("M1"), TEXT("M2")}, {TEXT("B1")}}},
    };
    // The get-ups on foot, matched to how the body lies.
    const TCHAR* const Recoveries[] = {TEXT("W_RECOVERY_ONBACKFACE_N_0_N"), TEXT("W_RECOVERY_ONBACKLGUT_N_0_N"),
        TEXT("W_RECOVERY_ONBACKLSPRAWL_N_0_N"), TEXT("W_RECOVERY_ONBACKRFACE_N_0_N"), TEXT("W_RECOVERY_ONBACKRSPRAWL_N_0_N"),
        TEXT("W_RECOVERY_ONBACKSPRAWL_N_0_N"), TEXT("W_RECOVERY_ONFRONT_N_0_N"), TEXT("W_RECOVERY_ONLEFT_N_0_N"),
        TEXT("W_RECOVERY_ONRIGHTHEAD_N_0_N"), TEXT("W_RECOVERY_ONRIGHT_N_0_N")};

    float Length(const UAnimSequence* Clip) { return Clip ? Clip->GetPlayLength() : 0.f; }

    /** The clip's travel velocity about Time (cm/s, level, in its trajectory's frame). */
    FVector ClipVelocity(const UAnimSequence* Clip, float Time)
    {
        const float From = FMath::Max(0.f, Time - DriveWindow), To = FMath::Min(Length(Clip), Time + DriveWindow);
        if (To <= From) return FVector::ZeroVector;
        FVector Move = FRideAnimator::RootMotion(Clip, From, To).GetTranslation();
        Move.Z = 0.;
        return Move / (To - From);
    }

    /** The clip's horizontal speed over [From, To] (cm/s). */
    float ClipSpeed(const UAnimSequence* Clip, float From, float To)
    {
        From = FMath::Max(0.f, From); To = FMath::Min(Length(Clip), To);
        return To > From ? float(FRideAnimator::RootMotion(Clip, From, To).GetTranslation().Size2D()) / (To - From) : 0.f;
    }

    /** The first time (at 30 Hz) the clip's board is above HeldHeight (bAbove) or below it, or Default. */
    float BoardCrossing(const UAnimSequence* Clip, bool bAbove, float Default)
    {
        const float End = Length(Clip);
        for (float Time = 0.f; Time <= End; Time += 1.f / 30.f)
        {
            const float Z = FRideAnimator::Track(Clip, DeckBone, Time).GetLocation().Z;
            if (bAbove ? Z > HeldHeight : Z < HeldHeight) return Time;
        }
        return Default;
    }

    /** A bone in the clip's trajectory space (the parent chain composed up to the trajectory). */
    FTransform ClipBoneTransform(const UAnimSequence* Clip, FName Bone, float Time)
    {
        const USkeleton* Skeleton = Clip ? Clip->GetSkeleton() : nullptr;
        if (!Skeleton) return FTransform::Identity;
        const FReferenceSkeleton& Ref = Skeleton->GetReferenceSkeleton();
        FTransform Space = FTransform::Identity;
        for (int32 I = Ref.FindBoneIndex(Bone); I != INDEX_NONE && Ref.GetBoneName(I) != Trajectory; I = Ref.GetParentIndex(I))
            Space = Space * FRideAnimator::Track(Clip, Ref.GetBoneName(I), Time);
        return Space;
    }

    FVector ClipBone(const UAnimSequence* Clip, FName Bone, float Time) { return ClipBoneTransform(Clip, Bone, Time).GetLocation(); }

    /** The clip trajectory's own yaw at Time (degrees). */
    float ClipYaw(const UAnimSequence* Clip, float Time) { return float(FRideAnimator::Track(Clip, Trajectory, Time).GetRotation().Rotator().Yaw); }

    /** A direction's yaw in the clip (degrees) as seen in the world, the clip's trajectory facing Yaw. */
    float ClipYawToWorld(float Local, bool bMirror, float Yaw) { return Yaw + (bMirror ? -Local : Local); }

    /** The yaw of the clip's board (its nose) in its trajectory space at Time. */
    float ClipDeckYaw(const UAnimSequence* Clip, float Time)
    {
        return float(ClipBoneTransform(Clip, DeckBone, Time).GetRotation().GetForwardVector().Rotation().Yaw);
    }

    /** A bone of a published pose (parent-relative, the mesh's bone order) in the world. */
    bool PoseBoneTransform(const USkeletalMeshComponent* Mesh, const FTransform& MeshWorld, const TArray<FTransform>& Pose, FName Bone, FTransform& Out)
    {
        const USkeletalMesh* Asset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
        if (!Asset || Bone.IsNone()) return false;
        const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
        int32 I = Ref.FindBoneIndex(Bone);
        if (I == INDEX_NONE || Pose.Num() != Ref.GetNum()) return false;
        FTransform Space = FTransform::Identity;
        for (; I != INDEX_NONE; I = Ref.GetParentIndex(I)) Space = Space * Pose[I];
        Out = Space * MeshWorld;
        return true;
    }

    bool PoseBoneWorld(const USkeletalMeshComponent* Mesh, const FTransform& MeshWorld, const TArray<FTransform>& Pose, FName Bone, FVector& Out)
    {
        FTransform World;
        if (!PoseBoneTransform(Mesh, MeshWorld, Pose, Bone, World)) return false;
        Out = World.GetLocation();
        return true;
    }

    /** The way a body faces (degrees): level, across its thighs. */
    float FacingYaw(const FVector& Left, const FVector& Right) { return float(FVector::CrossProduct(Right - Left, FVector::UpVector).Rotation().Yaw); }

    /** The way the player is pushing the move stick or keys, in the world (zero without). */
    FVector MoveWish(const ACharacter* Rider)
    {
        const APlayerController* PC = Rider ? Cast<APlayerController>(Rider->GetController()) : nullptr;
        if (!PC) return FVector::ZeroVector;
        auto Down = [&](const FKey& Key) { return PC->IsInputKeyDown(Key) ? 1.f : 0.f; };
        const float X = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftX) + Down(EKeys::D) - Down(EKeys::A);
        const float Y = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftY) + Down(EKeys::W) - Down(EKeys::S);
        if (FVector2D(X, Y).Size() < .3f) return FVector::ZeroVector;
        return FRotator(0, PC->GetControlRotation().Yaw, 0).RotateVector(FVector(Y, X, 0.f)).GetSafeNormal();
    }

    /** A clip's local translation in the world: the clips are authored goofy, a mirrored clip runs along -Y. */
    FVector ClipToWorld(FVector Local, bool bMirror, float Yaw)
    {
        if (bMirror) Local.Y = -Local.Y;
        return FRotator(0, Yaw, 0).RotateVector(Local);
    }
}

FRideTransition& USkateComponent::Transit()
{
    if (!Transition) Transition = MakeShared<FRideTransition>();
    return *Transition;
}

bool USkateComponent::WantsGetUpOnFoot() const { return Transition && Transition->bGetUpOnFoot; }

bool USkateComponent::IsBoardInHand() const { return Transition && Transition->Foot == ERideFoot::Carry; }

// ---------------------------------------------------------------------------------------------------------------
// The clips.

bool USkateComponent::PrepareRideClips()
{
    if (!Rider || USkateSettings::ActiveBackend() != ESkateBackend::Ride) return false;
    FRideTransition& T = Transit();
    if (!Ride) PreloadRide();
    FRideAnimator& Animator = Ride->GetAnimator();
    if (!Animator.HasClips()) Ride->Preload();
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
// Getting on.

bool USkateComponent::RideMount(bool bInstant)
{
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (!M || !Capsule || !Mesh || Rider->bIsCrouched) return false;
    if (!M->IsMovingOnGround())
    {
        // In the air (a jump, with or without the board in hand, or a step off the board): the board is thrown under
        // the feet.
        if (bInstant || !M->IsFalling() || (bRideClip && Transit().Foot != ERideFoot::Air)) return false;
        return PrepareRideClips() && BeginAirMountClip();
    }
    if (bRideClip && !bInstant) return false;              // a mount or dismount is playing
    if (!bInstant && PrepareRideClips() && BeginMountClip()) return true;
    // At once: the board under the feet along the way the character is moving, at its speed.
    EndRideClip();
    RiderApi->PrepareToSkate();
    const FVector Ground = Rider->GetActorLocation() - FVector(0, 0, Capsule->GetScaledCapsuleHalfHeight() + M->CurrentFloor.FloorDist);
    const FVector Normal = M->CurrentFloor.HitResult.bBlockingHit ? FVector(M->CurrentFloor.HitResult.ImpactNormal) : FVector::UpVector;
    FQuat Rotation = AlignUp(FRotator(0, Rider->GetActorRotation().Yaw, 0).Quaternion(), Normal, 1.f);
    const FVector Velocity = FVector::VectorPlaneProject(M->Velocity, Normal);
    if (Velocity.SizeSquared() > FMath::Square(30.f)) Rotation = FRotationMatrix::MakeFromXZ(Velocity.GetSafeNormal(), Normal).ToQuat();
    return GetOnBoard(Ground, Rotation, Velocity, FRideTuning::Get().MountBlend);
}

bool USkateComponent::BeginMountClip()
{
    FRideTransition& T = Transit();
    // A board lying close by is stepped onto where it lies.
    if (T.Board == ERideBoard::World && BeginStepOnClip()) return true;
    UCharacterMovementComponent* M = Movement();
    const FRideTuning& Tune = FRideTuning::Get();
    const FVector Flat(M->Velocity.X, M->Velocity.Y, 0.f);
    const float Speed = Flat.Size();
    // The gait by speed, and the clip that leaves the stride at the nearest quarter of the step.
    const int32 Gait = Speed < WalkMount ? 0 : Speed < RunMount ? 1 : Speed < SprintMount ? 2 : 3;
    const bool bMirror = !bGoofy;
    float Phase = 0.f;
    const bool bCarrying = T.Foot == ERideFoot::Carry && T.bCarryShown;
    if (Gait > 0) Phase = bCarrying ? T.Phase : T.bFeetKnown ? FeetPhase(bMirror) : 0.f;
    const int32 Variant = FMath::RoundToInt(Phase * 4.f) % 4;
    const FString Name = Gait == 0 ? FString(TEXT("BR_STAND_0_INTO_MOUNT")) : FString::Printf(TEXT("BR_%s_FWD_%d_INTO_MOUNT"), Gaits[Gait], Variant * 25);
    UAnimSequence* Clip = Ride->GetAnimator().Clip(*Name);
    if (!Clip || Length(Clip) < .1f) return false;
    RiderApi->PrepareToSkate();
    StopMomentum();
    const float Yaw = Speed > 30.f ? float(Flat.Rotation().Yaw) : float(Rider->GetActorRotation().Yaw);
    // The pose: from the carry the pose mesh cross-fades between its own clips (both on the ground); from the
    // character's own pose the character blends.
    StartClip(Clip, ERideFoot::Mount, bMirror, Yaw, bCarrying ? Tune.ClipBlend : 0.f);
    T.BoardContact = BoardCrossing(Clip, false, T.ClipLength * .6f);
    // The speed carries on: the capsule moves along the clip's travel at the character's speed, and leaves at least
    // as fast as the clip ends (the board leaves at the speed the rider ran in at); a faster run plays the clip a
    // little faster too. From a stand the clip's own travel.
    if (Gait > 0)
    {
        T.ClipRate = FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, 0.f, T.ClipLength)), 1.f, 1.3f);
        T.SpeedStart = Speed;
        T.SpeedEnd = FMath::Max(Speed, ClipSpeed(Clip, T.ClipLength - .25f, T.ClipLength) * T.ClipRate);
    }
    // The ride starts with the capsule over the deck: the capsule moves on to where the clip leaves the board.
    const FVector EndDeck = ClipBone(Clip, DeckBone, T.ClipLength);
    T.TrajEnd = -ClipToWorld(FVector(EndDeck.X, EndDeck.Y, 0.), bMirror, Yaw);
    T.TrajEndTime = T.ClipLength;
    // The board: the one in hand, or one that dissolves into the hand over the clip's first frames.
    UseWorldBoard();
    if (T.Board == ERideBoard::World) DropLyingBoard();
    if (T.Board != ERideBoard::Hand) T.Shown = 0.f;
    T.Board = ERideBoard::Hand; T.bRecall = false;
    ShowBoard(1.f, false);
    if (!bCarrying) RequestPoseBlend(Tune.ClipBlend);
    TurnActor(Yaw);
    SetDrive(Flat);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride mount: %s at %.0f cm/s (phase %.2f), rate %.2f, speed %.0f..%.0f cm/s, onto the deck %.1f cm on"),
        *Name, Speed, Phase, T.ClipRate, T.SpeedStart, T.SpeedEnd, T.TrajEnd.Size());
    return true;
}

bool USkateComponent::BeginStepOnClip()
{
    // A board lying wheels down within reach: the stand mount from the clip's touchdown, its board held on the lying
    // one, nose to nose or turned end to end (the deck looks the same), whichever puts the clip's body nearer the
    // character's. The trajectory is held in the world and the capsule follows it onto the deck.
    FRideTransition& T = Transit();
    UCharacterMovementComponent* M = Movement();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (!BoardRoot || !Mesh) return false;
    const FTransform Lying = BoardRoot->GetComponentTransform();
    const UPrimitiveComponent* Body = T.LooseBoard.Get();
    const TCHAR* Why = T.Flight.IsValid() ? TEXT("still flying") : T.SettleTime >= 0.f ? TEXT("settling") : T.ShownTarget <= 0.f ? TEXT("dissolving")
        : Lying.GetRotation().GetUpVector().Z < StepOnUp ? TEXT("not on its wheels") : M->Velocity.Size2D() > RunMount ? TEXT("running too fast")
        : FVector::Dist2D(Lying.GetLocation(), Rider->GetActorLocation()) > StepOnReach ? TEXT("out of reach")
        : Body && Body->IsSimulatingPhysics() && Body->GetPhysicsLinearVelocity().Size() > 30.f ? TEXT("still moving") : nullptr;
    if (Why)
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride no step on: the lying board is %s (%.0f cm away, up %.2f, %.0f cm/s)"), Why,
            FVector::Dist2D(Lying.GetLocation(), Rider->GetActorLocation()), Lying.GetRotation().GetUpVector().Z, M->Velocity.Size2D());
        return false;
    }
    UAnimSequence* Clip = Ride->GetAnimator().Clip(TEXT("BR_STAND_0_INTO_MOUNT"));
    const FName Pelvis = RiderApi->GetSkateBone(TEXT("pelvis"));
    if (!Clip || Length(Clip) < .1f || Pelvis.IsNone() || Mesh->GetBoneIndex(Pelvis) == INDEX_NONE) return false;
    const float L = Length(Clip);
    const float From = BoardCrossing(Clip, false, L * .6f);
    const bool bMirror = !bGoofy;
    const FVector ClipDeck = ClipBone(Clip, DeckBone, From), ClipHips = ClipBone(Clip, TEXT("HIPS"), From);
    const float DeckYaw = ClipYawToWorld(ClipDeckYaw(Clip, From), bMirror, 0.f);
    const FVector Hips = Mesh->GetBoneLocation(Pelvis);
    const float BoardYaw = float(Lying.GetRotation().GetForwardVector().Rotation().Yaw);
    float Yaw = 0.f; FVector Origin = FVector::ZeroVector; double Nearest = MAX_dbl;
    for (const float Turn : {0.f, 180.f})
    {
        const float Option = BoardYaw + Turn - DeckYaw;
        const FVector At = Lying.GetLocation() - ClipToWorld(FVector(ClipDeck.X, ClipDeck.Y, 0.), bMirror, Option);
        const double Distance = FVector::Dist2D(At + ClipToWorld(ClipHips, bMirror, Option), Hips);
        if (Distance < Nearest) { Nearest = Distance; Yaw = Option; Origin = At; }
    }
    RiderApi->PrepareToSkate();
    StopMomentum();
    StartClip(Clip, ERideFoot::Mount, bMirror, Yaw, 0.f);
    T.ClipTime = From; T.BoardContact = From;
    T.bAnchored = true; T.Anchor = Origin; T.bMatchDeck = true;
    // The capsule sets off from where it stands, at rest, and is on the trajectory by the clip's end.
    T.AnchorFrom = OffBoardGround(); T.AnchorBlendFrom = From;
    const FVector EndDeck = ClipBone(Clip, DeckBone, L);
    T.TrajEnd = -ClipToWorld(FVector(EndDeck.X, EndDeck.Y, 0.), bMirror, Yaw);
    T.TrajEndTime = L;
    // The lying board is the clip's from here: no body of its own, and it eases onto the clip's.
    if (UPrimitiveComponent* Loose = T.LooseBoard.Get()) Loose->DestroyComponent();
    T.LooseBoard.Reset();
    T.Board = ERideBoard::Hand; T.bRecall = false;
    UseWorldBoard();
    ShowBoard(1.f, false);
    OffBoardDeckFrom = Lying; OffBoardDeckBlend = 0.f;
    RequestPoseBlend(StepOnBlend);
    TurnActor(Yaw);
    SetDrive(FVector::ZeroVector);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride step on: the lying board %.0f cm away, %s, the body %.0f cm from the clip's"),
        FVector::Dist2D(Lying.GetLocation(), Rider->GetActorLocation()), FMath::Abs(FMath::FindDeltaAngleDegrees(BoardYaw, Yaw + DeckYaw)) > 90.f ? TEXT("tail first") : TEXT("nose first"), Nearest);
    return true;
}

bool USkateComponent::GetOnBoard(const FVector& Where, const FQuat& Rotation, const FVector& Velocity, float Blend)
{
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    FRideTransition& T = Transit();
    // On the floor under the deck, never inside it: a clip's board can come down a little into the floor (a caveman
    // onto a pier's planks), and a ride started below the surface finds no ground under it and falls through. A
    // wheel-sized sweep down the deck's normal to the start finds a floor above it; something close overhead (a bench,
    // a ledge) is skipped by looking again from a step above.
    FVector Ground = Where;
    {
        const FRideTuning& Tune = FRideTuning::Get();
        const FVector Up = Rotation.GetUpVector();
        const float R = Tune.WheelRadius;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideHandOff), false, Rider);
        for (const float Above : {HandOffReach, Tune.StepUp})
        {
            FHitResult Hit;
            if (!GetWorld()->SweepSingleByChannel(Hit, Where + Up * (Above + R), Where + Up * R, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(R), Params)) break;
            if (Hit.bStartPenetrating) continue;
            if (FVector::DotProduct(Hit.ImpactNormal, Up) >= Tune.WallSlope) Ground = Hit.Location - Up * R;
            break;
        }
        if (FVector::DistSquared(Ground, Where) > 1.f)
            UE_LOG(LogTemp, Display, TEXT("SKATE ride hand-off: the deck was %.1f cm inside the floor; the ride starts on it"), FVector::Dist(Ground, Where));
    }
    StopMomentum(); StopDrive();
    // The on-foot body to return to, without the offset and turn a recent switch may still be easing away.
    SavedRadius = Capsule->GetUnscaledCapsuleRadius(); SavedHalf = Capsule->GetUnscaledCapsuleHalfHeight();
    SavedMeshLocation = Mesh->GetRelativeLocation() - T.MeshOffset; SavedMeshRotation = T.MeshTurn.Inverse() * Mesh->GetRelativeRotation().Quaternion();
    SavedStep = M->MaxStepHeight;
    T.MeshSettleTime = -1.f;
    Pos = Ground; Rot = Rotation; Vel = Velocity;
    const FTransform MeshWorld = Mesh->GetRelativeTransform() * Rider->GetActorTransform();
    bRideBody = true;
    ResetInput(); ShownCombo.Reset(); ComboFade = 0;
    Mode = ESkateMode::Ground;
    // A board left lying elsewhere goes; the board is placed in the world from now on, so it can stay behind when the
    // rider leaves it.
    if (T.Board == ERideBoard::World) { DropLyingBoard(); T.Shown = 0.f; }
    T.Board = ERideBoard::Ride; T.bGetUpOnFoot = false; T.Foot = ERideFoot::Off; T.bRecall = false; T.bCarryShown = false;
    UseWorldBoard();
    // The pose shown this frame stays until the ride publishes its first (starting the ride clears it).
    const TArray<FTransform> Shown = RetailPose;
    if (!StartRetailRuntime()) { StowImmediately(); return false; }
    if (!Shown.IsEmpty()) RetailPose = Shown;
    // A slow, upright bail is offered to the transition first: it runs out on foot.
    if (PhysicalRider && !PhysicalRider->OnBailStart.IsBound()) PhysicalRider->OnBailStart.BindUObject(this, &USkateComponent::TakeRunOut);
    // The ride's own clips take over from a transition clip; the character's blend hides the switch.
    if (Ride) Ride->GetAnimator().ClearOverride(0.f);
    Capsule->SetCapsuleSize(RidingRadius, RidingHalf);      // about its centre: nothing moves
    M->SetMovementMode(MOVE_Custom, MovementMode);
    // The actor stays where it is: the body's height above the session's root is measured rather than assumed. It
    // turns to the board as the first ride frame would; the mesh keeps its world place and rotation over that turn
    // (riding, the pose is anchored on the board, so they only matter to the blend into it, which works in the mesh's
    // frame).
    BodyLift = Rider->GetActorLocation().Z - Ride->Root.GetLocation().Z;
    Rider->SetActorLocationAndRotation(Ride->Root.GetLocation() + FVector(0, 0, BodyLift), Ride->Root.GetRotation(), false, nullptr, ETeleportType::None);
    KeepMeshWorld(MeshWorld);
    // The blend is for the ride's first pose, not the held one: asked when that pose is written, so the character's
    // graph starts it on the frame the pose changes (a request a frame early blends nothing, and the change pops).
    RequestPoseBlendWithNextPose(Blend);
    ShowBoard(1.f, false);
    return true;
}

// ---------------------------------------------------------------------------------------------------------------
// Getting off.

bool USkateComponent::RideDismount()
{
    FRideTransition& T = Transit();
    // During a bail the button asks to get up on foot: the physical rider reads WantsGetUpOnFoot when the body settles.
    const bool bDown = Mode == ESkateMode::Bail || (Ride && (Ride->IsBailing() || Ride->GetMode() == ERideState::GetUp)) ||
        (PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
    if (bDown) { T.bGetUpOnFoot = true; return true; }
    // In the air the rider lets go of the board from the grab and comes down on foot holding it.
    if (Mode == ESkateMode::Air) return T.Board == ERideBoard::Ride && PrepareRideClips() && BeginAirDismountClip();
    if (Mode != ESkateMode::Ground) return false;           // not from a grind
    T.bGetUpOnFoot = false;
    // Off a ridden board the step-off clip carries the board into the hand; after a bail (the board lying on its own)
    // the rider steps off at once and the board stays where it lies.
    if (T.Board == ERideBoard::Ride && PrepareRideClips() && BeginDismountClip()) return true;
    // At once: the character's own pose blended from the riding pose, the board left lying.
    UCharacterMovementComponent* M = Movement();
    const FRideTuning& Tune = FRideTuning::Get();
    const FVector Carried = Vel;
    SuspendRetailRuntime();
    RequestPoseBlend(Tune.DismountBlend);
    LeaveBoard();
    const bool bFloor = StandUpOffBoard(Rider->GetActorRotation().Yaw);
    // The speed carries on; the stick then shares it out between the character's own and momentum (ReleaseDrive).
    const FVector Flat(Carried.X, Carried.Y, 0.f);
    M->Velocity = bFloor ? Flat : FVector(Flat.X, Flat.Y, Carried.Z);
    HoldDriveForInput(Flat);
    if (T.Board == ERideBoard::Ride) { T.Board = ERideBoard::World; T.BoardTime = 0.f; ShowBoard(0.f, false); }
    UE_LOG(LogTemp, Display, TEXT("SKATE ride dismount at %.0f cm/s, %s"), Flat.Size(), bFloor ? TEXT("walking") : TEXT("falling"));
    return true;
}

void USkateComponent::LeaveBoard()
{
    // The ride's end, shared by every way off: no trick line, no loops.
    ShownCombo.Reset(); ComboFade = 0;
    Mode = ESkateMode::Off;
    bManual = bPowerslide = bPushing = bBraking = false;
    for (int32 I = 0; I < Loops.Num(); ++I) { if (Loops[I]) Loops[I]->Stop(); LoopVolume[I] = 0.f; }
    ++Serial;
}

bool USkateComponent::StandUpOffBoard(float Yaw, bool bMayStand)
{
    // Standing: the capsule grows about its centre, turns upright to Yaw and settles onto the floor under it when there
    // is one close by (and bMayStand); otherwise the character falls from where it is, lifted out of a floor the grown
    // capsule would reach into. The body keeps its world place while the capsule moves under it, then eases back onto
    // it.
    FRideTransition& T = Transit();
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FTransform MeshWorld = Mesh->GetRelativeTransform() * Rider->GetActorTransform();
    Capsule->SetCapsuleSize(SavedRadius, SavedHalf);
    M->MaxStepHeight = SavedStep;
    const FVector Centre = Rider->GetActorLocation();
    FVector Stand = Centre;
    bool bFloor = false;
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideDismount), false, Rider);
        FCollisionResponseParams Response;
        Capsule->InitSweepCollisionParams(Params, Response);
        const FCollisionShape Shape = Capsule->GetCollisionShape();
        for (const float Up : {SettleUp, 0.f})
        {
            FHitResult Hit;
            if (!GetWorld()->SweepSingleByChannel(Hit, Centre + FVector(0, 0, Up), Centre - FVector(0, 0, SettleDown), FQuat::Identity,
                Capsule->GetCollisionObjectType(), Shape, Params, Response)) break;
            if (Hit.bStartPenetrating) continue;              // a ceiling close above: try again from the centre
            if (M->IsWalkable(Hit))
            {
                if (bMayStand) { Stand = Hit.Location + FVector(0, 0, FloorGap); bFloor = true; }
                else if (Hit.Location.Z + FloorGap > Stand.Z) Stand.Z = Hit.Location.Z + FloorGap;
            }
            break;
        }
    }
    Rider->SetActorLocationAndRotation(Stand, FRotator(0, Yaw, 0), false, nullptr, ETeleportType::None);
    M->SetMovementMode(bFloor ? MOVE_Walking : MOVE_Falling);
    if (bFloor) M->FindFloor(M->UpdatedComponent->GetComponentLocation(), M->CurrentFloor, false);
    KeepMeshWorld(MeshWorld);
    T.MeshOffsetStart = T.MeshOffset; T.MeshTurnStart = T.MeshTurn; T.MeshSettleTime = 0.f;
    return bFloor;
}

bool USkateComponent::BeginDismountClip()
{
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    const FVector Flat(Vel.X, Vel.Y, 0.f);
    const float Speed = Flat.Size();
    const FVector DeckForward = FVector(Forward().X, Forward().Y, 0.f).GetSafeNormal();
    if (DeckForward.IsNearlyZero()) return false;
    // Off the way the board is going: riding fakie the rider faces the other end, which looks like the other stance.
    const bool bBackward = Speed > 15.f ? FVector::DotProduct(Flat, DeckForward) < 0.f : bFakie;
    const bool bLow = Ride && Ride->GetBody().Crouch > .5f;
    const bool bStick = In.Left.Size() > .3f;
    const TCHAR* Height = bLow ? TEXT("LO") : TEXT("HI");
    FString Name; float EndPhase = 0.f;
    const bool bEndsRunning = Speed > RunDismount || bStick;
    if (Speed > FastDismount) { Name = FString::Printf(TEXT("BR_DISMOUNT_FAST_%s_INTO_RUN_FWD"), Height); EndPhase = .75f; }
    else if (bEndsRunning) { Name = FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_RUN_FWD"), Height); EndPhase = .5f; }
    else Name = FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_STAND_0"), Height);
    UAnimSequence* Clip = Ride->GetAnimator().Clip(*Name);
    if (!Clip || Length(Clip) < .1f) return false;
    if (Clip->HasCurveData(CadenceCurve, false))
    {
        float Cadence = Clip->EvaluateCurveData(CadenceCurve, FAnimExtractContext(double(Length(Clip))));
        if (Cadence > 1.f) Cadence /= 100.f;
        EndPhase = Cadence;
    }
    // The riding pose and the clip's are in different root spaces (the deck's pivot, the ground): the pose mesh cuts
    // and the character's blend hides the switch.
    const bool bMirror = bGoofy == bBackward;
    StartClip(Clip, ERideFoot::Dismount, bMirror, float((bBackward ? -DeckForward : DeckForward).Rotation().Yaw), 0.f);
    // The carry plays in the rider's own stance: a fakie step-off ends half a stride on.
    T.EndPhase = FMath::Frac(EndPhase + (T.bMirror != !bGoofy ? .5f : 0.f));
    // The speed carries on: a run-off keeps the board's speed (and picks up the clip's run with the stick held); a
    // step off to a stand slows with the clip from the board's speed.
    if (bEndsRunning)
    {
        T.SpeedStart = Speed;
        T.SpeedEnd = bStick ? FMath::Max(Speed, ClipSpeed(Clip, T.ClipLength - .25f, T.ClipLength)) : Speed;
    }
    else T.ScaleStart = FMath::Clamp(Speed / FMath::Max(50.f, float(ClipVelocity(Clip, 0.f).Size2D())), .2f, 3.f);
    T.BoardContact = BoardCrossing(Clip, true, .3f);
    T.Lift = 1.f;
    T.bEndsStanding = !bEndsRunning;
    SuspendRetailRuntime();
    RequestPoseBlend(Tune.ClipBlend);
    LeaveBoard();
    // The deck it leaves, before the capsule changes.
    const FVector DeckNow = Pos + Up() * DeckPivot;
    const bool bFloor = StandUpOffBoard(T.TrajYaw);
    // The clip starts with its board exactly on that deck; the offset from the capsule's floor eases away.
    const FVector ClipDeck = ClipToWorld(ClipBone(Clip, DeckBone, 0.f), T.bMirror, T.TrajYaw);
    T.TrajOffset = DeckNow - ClipDeck - OffBoardGround();
    T.OffsetTime = FMath::Max(.1f, Tune.MeshSettle * 1.4f);
    T.Board = ERideBoard::Hand;
    UseWorldBoard();
    M->Velocity = FVector(Flat.X, Flat.Y, bFloor ? 0.f : Vel.Z);
    T.AirStartZ = OffBoardGround().Z; T.AirTime = 0.f; T.FallSpeed = 0.f; T.LandPhase = 0; T.AirNext = nullptr;
    SetDrive(Flat);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride dismount: %s at %.0f cm/s%s, speed %.0f..%.0f (travel x%.2f), offset %.1f cm, %s"),
        *Name, Speed, bBackward ? TEXT(" fakie") : TEXT(""), T.SpeedStart, T.SpeedEnd, T.ScaleStart, T.TrajOffset.Size(), bFloor ? TEXT("walking") : TEXT("falling"));
    return true;
}

void USkateComponent::BeginGetUpOnFoot(const FVector& Ground, float Yaw, bool bFaceUp)
{
    FRideTransition& T = Transit();
    T.bGetUpOnFoot = true;
    // The board stays where it came to rest, a body of its own.
    if (PhysicalRider)
        if (UBoxComponent* Loose = PhysicalRider->TakeLooseBoard())
        {
            if (T.Board == ERideBoard::World) DropLyingBoard();
            T.LooseBoard = Loose; T.Board = ERideBoard::World; T.BoardTime = 0.f;
            ShowBoard(1.f, true);
        }
    // The body gets up where it lies with the recovery that fits how it lies (BeginRecover, after the ride's frame,
    // blended out of the fallen pose's snapshot). Without the clips the session's get-up stands the rider up and the
    // rider steps off once up (TickTransition).
    if (PrepareRideClips())
    {
        T.bRecoverPending = true; T.RecoverGround = Ground; T.RecoverYaw = Yaw; T.bRecoverFaceUp = bFaceUp;
        return;
    }
    if (Ride && Ride->IsBailing()) Ride->GetUp(Ground, Yaw);
}

bool USkateComponent::BeginRecover()
{
    // The recovery whose first frame lies most like the fallen body: its head-from-hips way turned onto the body's,
    // then the hands, feet and the way the front faces compared about the hips (scaled to the character).
    FRideTransition& T = Transit();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (!Ride || !Mesh) return false;
    struct FPart { const TCHAR* Own; const TCHAR* Clip; };
    static const FPart Parts[] = {{TEXT("head"), TEXT("HEAD")}, {TEXT("hand_L"), TEXT("LEFTHAND")}, {TEXT("hand_R"), TEXT("RIGHTHAND")},
        {TEXT("foot_L"), TEXT("LEFTFOOT")}, {TEXT("foot_R"), TEXT("RIGHTFOOT")}, {TEXT("thigh_L"), TEXT("LEFTUPLEG")}, {TEXT("thigh_R"), TEXT("RIGHTUPLEG")}};
    constexpr int32 Head = 0, ThighL = 5, ThighR = 6, NumParts = UE_ARRAY_COUNT(Parts);
    const FName Pelvis = RiderApi->GetSkateBone(TEXT("pelvis"));
    if (Pelvis.IsNone() || Mesh->GetBoneIndex(Pelvis) == INDEX_NONE) return false;
    // The fallen body, read before anything moves (the mesh still shows it).
    const FVector Hips = Mesh->GetBoneLocation(Pelvis);
    FVector Own[NumParts];
    for (int32 I = 0; I < NumParts; ++I)
    {
        const FName Bone = RiderApi->GetSkateBone(Parts[I].Own);
        if (Bone.IsNone() || Mesh->GetBoneIndex(Bone) == INDEX_NONE) return false;
        Own[I] = Mesh->GetBoneLocation(Bone) - Hips;
    }
    const float OwnSize = FMath::Max(1.f, float(Own[Head].Size()));
    const FVector OwnFront = FVector::CrossProduct(Own[ThighR] - Own[ThighL], Own[Head]).GetSafeNormal();
    const float OwnYaw = float(Own[Head].Rotation().Yaw);
    UAnimSequence* Best = nullptr; float BestYaw = 0.f, BestFit = MAX_flt;
    for (const TCHAR* Name : Recoveries)
    {
        UAnimSequence* Clip = Ride->GetAnimator().Clip(Name);
        if (!Clip || Length(Clip) < .3f) continue;
        const FVector ClipHips = ClipBone(Clip, TEXT("HIPS"), 0.f);
        FVector Part[NumParts];
        for (int32 I = 0; I < NumParts; ++I) Part[I] = ClipBone(Clip, Parts[I].Clip, 0.f) - ClipHips;
        const float Scale = OwnSize / FMath::Max(1.f, float(Part[Head].Size()));
        const float Yaw = OwnYaw - float(Part[Head].Rotation().Yaw);
        const FRotator Turn(0, Yaw, 0);
        float Fit = 0.f;
        for (int32 I = 0; I < NumParts; ++I) Fit += float(FVector::DistSquared(Turn.RotateVector(Part[I] * Scale), Own[I]));
        const FVector Front = Turn.RotateVector(FVector::CrossProduct(Part[ThighR] - Part[ThighL], Part[Head]).GetSafeNormal());
        Fit += FMath::Square(OwnSize) * float(FVector::DistSquared(Front, OwnFront));
        if (Fit < BestFit) { BestFit = Fit; Best = Clip; BestYaw = Yaw; }
    }
    if (!Best) return false;
    const FRideTuning& Tune = FRideTuning::Get();
    SuspendRetailRuntime();
    LeaveBoard();
    StandUpOffBoard(BestYaw);
    StartClip(Best, ERideFoot::Recover, false, BestYaw, 0.f);
    // No travel: the clip's trajectory is held where its pelvis lies on the body's (MatchPelvis), and the capsule
    // moves under it.
    T.SpeedStart = T.SpeedEnd = 0.f;
    T.bAnchored = true; T.Anchor = OffBoardGround();
    T.bMatchPelvis = true; T.OffsetTime = FMath::Max(.3f, T.ClipLength * .8f);
    T.bEndsStanding = true;
    T.bGetUpOnFoot = false;
    if (T.Board == ERideBoard::Ride) { T.Board = ERideBoard::World; T.BoardTime = 0.f; }
    SetDrive(FVector::ZeroVector);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride get up on foot: %s (%s, match %.0f cm), over %.2f s"), *Best->GetName(),
        T.bRecoverFaceUp ? TEXT("face up") : TEXT("face down"), FMath::Sqrt(BestFit / NumParts), Tune.RecoverBlend);
    return true;
}

bool USkateComponent::TakeRunOut(ERideBailKind Kind)
{
    // URidePhysicalRider::OnBailStart, in the ride's frame: a slow, upright bail is run out on foot. The run-out by the
    // way the board was going under the rider (on along its nose, back along its tail, or across it toward the toes or
    // the heels), high or crouched, and small to big by how hard the bail was. It starts after the ride's frame.
    FRideTransition& T = Transit();
    if (Kind != ERideBailKind::RunOut || !Ride || !BoardRoot || T.Board != ERideBoard::Ride || !PrepareRideClips()) return false;
    const FVector Bail = Ride->GetBailVelocity();
    // Riding switch the rider stands on the board the other way round, in the other stance: the way is his.
    const bool bSwitched = Ride->IsSwitch();
    FQuat DeckRotation = BoardRoot->GetComponentQuat();
    if (bSwitched) DeckRotation = FQuat(DeckRotation.GetUpVector(), PI) * DeckRotation;
    float Along = FVector::DotProduct(Bail, DeckRotation.GetForwardVector());
    float Across = FVector::DotProduct(Bail, DeckRotation.GetRightVector());
    if (bGoofy == bSwitched) Across = -Across;              // the clips are authored goofy
    if (FMath::Abs(Along) + FMath::Abs(Across) < 20.f) { Along = bFakie != bSwitched ? -1.f : 1.f; Across = 0.f; }
    const float Angle = FMath::RadiansToDegrees(FMath::Atan2(Across, Along));
    const int32 Way = FMath::Abs(Angle) < 45.f ? 0 : FMath::Abs(Angle) > 135.f ? 1 : Across < 0.f ? 2 : 3;
    const URidePhysicalSettings* Settings = GetDefault<URidePhysicalSettings>();
    const float Energy = FMath::Max3(float(Bail.Size2D()) / FMath::Max(1.f, Settings->RunOutSpeed), FMath::Abs(float(Bail.Z)) / FMath::Max(1.f, Settings->RunOutImpact),
        FMath::RadiansToDegrees(float(Ride->GetBailSpin().Size())) / FMath::Max(1.f, Settings->RunOutSpin));
    const TCHAR* Height = Ride->GetBody().Crouch > .5f ? TEXT("LO") : TEXT("HI");
    // The size the energy asks for, or the nearest one this way has.
    const int32 Wanted = Energy < .4f ? 0 : Energy < .75f ? 1 : 2;
    for (const int32 Size : {Wanted, Wanted - 1, Wanted + 1, Wanted - 2, Wanted + 2})
    {
        if (Size < 0 || Size > 2) continue;
        TArray<UAnimSequence*> Options;
        for (const TCHAR* Variant : RunOutWays[Way].Sizes[Size])
            if (Variant)
                if (UAnimSequence* Clip = Ride->GetAnimator().Clip(*FString::Printf(TEXT("RUNOUT_%s_%s_%s_TO_RUN_FWD"), RunOutWays[Way].Way, Height, Variant)); Clip && Length(Clip) > .2f)
                    Options.Add(Clip);
        if (Options.IsEmpty()) continue;
        T.PendingClip = Options[FMath::RandHelper(Options.Num())];
        T.bRunOutPending = true;
        UE_LOG(LogTemp, Display, TEXT("SKATE ride run-out: %s (the board going %.0f deg from its nose at %.0f cm/s, energy %.2f)"),
            *T.PendingClip->GetName(), Angle, Bail.Size(), Energy);
        return true;
    }
    return false;
}

bool USkateComponent::BeginRunOut()
{
    // Off the board on foot: the run-out's board starts on the deck the rider bailed from (its trajectory turned so the
    // clip's board points the deck's way) and rolls on with the clip; the body starts where the rider's is, at the speed
    // of the bail, and runs out with the clip's turns.
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    UAnimSequence* Clip = T.PendingClip;
    T.bRunOutPending = false; T.PendingClip = nullptr;
    if (!Ride || !M || !Clip || !BoardRoot) return false;
    // In the stance in effect, on the board the way the rider stands on it (riding switch, the other way round).
    const bool bSwitched = Ride->IsSwitch();
    const bool bMirror = bGoofy == bSwitched;
    const FTransform Bailed = BoardRoot->GetComponentTransform();
    const float DeckYaw = float(Bailed.GetRotation().GetForwardVector().Rotation().Yaw) + (bSwitched ? 180.f : 0.f);
    const float Yaw = DeckYaw - ClipYawToWorld(ClipDeckYaw(Clip, 0.f), bMirror, 0.f);
    const FVector Carried = Ride->GetBailVelocity();
    const FVector Flat(Carried.X, Carried.Y, 0.f);
    SuspendRetailRuntime();
    RequestPoseBlend(Tune.DismountBlend);
    LeaveBoard();
    const bool bFloor = StandUpOffBoard(Yaw);
    StartClip(Clip, ERideFoot::RunOut, bMirror, Yaw, 0.f);
    T.bFollowYaw = true;
    T.bMatchPelvis = true; T.OffsetTime = .4f;
    T.ScaleStart = FMath::Clamp(float(Flat.Size()) / FMath::Max(50.f, float(ClipVelocity(Clip, 0.f).Size2D())), .5f, 2.f);
    T.ScaleEnd = 1.f;
    T.bEndsStanding = false; T.bGetUpOnFoot = false;
    // The board is the clip's until it ends, easing from the deck onto the clip's; then it rolls on by itself.
    T.Board = ERideBoard::World; T.BoardTime = 0.f;
    UseWorldBoard();
    OffBoardDeckFrom = Bailed; OffBoardDeckBlend = 0.f;
    M->Velocity = FVector(Flat.X, Flat.Y, bFloor ? 0.f : Carried.Z);
    SetDrive(Flat);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride run out: %s at %.0f cm/s (travel x%.2f), %s"), *Clip->GetName(), Flat.Size(), T.ScaleStart,
        bFloor ? TEXT("walking") : TEXT("falling"));
    return true;
}

void USkateComponent::LaunchBoard()
{
    // The board leaves the clip that had it: kicked away (at least KickSpeed from the rider), or rolling on from a
    // run-out. It flies as a small sphere moved by a projectile movement, bouncing off what it hits, its deck turning
    // with the spin it left with (StepLooseBoard); barely moving, it settles where it is.
    FRideTransition& T = Transit();
    const bool bKick = T.bKickOut;
    T.bKickOut = false;
    UCharacterMovementComponent* M = Movement();
    if (!BoardRoot || !Rider || !M) return;
    if (T.Board == ERideBoard::World) DropLyingBoard();
    T.Board = ERideBoard::World; T.BoardTime = 0.f;
    UseWorldBoard();
    const FTransform Leaving = BoardRoot->GetComponentTransform();
    FVector Velocity = T.bDeckKnown ? T.KickVelocity : M->Velocity;
    if (bKick)
    {
        const FVector Away = (Leaving.GetLocation() - Rider->GetActorLocation()).GetSafeNormal2D();
        const float Out = FVector::DotProduct(Velocity - M->Velocity, Away);
        if (!Away.IsNearlyZero() && Out < KickSpeed) Velocity += Away * (KickSpeed - Out);
    }
    if (!bKick && Velocity.Size() < FlightStop) { SettleBoard(); return; }
    const float Scale = BoardScale();
    USphereComponent* Body = NewObject<USphereComponent>(Rider, NAME_None, RF_Transient);
    Body->InitSphereRadius(FlightRadius * Scale);
    Body->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Body->SetCollisionObjectType(ECC_WorldDynamic);
    Body->SetCollisionResponseToAllChannels(ECR_Block);
    Body->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
    Body->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Ignore);
    Body->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
    Body->SetCollisionResponseToChannel(ECC_Visibility, ECR_Ignore);
    Body->SetGenerateOverlapEvents(false);
    Body->SetCanEverAffectNavigation(false);
    Body->SetHiddenInGame(true);
    // The sphere's bottom where the wheels touch (a little above, so it starts clear of the ground).
    Body->SetWorldLocation(Leaving.GetLocation() - Leaving.GetRotation().GetUpVector() * (DeckPivot - FlightRadius) * Scale + FVector(0, 0, 1.f));
    Body->RegisterComponent();
    UProjectileMovementComponent* Flight = NewObject<UProjectileMovementComponent>(Rider, NAME_None, RF_Transient);
    Flight->bAutoRegisterUpdatedComponent = false;
    Flight->SetUpdatedComponent(Body);
    Flight->bInitialVelocityInLocalSpace = false;
    Flight->bRotationFollowsVelocity = false;
    Flight->bShouldBounce = true;
    Flight->Bounciness = FlightBounce;
    Flight->Friction = FlightFriction;
    Flight->BounceVelocityStopSimulatingThreshold = FlightStop;
    Flight->InitialSpeed = 0.f; Flight->MaxSpeed = 0.f;
    Flight->RegisterComponent();
    Flight->Velocity = Velocity;
    T.LooseBoard = Body; T.Flight = Flight;
    T.FlightRotation = Leaving.GetRotation(); T.FlightTime = 0.f; T.SettleTime = -1.f;
    if (!T.bDeckKnown) T.FlightSpin = FVector::ZeroVector;
    UE_LOG(LogTemp, Display, TEXT("SKATE ride board %s at %.0f cm/s, spinning %.0f deg/s"), bKick ? TEXT("kicked away") : TEXT("rolls on"), Velocity.Size(),
        FMath::RadiansToDegrees(T.FlightSpin.Size()));
}

void USkateComponent::StepLooseBoard(float Dt)
{
    // The board on its own: flying (the deck over the sphere), settling flat, or following the physical rider's box.
    FRideTransition& T = Transit();
    if (!BoardRoot) return;
    const float Scale = BoardScale();
    if (UProjectileMovementComponent* Flight = T.Flight.Get())
    {
        T.FlightTime += Dt;
        const USceneComponent* Body = Flight->UpdatedComponent;
        if (!Body || Flight->HasStoppedSimulation() || T.FlightTime > FlightLimit) { SettleBoard(); return; }
        // On the ground it slides to a stop and its spin dies away.
        FHitResult Hit;
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardFlight), false, Rider);
        const FVector At = Body->GetComponentLocation();
        const bool bLow = GetWorld()->LineTraceSingleByChannel(Hit, At, At - FVector(0, 0, FlightRadius * Scale + 3.f), ECC_WorldStatic, Params);
        if (bLow && FMath::Abs(Flight->Velocity.Z) < 60.f)
        {
            const FVector Flat(Flight->Velocity.X, Flight->Velocity.Y, 0.f);
            Flight->Velocity -= Flat.GetSafeNormal() * FMath::Min(float(Flat.Size()), FlightRoll * Dt);
            T.FlightSpin *= FMath::Exp(-6.f * Dt);
            if (Flight->Velocity.Size() < FlightStop) { SettleBoard(); return; }
        }
        if (!T.FlightSpin.IsNearlyZero()) T.FlightRotation = (FQuat(T.FlightSpin.GetSafeNormal(), float(T.FlightSpin.Size()) * Dt) * T.FlightRotation).GetNormalized();
        BoardRoot->SetWorldTransform(FTransform(T.FlightRotation, At + T.FlightRotation.GetUpVector() * (DeckPivot - FlightRadius) * Scale, FVector(Scale)));
        return;
    }
    if (T.SettleTime >= 0.f)
    {
        T.SettleTime += Dt;
        const float A = FMath::SmoothStep(0.f, 1.f, T.SettleTime / BoardSettle);
        FTransform Shown;
        Shown.Blend(T.SettleFrom, T.SettleTo, A);
        BoardRoot->SetWorldTransform(Shown);
        if (A >= 1.f) T.SettleTime = -1.f;
        return;
    }
    if (const UPrimitiveComponent* Loose = T.LooseBoard.Get())
    {
        const FTransform Body = Loose->GetComponentTransform();
        BoardRoot->SetWorldTransform(FTransform(Body.GetRotation(), Body.GetLocation() + Body.GetRotation().GetUpVector() * LooseBoardDrop * Scale, FVector(Scale)));
    }
}

void USkateComponent::SettleBoard()
{
    // The board comes to rest flat on the ground under it, keeping its heading: wheels down, or upside down when it
    // came down closer to that.
    FRideTransition& T = Transit();
    if (UProjectileMovementComponent* Flight = T.Flight.Get()) Flight->DestroyComponent();
    T.Flight.Reset();
    if (USphereComponent* Body = Cast<USphereComponent>(T.LooseBoard.Get())) { Body->DestroyComponent(); T.LooseBoard.Reset(); }
    T.SettleTime = -1.f;
    if (!BoardRoot || !Rider) return;
    const FTransform From = BoardRoot->GetComponentTransform();
    const float Scale = BoardScale();
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardSettle), false, Rider);
    const FVector Start = From.GetLocation() + FVector(0, 0, 30.f * Scale);
    if (!GetWorld()->LineTraceSingleByChannel(Hit, Start, Start - FVector(0, 0, 300.f), ECC_WorldStatic, Params)) return;
    const FVector Normal = Hit.ImpactNormal;
    const bool bUpsideDown = From.GetRotation().GetUpVector().Z < 0.f;
    FVector Nose = FVector::VectorPlaneProject(From.GetRotation().GetForwardVector(), Normal);
    if (Nose.SizeSquared() < .01) Nose = FVector::CrossProduct(From.GetRotation().GetRightVector(), Normal);
    const FQuat Rotation = FRotationMatrix::MakeFromXZ(Nose.GetSafeNormal(), bUpsideDown ? -Normal : Normal).ToQuat();
    T.SettleFrom = From;
    T.SettleTo = FTransform(Rotation, FVector(Hit.ImpactPoint) + Normal * (bUpsideDown ? UpsideDownDeck : DeckPivot) * Scale, FVector(Scale));
    T.SettleTime = 0.f;
}

void USkateComponent::EndOnFoot(float Blend)
{
    // The character's own pose blends in from where the clip left the body; the board stays where it is.
    FRideTransition& T = Transit();
    T.Foot = ERideFoot::Off; T.bCarryShown = false;
    if (Ride) Ride->GetAnimator().ClearOverride(0.f);
    if (!RetailPose.IsEmpty()) { RetailPose.Reset(); RequestPoseBlend(Blend); }
}

// ---------------------------------------------------------------------------------------------------------------
// The mount and dismount clips.

void USkateComponent::StepRideClip(float Dt)
{
    FRideTransition& T = *Transition;
    UCharacterMovementComponent* M = Movement();
    const FRideTuning& Tune = FRideTuning::Get();
    if (!Ride || !T.Clip || !M) { EndRideClip(); return; }
    const bool bGround = M->IsMovingOnGround();
    // In the air: CharacterMovement keeps the fall. The landing ends a jump (a landing clip, the board in hand) and
    // a board thrown under the feet (on it once it is there, else on foot holding it).
    if (T.Foot == ERideFoot::Air || T.Foot == ERideFoot::AirMount)
    {
        if (!bGround) { T.AirTime += Dt; T.FallSpeed = M->Velocity.Z; }
        else if (T.Foot == ERideFoot::AirMount && T.ClipTime >= T.BoardContact) { FinishRideClip(); return; }
        else
        {
            // Down before a kicked board left the clip: it flies on from here.
            if (T.bKickOut) LaunchBoard();
            if (!BeginLandClip()) { FinishRideClip(); return; }
        }
    }
    const float Before = T.ClipTime;
    // A get-up holds its first frame (the fallen pose's snapshot) until the physical rider has handed its bodies over
    // to the animation (a frame or two), at most RecoverWait.
    const bool bWaiting = T.Foot == ERideFoot::Recover && PhysicalRider && PhysicalRider->IsGettingUp() && PhysicalRider->GetGetUpAlpha() <= 0.f &&
        T.WaitTime < RecoverWait;
    if (bWaiting) T.WaitTime += Dt;
    else if (T.bClipStarted) T.ClipTime = FMath::Min(T.ClipLength, T.ClipTime + Dt * T.ClipRate);
    T.bClipStarted = true;
    // A trajectory held in the world moves on by the clip's own travel; one that turns turns the clip's way.
    if (T.bAnchored && T.ClipTime > Before)
    {
        FVector Move = FRideAnimator::RootMotion(T.Clip, Before, T.ClipTime).GetTranslation();
        Move.Z = 0.;
        T.Anchor += ClipToWorld(Move, T.bMirror, T.TrajYaw);
    }
    if (T.bFollowYaw)
    {
        const float Yaw = ClipYaw(T.Clip, T.ClipTime);
        T.TrajYaw = ClipYawToWorld(FMath::FindDeltaAngleDegrees(T.ClipYawLast, Yaw), T.bMirror, T.TrajYaw);
        T.ClipYawLast = Yaw;
    }
    // The body stands on the deck from the board's touchdown (mount), or steps down off it (dismount); a clip with
    // the board in hand only (a jump, a landing) never stands on it.
    if (T.BoardContact < 0.f) T.Lift = 0.f;
    else if (T.Foot == ERideFoot::Mount || T.Foot == ERideFoot::AirMount) T.Lift = FMath::SmoothStep(T.BoardContact, T.ClipLength, T.ClipTime);
    else T.Lift = 1.f - FMath::SmoothStep(0.f, FMath::Max(.05f, T.BoardContact), T.ClipTime);
    FRideAnimLayers Layers;
    Layers.bMirror = T.bMirror; Layers.Lock = 1.f;          // Lock 1: at the handover the session puts the clip's board on its deck
    Layers.Add(T.Clip, T.ClipTime, 1.f);
    Ride->GetAnimator().SetOverride(Layers, T.ClipBlendIn);
    Rider->SetActorRotation(FRotator(0, T.TrajYaw, 0));
    // The board goes where the clip has it while it is the clip's (in hand, or rolling away in a run-out).
    const bool bClipBoard = T.Board == ERideBoard::Hand || T.Foot == ERideFoot::RunOut;
    auto Show = [&](float StepDt)
    {
        // The trajectory on the capsule's floor, displaced by an offset easing away, moving onto the deck by TrajEnd,
        // or held in the world.
        const FVector Floor = OffBoardGround();
        // On the board in the air (a caveman after its touchdown) the deck stays over the capsule, where the ride
        // starts: the trajectory moves back as the clip's board moves on.
        if (T.Foot == ERideFoot::AirMount && T.TrajEndTime > 0.f && T.ClipTime > T.TrajEndTime)
        {
            const FVector OnDeck = ClipBone(T.Clip, DeckBone, T.ClipTime);
            T.TrajEnd = -ClipToWorld(FVector(OnDeck.X, OnDeck.Y, 0.), T.bMirror, T.TrajYaw);
        }
        FVector Offset = T.TrajOffset * (1.f - FMath::SmoothStep(0.f, T.OffsetTime, T.ClipTime));
        if (T.TrajEndTime > 0.f) Offset += (T.TrajEnd - T.DeckDrift) * FMath::SmoothStep(0.f, T.TrajEndTime, T.ClipTime);
        if (T.bAnchored) { Offset.X = T.Anchor.X - Floor.X; Offset.Y = T.Anchor.Y - Floor.Y; }
        T.AppliedOffset = Offset;
        Ride->StepOffBoard(StepDt, FTransform(FRotator(0, T.TrajYaw, 0), Floor + Offset));
        // Where the pose put the board against where the clip's tracks have it, for the frames to come.
        const int32 DeckIndex = Ride->Names.IndexOfByKey(DeckBone);
        if (T.TrajEndTime > 0.f && (T.ClipTime < T.TrajEndTime || T.Foot == ERideFoot::AirMount) && Ride->Bones.IsValidIndex(DeckIndex))
        {
            const FVector Posed = (Ride->Bones[DeckIndex] * Ride->Root).GetLocation();
            const FVector Tracked = Ride->Root.GetLocation() + ClipToWorld(ClipBone(T.Clip, DeckBone, T.ClipTime), T.bMirror, T.TrajYaw);
            T.DeckDrift = FVector(Posed.X - Tracked.X, Posed.Y - Tracked.Y, 0.);
        }
        PublishOffBoardPose(T.Lift, bClipBoard);
    };
    Show(Dt);
    // From the character's own pose (or a fallen body): the clip's pelvis starts where the character's is.
    if (T.bMatchPelvis) { T.bMatchPelvis = false; if (MatchPelvis()) Show(0.f); }
    // Onto a lying board: the posed board where the lying one is (the clip's tracks only nearly agree with the pose).
    if (T.bMatchDeck)
    {
        T.bMatchDeck = false;
        const int32 DeckIndex = Ride->Names.IndexOfByKey(DeckBone);
        if (Ride->Bones.IsValidIndex(DeckIndex))
        {
            const FVector Delta = OffBoardDeckFrom.GetLocation() - (Ride->Bones[DeckIndex] * Ride->Root).GetLocation();
            T.Anchor += FVector(Delta.X, Delta.Y, 0.);
            Show(0.f);
        }
    }
    // Getting up: the pose rises out of the fallen body (the physical rider's snapshot of it).
    if (T.Foot == ERideFoot::Recover && PhysicalRider && !RetailPose.IsEmpty())
        PhysicalRider->BlendFromSnapshot(RetailPose, T.ClipTime / FMath::Max(.05f, Tune.RecoverBlend));
    // A kick-out's or run-out's board: its motion over the frames shown, for its flight once the clip lets it go.
    if ((T.bKickOut || T.Foot == ERideFoot::RunOut) && BoardRoot && Dt > 0.f)
    {
        // Measured over KickWindow at least: a very short frame would turn the pose's small uneven steps into a
        // fast throw.
        const FTransform Shown = BoardRoot->GetComponentTransform();
        T.KickTime += Dt;
        if (!T.bDeckKnown)
        {
            T.KickVelocity = M->Velocity; T.FlightSpin = FVector::ZeroVector;
            T.LastDeck = Shown; T.bDeckKnown = true; T.KickTime = 0.f;
        }
        else if (T.KickTime >= KickWindow)
        {
            const FVector Velocity = (Shown.GetLocation() - T.LastDeck.GetLocation()) / T.KickTime;
            const FQuat Turn = (Shown.GetRotation() * T.LastDeck.GetRotation().Inverse()).GetNormalized();
            FVector Axis; float Angle;
            Turn.ToAxisAndAngle(Axis, Angle);
            if (Angle > PI) Angle -= 2.f * PI;
            T.KickVelocity = FMath::Lerp(T.KickVelocity, Velocity, .5f);
            T.FlightSpin = FMath::Lerp(T.FlightSpin, Axis * (Angle / T.KickTime), .5f);
            T.LastDeck = Shown; T.KickTime = 0.f;
        }
    }
    if (T.ClipTime >= T.ClipLength)
    {
        if (T.Foot == ERideFoot::Air)
        {
            // A kicked board flies on by itself from the clip's end.
            if (T.bKickOut) LaunchBoard();
            // Still in the air: the next clip of the fall when there is time for it, else this one's last frame.
            const float Left = AirTimeLeft();
            if (T.AirNext && Left > AirChain)
            {
                UAnimSequence* Next = T.AirNext;
                const FVector Applied = T.AppliedOffset;
                StartClip(Next, ERideFoot::Air, T.bMirror, T.TrajYaw, Tune.ClipBlend * .5f);
                T.ClipRate = FMath::Clamp(T.ClipLength / Left, .5f, 2.f);
                T.TrajOffset = Applied; T.OffsetTime = FMath::Min(.2f, T.ClipLength);
            }
            return;
        }
        if (T.Foot == ERideFoot::AirMount && !bGround)
        {
            // Close above the ground the ride would snap down onto it: the feet stay on the board until the landing.
            float Height = -1.f;
            AirTimeLeft(&Height);
            if (Height >= 0.f && Height < AirMountHeight) return;
        }
        FinishRideClip();
        return;
    }
    // A clip that ends standing gives way to the stick after a while, and any landing, step-off or run-out to a turn
    // away from it.
    float FreeFrom = 2.f;
    if (T.Foot == ERideFoot::Land || T.Foot == ERideFoot::Dismount) FreeFrom = .4f;
    else if (T.Foot == ERideFoot::RunOut) FreeFrom = .6f;
    else if (T.Foot == ERideFoot::Recover) FreeFrom = FMath::Max(.65f, (Tune.RecoverBlend + .2f) / FMath::Max(.1f, T.ClipLength));
    if (T.ClipTime > FreeFrom * T.ClipLength)
    {
        const FVector Wish = MoveWish(Rider);
        if (!Wish.IsNearlyZero() && (T.bEndsStanding || FVector::DotProduct(Wish, FRotator(0, T.TrajYaw, 0).Vector()) < .5f))
        {
            T.EndPhase = ClipPhase(T.Clip, T.ClipTime, T.bMirror);
            FinishRideClip();
            return;
        }
    }
    if (!T.bDrive) return;
    // The capsule follows the clip's travel (its velocity about the time shown, so the uneven native steps do not
    // shake it): at the clip's own speed scaled from ScaleStart to ScaleEnd, or along it at a speed going from
    // SpeedStart to SpeedEnd.
    const float A = FMath::SmoothStep(0.f, 1.f, T.ClipTime / FMath::Max(.01f, T.ClipLength));
    const FVector Travel = ClipToWorld(ClipVelocity(T.Clip, T.ClipTime), T.bMirror, T.TrajYaw) * T.ClipRate;
    FVector Drive;
    if (T.SpeedStart >= 0.f)
    {
        const FVector Way = Travel.Size2D() > 20.f ? Travel.GetSafeNormal2D() : FRotator(0, T.TrajYaw, 0).Vector();
        Drive = Way * FMath::Lerp(T.SpeedStart, T.SpeedEnd, A);
    }
    else Drive = Travel * FMath::Lerp(T.ScaleStart, T.ScaleEnd, A);
    if (T.bAnchored && T.AnchorBlendFrom >= 0.f && Dt > 0.f)
    {
        // Stepping on: where the capsule should be at the next frame's clip time, eased from where it stood onto the
        // trajectory held in the world, and the speed that takes it there (from rest, without lagging behind).
        const float Next = FMath::Min(T.ClipLength, T.ClipTime + Dt * T.ClipRate);
        FVector Move = FRideAnimator::RootMotion(T.Clip, T.ClipTime, Next).GetTranslation();
        Move.Z = 0.;
        const FVector Anchor = T.Anchor + ClipToWorld(Move, T.bMirror, T.TrajYaw);
        const FVector Target = Anchor - (T.TrajEndTime > 0.f ? T.TrajEnd * FMath::SmoothStep(0.f, T.TrajEndTime, Next) : FVector::ZeroVector);
        const FVector Want = FMath::Lerp(T.AnchorFrom, Target, FMath::SmoothStep(T.AnchorBlendFrom, T.ClipLength, Next));
        Drive = (Want - OffBoardGround()) / Dt;
        Drive.Z = 0.;
        Drive = Drive.GetClampedToMaxSize2D(2.f * AnchorSpeed);
    }
    else if (T.bAnchored)
    {
        // After the trajectory held in the world (onto the deck by the clip's end, for a mount).
        const FVector Target = T.Anchor - (T.TrajEndTime > 0.f ? T.TrajEnd * FMath::SmoothStep(0.f, T.TrajEndTime, T.ClipTime) : FVector::ZeroVector);
        FVector Pull = (Target - OffBoardGround()) * AnchorGain;
        Pull.Z = 0.;
        Drive = (Drive + Pull).GetClampedToMaxSize2D(AnchorSpeed);
    }
    else if (T.TrajEndTime > 0.f && T.ClipTime < T.TrajEndTime && Dt > 0.f)
    {
        // Onto the deck: the capsule moves on by what the trajectory moves back.
        const float Next = FMath::Min(T.ClipLength, T.ClipTime + Dt * T.ClipRate);
        Drive -= T.TrajEnd * (FMath::SmoothStep(0.f, T.TrajEndTime, Next) - FMath::SmoothStep(0.f, T.TrajEndTime, T.ClipTime)) / Dt;
    }
    SetDrive(Drive);
}

void USkateComponent::FinishRideClip()
{
    FRideTransition& T = *Transition;
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    // A driven clip leaves at its drive's speed; in the air at the fall's.
    const FVector Velocity = T.bDrive ? T.DriveVelocity : M->Velocity;
    const ERideFoot Was = T.Foot;
    const bool bMount = Was == ERideFoot::Mount || Was == ERideFoot::AirMount;
    EndRideClip(!bMount);
    if (bMount)
    {
        // On the board where the clip put it down, moving as the rider was.
        const int32 D = Ride->Names.IndexOfByKey(DeckBone);
        const FTransform DeckWorld = Ride->Bones.IsValidIndex(D) ? Ride->Bones[D] * Ride->Root : Ride->Root;
        const FQuat Q = DeckWorld.GetRotation();
        UE_LOG(LogTemp, Display, TEXT("SKATE ride mount: onto the board at %.0f cm/s%s, nose %.0f deg from the travel, the deck %.1f cm from the capsule (drift %.1f cm)"), Velocity.Size(),
            M->IsMovingOnGround() ? TEXT("") : TEXT(" in the air"),
            FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Q.GetForwardVector().GetSafeNormal2D(), Velocity.GetSafeNormal2D())), -1.f, 1.f))),
            FVector::Dist2D(DeckWorld.GetLocation(), Rider->GetActorLocation()), T.DeckDrift.Size());
        if (!GetOnBoard(DeckWorld.GetLocation() - Q.GetUpVector() * DeckPivot, Q, Velocity, Tune.ClipBlend))
            UE_LOG(LogTemp, Warning, TEXT("SKATE ride mount: the ride did not start"));
        return;
    }
    // Off: running on (or standing) at the clip's speed, which the stick then shares out between the character's own
    // and momentum that fades (ReleaseDrive). With the board in hand the carry goes on; without it (lying, kicked
    // away, rolling on from a run-out) the character's own pose does.
    const FVector Flat(Velocity.X, Velocity.Y, 0.f);
    M->Velocity = FVector(Flat.X, Flat.Y, M->Velocity.Z);
    HoldDriveForInput(Flat);
    if (Was == ERideFoot::RunOut) LaunchBoard();
    if (T.Board == ERideBoard::Hand) BeginCarry(Was == ERideFoot::Air ? T.Phase : T.EndPhase);
    else EndOnFoot(Tune.CarryBlend);
}

void USkateComponent::EndRideClip(bool bKeepDrive)
{
    if (!bKeepDrive) StopDrive();
    bRideClip = false;
    if (!Transition) return;
    FRideTransition& T = *Transition;
    T.Clip = nullptr; T.AirNext = nullptr; T.bMatchPelvis = false;
    if (T.Foot != ERideFoot::Off && T.Foot != ERideFoot::Carry) T.Foot = ERideFoot::Off;
}

void USkateComponent::SetDrive(const FVector& Velocity)
{
    // An override root motion source moves the capsule along the clip (its Z left to CharacterMovement: gravity and
    // floors still apply); the character's own input waits until the clip ends.
    UCharacterMovementComponent* M = Movement();
    if (!M) return;
    FRideTransition& T = Transit();
    T.DriveVelocity = FVector(Velocity.X, Velocity.Y, 0.f);
    const TSharedPtr<FRootMotionSource> Existing = T.DriveId ? M->GetRootMotionSourceByID(T.DriveId) : nullptr;
    if (Existing.IsValid() && Existing->GetScriptStruct() == FRootMotionSource_ConstantForce::StaticStruct())
    {
        static_cast<FRootMotionSource_ConstantForce*>(Existing.Get())->Force = T.DriveVelocity;
        return;
    }
    TSharedPtr<FRootMotionSource_ConstantForce> Source = MakeShared<FRootMotionSource_ConstantForce>();
    Source->InstanceName = DriveName;
    Source->AccumulateMode = ERootMotionAccumulateMode::Override;
    Source->Priority = 10;
    Source->Force = T.DriveVelocity;
    Source->Duration = -1.f;                                 // until the clip ends (EndRideClip)
    Source->Settings.SetFlag(ERootMotionSourceSettingsFlags::IgnoreZAccumulate);
    T.DriveId = M->ApplyRootMotionSource(Source);
}

void USkateComponent::StopDrive()
{
    if (!Transition) return;
    FRideTransition& T = *Transition;
    if (T.DriveId) if (UCharacterMovementComponent* M = Movement()) M->RemoveRootMotionSourceByID(T.DriveId);
    T.DriveId = 0; T.bReleasePending = false;
}

void USkateComponent::HoldDriveForInput(const FVector& Velocity)
{
    // CharacterMovement moves before the character's tick gives it the stick, so its first move off the board would
    // have none and brake the speed away: the drive carries the speed over that move, and the stick the character's
    // tick then gives the move after it shares the speed out (ReleaseDrive, the next frame).
    StopMomentum();
    SetDrive(Velocity);
    Transit().bReleasePending = true;
}

void USkateComponent::ReleaseDrive()
{
    FRideTransition& T = Transit();
    const FVector Flat(T.DriveVelocity.X, T.DriveVelocity.Y, 0.f);
    StopDrive();
    UCharacterMovementComponent* M = Movement();
    if (!M || !Rider || Mode != ESkateMode::Off || bRideClip) return;
    // The character runs on as fast as the stick lets it (the analog speed CharacterMovement's CalcVelocity allows);
    // the rest fades as momentum, so with the stick let go the whole speed runs out.
    const float Stick = FMath::Min(1.f, float(Rider->GetPendingMovementInputVector().Size()));
    const FVector Own = Flat.GetClampedToMaxSize(FMath::Max(M->GetMaxSpeed() * Stick, M->GetMinAnalogSpeed()));
    M->Velocity = FVector(Own.X, Own.Y, M->Velocity.Z);
    StartMomentum(Flat - Own);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride on foot at %.0f cm/s: %.0f cm/s the character's own (stick %.2f), %.0f cm/s momentum"),
        Flat.Size(), Own.Size(), Stick, (Flat - Own).Size());
}

// ---------------------------------------------------------------------------------------------------------------
// In the air: a jump with the board in hand, the board thrown under the feet, a step off it from a grab, the landings.

bool USkateComponent::StartClip(UAnimSequence* Clip, ERideFoot Foot, bool bMirror, float Yaw, float BlendIn)
{
    if (!Clip || Length(Clip) < .05f) return false;
    FRideTransition& T = Transit();
    T.Clip = Clip; T.ClipTime = 0.f; T.ClipLength = Length(Clip); T.ClipRate = 1.f; T.bClipStarted = false;
    T.Foot = Foot; T.bMirror = bMirror; T.TrajYaw = Yaw; T.ClipBlendIn = BlendIn;
    T.ScaleStart = T.ScaleEnd = 1.f; T.TrajOffset = FVector::ZeroVector; T.OffsetTime = .35f;
    T.BoardContact = -1.f; T.Lift = 0.f; T.bCarryShown = false; T.bMatchPelvis = false; T.bEndsStanding = false;
    T.AirNext = nullptr;
    T.SpeedStart = T.SpeedEnd = -1.f; T.TrajEnd = T.DeckDrift = FVector::ZeroVector; T.TrajEndTime = 0.f; T.WaitTime = 0.f; T.bMatchDeck = false;
    T.bFollowYaw = false; T.ClipYawLast = ClipYaw(Clip, 0.f); T.bAnchored = false; T.bKickOut = false; T.bDeckKnown = false;
    T.AnchorBlendFrom = -1.f; T.KickTime = 0.f;
    // In the air CharacterMovement keeps the fall; on the ground the clip's travel moves the capsule.
    T.bDrive = Foot != ERideFoot::Air && Foot != ERideFoot::AirMount;
    T.bReleasePending = false;
    // In the air a drive holds the flat velocity (gravity keeps the height): the landing's move, before this
    // component sees it, does not brake a character that has no stick yet.
    if (!T.bDrive) if (const UCharacterMovementComponent* M = Movement()) SetDrive(FVector(M->Velocity.X, M->Velocity.Y, 0.f));
    bRideClip = true;
    return true;
}

void USkateComponent::AnchorClipAt(FName Bone, const FVector& World)
{
    // The trajectory placed so the clip's bone starts at World; the offset from the capsule's floor eases away.
    FRideTransition& T = Transit();
    T.TrajOffset = World - ClipToWorld(ClipBone(T.Clip, Bone, T.ClipTime), T.bMirror, T.TrajYaw) - OffBoardGround();
}

bool USkateComponent::MatchPelvis()
{
    // The clip's pose was just published: move its trajectory so its pelvis is where the character's own was.
    FRideTransition& T = Transit();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FName Pelvis = RiderApi->GetSkateBone(TEXT("pelvis"));
    if (!Mesh || Pelvis.IsNone() || Mesh->GetBoneIndex(Pelvis) == INDEX_NONE) return false;
    FVector Shown;
    if (!PoseBoneWorld(Mesh, Mesh->GetRelativeTransform() * Rider->GetActorTransform(), RetailPose, Pelvis, Shown)) return false;
    const FVector Delta = Mesh->GetBoneLocation(Pelvis) - Shown;
    // A trajectory held in the world moves there; otherwise the offset from the capsule's floor (easing away) does.
    if (T.bAnchored) { T.Anchor += FVector(Delta.X, Delta.Y, 0.); T.TrajOffset.Z += Delta.Z; }
    else T.TrajOffset += Delta;
    return true;
}

float USkateComponent::ClipPhase(const UAnimSequence* Clip, float Time, bool bMirror) const
{
    // The run cycle's phase that matches the clip's feet at Time (FeetPhase's convention), in the carry's stance.
    const FRideTransition& T = *Transition;
    static const FName Left(TEXT("LEFTFOOT")), Right(TEXT("RIGHTFOOT"));
    auto Lead = [&](float At) { return float(ClipBone(Clip, Left, At).X - ClipBone(Clip, Right, At).X); };
    const float Step = FMath::Min(1.f / 30.f, Time);
    const float Now = Lead(Time);
    const float Rate = Step > 0.f ? (Now - Lead(Time - Step)) / Step : 0.f;
    const float W = 2.f * PI / FMath::Max(.1f, T.CycleLength[2]);
    return FMath::Frac(FMath::Atan2(-Now, -Rate / W) / (2.f * PI) + (bMirror != !bGoofy ? .5f : 0.f));
}

float USkateComponent::AirTimeLeft(float* Height) const
{
    // The time to the ground straight below on the current fall (and the height above it, -1 without one in 30 m).
    const UCharacterMovementComponent* M = Movement();
    const UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    const FVector Feet = OffBoardGround();
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideAirTime), false, Rider);
    FCollisionResponseParams Response;
    Capsule->InitSweepCollisionParams(Params, Response);
    FHitResult Hit;
    const bool bHit = GetWorld()->LineTraceSingleByChannel(Hit, Feet, Feet - FVector(0, 0, 3000.f), Capsule->GetCollisionObjectType(), Params, Response);
    const float Drop = bHit ? float(Feet.Z - Hit.ImpactPoint.Z) : 3000.f;
    if (Height) *Height = bHit ? Drop : -1.f;
    const float G = FMath::Max(100.f, float(-M->GetGravityZ()));
    const float Up = M->Velocity.Z;
    return (Up + FMath::Sqrt(FMath::Max(0.f, Up * Up + 2.f * G * FMath::Max(0.f, Drop)))) / G;
}

bool USkateComponent::BeginCarryJump(float Speed)
{
    // The jump with the board in hand, taking off from the stride's quarter (or from a stand), timed to the fall.
    FRideTransition& T = Transit();
    UCharacterMovementComponent* M = Movement();
    const int32 Quarter = FMath::RoundToInt(T.Phase * 4.f) % 4;
    const bool bRun = Speed > RunDismount;
    const int32 Land = Quarter < 2 ? 25 : 75;
    const FString Name = bRun ? FString::Printf(TEXT("JBR_RUN_FWD_%d_TO_SML_FWD_%d"), Quarter * 25, Land) : FString(TEXT("JBR_STAND_0_TO_SML_FWD_0"));
    const FVector Applied = T.AppliedOffset;
    if (!StartClip(Ride->GetAnimator().Clip(*Name), ERideFoot::Air, !bGoofy, Rider->GetActorRotation().Yaw, FRideTuning::Get().ClipBlend * .5f)) return false;
    T.TrajOffset = Applied; T.OffsetTime = FMath::Min(.2f, T.ClipLength);
    T.LandPhase = bRun ? Land : 0;
    T.AirStartZ = OffBoardGround().Z; T.AirTime = 0.f; T.FallSpeed = M->Velocity.Z;
    const float Left = AirTimeLeft();
    T.ClipRate = FMath::Clamp(T.ClipLength / FMath::Max(.1f, Left), .6f, 1.4f);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride jump: %s at %.0f cm/s, %.2f s in the air ahead, rate %.2f"), *Name, Speed, Left, T.ClipRate);
    return true;
}

bool USkateComponent::BeginLandClip()
{
    // Down on foot with the board in hand: the landing by how big the fall was, how far down or up from the take-off,
    // and whether the character runs on; its travel scaled so the speed carries on.
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    if (!Ride || !M || T.Board != ERideBoard::Hand) return false;
    const FVector Flat(M->Velocity.X, M->Velocity.Y, 0.f);
    const float Speed = Flat.Size();
    const float Drop = OffBoardGround().Z - T.AirStartZ;
    const bool bBig = T.AirTime > BigAirTime || T.FallSpeed < BigFall;
    const bool bDown = Drop < LandDown;
    const TCHAR* Size = bBig ? TEXT("BIG") : TEXT("SML");
    const TCHAR* Slope = bDown ? TEXT("DN") : Drop > LandUp ? TEXT("UP") : TEXT("FWD");
    const bool bRun = Speed > RunDismount;
    const int32 Step = bBig && bDown ? 0 : T.LandPhase >= 50 ? 75 : 25;
    const FString Name = bRun ? FString::Printf(TEXT("BR_LAND_%s_%s_%d_INTO_RUN_FWD"), Size, Slope, Step)
        : FString::Printf(TEXT("BR_LAND_%s_%s_0_INTO_STAND"), Size, Slope);
    UAnimSequence* Clip = Ride->GetAnimator().Clip(*Name);
    const FVector Applied = T.AppliedOffset;
    const float AirTime = T.AirTime, Fall = T.FallSpeed;
    if (!StartClip(Clip, ERideFoot::Land, T.bMirror, T.TrajYaw, Tune.ClipBlend)) return false;
    T.TrajOffset = Applied; T.OffsetTime = FMath::Min(.2f, T.ClipLength);
    T.bEndsStanding = !bRun;
    // Running on, at the speed it came down with; stopping, from that speed with the clip.
    if (bRun) T.SpeedStart = T.SpeedEnd = Speed;
    else T.ScaleStart = FMath::Clamp(Speed / FMath::Max(50.f, float(ClipVelocity(Clip, 0.f).Size2D())), .3f, 3.f);
    if (Clip->HasCurveData(CadenceCurve, false))
    {
        float Cadence = Clip->EvaluateCurveData(CadenceCurve, FAnimExtractContext(double(T.ClipLength)));
        if (Cadence > 1.f) Cadence /= 100.f;
        T.EndPhase = FMath::Frac(Cadence + (T.bMirror != !bGoofy ? .5f : 0.f));
    }
    else T.EndPhase = ClipPhase(Clip, T.ClipLength, T.bMirror);
    SetDrive(Flat);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride landing: %s at %.0f cm/s after %.2f s in the air (falling %.0f cm/s, %.0f cm %s the take-off)"),
        *Name, Speed, AirTime, -Fall, FMath::Abs(Drop), Drop < 0.f ? TEXT("below") : TEXT("above"));
    return true;
}

bool USkateComponent::BeginAirMountClip()
{
    // A caveman: in the air the board (in hand, or dissolving into it) goes under the feet, the foot nearer the front
    // first, and the ride starts where it lands on it.
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    const bool bMirror = !bGoofy;
    const bool bLeft = (T.FootDiff > 0.f) != bMirror;
    UAnimSequence* Clip = Ride->GetAnimator().Clip(bLeft ? TEXT("BR_LF_AIR_INTO_MOUNT_BSGRAB") : TEXT("BR_RF_AIR_INTO_MOUNT_BSGRAB"));
    if (!Clip || Length(Clip) < .1f) return false;
    // From a clip (a jump with the board, a step off it) the pose mesh blends; from the character's own pose the
    // character does, and the clip's pelvis starts at the character's.
    const bool bFromClip = bRideClip && T.Foot == ERideFoot::Air;
    const FVector Applied = bFromClip ? T.AppliedOffset : FVector::ZeroVector;
    const FVector Flat(M->Velocity.X, M->Velocity.Y, 0.f);
    const float Yaw = bFromClip ? T.TrajYaw : Flat.Size() > 100.f ? float(Flat.Rotation().Yaw) : float(Rider->GetActorRotation().Yaw);
    RiderApi->PrepareToSkate();
    StopMomentum();
    UseWorldBoard();
    if (T.Board == ERideBoard::World) DropLyingBoard();
    if (T.Board != ERideBoard::Hand) T.Shown = 0.f;
    T.Board = ERideBoard::Hand; T.bRecall = false;
    ShowBoard(1.f, false);
    if (!StartClip(Clip, ERideFoot::AirMount, bMirror, Yaw, bFromClip ? Tune.ClipBlend : 0.f)) return false;
    if (!bFromClip) RequestPoseBlend(Tune.ClipBlend);
    T.BoardContact = BoardCrossing(Clip, false, T.ClipLength * .6f);
    float Height = -1.f;
    const float Left = AirTimeLeft(&Height);
    T.ClipRate = FMath::Clamp(T.ClipLength / FMath::Max(.05f, Left), .8f, 1.5f);
    T.TrajOffset = Applied; T.bMatchPelvis = !bFromClip; T.OffsetTime = FMath::Max(.1f, T.BoardContact);
    // The ride starts with the capsule over the deck: by the board's touchdown the clip's board is under it.
    const FVector Contact = ClipBone(Clip, DeckBone, T.BoardContact);
    T.TrajEnd = -ClipToWorld(FVector(Contact.X, Contact.Y, 0.), bMirror, Yaw);
    T.TrajEndTime = FMath::Max(.05f, T.BoardContact);
    TurnActor(Yaw);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride caveman: %s at %.0f cm/s, %.0f cm up, %.2f s in the air ahead, rate %.2f, %s"),
        *Clip->GetName(), Flat.Size(), Height, Left, T.ClipRate, bFromClip ? TEXT("from the jump") : TEXT("from the character's own pose"));
    return true;
}

bool USkateComponent::BeginAirDismountClip()
{
    // In the air the rider lets go with the feet: from a grab the step off the board, the board into the hand, then
    // the fall on foot (JBR_AIRDISMOUNT_TO_BIG_DN_0) and a landing; without one the feet kick the board away
    // (BR_KICKOUT_*), it flies on by itself once the clip lets it go, and the rider falls on without it.
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    if (!Ride || !M) return false;
    const ERideGrab Held = Ride->GetBody().Grab;
    const bool bKick = Held == ERideGrab::None;
    const TCHAR* Grab = TEXT("MUTE");
    switch (Held)
    {
    case ERideGrab::Indy: Grab = TEXT("FS"); break;
    case ERideGrab::Melon: Grab = TEXT("BS"); break;
    case ERideGrab::ChristAir: Grab = TEXT("STALE"); break;
    case ERideGrab::TuckKnee: Grab = TEXT("DBL"); break;
    default: break;
    }
    const FString Name = bKick ? FString::Printf(TEXT("BR_KICKOUT_%s_INTO_NB_AIR"), Ride->GetBody().Crouch > .5f ? TEXT("LO") : TEXT("HI"))
        : FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_BR_AIR"), Grab);
    UAnimSequence* Clip = Ride->GetAnimator().Clip(*Name);
    const FVector DeckForward = FVector(Forward().X, Forward().Y, 0.f).GetSafeNormal();
    if (!Clip || Length(Clip) < .1f || DeckForward.IsNearlyZero()) return false;
    const FVector Carried = Vel;
    const FVector Flat(Carried.X, Carried.Y, 0.f);
    const bool bBackward = Flat.Size() > 15.f ? FVector::DotProduct(Flat, DeckForward) < 0.f : bFakie;
    const float Yaw = (bBackward ? -DeckForward : DeckForward).Rotation().Yaw;
    // The deck it leaves, before the capsule changes.
    const FVector DeckNow = Pos + Up() * DeckPivot;
    SuspendRetailRuntime();
    RequestPoseBlend(Tune.ClipBlend);
    LeaveBoard();
    // Rising, or with more than a moment of the fall ahead, the rider falls on with the board's velocity: a floor found
    // then would drop the rise and end the clip at once.
    M->Velocity = Carried;
    const bool bComingDown = Carried.Z <= 0.f && AirTimeLeft() <= KickFloorTime;
    const bool bFloor = StandUpOffBoard(Yaw, bComingDown);
    M->Velocity = bFloor ? Flat : Carried;
    StartClip(Clip, ERideFoot::Air, bGoofy == bBackward, Yaw, 0.f);
    T.BoardContact = BoardCrossing(Clip, true, .2f);
    T.Lift = 1.f;
    // The clip starts with its board on that deck; the offset from the capsule's floor eases away before the landing.
    AnchorClipAt(DeckBone, DeckNow);
    const float Left = AirTimeLeft();
    T.OffsetTime = FMath::Clamp(Left * .8f, .15f, T.ClipLength);
    T.AirNext = Ride->GetAnimator().Clip(bKick ? TEXT("JNB_KICKOUT_TO_SML_FWD_75") : TEXT("JBR_AIRDISMOUNT_TO_BIG_DN_0"));
    T.AirStartZ = OffBoardGround().Z; T.AirTime = 0.f; T.FallSpeed = Carried.Z; T.LandPhase = 0;
    // The clip has the board (in the hand, or under the kicking feet) until it lets it go.
    T.Board = ERideBoard::Hand; T.bGetUpOnFoot = false; T.bKickOut = bKick;
    UseWorldBoard();
    UE_LOG(LogTemp, Display, TEXT("SKATE ride air %s: %s at %.0f cm/s%s, %.2f s in the air ahead, offset %.1f cm, %s"), bKick ? TEXT("kick-out") : TEXT("dismount"),
        *Name, Carried.Size(), bBackward ? TEXT(" fakie") : TEXT(""), Left, T.TrajOffset.Size(), bFloor ? TEXT("walking") : TEXT("falling"));
    return true;
}

// ---------------------------------------------------------------------------------------------------------------
// Carrying the board.

void USkateComponent::RecallBoard()
{
    if (!Rider || !bAvailable || Mode != ESkateMode::Off || bRideClip) return;
    if (USkateSettings::ActiveBackend() != ESkateBackend::Ride) return;
    FRideTransition& T = Transit();
    if (T.Foot == ERideFoot::Carry) { PutBoardAway(); return; }
    if (!RiderApi->CanCarrySkateBoard() || !PrepareRideClips()) return;
    // A board lying in the world dissolves first, then a fresh one comes to the hand (TickTransition).
    if (T.Board == ERideBoard::World) { T.bRecall = true; ShowBoard(0.f, false); return; }
    T.Shown = 0.f;
    BeginCarry(0.f);
}

void USkateComponent::BeginCarry(float Phase)
{
    FRideTransition& T = Transit();
    T.Foot = ERideFoot::Carry; T.Phase = Phase; T.StandTime = 0.f; T.HoldTime = 0.f; T.bCarryShown = false;
    T.Board = ERideBoard::Hand; T.bRecall = false;
    UseWorldBoard();
    ShowBoard(1.f, false);
}

void USkateComponent::StepCarry(float Dt)
{
    FRideTransition& T = *Transition;
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    T.HoldTime += Dt;
    // Held for a while, or the hands are needed (a weapon, a climb, the sail...): it is put away.
    if (!M || !Ride || T.HoldTime > Tune.BoardHoldTime || !RiderApi->CanCarrySkateBoard()) { PutBoardAway(); return; }
    if (!M->IsMovingOnGround())
    {
        // A jump: the jump with the board in hand, from where the stride is.
        if (T.bCarryShown && M->Velocity.Z > JumpSpeed && BeginCarryJump(M->Velocity.Size2D())) return;
        // Off a ledge the character's own pose plays, the board in the hand that held it.
        if (!RetailPose.IsEmpty()) { HoldBoardAtHand(); RetailPose.Reset(); RequestPoseBlend(Tune.CarryBlend); }
        T.bCarryShown = false;
        return;
    }
    const bool bOwnPose = RetailPose.IsEmpty();
    ReleaseBoardFromHand();
    // The four cycles blended by speed between their own speeds; walk, run and sprint share one phase that advances
    // by the distance covered over the blended stride, so the feet keep to the ground.
    const float Speed = M->Velocity.Size2D();
    float Weight[4] = {};
    if (Speed <= T.CycleSpeed[1]) { const float A = Speed / T.CycleSpeed[1]; Weight[0] = 1.f - A; Weight[1] = A; }
    else if (Speed <= T.CycleSpeed[2]) { const float A = (Speed - T.CycleSpeed[1]) / (T.CycleSpeed[2] - T.CycleSpeed[1]); Weight[1] = 1.f - A; Weight[2] = A; }
    else if (Speed <= T.CycleSpeed[3]) { const float A = (Speed - T.CycleSpeed[2]) / (T.CycleSpeed[3] - T.CycleSpeed[2]); Weight[2] = 1.f - A; Weight[3] = A; }
    else Weight[3] = 1.f;
    float Moving = 0.f, Stride = 0.f;
    for (int32 I = 1; I < 4; ++I) { Moving += Weight[I]; Stride += Weight[I] * T.CycleStride[I]; }
    Stride = Moving > 1e-3f ? Stride / Moving : T.CycleStride[1];
    T.Phase = FMath::Frac(T.Phase + Dt * Speed / FMath::Max(10.f, Stride));
    T.StandTime += Dt;
    FRideAnimLayers Layers;
    Layers.bMirror = !bGoofy; Layers.Lock = 0.f;
    Layers.Add(T.Cycle[0], FMath::Fmod(T.StandTime, T.CycleLength[0]), Weight[0]);
    for (int32 I = 1; I < 4; ++I) Layers.Add(T.Cycle[I], T.Phase * T.CycleLength[I], Weight[I]);
    // Into the carry from another clip the pose mesh cross-fades; from the character's own pose the character blends.
    Ride->GetAnimator().SetOverride(Layers, bOwnPose || T.bCarryShown ? 0.f : Tune.CarryBlend);
    if (bOwnPose) RequestPoseBlend(Tune.CarryBlend);
    const FTransform Actor = Rider->GetActorTransform();
    T.AppliedOffset = Actor.GetRotation().RotateVector(T.MeshOffset);
    Ride->StepOffBoard(Dt, FTransform(FRotator(0, Actor.Rotator().Yaw, 0), OffBoardGround() + T.AppliedOffset));
    T.bCarryShown = PublishOffBoardPose(0.f);
    if (!T.bCarryShown) PutBoardAway();
}

void USkateComponent::PutBoardAway()
{
    // The character's own pose blends back in, the board dissolving in the hand that held it.
    FRideTransition& T = Transit();
    if (T.Foot == ERideFoot::Carry) T.Foot = ERideFoot::Off;
    if (Ride) Ride->GetAnimator().ClearOverride(0.f);
    if (!RetailPose.IsEmpty()) { HoldBoardAtHand(); RetailPose.Reset(); RequestPoseBlend(FRideTuning::Get().CarryBlend); }
    T.bCarryShown = false;
    if (T.Board == ERideBoard::Hand) ShowBoard(0.f, false);
}

void USkateComponent::HoldBoardAtHand()
{
    // The character's own pose has no board: it goes on the hand (a socket on that bone) where it is now.
    FRideTransition& T = Transit();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (!Mesh || !BoardRoot) return;
    FName Best; double Nearest = MAX_dbl;
    for (const TCHAR* Hand : {TEXT("hand_L"), TEXT("hand_R")})
    {
        const FName Bone = RiderApi->GetSkateBone(Hand);
        if (Bone.IsNone() || Mesh->GetBoneIndex(Bone) == INDEX_NONE) continue;
        const double Distance = FVector::Dist(Mesh->GetBoneLocation(Bone), BoardRoot->GetComponentLocation());
        if (Distance < Nearest) { Nearest = Distance; Best = Bone; }
    }
    if (Best.IsNone()) return;
    const FTransform World = BoardRoot->GetComponentTransform();
    BoardRoot->SetAbsolute(false, false, false);
    BoardRoot->AttachToComponent(Mesh, FAttachmentTransformRules::KeepRelativeTransform, Best);
    BoardRoot->SetWorldTransform(World);
    T.HandBone = Best;
}

void USkateComponent::ReleaseBoardFromHand()
{
    if (!BoardRoot || !Rider || BoardRoot->GetAttachParent() == Rider->GetRootComponent()) return;
    const FTransform World = BoardRoot->GetComponentTransform();
    // The visible deck eases from the hand onto where the clips have it (PublishOffBoardPose).
    OffBoardDeckFrom = World; OffBoardDeckBlend = 0.f;
    BoardRoot->AttachToComponent(Rider->GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform);
    BoardRoot->SetAbsolute(true, true, true);
    BoardRoot->SetWorldTransform(World);
    if (Transition) Transition->HandBone = NAME_None;
}

void USkateComponent::UseWorldBoard()
{
    // The Ride backend places the board in the world (it can stay behind when the rider leaves it).
    ReleaseBoardFromHand();
    if (BoardRoot && !BoardRoot->IsUsingAbsoluteLocation())
    {
        const FTransform Board = BoardRoot->GetComponentTransform();
        BoardRoot->SetAbsolute(true, true, true);
        BoardRoot->SetWorldTransform(Board);
    }
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
    // A bail handed over during the ride's frame: a run-out on foot, or a fallen body getting up where it lies (without
    // the clips, the session's get-up and a step off once up).
    if (T.bRunOutPending) BeginRunOut();
    if (T.bRecoverPending)
    {
        T.bRecoverPending = false;
        if (!BeginRecover() && Ride && Ride->IsBailing()) Ride->GetUp(T.RecoverGround, T.RecoverYaw);
    }

    // A bail left on foot: the pose rises out of the fallen body, and the rider steps off once up. Without the
    // physical rider (or after it gave up) the session gets up by itself and the rider steps off then.
    if (T.bGetUpOnFoot)
    {
        if (Mode == ESkateMode::Off) T.bGetUpOnFoot = false;
        else
        {
            if (PhysicalRider && PhysicalRider->IsGettingUp() && PhysicalRider->GetGetUpExit() == ERideGetUpExit::OnFoot && !RetailPose.IsEmpty())
                PhysicalRider->BlendFromSnapshot(RetailPose, PhysicalRider->GetGetUpAlpha());
            const bool bUp = Ride && Mode == ESkateMode::Ground && !Ride->IsBailing() && Ride->GetMode() != ERideState::GetUp &&
                !(PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
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
    if (Ride && T.Foot != ERideFoot::Off) Ride->GetAnimator().ClearOverride(0.f);
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
