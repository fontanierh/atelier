#include "HorseComponent.h"
#include "WandererCharacter.h"
#include "JapanNetwork.h"
#include "JapanVehicleTelemetry.h"
#include "JapanVehicleVisuals.h"
#include "JapanCharacterMovement.h"
#include "Components/SceneComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/World.h"

// The horse in a shared game, as BikeNetwork.cpp: the owner and the host advance AdvanceSimulation inside the movement
// component's moves; corrections restore FJapanHorseState before replay; remote players show the host's presentation.

void UHorseComponent::SimulateNetwork(float Dt, const FHorseInput& In)
{
    if (!JapanNetwork::IsOnline(GetWorld()) || !Rider || Phase == EPhase::Stowed || !FMath::IsFinite(Dt) || Dt <= 0.f) return;
    // Online the end of dismounting only marks NeedsNetworkStow(); the host's actor tick stows and changes the epoch.
    AdvanceSimulation(Dt, In);
}

FJapanHorseState UHorseComponent::CaptureNetworkState() const
{
    FJapanHorseState S;
    S.Phase = uint8(Phase); S.Role = uint8(Role); S.ForcedIdle = uint8(ForcedIdle); S.Serial = Serial;
    S.Yaw = Rider ? float(FRotator::NormalizeAxis(Rider->GetActorRotation().Yaw)) : 0.f;
    S.Speed = Speed; S.Steering = Steering; S.PhaseTime = PhaseTime; S.GaitPhase = GaitPhase;
    S.IdleTimer = IdleTimer; S.IdleCooldown = IdleCooldown;
    S.Sprint = bSprint; S.Terminal = bTerminal; S.ReinIn = bReinIn;
    return S;
}

bool UHorseComponent::ApplyNetworkState(const FJapanHorseState& S, bool RestoreFacing)
{
    // A correction never stows: activity handoffs own the horse's arrival and departure, friction and visibility.
    if (!S.IsValid() || S.Phase == uint8(EPhase::Stowed) || !Rider || !bAssetsReady) return false;
    if (RestoreFacing) Rider->SetActorRotation(FRotator(0.f, S.Yaw, 0.f));
    Phase = EPhase(S.Phase); Role = EHorseRole(S.Role); ForcedIdle = EHorseRole(S.ForcedIdle); Serial = S.Serial;
    Speed = S.Speed; Steering = S.Steering; PhaseTime = S.PhaseTime; GaitPhase = S.GaitPhase;
    // The host's timer never exceeds its clip; a replacement rider's own clip may be shorter.
    IdleTimer = FMath::Min(S.IdleTimer, ClipLength(ForcedIdle)); IdleCooldown = S.IdleCooldown;
    bSprint = S.Sprint; bTerminal = S.Terminal; bReinIn = S.ReinIn;
    return true;
}

bool UHorseComponent::QueueNetworkAction(FName Button, bool& Accepted)
{
    if (!Rider || !JapanNetwork::IsOnline(GetWorld())) return false;
    auto* Movement = CastChecked<UJapanCharacterMovement>(Rider->GetCharacterMovement());
    if (Movement->IsExecutingMove()) return false;
    Accepted = Movement->QueueMoveButton(Button);
    return true;
}

void UHorseComponent::RefreshTickOrder()
{
    if (!Rider) return;
    const bool Online = JapanNetwork::IsOnline(GetWorld());
    if (bTickModeSet && bNetworkTickOrder == Online) return;
    auto* Movement = Rider->GetCharacterMovement();
    Movement->RemoveTickPrerequisiteComponent(this);
    RemoveTickPrerequisiteComponent(Movement);
    if (Online) AddTickPrerequisiteComponent(Movement);
    else Movement->AddTickPrerequisiteComponent(this);
    bTickModeSet = true; bNetworkTickOrder = Online;
}

bool UHorseComponent::ApplyNetworkActivity(const FJapanHorseState& Snapshot)
{
    if (!Rider || !CanRide() || !Snapshot.IsValid() || Snapshot.Phase == uint8(EPhase::Stowed)) return false;
    const bool bArriving = Phase == EPhase::Stowed;
    if (!ApplyNetworkState(Snapshot)) return false;
    RefreshTickOrder();
    // Saved on the first install only (the host's own Toggle already saved them), whatever a correction did to Phase.
    HoldFriction();
    if (bArriving)
    {
        ResetPresentation();
        JapanVehicleVisuals::SetRiderPose(Rider, MeshLocation, MeshRotation.Quaternion(), false);
    }
    bHorseClipStale = true;
    Hint.Reset();
    HorseRoot->SetVisibility(true, true);
    return true;
}

void UHorseComponent::ReceiveNetworkPresentation(uint32 Epoch, double Stamp, const FJapanHorseState& Snapshot)
{
    if (!Rider || Rider->HasAuthority() || Rider->IsLocallyControlled() || !Snapshot.IsValid() || !FMath::IsFinite(Stamp)) return;
    if (Epoch != Rider->GetActivityEpoch()) return;
    if (PresentationBufferEpoch != Epoch)
    { PresentationBufferEpoch = Epoch; NetworkPoses.Reset(); NetworkPlayout = FJapanSkatePlayout(); LastPresentationStamp = -1.; }
    if (Stamp <= LastPresentationStamp) return;
    LastPresentationStamp = Stamp;
    const double Now = GetWorld()->GetTimeSeconds();
    const double At = NetworkPlayout.Map(Stamp, Now);
    if (!NetworkPoses.IsEmpty() && At <= NetworkPoses.Last().At) return;
    NetworkPlayout.ReceivePose(At, Now, .05);
    NetworkPoses.Add({At, Snapshot});
    if (NetworkPoses.Num() > 48) NetworkPoses.RemoveAt(0, NetworkPoses.Num() - 48);
}

void UHorseComponent::SampleNetworkPresentation()
{
    if (!Rider || Rider->HasAuthority() || Rider->IsLocallyControlled() || NetworkPoses.IsEmpty() ||
        PresentationBufferEpoch != Rider->GetActivityEpoch()) return;
    const auto Sample = FJapanSkatePlayout::Sample(NetworkPoses, NetworkPlayout.Advance(GetWorld()->GetTimeSeconds()),
        [](const FNetworkPose& P) { return P.At; });
    const FJapanHorseState& A = NetworkPoses[Sample.A].State;
    const FJapanHorseState& B = NetworkPoses[Sample.B].State;
    FJapanHorseState StateToShow = Sample.Alpha >= 1.f ? B : A;
    // Within one clip the continuous values blend; a looping gait's cycle wraps forward through its end.
    if (A.Serial == B.Serial && A.Phase == B.Phase && A.Role == B.Role)
    {
        float EndPhase = B.GaitPhase;
        const bool bLoop = Loops(EHorseRole(A.Role));
        if (bLoop && EndPhase < A.GaitPhase) EndPhase += 1.f;
        const float Phase01 = FMath::Lerp(A.GaitPhase, EndPhase, Sample.Alpha);
        StateToShow.GaitPhase = bLoop ? FMath::Frac(Phase01) : FMath::Clamp(Phase01, 0.f, 1.f);
        StateToShow.Speed = FMath::Lerp(A.Speed, B.Speed, Sample.Alpha);
        StateToShow.Steering = FMath::Lerp(A.Steering, B.Steering, Sample.Alpha);
        StateToShow.PhaseTime = FMath::Lerp(A.PhaseTime, B.PhaseTime, Sample.Alpha);
    }
    // CMC owns and smooths the proxy's root; the presented state never turns it.
    if (ApplyNetworkState(StateToShow, false)) JapanVehicleTelemetry::Presentation(Rider, NetworkPoses[Sample.Alpha >= 1.f ? Sample.B : Sample.A].At);
}

void UHorseComponent::PresentNetwork(float Dt)
{
    // Prediction and the remote presentation both reach this once, after any movement replay.
    SampleNetworkPresentation();
    if (Phase == EPhase::Stowed) return;
    Present(Dt);
}
