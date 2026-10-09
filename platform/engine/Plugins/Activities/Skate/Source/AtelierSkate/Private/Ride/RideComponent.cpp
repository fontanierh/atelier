// USkateComponent's side of the Ride backend (RIDE.md): Native's session rides under Ride's body. Riding, the body (the
// physical rider, RidePhysicalRider.h) follows the retargeted Native pose; a Native wipeout hands the rider to the Chaos
// body, which falls with the momentum it has while the board goes on with the session's wipeout; the settled body gets
// up where it lies and a fresh session takes the ride back from there. Native's rider off the board on foot becomes the
// character.
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "RideClipPlayer.h"
#include "RidePhysicalRider.h"
#include "RideTransition.h"
#include "RideTuning.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "CollisionShape.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"

namespace
{
    // Native's rider is off the board on foot for good once BipedGround lasts this long: a wipeout passes through it for
    // 1-3 frames (every recorded ride), the rider who lands beside the board stays in it.
    constexpr float NativeOnFootHold = .2f;
    // A ride's start looks for the floor this far below the board (cm).
    constexpr float StartBelow = 60.f;
}

void USkateComponent::PreloadRide()
{
    if (!Clips) Clips = MakeShared<FRideClipPlayer>();
    Clips->Preload();
}

bool USkateComponent::StartRide()
{
    if (!Rider) return false;
    if (!Clips) Clips = MakeShared<FRideClipPlayer>();
    // The rider's bodies: kinematic on the animation until the mount blends them in (skate.RidePhysical) or a bail
    // lets them go.
    if (!PhysicalRider) PhysicalRider = NewObject<URidePhysicalRider>(this, NAME_None, RF_Transient);
    // The start's own cost, logged: it lands on one frame (the mount's last).
    const double Started = FPlatformTime::Seconds();
    const bool bBody = PhysicalRider->Begin(Rider, RiderApi);
    PhysicalRider->ClearBailOffer();
    SettleRideStart();
    if (bBody && URidePhysicalRider::IsWanted()) PhysicalRider->BlendIn(GetDefault<URidePhysicalSettings>()->MountBlend);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride started at (%.0f, %.0f, %.0f) speed %.0f, %s, in %.2f ms"), Pos.X, Pos.Y, Pos.Z, Vel.Size(),
        !bBody ? TEXT("no ragdoll") : URidePhysicalRider::IsWanted() ? TEXT("physical rider") : TEXT("ragdoll for bails"),
        (FPlatformTime::Seconds() - Started) * 1000.);
    return true;
}

void USkateComponent::StopRide()
{
    // The body lets go over the dismount and the mesh is pure animation again on foot.
    if (PhysicalRider) PhysicalRider->Release(GetDefault<URidePhysicalSettings>()->DismountBlend);
}

void USkateComponent::SettleRideStart()
{
    // Native's session starts on the floor under the board, or on one the start is a little inside (a hand-off a little
    // low), not inside the floor where its wheels find nothing. With no floor within reach it starts in the air.
    UWorld* World = GetWorld();
    if (!World) return;
    const FRideTuning& Tune = FRideTuning::Get();
    const FVector Up = Rot.GetUpVector();
    const float R = Tune.WheelRadius;
    const FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateRideStart), false, Rider);
    const FCollisionShape Wheel = FCollisionShape::MakeSphere(R);
    auto Floor = [&](const FVector& From, const FVector& To, FVector& Ground)
    {
        FHitResult Hit;
        if (!World->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Pawn, Wheel, Params)) return 0;
        if (Hit.bStartPenetrating || FVector::DotProduct(Hit.Normal, Up) < Tune.WallSlope) return -1;   // inside, or a wall
        Ground = Hit.Location - Up * R;
        return 1;
    };
    FVector Ground;
    int32 Found = Floor(Pos + Up * (Tune.StepUp + R), Pos - Up * (StartBelow - R), Ground);
    if (Found < 0 && Floor(Pos + Up * (Tune.StartRecover + R), Pos + Up * R, Ground) > 0)
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride start inside the floor: %.0f cm up onto it"), float(FVector::DotProduct(Ground - Pos, Up)));
        Found = 1;
    }
    if (Found > 0) Pos = Ground;
}

void USkateComponent::AfterNativeRideFrame(float Dt)
{
    // Without bodies (no physics asset) the session's own wipeout and recovery play.
    if (!PhysicalRider || !PhysicalRider->IsActive()) return;
    URidePhysicalRider& Body = *PhysicalRider;
    const URidePhysicalSettings* Settings = GetDefault<URidePhysicalSettings>();

    // A wipeout is offered to the transition first, as Ride's are (a slow, upright one runs out on foot: BeginRunOut
    // suspends the session); otherwise the body goes limp with its momentum.
    if (Mode == ESkateMode::Bail && !bNativeBail && !Body.IsBailing() && !Body.IsGettingUp() && !Transit().bRunOutPending)
    {
        if (Body.OfferBail(Vel, RideSpin)) {}
        else if (Body.StartBail(Vel, RideSpin, URidePhysicalRider::ShownTransform(BoardRoot), BoardScale()))
        {
            bNativeBail = true;
            BeginNativeBoardInBail();
            UE_LOG(LogTemp, Display, TEXT("SKATE Native wipeout (%s) at %.0f cm/s handed to the body"), *GetRetailState().Left(32), Vel.Size());
        }
    }
    if (bNativeBail)
    {
        if (Body.IsBailing())
        {
            const ERideBodyState State = Body.UpdateBail(Dt, FRideTuning::Get().BailSettle * Feel.GetUpDelay);
            // The actor (and the character's camera) goes with the body; the ride stands still meanwhile, as Ride's root
            // does while it follows the body.
            Pos = Body.GetBodyGround(); Vel = FVector::ZeroVector;
            Rider->SetActorLocation(Pos + FVector(0, 0, BodyLift), false, nullptr, ETeleportType::None);
            // The character stands still with it (Ride's root does, and the get-up starts from rest, not the ride's speed).
            if (UCharacterMovementComponent* M = Movement()) M->Velocity = Vel;
            if (State == ERideBodyState::Unstable) { Body.Abort(); GetUpFromNativeBail(); }
            else if (State == ERideBodyState::Settled) GetUpFromNativeBail();
        }
        else GetUpFromNativeBail();
        if (!PhysicalRider->IsActive()) return;
    }

    // The active ragdoll follows skate.RidePhysical live, outside bails and get-ups.
    const bool bSteady = !bNativeBail && !Body.IsBailing() && !Body.IsGettingUp() && Mode != ESkateMode::Bail;
    if (bSteady && URidePhysicalRider::IsWanted() && !Body.IsSimulating()) Body.BlendIn(Settings->MountBlend);
    else if (bSteady && !URidePhysicalRider::IsWanted() && Body.IsSimulating()) Body.BlendOut(Settings->DismountBlend);
    ERidePhysicalPhase Phase = Mode == ESkateMode::Air ? ERidePhysicalPhase::Air : Mode == ESkateMode::Grind ? ERidePhysicalPhase::Grind :
        bManual ? ERidePhysicalPhase::Manual : ERidePhysicalPhase::Riding;
    if (Body.IsBailing()) Phase = ERidePhysicalPhase::Bail;
    else if (Body.IsGettingUp()) Phase = ERidePhysicalPhase::GetUp;
    Body.Update(Dt, Phase);
    if (!PhysicalRider->IsActive()) return;

    // Getting up onto the board: the pose rises out of the fallen body's snapshot.
    if (Body.IsGettingUp() && Body.GetGetUpExit() == ERideGetUpExit::Board) Body.BlendFromSnapshot(RetailPose, Body.GetGetUpAlpha());

    // The board's meshes follow the loose board while it is ours.
    FRideTransition& T = Transit();
    if (Body.GetLooseBoard())
    {
        const bool bOntoBoard = Body.IsGettingUp() && Body.GetGetUpExit() == ERideGetUpExit::Board;
        const bool bLeaving = !Body.IsBailing() && T.Board == ERideBoard::Ride && T.ShownTarget <= 0.f;
        if (bLeaving && T.Shown <= 0.f) Body.DropLooseBoard();
        else if (Body.IsBailing() || bLeaving || (Body.IsGettingUp() && !bOntoBoard)) BoardRoot->SetWorldTransform(Body.GetLooseBoardDeck());
        else if (bOntoBoard)
        {
            const FTransform Loose = Body.GetLooseBoardDeck(), Ridden = BoardRoot->GetComponentTransform();
            const float A = FMath::SmoothStep(0.f, 1.f, Body.GetGetUpAlpha());
            FTransform Blend;
            Blend.Blend(Loose, Ridden, A);
            BoardRoot->SetWorldTransform(Blend);
        }
        else Body.DropLooseBoard();
    }
    if (!Body.GetLooseBoard() && !Body.IsBailing() && !bNativeBail && T.Board == ERideBoard::Ride && T.ShownTarget <= 0.f) ShowBoard(1.f, false);
}

void USkateComponent::GetUpFromNativeBail()
{
    URidePhysicalRider& Body = *PhysicalRider;
    const FVector Ground = Body.GetBodyGround();
    const float Yaw = Body.GetBodyYaw();
    const bool bFaceUp = Body.IsFaceUp();
    EndNativeBoardInBail();
    bNativeBail = false;
    if (WantsGetUpOnFoot())
    {
        Body.StartGetUp(ERideGetUpExit::OnFoot);
        BeginGetUpOnFoot(bFaceUp);
        return;
    }
    Body.StartGetUp(ERideGetUpExit::Board);
    // The session takes the ride back where the body lies, stopped, facing the way the body does; the pose rises into
    // its first one out of the fallen body's snapshot. A session that failed during the ride was relaunched as the body
    // fell; should that one fail too, the board is stowed (the one clean exit that needs neither Native nor the clips).
    Pos = Ground; Rot = FRotator(0, Yaw, 0).Quaternion(); Vel = FVector::ZeroVector;
    if (!StartNativeRide()) { RuntimeFailure(TEXT("Native skating could not take the ride back after the bail.")); StowImmediately(); return; }
    const FTransform Root = RideRoot();
    Rider->SetActorLocationAndRotation(Root.GetLocation() + FVector(0, 0, BodyLift), Root.GetRotation(), false, nullptr, ETeleportType::None);
    // The board went with the actor: it stays where it lies.
    if (Body.GetLooseBoard()) BoardRoot->SetWorldTransform(Body.GetLooseBoardDeck());
    // A ride placed without the transitions' board (a QA placement) takes it now, as a mount does: the board shown is
    // the ride's.
    FRideTransition& T = Transit();
    if (Body.GetLooseBoard() && T.Board == ERideBoard::Away) { T.Board = ERideBoard::Ride; T.Shown = T.ShownTarget = 1.f; }
    // Onto the board: within a step of where the rider gets up, and lying wheels down, the rider steps onto it; otherwise it
    // dissolves out where it lies, and a board dissolves in under the feet.
    if (Body.GetLooseBoard() && T.Board == ERideBoard::Ride)
    {
        const FTransform Lying = Body.GetLooseBoardDeck();
        const float Away = FVector::Dist(Lying.GetLocation(), Ground);
        const bool bStepOn = Away <= FRideTuning::Get().GetUpBoardReach && Lying.GetRotation().GetUpVector().Z > .5f;
        if (!bStepOn) ShowBoard(0.f, false);
        UE_LOG(LogTemp, Display, TEXT("SKATE Native get-up at (%.0f, %.0f, %.0f): the board lying %.0f cm away, %s"), Ground.X, Ground.Y, Ground.Z, Away,
            bStepOn ? TEXT("stepped onto") : TEXT("dissolved out there and in under the feet"));
    }
}

bool USkateComponent::IsNativeOnFoot() const
{
    return bRetailActive && NativeStateStarts(TEXT("Biped"));
}

bool USkateComponent::TakeNativeOnFoot(float Dt)
{
    // Native's rider who lands beside the board (a dark catch, a run-out) goes on in the session on Native's feet while
    // the board rolls away; riding on, the next dismount started on that board metres from the rider and the body jumped
    // there (U120). Once it lasts, the session ends: the character runs on from the rider's place at the rider's speed,
    // and the board rolls on from Native's deck at its own, a board in the world as after a run-out (a mount steps onto
    // it, or brings it under the feet).
    const FVector Root = RideRoot().GetLocation();
    const bool bOnFoot = NativeStateStarts(TEXT("BipedGround")) && !bNativeBail &&
        !(PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
    if (!bOnFoot) { NativeOnFootTime = 0.f; NativeOnFootRoot = Root; NativeOnFootVelocity = FVector::ZeroVector; return false; }
    if (Dt <= 0.f) return false;
    // The rider's own motion, from the root's (the published velocity is the board's).
    NativeOnFootVelocity = FMath::Lerp(NativeOnFootVelocity, (Root - NativeOnFootRoot) / Dt, NativeOnFootTime > 0.f ? .3f : 1.f);
    NativeOnFootRoot = Root; NativeOnFootTime += Dt;
    UCharacterMovementComponent* M = Movement();
    if (NativeOnFootTime < NativeOnFootHold || !M || !BoardRoot) return false;
    FRideTransition& T = Transit();
    const FVector Carried = NativeOnFootVelocity, BoardVelocity = Vel, BoardSpin = RideSpin;
    const float Since = NativeOnFootTime;
    NativeOnFootTime = 0.f;
    SuspendRetailRuntime();
    RequestPoseBlend(FRideTuning::Get().DismountBlend);
    LeaveBoard();
    const bool bFloor = StandUpOffBoard(Rider->GetActorRotation().Yaw);
    const FVector Flat(Carried.X, Carried.Y, 0.f);
    M->Velocity = bFloor ? Flat : FVector(Flat.X, Flat.Y, Carried.Z);
    HoldDriveForInput(Flat);
    T.bGetUpOnFoot = false;
    const float Away = FVector::Dist(BoardRoot->GetComponentLocation(), Rider->GetActorLocation());
    if (T.Board == ERideBoard::Ride) { T.KickVelocity = BoardVelocity; T.FlightSpin = BoardSpin; T.bDeckKnown = true; T.bKickOut = false; LaunchBoard(); }
    UE_LOG(LogTemp, Display, TEXT("SKATE Native rider off the board on foot after %.2f s: on foot at %.0f cm/s, the board %.0f cm away rolling on at %.0f cm/s, %s"),
        Since, Flat.Size(), Away, BoardVelocity.Size(), bFloor ? TEXT("walking") : TEXT("falling"));
    return true;
}
