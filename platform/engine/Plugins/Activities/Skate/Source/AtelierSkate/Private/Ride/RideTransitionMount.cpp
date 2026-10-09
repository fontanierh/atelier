// USkateComponent getting on and off the board (RideTransition.cpp): stepping on, stepping off and the mount and dismount clips.
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
    UAnimSequence* Clip = Clips->GetAnimator().Clip(*Name);
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
    UAnimSequence* Clip = Clips->GetAnimator().Clip(TEXT("BR_STAND_0_INTO_MOUNT"));
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
    if (Clips) Clips->GetAnimator().ClearOverride();
    Capsule->SetCapsuleSize(RidingRadius, RidingHalf);      // about its centre: nothing moves
    M->SetMovementMode(MOVE_Custom, MovementMode);
    // The actor stays where it is: the body's height above the session's root is measured rather than assumed. It
    // turns to the board as the first ride frame would; the mesh keeps its world place and rotation over that turn
    // (riding, the pose is anchored on the board, so they only matter to the blend into it, which works in the mesh's
    // frame).
    const FTransform Root = RideRoot();
    BodyLift = Rider->GetActorLocation().Z - Root.GetLocation().Z;
    Rider->SetActorLocationAndRotation(Root.GetLocation() + FVector(0, 0, BodyLift), Root.GetRotation(), false, nullptr, ETeleportType::None);
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
    const bool bDown = Mode == ESkateMode::Bail || (PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
    if (bDown) { T.bGetUpOnFoot = true; return true; }
    // Native's rider already off the board on foot becomes the character in a moment (TakeNativeOnFoot): no dismount
    // starts on the board it left.
    if (IsNativeOnFoot()) return true;
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
    const bool bLow = ShownCrouch();
    const bool bStick = In.Left.Size() > .3f;
    const TCHAR* Height = bLow ? TEXT("LO") : TEXT("HI");
    FString Name; float EndPhase = 0.f;
    const bool bEndsRunning = Speed > RunDismount || bStick;
    if (Speed > FastDismount) { Name = FString::Printf(TEXT("BR_DISMOUNT_FAST_%s_INTO_RUN_FWD"), Height); EndPhase = .75f; }
    else if (bEndsRunning) { Name = FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_RUN_FWD"), Height); EndPhase = .5f; }
    else Name = FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_STAND_0"), Height);
    UAnimSequence* Clip = Clips->GetAnimator().Clip(*Name);
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

void USkateComponent::BeginGetUpOnFoot(bool bFaceUp)
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
    // blended out of the fallen pose's snapshot).
    if (PrepareRideClips()) { T.bRecoverPending = true; T.bRecoverFaceUp = bFaceUp; }
}

bool USkateComponent::BeginRecover()
{
    // The recovery whose first frame lies most like the fallen body: its head-from-hips way turned onto the body's,
    // then the hands, feet and the way the front faces compared about the hips (scaled to the character).
    FRideTransition& T = Transit();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (!Clips || !Mesh) return false;
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
        UAnimSequence* Clip = Clips->GetAnimator().Clip(Name);
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
    if (Kind != ERideBailKind::RunOut || !Clips || !BoardRoot || T.Board != ERideBoard::Ride || !PrepareRideClips()) return false;
    const FVector Bail = BailVelocity();
    // The way is the shown deck's: Native's pose carries its stance, so the rider never counts as switch.
    const FQuat DeckRotation = BoardRoot->GetComponentQuat();
    float Along = FVector::DotProduct(Bail, DeckRotation.GetForwardVector());
    float Across = FVector::DotProduct(Bail, DeckRotation.GetRightVector());
    if (!bGoofy) Across = -Across;                          // the clips are authored goofy
    if (FMath::Abs(Along) + FMath::Abs(Across) < 20.f) { Along = bFakie ? -1.f : 1.f; Across = 0.f; }
    const float Angle = FMath::RadiansToDegrees(FMath::Atan2(Across, Along));
    const int32 Way = FMath::Abs(Angle) < 45.f ? 0 : FMath::Abs(Angle) > 135.f ? 1 : Across < 0.f ? 2 : 3;
    const URidePhysicalSettings* Settings = GetDefault<URidePhysicalSettings>();
    const float Energy = FMath::Max3(float(Bail.Size2D()) / FMath::Max(1.f, Settings->RunOutSpeed), FMath::Abs(float(Bail.Z)) / FMath::Max(1.f, Settings->RunOutImpact),
        FMath::RadiansToDegrees(float(BailSpin().Size())) / FMath::Max(1.f, Settings->RunOutSpin));
    const TCHAR* Height = ShownCrouch() ? TEXT("LO") : TEXT("HI");
    // The size the energy asks for, or the nearest one this way has.
    const int32 Wanted = Energy < .4f ? 0 : Energy < .75f ? 1 : 2;
    for (const int32 Size : {Wanted, Wanted - 1, Wanted + 1, Wanted - 2, Wanted + 2})
    {
        if (Size < 0 || Size > 2) continue;
        TArray<UAnimSequence*> Options;
        for (const TCHAR* Variant : RunOutWays[Way].Sizes[Size])
            if (Variant)
                if (UAnimSequence* Clip = Clips->GetAnimator().Clip(*FString::Printf(TEXT("RUNOUT_%s_%s_%s_TO_RUN_FWD"), RunOutWays[Way].Way, Height, Variant)); Clip && Length(Clip) > .2f)
                    Options.Add(Clip);
        if (Options.IsEmpty()) continue;
        // Picked from the bail itself rather than at random, so a replay picks the same one.
        T.PendingClip = Options[GetTypeHash(FIntVector(FMath::RoundToInt(Angle), FMath::RoundToInt(float(Bail.Size())), FMath::RoundToInt(Energy * 100.f))) % uint32(Options.Num())];
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
    if (!Clips || !M || !Clip || !BoardRoot) return false;
    // In the stance in effect, on the board the way the shown deck has the rider stand on it.
    const bool bMirror = !bGoofy;
    const FTransform Bailed = BoardRoot->GetComponentTransform();
    const float DeckYaw = float(Bailed.GetRotation().GetForwardVector().Rotation().Yaw);
    const float Yaw = DeckYaw - ClipYawToWorld(ClipDeckYaw(Clip, 0.f), bMirror, 0.f);
    const FVector Carried = BailVelocity();
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
    // A sphere starting inside something would be pushed out to whichever side is nearer (through a thin wall), and one
    // behind a face from the deck over it flies on beyond it: the board settles where it is instead.
    const FVector Start = Leaving.GetLocation() - Leaving.GetRotation().GetUpVector() * (DeckPivot - FlightRadius) * Scale + FVector(0, 0, 1.f);
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardLaunch), false, Rider);
        FVector Extent;
        FHitResult Between;
        const FVector Middle = DeckFitBox(Leaving, Extent).GetLocation();
        if (GetWorld()->OverlapBlockingTestByChannel(Start, FQuat::Identity, ECC_WorldDynamic, FCollisionShape::MakeSphere(FMath::Max(.5f, (FlightRadius - 1.f) * Scale)),
                Params, FlightResponses()) ||
            GetWorld()->LineTraceSingleByChannel(Between, Middle, Start, ECC_WorldDynamic, Params, FlightResponses()))
        {
            UE_LOG(LogTemp, Display, TEXT("SKATE ride board %s at %.0f cm/s: its flight would start inside something, it settles"),
                bKick ? TEXT("kicked away") : TEXT("rolls on"), Velocity.Size());
            SettleBoard();
            return;
        }
    }
    USphereComponent* Body = NewObject<USphereComponent>(Rider, NAME_None, RF_Transient);
    Body->InitSphereRadius(FlightRadius * Scale);
    Body->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Body->SetCollisionObjectType(ECC_WorldDynamic);
    Body->SetCollisionResponseToChannels(FlightResponses().CollisionResponse);
    Body->SetGenerateOverlapEvents(false);
    Body->SetCanEverAffectNavigation(false);
    Body->SetHiddenInGame(true);
    // The sphere's bottom where the wheels touch (a little above, so it starts clear of the ground).
    Body->SetWorldLocation(Start);
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
        FTransform Shown(T.FlightRotation, At + T.FlightRotation.GetUpVector() * (DeckPivot - FlightRadius) * Scale, FVector(Scale));
        // The deck reaches far past the sphere that flies it: its whole box goes from where it was shown to where the
        // sphere takes it, turned in steps, and stops at what it meets (FitDeck). Stopped, the sphere comes back under
        // it (swept), the motion into the face turns back as a bounce off a wall and ends on the floor, where the deck
        // lies down along it (its tilt is what met it; the next frame's sweep checks the turn), and the spin dies down.
        FVector Normal;
        if (FitDeck(*GetWorld(), BoardRoot->GetComponentTransform(), Shown, Params, Normal) != EDeckFit::Clear)
        {
            T.FlightRotation = Shown.GetRotation();
            const FVector Under = Shown.GetLocation() - Shown.GetRotation().GetUpVector() * (DeckPivot - FlightRadius) * Scale;
            Flight->MoveUpdatedComponent(Under - Body->GetComponentLocation(), Body->GetComponentQuat(), true);
            T.FlightSpin *= FMath::Exp(-ContactSpinDamp * Dt);
            if (Normal.IsNearlyZero()) Flight->Velocity = FVector::ZeroVector;
            else
            {
                const bool bFloor = Normal.Z >= .7f;
                const float Into = float(FVector::DotProduct(Flight->Velocity, Normal));
                if (Into < 0.f) Flight->Velocity -= Normal * Into * (bFloor ? 1.f : 1.f + FlightBounce);
                if (bFloor)
                {
                    const FVector DeckUp = T.FlightRotation.GetUpVector();
                    const FQuat Lie = FQuat::FindBetweenNormals(DeckUp, DeckUp.Z >= 0. ? Normal : -Normal);
                    T.FlightRotation = (FQuat::Slerp(FQuat::Identity, Lie, 1.f - FMath::Exp(-DeckLieRate * Dt)) * T.FlightRotation).GetNormalized();
                }
            }
        }
        BoardRoot->SetWorldTransform(Shown);
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
        // The board the physical rider handed over is physics' own, kept out of what physics does not see.
        if (PhysicalRider) PhysicalRider->GuardBoards();
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
    // From no higher than the room over the board: one under a ledge or a bench settles under it, not on top.
    FVector Start = From.GetLocation() + FVector(0, 0, 30.f * Scale);
    if (GetWorld()->LineTraceSingleByChannel(Hit, From.GetLocation(), Start, ECC_WorldStatic, Params)) Start = Hit.Location - FVector(0, 0, 1.f);
    if (!GetWorld()->LineTraceSingleByChannel(Hit, Start, Start - FVector(0, 0, 300.f), ECC_WorldStatic, Params))
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride board settles nowhere: no ground within 3 m under (%.0f, %.0f, %.0f)"), Start.X, Start.Y, Start.Z);
        return;
    }
    UE_LOG(LogTemp, Display, TEXT("SKATE ride board settles at (%.0f, %.0f, %.0f) on %s"), Hit.ImpactPoint.X, Hit.ImpactPoint.Y, Hit.ImpactPoint.Z,
        Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("?"));
    const FVector Normal = Hit.ImpactNormal;
    const bool bUpsideDown = From.GetRotation().GetUpVector().Z < 0.f;
    FVector Nose = FVector::VectorPlaneProject(From.GetRotation().GetForwardVector(), Normal);
    if (Nose.SizeSquared() < .01) Nose = FVector::CrossProduct(From.GetRotation().GetRightVector(), Normal);
    const FQuat Rotation = FRotationMatrix::MakeFromXZ(Nose.GetSafeNormal(), bUpsideDown ? -Normal : Normal).ToQuat();
    T.SettleFrom = From;
    T.SettleTo = FTransform(Rotation, FVector(Hit.ImpactPoint) + Normal * (bUpsideDown ? UpsideDownDeck : DeckPivot) * Scale, FVector(Scale));
    // Lying flat it may reach into a wall it flew clear of: slid out along the ground when it comes free near. The way
    // there is swept like the flight (FitDeck): the board settles as far as it is free to, or stays as it is.
    FVector Extent, Push;
    if (LeaveInside(*GetWorld(), DeckFitBox(T.SettleTo, Extent), Extent, Scale, Params, Normal, Push)) T.SettleTo.AddToTranslation(Push);
    FVector Met;
    FitDeck(*GetWorld(), From, T.SettleTo, Params, Met, Normal);
    T.SettleTime = 0.f;
}

void USkateComponent::EndOnFoot(float Blend)
{
    // The character's own pose blends in from where the clip left the body; the board stays where it is.
    FRideTransition& T = Transit();
    T.Foot = ERideFoot::Off; T.bCarryShown = false;
    if (Clips) Clips->GetAnimator().ClearOverride();
    if (!RetailPose.IsEmpty()) { RetailPose.Reset(); RequestPoseBlend(Blend); }
}

// ---------------------------------------------------------------------------------------------------------------
// The mount and dismount clips.

void USkateComponent::StepRideClip(float Dt)
{
    FRideTransition& T = *Transition;
    UCharacterMovementComponent* M = Movement();
    const FRideTuning& Tune = FRideTuning::Get();
    if (!Clips || !T.Clip || !M) { EndRideClip(); return; }
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
    Layers.bMirror = T.bMirror;
    Layers.Add(T.Clip, T.ClipTime, 1.f);
    Clips->GetAnimator().SetOverride(Layers, T.ClipBlendIn);
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
        Clips->Step(StepDt, FTransform(FRotator(0, T.TrajYaw, 0), Floor + Offset));
        // Where the pose put the board against where the clip's tracks have it, for the frames to come.
        const int32 DeckIndex = Clips->Names.IndexOfByKey(DeckBone);
        if (T.TrajEndTime > 0.f && (T.ClipTime < T.TrajEndTime || T.Foot == ERideFoot::AirMount) && Clips->Bones.IsValidIndex(DeckIndex))
        {
            const FVector Posed = (Clips->Bones[DeckIndex] * Clips->Root).GetLocation();
            const FVector Tracked = Clips->Root.GetLocation() + ClipToWorld(ClipBone(T.Clip, DeckBone, T.ClipTime), T.bMirror, T.TrajYaw);
            T.DeckDrift = FVector(Posed.X - Tracked.X, Posed.Y - Tracked.Y, 0.);
        }
        // A board the clip rolls away (a run-out) or kicks off goes only where it is free to: its box, swept from where
        // it was shown to where the clip has it, stops at what it meets (FitDeck), so a run-out by a wall never carries
        // it through and its flight starts on this side. From inside something it takes the clip's pose once that is
        // free and reached from the capsule. A clip board that jumps from its own last frame (or from the shown one, on
        // a clip's first frame) was placed: it stands as the clip has it when it is free there and reached from the
        // capsule, else it is swept as a moved one is (it never lands inside something). One held back by a wall is
        // swept on from where it is held.
        const bool bFitBoard = bClipBoard && BoardRoot && Rider && (T.Foot == ERideFoot::RunOut || T.bKickOut) && T.Shown > 0.f;
        const FTransform Was = bFitBoard ? BoardRoot->GetComponentTransform() : FTransform::Identity;
        const bool bClipLast = bFitBoard && T.ClipDeckClip == T.Clip;
        const FTransform ClipLast = T.ClipDeckLast;
        T.ClipDeckClip = nullptr;
        if (PublishOffBoardPose(T.Lift, bClipBoard) && bFitBoard)
        {
            const FTransform ClipDeck = BoardRoot->GetComponentTransform();
            T.ClipDeckLast = ClipDeck; T.ClipDeckClip = T.Clip;
            const FVector From = (bClipLast ? ClipLast : Was).GetLocation();
            const bool bJump = FVector::DistSquared(From, ClipDeck.GetLocation()) >= FMath::Square(ClipBoardJump * float(ClipDeck.GetScale3D().X));
            const FCollisionQueryParams Params(SCENE_QUERY_STAT(RideClipBoard), false, Rider);
            const FVector Reach = Rider->GetActorLocation();
            if (!bJump || !DeckFreeFrom(*GetWorld(), ClipDeck, Reach, Params))
            {
                FTransform To = ClipDeck;
                FVector Normal;
                const EDeckFit Fit = FitDeck(*GetWorld(), Was, To, Params, Normal);
                if (Fit == EDeckFit::Corrected || (Fit == EDeckFit::Unresolved && (bJump || !DeckFreeFrom(*GetWorld(), ClipDeck, Reach, Params))))
                    PlaceBoardParts(To);
            }
        }
    };
    Show(Dt);
    // From the character's own pose (or a fallen body): the clip's pelvis starts where the character's is.
    if (T.bMatchPelvis) { T.bMatchPelvis = false; if (MatchPelvis()) Show(0.f); }
    // Onto a lying board: the posed board where the lying one is (the clip's tracks only nearly agree with the pose).
    if (T.bMatchDeck)
    {
        T.bMatchDeck = false;
        const int32 DeckIndex = Clips->Names.IndexOfByKey(DeckBone);
        if (Clips->Bones.IsValidIndex(DeckIndex))
        {
            const FVector Delta = OffBoardDeckFrom.GetLocation() - (Clips->Bones[DeckIndex] * Clips->Root).GetLocation();
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
    if (T.ClipTime > ClipFreeFrom() * T.ClipLength)
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
        const int32 D = Clips->Names.IndexOfByKey(DeckBone);
        const FTransform DeckWorld = Clips->Bones.IsValidIndex(D) ? Clips->Bones[D] * Clips->Root : Clips->Root;
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

float USkateComponent::ClipFreeFrom() const
{
    const FRideTransition& T = *Transition;
    if (T.Foot == ERideFoot::Land || T.Foot == ERideFoot::Dismount) return .4f;
    if (T.Foot == ERideFoot::RunOut) return .6f;
    if (T.Foot == ERideFoot::Recover) return FMath::Max(.65f, (FRideTuning::Get().RecoverBlend + .2f) / FMath::Max(.1f, T.ClipLength));
    return 2.f;
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
