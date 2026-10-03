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
#include "RideTransition.h"
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "RideSession.h"
#include "RideAnimator.h"
#include "RideAnimInstance.h"
#include "RidePhysicalRider.h"
#include "RideTuning.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/RootMotionSource.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
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
    // ~170, run ~540, sprint ~910).
    constexpr float WalkMount = 80.f, RunMount = 350.f, SprintMount = 720.f;
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

    float Length(const UAnimSequence* Clip) { return Clip ? Clip->GetPlayLength() : 0.f; }

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

    /** A bone's place in the clip's trajectory space (the parent chain composed up to the trajectory). */
    FVector ClipBone(const UAnimSequence* Clip, FName Bone, float Time)
    {
        const USkeleton* Skeleton = Clip ? Clip->GetSkeleton() : nullptr;
        if (!Skeleton) return FVector::ZeroVector;
        const FReferenceSkeleton& Ref = Skeleton->GetReferenceSkeleton();
        FTransform Space = FTransform::Identity;
        for (int32 I = Ref.FindBoneIndex(Bone); I != INDEX_NONE && Ref.GetBoneName(I) != Trajectory; I = Ref.GetParentIndex(I))
            Space = Space * FRideAnimator::Track(Clip, Ref.GetBoneName(I), Time);
        return Space.GetLocation();
    }

    /** A bone of a published pose (parent-relative, the mesh's bone order) in the world. */
    bool PoseBoneWorld(const USkeletalMeshComponent* Mesh, const FTransform& MeshWorld, const TArray<FTransform>& Pose, FName Bone, FVector& Out)
    {
        const USkeletalMesh* Asset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
        if (!Asset || Bone.IsNone()) return false;
        const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
        int32 I = Ref.FindBoneIndex(Bone);
        if (I == INDEX_NONE || Pose.Num() != Ref.GetNum()) return false;
        FTransform Space = FTransform::Identity;
        for (; I != INDEX_NONE; I = Ref.GetParentIndex(I)) Space = Space * Pose[I];
        Out = (Space * MeshWorld).GetLocation();
        return true;
    }

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
        // Load every transition clip now (while walking), not at the first mount.
        T.bClipsTried = true; T.bClips = true;
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
    T.Clip = Clip; T.ClipTime = 0.f; T.ClipLength = Length(Clip); T.bMirror = bMirror; T.bClipStarted = false;
    T.Foot = ERideFoot::Mount; T.bCarryShown = false; T.bDrive = true; T.bEndsStanding = false;
    T.TrajYaw = Speed > 30.f ? float(Flat.Rotation().Yaw) : float(Rider->GetActorRotation().Yaw);
    T.TrajOffset = FVector::ZeroVector;
    T.BoardContact = BoardCrossing(Clip, false, T.ClipLength * .6f);
    T.Lift = 0.f;
    // The speed carries on: the clip's travel is scaled to start at the character's speed and to end at it (the
    // board leaves at the speed the rider ran in at), and a faster run plays the clip a little faster too.
    if (Gait == 0) { T.ClipRate = 1.f; T.ScaleStart = T.ScaleEnd = 1.f; }
    else
    {
        T.ClipRate = FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, 0.f, T.ClipLength)), 1.f, 1.3f);
        T.ScaleStart = FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, 0.f, .1f)), .5f, 2.5f);
        T.ScaleEnd = FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, T.ClipLength - .1f, T.ClipLength)), .5f, 2.5f);
    }
    // The board: the one in hand, or one that dissolves into the hand over the clip's first frames.
    UseWorldBoard();
    if (T.Board == ERideBoard::World) DropLyingBoard();
    if (T.Board != ERideBoard::Hand) T.Shown = 0.f;
    T.Board = ERideBoard::Hand; T.bRecall = false;
    ShowBoard(1.f, false);
    // The pose: from the carry the pose mesh cross-fades between its own clips (both on the ground); from the
    // character's own pose the character blends.
    T.ClipBlendIn = bCarrying ? Tune.ClipBlend : 0.f;
    if (!bCarrying) RequestPoseBlend(Tune.ClipBlend);
    bRideClip = true;
    Rider->SetActorRotation(FRotator(0, T.TrajYaw, 0));
    SetDrive(Flat);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride mount: %s at %.0f cm/s (phase %.2f), rate %.2f, travel x%.2f..%.2f"),
        *Name, Speed, Phase, T.ClipRate, T.ScaleStart, T.ScaleEnd);
    return true;
}

bool USkateComponent::GetOnBoard(const FVector& Ground, const FQuat& Rotation, const FVector& Velocity, float Blend)
{
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    FRideTransition& T = Transit();
    StopMomentum(); StopDrive();
    // The on-foot body to return to, without the offset a recent dismount may still be easing away.
    SavedRadius = Capsule->GetUnscaledCapsuleRadius(); SavedHalf = Capsule->GetUnscaledCapsuleHalfHeight();
    SavedMeshLocation = Mesh->GetRelativeLocation() - T.MeshOffset; SavedMeshRotation = Mesh->GetRelativeRotation().Quaternion();
    SavedStep = M->MaxStepHeight;
    T.MeshSettleTime = -1.f;
    Pos = Ground; Rot = Rotation; Vel = Velocity;
    const FVector MeshWorld = (Mesh->GetRelativeTransform() * Rider->GetActorTransform()).GetLocation();
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
    // The ride's own clips take over from a transition clip; the character's blend hides the switch.
    if (Ride) Ride->GetAnimator().ClearOverride(0.f);
    Capsule->SetCapsuleSize(RidingRadius, RidingHalf);      // about its centre: nothing moves
    M->SetMovementMode(MOVE_Custom, MovementMode);
    // The actor stays where it is: the body's height above the session's root is measured rather than assumed. It
    // turns to the board as the first ride frame would; the mesh keeps its world place over that turn (riding, the
    // pose is anchored on the board, so the offset only matters to the blend into it).
    BodyLift = Rider->GetActorLocation().Z - Ride->Root.GetLocation().Z;
    Rider->SetActorLocationAndRotation(Ride->Root.GetLocation() + FVector(0, 0, BodyLift), Ride->Root.GetRotation(), false, nullptr, ETeleportType::None);
    SetMeshOffset(Rider->GetActorTransform().InverseTransformPosition(MeshWorld) - SavedMeshLocation);
    RequestPoseBlend(Blend);
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
    // The character takes the speed it can run at; the rest carries on as momentum that fades.
    const FVector Flat(Carried.X, Carried.Y, 0.f);
    const FVector Own = Flat.GetClampedToMaxSize(M->GetMaxSpeed());
    M->Velocity = bFloor ? Own : FVector(Own.X, Own.Y, Carried.Z);
    StartMomentum(Flat - Own);
    if (T.Board == ERideBoard::Ride) { T.Board = ERideBoard::World; T.BoardTime = 0.f; ShowBoard(0.f, false); }
    UE_LOG(LogTemp, Display, TEXT("SKATE ride dismount at %.0f cm/s (%.0f carried as momentum), %s"),
        Flat.Size(), (Flat - Own).Size(), bFloor ? TEXT("walking") : TEXT("falling"));
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

bool USkateComponent::StandUpOffBoard(float Yaw)
{
    // Standing: the capsule grows about its centre, turns upright to Yaw and settles onto the floor under it when there
    // is one close by; otherwise the character falls from where it is. The body keeps its world place while the capsule
    // moves under it, then eases back onto it.
    FRideTransition& T = Transit();
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FVector MeshWorld = (Mesh->GetRelativeTransform() * Rider->GetActorTransform()).GetLocation();
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
            if (M->IsWalkable(Hit)) { Stand = Hit.Location + FVector(0, 0, FloorGap); bFloor = true; }
            break;
        }
    }
    Rider->SetActorLocationAndRotation(Stand, FRotator(0, Yaw, 0), false, nullptr, ETeleportType::None);
    M->SetMovementMode(bFloor ? MOVE_Walking : MOVE_Falling);
    if (bFloor) M->FindFloor(M->UpdatedComponent->GetComponentLocation(), M->CurrentFloor, false);
    SetMeshOffset(Rider->GetActorTransform().InverseTransformPosition(MeshWorld) - SavedMeshLocation);
    T.MeshOffsetStart = T.MeshOffset; T.MeshSettleTime = 0.f;
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
    if (Speed > FastDismount) { Name = FString::Printf(TEXT("BR_DISMOUNT_FAST_%s_INTO_RUN_FWD"), Height); EndPhase = .75f; }
    else if (Speed > RunDismount || bStick) { Name = FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_RUN_FWD"), Height); EndPhase = .5f; }
    else Name = FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_STAND_0"), Height);
    UAnimSequence* Clip = Ride->GetAnimator().Clip(*Name);
    if (!Clip || Length(Clip) < .1f) return false;
    if (Clip->HasCurveData(CadenceCurve, false))
    {
        float Cadence = Clip->EvaluateCurveData(CadenceCurve, FAnimExtractContext(double(Length(Clip))));
        if (Cadence > 1.f) Cadence /= 100.f;
        EndPhase = Cadence;
    }
    T.Clip = Clip; T.ClipTime = 0.f; T.ClipLength = Length(Clip); T.ClipRate = 1.f; T.bClipStarted = false;
    T.bMirror = bGoofy == bBackward;
    // The carry plays in the rider's own stance: a fakie step-off ends half a stride on.
    T.EndPhase = FMath::Frac(EndPhase + (T.bMirror != !bGoofy ? .5f : 0.f));
    T.TrajYaw = (bBackward ? -DeckForward : DeckForward).Rotation().Yaw;
    T.ScaleStart = FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, 0.f, .1f)), .2f, 3.f);
    T.ScaleEnd = 1.f;
    T.BoardContact = BoardCrossing(Clip, true, .3f);
    T.Lift = 1.f;
    T.Foot = ERideFoot::Dismount; T.bCarryShown = false; T.bDrive = true; T.bEndsStanding = Speed <= RunDismount && !bStick;
    // The riding pose and the clip's are in different root spaces (the deck's pivot, the ground): the pose mesh cuts
    // and the character's blend hides the switch.
    T.ClipBlendIn = 0.f;
    SuspendRetailRuntime();
    RequestPoseBlend(Tune.ClipBlend);
    LeaveBoard();
    // The deck it leaves, before the capsule changes.
    const FVector DeckNow = Pos + Up() * DeckPivot;
    const bool bFloor = StandUpOffBoard(T.TrajYaw);
    // The clip starts with its board exactly on that deck; the offset from the capsule's floor eases away.
    const FVector ClipDeck = ClipToWorld(FRideAnimator::Track(Clip, DeckBone, 0.f).GetLocation(), T.bMirror, T.TrajYaw);
    T.TrajOffset = DeckNow - ClipDeck - OffBoardGround();
    T.OffsetTime = FMath::Max(.1f, Tune.MeshSettle * 1.4f);
    T.Board = ERideBoard::Hand;
    UseWorldBoard();
    bRideClip = true;
    M->Velocity = FVector(Flat.X, Flat.Y, bFloor ? 0.f : Vel.Z);
    T.AirStartZ = OffBoardGround().Z; T.AirTime = 0.f; T.FallSpeed = 0.f; T.LandPhase = 0; T.AirNext = nullptr;
    SetDrive(Flat);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride dismount: %s at %.0f cm/s%s, travel x%.2f, offset %.1f cm, %s"),
        *Name, Speed, bBackward ? TEXT(" fakie") : TEXT(""), T.ScaleStart, T.TrajOffset.Size(), bFloor ? TEXT("walking") : TEXT("falling"));
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
    // Until the on-foot recovery clips play off the board, the session's get-up stands the rider up where the body
    // lies (the pose rising out of the fallen body's snapshot, TickTransition) and the rider steps off once up.
    if (Ride && Ride->IsBailing()) Ride->GetUp(Ground, Yaw);
}

// ---------------------------------------------------------------------------------------------------------------
// The mount and dismount clips.

void USkateComponent::StepRideClip(float Dt)
{
    FRideTransition& T = *Transition;
    UCharacterMovementComponent* M = Movement();
    if (!Ride || !T.Clip || !M) { EndRideClip(); return; }
    const bool bGround = M->IsMovingOnGround();
    // In the air: CharacterMovement keeps the fall. The landing ends a jump (a landing clip, the board in hand) and
    // a board thrown under the feet (on it once it is there, else on foot holding it).
    if (T.Foot == ERideFoot::Air || T.Foot == ERideFoot::AirMount)
    {
        if (!bGround) { T.AirTime += Dt; T.FallSpeed = M->Velocity.Z; }
        else if (T.Foot == ERideFoot::AirMount && T.ClipTime >= T.BoardContact) { FinishRideClip(); return; }
        else if (!BeginLandClip()) { FinishRideClip(); return; }
    }
    if (T.bClipStarted) T.ClipTime = FMath::Min(T.ClipLength, T.ClipTime + Dt * T.ClipRate);
    T.bClipStarted = true;
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
    auto Show = [&](float StepDt)
    {
        T.AppliedOffset = T.TrajOffset * (1.f - FMath::SmoothStep(0.f, T.OffsetTime, T.ClipTime));
        Ride->StepOffBoard(StepDt, FTransform(FRotator(0, T.TrajYaw, 0), OffBoardGround() + T.AppliedOffset));
        PublishOffBoardPose(T.Lift);
    };
    Show(Dt);
    // From the character's own pose: the clip's pelvis starts where the character's is.
    if (T.bMatchPelvis) { T.bMatchPelvis = false; if (MatchPelvis()) Show(0.f); }
    if (T.ClipTime >= T.ClipLength)
    {
        if (T.Foot == ERideFoot::Air)
        {
            // Still in the air: the next clip of the fall when there is time for it, else this one's last frame.
            const float Left = AirTimeLeft();
            if (T.AirNext && Left > AirChain)
            {
                UAnimSequence* Next = T.AirNext;
                const FVector Applied = T.AppliedOffset;
                StartClip(Next, ERideFoot::Air, T.bMirror, T.TrajYaw, FRideTuning::Get().ClipBlend * .5f);
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
    // A clip that ends standing gives way to the stick after 40%, and any landing or step-off to a turn away from it.
    if ((T.Foot == ERideFoot::Land || T.Foot == ERideFoot::Dismount) && T.ClipTime > .4f * T.ClipLength)
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
    // The capsule follows the clip's travel to the next frame, scaled so the speed carries on.
    const float Next = FMath::Min(T.ClipLength, T.ClipTime + Dt * T.ClipRate);
    const float Scale = FMath::Lerp(T.ScaleStart, T.ScaleEnd, FMath::SmoothStep(0.f, 1.f, T.ClipTime / T.ClipLength));
    if (Next > T.ClipTime && Dt > 0.f)
    {
        FVector Move = FRideAnimator::RootMotion(T.Clip, T.ClipTime, Next).GetTranslation(); Move.Z = 0.;
        SetDrive(ClipToWorld(Move, T.bMirror, T.TrajYaw) / (Dt * T.ClipRate) * Scale);
    }
}

void USkateComponent::FinishRideClip()
{
    FRideTransition& T = *Transition;
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    // A driven clip leaves at its drive's speed; in the air at the fall's.
    const FVector Velocity = T.bDrive ? T.DriveVelocity : M->Velocity;
    const ERideFoot Was = T.Foot;
    EndRideClip();
    if (Was == ERideFoot::Mount || Was == ERideFoot::AirMount)
    {
        // On the board where the clip put it down, moving as the rider was.
        const int32 D = Ride->Names.IndexOfByKey(DeckBone);
        const FTransform DeckWorld = Ride->Bones.IsValidIndex(D) ? Ride->Bones[D] * Ride->Root : Ride->Root;
        const FQuat Q = DeckWorld.GetRotation();
        UE_LOG(LogTemp, Display, TEXT("SKATE ride mount: onto the board at %.0f cm/s%s, nose %.0f deg from the travel"), Velocity.Size(),
            M->IsMovingOnGround() ? TEXT("") : TEXT(" in the air"),
            FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Q.GetForwardVector().GetSafeNormal2D(), Velocity.GetSafeNormal2D())), -1.f, 1.f))));
        if (!GetOnBoard(DeckWorld.GetLocation() - Q.GetUpVector() * DeckPivot, Q, Velocity, Tune.ClipBlend))
            UE_LOG(LogTemp, Warning, TEXT("SKATE ride mount: the ride did not start"));
        return;
    }
    // Off: running on (or standing) with the board in hand; the speed above the character's own fades as momentum.
    const FVector Flat(Velocity.X, Velocity.Y, 0.f);
    const FVector Own = Flat.GetClampedToMaxSize(M->GetMaxSpeed());
    M->Velocity = FVector(Own.X, Own.Y, M->Velocity.Z);
    StartMomentum(Flat - Own);
    BeginCarry(Was == ERideFoot::Air ? T.Phase : T.EndPhase);
}

void USkateComponent::EndRideClip()
{
    StopDrive();
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
    T.DriveId = 0;
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
    // In the air CharacterMovement keeps the fall; on the ground the clip's travel moves the capsule.
    T.bDrive = Foot != ERideFoot::Air && Foot != ERideFoot::AirMount;
    if (!T.bDrive) StopDrive();
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
    T.TrajOffset += Mesh->GetBoneLocation(Pelvis) - Shown;
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
    if (!Ride || !M) return false;
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
    T.ScaleStart = FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, 0.f, .1f)), .3f, 3.f);
    T.ScaleEnd = bRun ? FMath::Clamp(Speed / FMath::Max(50.f, ClipSpeed(Clip, T.ClipLength - .1f, T.ClipLength)), .3f, 3.f) : 1.f;
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
    T.TrajOffset = Applied; T.bMatchPelvis = !bFromClip; T.OffsetTime = T.ClipLength;
    Rider->SetActorRotation(FRotator(0, Yaw, 0));
    UE_LOG(LogTemp, Display, TEXT("SKATE ride caveman: %s at %.0f cm/s, %.0f cm up, %.2f s in the air ahead, rate %.2f, %s"),
        *Clip->GetName(), Flat.Size(), Height, Left, T.ClipRate, bFromClip ? TEXT("from the jump") : TEXT("from the character's own pose"));
    return true;
}

bool USkateComponent::BeginAirDismountClip()
{
    // In the air the rider lets go with the feet: the step off the board from the grab held (or a mute), the board
    // into the hand, then the fall on foot (JBR_AIRDISMOUNT_TO_BIG_DN_0) and a landing.
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    UCharacterMovementComponent* M = Movement();
    if (!Ride || !M) return false;
    const TCHAR* Grab = TEXT("MUTE");
    switch (Ride->GetBody().Grab)
    {
    case ERideGrab::Indy: Grab = TEXT("FS"); break;
    case ERideGrab::Melon: Grab = TEXT("BS"); break;
    case ERideGrab::ChristAir: Grab = TEXT("STALE"); break;
    case ERideGrab::TuckKnee: Grab = TEXT("DBL"); break;
    default: break;
    }
    UAnimSequence* Clip = Ride->GetAnimator().Clip(*FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_BR_AIR"), Grab));
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
    const bool bFloor = StandUpOffBoard(Yaw);
    M->Velocity = bFloor ? Flat : Carried;
    StartClip(Clip, ERideFoot::Air, bGoofy == bBackward, Yaw, 0.f);
    T.BoardContact = BoardCrossing(Clip, true, .2f);
    T.Lift = 1.f;
    // The clip starts with its board on that deck; the offset from the capsule's floor eases away before the landing.
    AnchorClipAt(DeckBone, DeckNow);
    const float Left = AirTimeLeft();
    T.OffsetTime = FMath::Clamp(Left * .8f, .15f, T.ClipLength);
    T.AirNext = Ride->GetAnimator().Clip(TEXT("JBR_AIRDISMOUNT_TO_BIG_DN_0"));
    T.AirStartZ = OffBoardGround().Z; T.AirTime = 0.f; T.FallSpeed = Carried.Z; T.LandPhase = 0;
    T.Board = ERideBoard::Hand; T.bGetUpOnFoot = false;
    UseWorldBoard();
    UE_LOG(LogTemp, Display, TEXT("SKATE ride air dismount: %s at %.0f cm/s%s, %.2f s in the air ahead, offset %.1f cm, %s"),
        *Clip->GetName(), Carried.Size(), bBackward ? TEXT(" fakie") : TEXT(""), Left, T.TrajOffset.Size(), bFloor ? TEXT("walking") : TEXT("falling"));
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
    // The transition clips load once the ride's rig has (PreloadRetailRuntime, 2 s after play).
    if (bRetailPreloaded && Ride && Ride->GetAnimator().HasClips() && !Transit().bClipsTried) PrepareRideClips();
    if (!Transition) return;
    FRideTransition& T = *Transition;
    const FRideTuning& Tune = FRideTuning::Get();
    OffBoardDeckBlend = FMath::Min(1.f, OffBoardDeckBlend + Dt / FMath::Max(.01f, Tune.ClipBlend));

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
        SetMeshOffset(T.MeshOffsetStart * (1.f - A));
        if (A >= 1.f) T.MeshSettleTime = -1.f;
    }

    // Off the board: the clips, the carry, the character's own stride (for the next mount).
    if (Mode == ESkateMode::Off)
    {
        if (USkeletalMeshComponent* Mesh = Rider->GetMesh(); Mesh && !bRideClip && T.Foot == ERideFoot::Off)
            SavedMeshRotation = Mesh->GetRelativeRotation().Quaternion();
        TrackFeet(Dt);
        if (T.Foot == ERideFoot::Carry) StepCarry(Dt);
        else if (T.Foot != ERideFoot::Off) StepRideClip(Dt);
    }

    // A board lying in the world follows its own body, and dissolves once the rider has been out of reach for a while.
    if (T.Board == ERideBoard::World)
    {
        if (const UPrimitiveComponent* Loose = T.LooseBoard.Get())
        {
            const FTransform Body = Loose->GetComponentTransform();
            const float Scale = BoardScale();
            BoardRoot->SetWorldTransform(FTransform(Body.GetRotation(), Body.GetLocation() + Body.GetRotation().GetUpVector() * LooseBoardDrop * Scale, FVector(Scale)));
        }
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
}

void USkateComponent::ResetTransition()
{
    bRideClip = false;
    if (!Transition) return;
    FRideTransition& T = *Transition;
    StopMomentum(); StopDrive();
    DropLyingBoard();
    if (Ride && T.Foot != ERideFoot::Off) Ride->GetAnimator().ClearOverride(0.f);
    T.Foot = ERideFoot::Off; T.Clip = nullptr; T.bCarryShown = false; T.bRecall = false;
    if (Mode == ESkateMode::Off && !RetailPose.IsEmpty()) RetailPose.Reset();
    ReleaseBoardFromHand();
    T.Board = ERideBoard::Away; T.bGetUpOnFoot = false;
    T.Shown = T.ShownTarget = 0.f; ApplyBoardShown();
    T.MeshSettleTime = -1.f; SetMeshOffset(FVector::ZeroVector);
}

// ---------------------------------------------------------------------------------------------------------------
// The body and the speed.

void USkateComponent::SetMeshOffset(const FVector& Offset)
{
    FRideTransition& T = Transit();
    // Applied as a change, so whatever else places the mesh (a crouch) keeps its part.
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (Mesh && Mesh->GetAttachParent() == Rider->GetRootComponent() && !Offset.Equals(T.MeshOffset))
        Mesh->SetRelativeLocation(Mesh->GetRelativeLocation() + Offset - T.MeshOffset);
    T.MeshOffset = Offset;
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

void USkateComponent::ApplyBoardShown()
{
    FRideTransition& T = Transit();
    const bool bPartial = T.Shown > 0.f && T.Shown < 1.f;
    if (bPartial && !BoardFade)
    {
        const FSoftObjectPath& Path = GetDefault<USkateSettings>()->BoardDissolveMaterial;
        if (UMaterialInterface* Base = Path.IsNull() ? nullptr : Cast<UMaterialInterface>(Path.TryLoad()))
            BoardFade = UMaterialInstanceDynamic::Create(Base, this);
    }
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
    if (UPrimitiveComponent* Loose = T.LooseBoard.Get()) Loose->DestroyComponent();
    T.LooseBoard.Reset();
    if (T.Board == ERideBoard::World) T.Board = ERideBoard::Away;
}

FString USkateComponent::DescribeTransition() const
{
    if (!Transition || !Rider) return FString();
    const FRideTransition& T = *Transition;
    static const TCHAR* Places[] = {TEXT("away"), TEXT("ride"), TEXT("hand"), TEXT("world")};
    static const TCHAR* Feet[] = {TEXT("off"), TEXT("carry"), TEXT("mount"), TEXT("dismount"), TEXT("air"), TEXT("land"), TEXT("airmount")};
    FVector Hip = FVector::ZeroVector;
    const USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FName Pelvis = RiderApi ? RiderApi->GetSkateBone(TEXT("pelvis")) : NAME_None;
    if (Mesh && !Pelvis.IsNone() && Mesh->GetBoneIndex(Pelvis) != INDEX_NONE) Hip = Mesh->GetBoneLocation(Pelvis);
    const FVector Board = BoardRoot ? BoardRoot->GetComponentLocation() : FVector::ZeroVector;
    const UCharacterMovementComponent* M = Movement();
    const FVector V = M ? M->Velocity : FVector::ZeroVector;
    return FString::Printf(TEXT(" board=%s shown=%.2f vis=%d hip=%.1f,%.1f,%.1f deck=%.1f,%.1f,%.1f vel=%.0f,%.0f,%.0f offset=%.1f,%.1f,%.1f momentum=%.0f getup_on_foot=%d foot=%s clip=%s t=%.2f lift=%.2f phase=%.2f hold=%.1f hand=%s air=%.2f moves=mount,dismount,carry,jump,caveman,airdismount"),
        Places[uint8(T.Board)], T.Shown, BoardRoot && BoardRoot->IsVisible() ? 1 : 0, Hip.X, Hip.Y, Hip.Z, Board.X, Board.Y, Board.Z, V.X, V.Y, V.Z,
        T.MeshOffset.X, T.MeshOffset.Y, T.MeshOffset.Z, T.Momentum, T.bGetUpOnFoot ? 1 : 0, Feet[uint8(T.Foot)],
        T.Clip ? *T.Clip->GetName() : TEXT("-"), T.ClipTime, T.Lift, T.Phase, T.HoldTime, *T.HandBone.ToString(), T.AirTime);
}
