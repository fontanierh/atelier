// USkateComponent's side of the Ride backend: starting and stepping the session, its sounds, and the physical rider
// (RidePhysicalRider.h) with the bail's loose board. SkateRuntime.cpp copies the session's outputs into RetailRuntime,
// so the board placement, retargeting, modes and HUD after the step are the same code for both backends.
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateRails.h"
#include "RideSession.h"
#include "RidePhysicalRider.h"
#include "RideTransition.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"

namespace
{
    FRideWorld RideWorld(ACharacter* Rider, USkateRailSubsystem* Rails, float BoardScale)
    {
        FRideWorld W; W.World = Rider ? Rider->GetWorld() : nullptr; W.Ignore = Rider; W.Rails = Rails; W.Owner = Rider;
        W.BoardScale = BoardScale;
        return W;
    }
    FRidePreferences RidePreferences()
    {
        const USkateSettings* S = GetDefault<USkateSettings>();
        FRidePreferences P;
        P.Pop = S->PopHeightScale; P.Spin = S->AirSpinScale; P.PushSpeed = S->PushSpeedScale; P.PushPower = S->PushPowerScale; P.VertAssist = S->VertAssist;
        return P;
    }
    ERidePhysicalPhase PhysicalPhase(ERideState Mode)
    {
        switch (Mode)
        {
        case ERideState::Air: return ERidePhysicalPhase::Air;
        case ERideState::Grind: return ERidePhysicalPhase::Grind;
        case ERideState::Manual: return ERidePhysicalPhase::Manual;
        case ERideState::Bail: return ERidePhysicalPhase::Bail;
        case ERideState::GetUp: return ERidePhysicalPhase::GetUp;
        default: return ERidePhysicalPhase::Riding;
        }
    }
}

void USkateComponent::PreloadRide()
{
    if (!Ride) Ride = MakeShared<FRideSession>();
    Ride->Preload();
}

bool USkateComponent::StartRide()
{
    if (!Rider) return false;
    if (!Ride) Ride = MakeShared<FRideSession>();
    // The rider's bodies: kinematic on the animation until the mount blends them in (skate.RidePhysical) or a bail
    // lets them go. Without them a bail slides.
    if (!PhysicalRider) PhysicalRider = NewObject<URidePhysicalRider>(this, NAME_None, RF_Transient);
    // The start's own cost, logged: it lands on one frame (the mount's last).
    const double Started = FPlatformTime::Seconds();
    const bool bBody = PhysicalRider->Begin(Rider, RiderApi);
    const double Bodied = FPlatformTime::Seconds();
    PhysicalRider->ClearBailOffer();
    Ride->SetRagdoll(bBody);
    Ride->Activate(RideWorld(Rider, RailSystem, BoardScale()), Pos, Rot, Vel, bGoofy, RidePreferences());
    if (bBody && URidePhysicalRider::IsWanted()) PhysicalRider->BlendIn(GetDefault<URidePhysicalSettings>()->MountBlend);
    const double Done = FPlatformTime::Seconds();
    UE_LOG(LogTemp, Display, TEXT("SKATE ride started at (%.0f, %.0f, %.0f) speed %.0f, %s, %s, in %.2f ms (body %.2f ms)"), Pos.X, Pos.Y, Pos.Z, Vel.Size(),
        Ride->HasRig() ? TEXT("rider clips") : TEXT("board only"),
        !bBody ? TEXT("no ragdoll") : URidePhysicalRider::IsWanted() ? TEXT("physical rider") : TEXT("ragdoll for bails"),
        (Done - Started) * 1000., (Bodied - Started) * 1000.);
    return true;
}

void USkateComponent::StopRide()
{
    // The body lets go over the dismount and the mesh is pure animation again on foot.
    if (PhysicalRider) PhysicalRider->Release(GetDefault<URidePhysicalSettings>()->DismountBlend);
}

bool USkateComponent::StepRide(float Dt)
{
    // The deliberate bail: both sticks clicked with both triggers held (scripted input sets bBail itself).
    if (!bScripted && Rider)
    {
        In.bBail = false;
        if (APlayerController* PC = Cast<APlayerController>(Rider->GetController()))
            In.bBail = PC->IsInputKeyDown(EKeys::Gamepad_LeftThumbstick) && PC->IsInputKeyDown(EKeys::Gamepad_RightThumbstick) &&
                PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis) > .5f && PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > .5f;
    }
    Ride->Step(Dt, In, RideWorld(Rider, RailSystem, BoardScale()));
    for (const ERideCue Cue : Ride->Cues)
        switch (Cue)
        {
        case ERideCue::Push: PlayCue(TEXT("push"), .7f); break;
        case ERideCue::Flick: PlayCue(TEXT("flick"), .6f); break;
        case ERideCue::Catch: PlayCue(TEXT("catch"), .7f); break;
        case ERideCue::Fall: PlayCue(TEXT("fall"), 1.f); break;
        }
    return true;
}

void USkateComponent::AfterRideFrame(float Dt)
{
    if (!Ride || !PhysicalRider || !PhysicalRider->IsActive()) return;
    URidePhysicalRider& Body = *PhysicalRider;
    const URidePhysicalSettings* Settings = GetDefault<URidePhysicalSettings>();

    // A bail: offered first to the transition (a run-out on foot), otherwise the body goes limp with its momentum and
    // the board tumbles on its own. When the body has settled the rider gets up where it lies.
    if (Ride->IsBailing())
    {
        // A run-out taken by the transition keeps the body active on foot.
        if (!Body.IsBailOffered() && !Body.OfferBail(Ride->GetBailVelocity(), Ride->GetBailSpin()) &&
            !Body.StartBail(Ride->GetBailVelocity(), Ride->GetBailSpin(), URidePhysicalRider::ShownTransform(BoardRoot), BoardScale()))
            Ride->SetRagdoll(false);
        if (Body.IsBailing())
        {
            const ERideBodyState State = Body.UpdateBail(Dt, FRideTuning::Get().BailSettle);
            if (State == ERideBodyState::Unstable)
            {
                // The session slides the rider to a stop instead; the board left lying goes with the bodies, and a board
                // dissolves in under the feet once he is up.
                Ride->SetRagdoll(false);
                Body.Abort();
                if (Transit().Board == ERideBoard::Ride) ShowBoard(0.f, true);
            }
            else
            {
                Ride->FollowBody(Body.GetBodyGround());
                if (State == ERideBodyState::Settled) GetUpFromBody();
            }
        }
    }
    else
    {
        // The session got up by itself (it waits BailSettle + 5 s for the body).
        if (Body.IsBailing()) GetUpFromBody();
        Body.ClearBailOffer();
        Ride->SetRagdoll(true);
    }

    // The active ragdoll follows skate.RidePhysical live, outside bails and get-ups.
    const bool bSteady = !Body.IsBailing() && !Body.IsGettingUp() && !Ride->IsBailing() && Ride->GetMode() != ERideState::GetUp;
    if (bSteady && URidePhysicalRider::IsWanted() && !Body.IsSimulating()) Body.BlendIn(Settings->MountBlend);
    else if (bSteady && !URidePhysicalRider::IsWanted() && Body.IsSimulating()) Body.BlendOut(Settings->DismountBlend);
    ERidePhysicalPhase Phase = PhysicalPhase(Ride->GetMode());
    if (Phase == ERidePhysicalPhase::Bail && !Body.IsBailing()) Phase = ERidePhysicalPhase::OnFoot;
    Body.Update(Dt, Phase);
    if (!PhysicalRider->IsActive()) return;

    // Getting up onto the board: the pose rises out of the fallen body's snapshot.
    if (Body.IsGettingUp() && Body.GetGetUpExit() == ERideGetUpExit::Board) Body.BlendFromSnapshot(RetailPose, Body.GetGetUpAlpha());

    // The board's meshes follow the loose board while it is ours. A board never travels by itself: getting up onto it,
    // the rider steps onto one lying within a step, which eases under the feet; one farther away dissolves out where it
    // lies (GetUpFromBody) and, once gone, dissolves back in under the feet while he rises.
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
    // The ridden board, once the one left lying is gone, dissolves in under the feet (a ridden board is never meant gone).
    if (!Body.GetLooseBoard() && !Body.IsBailing() && !Ride->IsBailing() && T.Board == ERideBoard::Ride && T.ShownTarget <= 0.f) ShowBoard(1.f, false);
}

void USkateComponent::GetUpFromBody()
{
    URidePhysicalRider& Body = *PhysicalRider;
    // Where the body lies and how: read before the get-up holds the bodies on the animation.
    const FVector Ground = Body.GetBodyGround();
    const float Yaw = Body.GetBodyYaw();
    const bool bFaceUp = Body.IsFaceUp();
    if (WantsGetUpOnFoot())
    {
        Body.StartGetUp(ERideGetUpExit::OnFoot);
        BeginGetUpOnFoot(Ground, Yaw, bFaceUp);
        return;
    }
    Body.StartGetUp(ERideGetUpExit::Board);
    if (Ride->IsBailing()) Ride->GetUp(Ground, Yaw);
    // Onto the board: within a step of where he gets up, and lying wheels down, he steps onto it (AfterRideFrame eases
    // it under the feet); otherwise it dissolves out where it lies, and a board dissolves in under his feet.
    if (Body.GetLooseBoard() && Transit().Board == ERideBoard::Ride)
    {
        const FTransform Lying = Body.GetLooseBoardDeck();
        const float Away = FVector::Dist(Lying.GetLocation(), Ground);
        const bool bStepOn = Away <= FRideTuning::Get().GetUpBoardReach && Lying.GetRotation().GetUpVector().Z > .5f;
        if (!bStepOn) ShowBoard(0.f, false);
        UE_LOG(LogTemp, Display, TEXT("SKATE ride get-up board: lying %.0f cm away, %s, %s"), Away,
            Lying.GetRotation().GetUpVector().Z > .5f ? TEXT("wheels down") : TEXT("not wheels down"),
            bStepOn ? TEXT("stepped onto") : TEXT("dissolved out there and in under the feet"));
    }
}
