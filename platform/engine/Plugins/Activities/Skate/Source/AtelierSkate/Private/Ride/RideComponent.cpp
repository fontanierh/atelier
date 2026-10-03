// USkateComponent's side of the Ride backend: starting and stepping the session, its sounds, and the physical rider
// (RidePhysicalRider.h) with the bail's loose board. SkateRuntime.cpp copies the session's outputs into RetailRuntime,
// so the board placement, retargeting, modes and HUD after the step are the same code for both backends.
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateRails.h"
#include "RideSession.h"
#include "RidePhysicalRider.h"
#include "Components/SceneComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"

namespace
{
    FRideWorld RideWorld(ACharacter* Rider, USkateRailSubsystem* Rails)
    {
        FRideWorld W; W.World = Rider ? Rider->GetWorld() : nullptr; W.Ignore = Rider; W.Rails = Rails; W.Owner = Rider; return W;
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
    const bool bBody = PhysicalRider->Begin(Rider, RiderApi);
    PhysicalRider->ClearBailOffer();
    Ride->SetRagdoll(bBody);
    Ride->Activate(RideWorld(Rider, RailSystem), Pos, Rot, Vel, bGoofy, RidePreferences());
    if (bBody && URidePhysicalRider::IsWanted()) PhysicalRider->BlendIn(GetDefault<URidePhysicalSettings>()->MountBlend);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride started at (%.0f, %.0f, %.0f) speed %.0f, %s, %s"), Pos.X, Pos.Y, Pos.Z, Vel.Size(),
        Ride->HasRig() ? TEXT("rider clips") : TEXT("board only"),
        !bBody ? TEXT("no ragdoll") : URidePhysicalRider::IsWanted() ? TEXT("physical rider") : TEXT("ragdoll for bails"));
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
    Ride->Step(Dt, In, RideWorld(Rider, RailSystem));
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
            !Body.StartBail(Ride->GetBailVelocity(), Ride->GetBailSpin(), BoardRoot->GetComponentTransform(), BoardScale()))
            Ride->SetRagdoll(false);
        if (Body.IsBailing())
        {
            const ERideBodyState State = Body.UpdateBail(Dt, FRideTuning::Get().BailSettle);
            if (State == ERideBodyState::Unstable)
            {
                // The session slides the rider to a stop instead.
                Ride->SetRagdoll(false);
                Body.Abort();
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

    // The board's meshes follow the loose board while it is ours, and go back under the feet in a get-up onto it.
    if (Body.GetLooseBoard())
    {
        const bool bOntoBoard = Body.IsGettingUp() && Body.GetGetUpExit() == ERideGetUpExit::Board;
        if (Body.IsBailing() || (Body.IsGettingUp() && !bOntoBoard)) BoardRoot->SetWorldTransform(Body.GetLooseBoardDeck());
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
}
