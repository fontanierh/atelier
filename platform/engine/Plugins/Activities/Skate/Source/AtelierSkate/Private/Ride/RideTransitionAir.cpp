// USkateComponent off the board in the air and carrying it (RideTransition.cpp).
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
// In the air: a jump with the board in hand, the board thrown under the feet, a step off it from a grab, the landings.

bool USkateComponent::StartClip(UAnimSequence* Clip, ERideFoot Foot, bool bMirror, float Yaw, float BlendIn)
{
    if (!Clip || Length(Clip) < .05f) return false;
    FRideTransition& T = Transit();
    T.Clip = Clip; T.ClipTime = 0.f; T.ClipLength = Length(Clip); T.ClipRate = 1.f; T.bClipStarted = false; T.ClipDeckClip = nullptr;
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
    if (!StartClip(Clips->GetAnimator().Clip(*Name), ERideFoot::Air, !bGoofy, Rider->GetActorRotation().Yaw, FRideTuning::Get().ClipBlend * .5f)) return false;
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
    if (!Clips || !M || T.Board != ERideBoard::Hand) return false;
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
    UAnimSequence* Clip = Clips->GetAnimator().Clip(*Name);
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
    UAnimSequence* Clip = Clips->GetAnimator().Clip(bLeft ? TEXT("BR_LF_AIR_INTO_MOUNT_BSGRAB") : TEXT("BR_RF_AIR_INTO_MOUNT_BSGRAB"));
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
    if (!Clips || !M) return false;
    const ERideGrab Held = RideGrab();
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
    const FString Name = bKick ? FString::Printf(TEXT("BR_KICKOUT_%s_INTO_NB_AIR"), ShownCrouch() ? TEXT("LO") : TEXT("HI"))
        : FString::Printf(TEXT("BR_DISMOUNT_%s_INTO_BR_AIR"), Grab);
    UAnimSequence* Clip = Clips->GetAnimator().Clip(*Name);
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
    T.AirNext = Clips->GetAnimator().Clip(bKick ? TEXT("JNB_KICKOUT_TO_SML_FWD_75") : TEXT("JBR_AIRDISMOUNT_TO_BIG_DN_0"));
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
    if (!M || !Clips || T.HoldTime > Tune.BoardHoldTime || !RiderApi->CanCarrySkateBoard()) { PutBoardAway(); return; }
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
    Layers.bMirror = !bGoofy;
    Layers.Add(T.Cycle[0], FMath::Fmod(T.StandTime, T.CycleLength[0]), Weight[0]);
    for (int32 I = 1; I < 4; ++I) Layers.Add(T.Cycle[I], T.Phase * T.CycleLength[I], Weight[I]);
    // Into the carry from another clip the pose mesh cross-fades; from the character's own pose the character blends.
    Clips->GetAnimator().SetOverride(Layers, bOwnPose || T.bCarryShown ? 0.f : Tune.CarryBlend);
    if (bOwnPose) RequestPoseBlend(Tune.CarryBlend);
    const FTransform Actor = Rider->GetActorTransform();
    T.AppliedOffset = Actor.GetRotation().RotateVector(T.MeshOffset);
    Clips->Step(Dt, FTransform(FRotator(0, Actor.Rotator().Yaw, 0), OffBoardGround() + T.AppliedOffset));
    T.bCarryShown = PublishOffBoardPose(0.f);
    if (!T.bCarryShown) PutBoardAway();
}

void USkateComponent::PutBoardAway()
{
    // The character's own pose blends back in, the board dissolving in the hand that held it.
    FRideTransition& T = Transit();
    if (T.Foot == ERideFoot::Carry) T.Foot = ERideFoot::Off;
    if (Clips) Clips->GetAnimator().ClearOverride();
    if (!RetailPose.IsEmpty()) { HoldBoardAtHand(); RetailPose.Reset(); RequestPoseBlend(FRideTuning::Get().CarryBlend); }
    T.bCarryShown = false;
    if (T.Board == ERideBoard::Hand) ShowBoard(0.f, false);
}

bool USkateComponent::CanYieldToCharacter() const
{
    // Riding, or on the way onto the board, the board keeps the character. A jump with the board in hand gives way at
    // once; any other clip where the stick may end it (a get-up once the body is up).
    if (Mode != ESkateMode::Off) return false;
    if (!bRideClip) return true;
    if (!Transition || !Transition->Clip) return false;
    const FRideTransition& T = *Transition;
    if (T.Foot == ERideFoot::Mount || T.Foot == ERideFoot::AirMount) return false;
    return T.Foot == ERideFoot::Air || T.ClipTime > ClipFreeFrom() * T.ClipLength;
}

bool USkateComponent::YieldToCharacter(bool bOwnVelocity)
{
    // The character's own move takes over from the board on foot (RIDE.md, "Transitions").
    if (!CanYieldToCharacter()) return false;
    if (!Transition) return true;
    FRideTransition& T = *Transition;
    if (bRideClip)
    {
        const ERideFoot Was = T.Foot;
        UCharacterMovementComponent* M = Movement();
        if (bOwnVelocity || !M) EndRideClip();
        else
        {
            // At the clip's speed (in the air the fall's), which the stick then shares out as at the clip's end.
            const FVector Velocity = T.bDrive ? T.DriveVelocity : M->Velocity;
            EndRideClip(true);
            const FVector Flat(Velocity.X, Velocity.Y, 0.f);
            M->Velocity = FVector(Flat.X, Flat.Y, M->Velocity.Z);
            HoldDriveForInput(Flat);
        }
        // A board the clip had goes on by itself (rolling on from a run-out, kicked away); a lying one stays.
        if (Was == ERideFoot::RunOut || T.bKickOut) LaunchBoard();
        if (T.Board != ERideBoard::Hand) { EndOnFoot(FRideTuning::Get().CarryBlend); return true; }
    }
    if (T.Foot == ERideFoot::Carry || (T.Board == ERideBoard::Hand && T.ShownTarget > 0.f))
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride on foot: the character's own move puts the board away"));
        PutBoardAway();
    }
    return true;
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
