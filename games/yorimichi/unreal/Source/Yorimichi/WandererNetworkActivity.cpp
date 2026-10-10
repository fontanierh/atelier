#include "WandererCharacter.h"
#include "JapanCharacterMovement.h"
#include "JapanNetwork.h"
#include "JapanWorld.h"
#include "JapanEncounters.h"
#include "JapanCombatResolver.h"
#include "JapanSession.h"
#include "JapanSkateNetwork.h"
#include "JapanVehicleTelemetry.h"
#include "JapanReactionDeliveryQA.h"
#include "AdventureMoveSet.h"
#include "SkateComponent.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"

namespace
{
bool FiniteInWorld(const FVector& Value, double Maximum)
{
    return !Value.ContainsNaN() && FMath::Abs(Value.X) <= Maximum &&
        FMath::Abs(Value.Y) <= Maximum && FMath::Abs(Value.Z) <= Maximum;
}
}

bool AWandererCharacter::ExitNetworkVehicle(uint8 ClockCorrection,TFunction<void()> FootReaction)
{
    if(!HasAuthority()||!JapanNetwork::IsOnline(GetWorld()))return false;
    bool Falling=GetCharacterMovement()->IsFalling();
    if(NetworkActivity.Kind==EJapanActivity::Bike)
    {
        FJapanBikeState ParkedPose;
        bool Parked=false;
        if(Bike->NeedsNetworkPark())
        {
            // A completed kickstand/crash already owns its authored end pose.
            ParkedPose=Bike->CaptureNetworkState();
            Parked=Bike->CommitNetworkPark();
        }
        else Parked=Bike->ForceNetworkPark(ParkedPose);
        if(Parked)
        {
            NetworkParkedBike.Visible=true;NetworkParkedBike.Pose=ParkedPose;
            NetworkParkedBike.Transform=Bike->GetBikeTransform();
        }
        else {Bike->StowImmediately();NetworkParkedBike.Visible=false;}
    }
    else if(NetworkActivity.Kind==EJapanActivity::Sailboat)
    {Sailboat->StowImmediately();Falling=true;}
    else return false;
    SetAction(NAME_None);
    // Timeout/budget recovery must not carry bike/sail velocity into walking.
    // Neutral physics resumes gravity after this single activity handoff.
    if(ClockCorrection)GetCharacterMovement()->StopMovementImmediately();
    // Strikes commit this same exit before damage. Outstanding vehicle moves
    // carry a stale epoch and cannot restore the mounted state.
    BeginNetworkActivity(EJapanActivity::OnFoot,Falling,ClockCorrection,MoveTemp(FootReaction));
    return true;
}

void AWandererCharacter::BeginNetworkActivity(EJapanActivity Kind, bool bFalling, uint8 ClockCorrection,
    TFunction<void()> FootReaction)
{
    if (!HasAuthority() || !JapanNetwork::IsOnline(GetWorld())) return;
    // Automatic server recoveries cannot erase a contact made in the old epoch.
    GetWorld()->GetSubsystem<UJapanCombatResolver>()->Flush(this);
    ++NetworkActivity.Epoch;
    if (!NetworkActivity.Epoch) ++NetworkActivity.Epoch;
    NetworkActivity.Kind = Kind;
    NetworkActivity.Location = GetActorLocation();
    NetworkActivity.Rotation = GetActorRotation();
    NetworkActivity.Velocity = GetCharacterMovement()->Velocity;
    // A grounded clock reset drops held drive. Share the stopped velocity so
    // different first-step lengths cannot integrate different braking distances.
    if (ClockCorrection && Kind == EJapanActivity::OnFoot && !bFalling && GetCharacterMovement()->IsMovingOnGround())
        NetworkActivity.Velocity = FVector::ZeroVector;
    NetworkActivity.bFalling = bFalling;
    NetworkActivity.ClockCorrection = ClockCorrection;
    NetworkActivity.Sail = Kind == EJapanActivity::Sailboat ? Sailboat->CaptureNetworkState() : FJapanSailState();
    NetworkActivity.Bike = Kind == EJapanActivity::Bike ? Bike->CaptureNetworkState() : FJapanBikeState();
    NetworkActivity.bFootReaction = false; NetworkActivity.FootBytes.Reset(); NetworkActivity.FootAction = NAME_None;
    OnRep_NetworkActivity();
    if (Kind == EJapanActivity::OnFoot && FootReaction)
    {
        // Old moves are already stale and the host has cleared mounted/held
        // state. Apply damage once, then publish the resulting reaction in this
        // same epoch. No actor tick or network send can interleave this call.
        TGuardValue<bool> Immediate(CastChecked<UJapanCharacterMovement>(GetCharacterMovement())->bImmediateMovementReaction, true);
        FootReaction();
        NetworkActivity.Location = GetActorLocation(); NetworkActivity.Rotation = GetActorRotation();
        NetworkActivity.Velocity = GetCharacterMovement()->Velocity;
        NetworkActivity.bFalling = GetCharacterMovement()->IsFalling();
        NetworkActivity.bFootReaction = true;
        if (Moves) Moves->ClearNetworkReactionTargets();
        const FJapanMoveCheckpoint Checkpoint = Moves ? Moves->CaptureNetworkState() : FJapanMoveCheckpoint();
        // A fresh undefended reaction has no lock/lunge target. Do not put
        // server-only strike actors or unresolved NetGUIDs in the handoff.
        ensureMsgf(!Checkpoint.Bytes.IsEmpty() && Checkpoint.Bytes.Num() <= FJapanMoveCheckpoint::MaximumBytes &&
            !Checkpoint.Target.IsValid() && !Checkpoint.LungeTarget.IsValid(),TEXT("Invalid target-free vehicle exit reaction"));
        NetworkActivity.FootBytes = Checkpoint.Bytes; NetworkActivity.FootAction = Checkpoint.Action;
        JapanVehicleTelemetry::Handoff(this,Checkpoint);
        JapanReactionDeliveryQA::Activity(CastChecked<UJapanCharacterMovement>(GetCharacterMovement()), TEXT("activity_committed"), NetworkActivity);
    }
    ForceNetUpdate();
}

void AWandererCharacter::OnRep_NetworkActivity()
{
    if (AppliedActivityEpoch == NetworkActivity.Epoch) return;
    if ((NetworkActivity.Kind==EJapanActivity::Sailboat&&!Sailboat->IsAvailable()) ||
        (NetworkActivity.Kind==EJapanActivity::Bike&&!Bike->IsAvailable()))
    {
        if(Landscape&&Landscape->bGameplayReady)if(auto* Session=GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->ReturnWithError(TEXT("The vehicle data does not match the host. Rejoin using the same build."));
        return; // Assets may still be loading before world readiness.
    }
    AppliedActivityEpoch = NetworkActivity.Epoch;
    bNetworkActivityPending = false; bNetworkSkateObserved = false;
    auto* Movement = CastChecked<UJapanCharacterMovement>(GetCharacterMovement());
    Movement->ResetActivityPrediction();
    Movement->RecordClockCorrection(NetworkActivity.ClockCorrection);
    if (Moves) { Moves->Reset(); Moves->DropHolds(); }
    MoveIntent = FVector2D::ZeroVector; bSprintHeld = bWalk = bJog = false;
    JumpBuffer = RollBuffer = 0.f; bPendingTakeoff = false;
    StopJumping();
    SetActorLocationAndRotation(NetworkActivity.Location, NetworkActivity.Rotation, false, nullptr, ETeleportType::TeleportPhysics);
    Movement->Velocity = NetworkActivity.Velocity;
    Movement->bForceNextFloorCheck = true;
    GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    if (NetworkActivity.Kind == EJapanActivity::OnFoot)
    {
        if (SkateRide->IsRiding()) SkateRide->StowImmediately();
        if (Bike->IsEquipped()) Bike->StowImmediately();
        if (Sailboat->IsEquipped()) Sailboat->StowImmediately();
        OnRep_NetworkParkedBike();
        Movement->SetMovementMode(NetworkActivity.bFalling ? MOVE_Falling : MOVE_Walking);
        if (NetworkActivity.bFootReaction)
        {
            // Stowing the old vehicle above clears movement. The committed
            // reaction velocity must be applied after that presentation cleanup.
            Movement->Velocity = NetworkActivity.Velocity;
            // Simulated proxies consume NetworkAvatar presentation; only the
            // owning predictor needs a simulation checkpoint or can reject it.
            if (!IsLocallyControlled()) return;
            FJapanMoveCheckpoint Checkpoint;
            Checkpoint.Bytes = NetworkActivity.FootBytes; Checkpoint.Action = NetworkActivity.FootAction;
            if (!Moves || !Moves->ApplyNetworkState(Checkpoint))
            {
                if (auto* Session=GetWorld()->GetGameInstance<UJapanGameInstance>())
                    Session->ReturnWithError(TEXT("The vehicle exit reaction does not match the host. Rejoin using the same build."));
                return;
            }
            JapanVehicleTelemetry::Handoff(this,Checkpoint);
            JapanReactionDeliveryQA::Activity(Movement, TEXT("activity_restored"), NetworkActivity);
        }
        return;
    }
    if (NetworkActivity.Kind == EJapanActivity::Sailboat)
    {
        if (SkateRide->IsRiding()) SkateRide->StowImmediately();
        Movement->SetMovementMode(MOVE_Flying);
        if(!Sailboat->ApplyNetworkActivity(NetworkActivity.Sail))
            if(auto* Session=GetWorld()->GetGameInstance<UJapanGameInstance>())
                Session->ReturnWithError(TEXT("The sailboat data does not match the host. Rejoin using the same build."));
        return;
    }
    if (NetworkActivity.Kind == EJapanActivity::Bike)
    {
        if (SkateRide->IsRiding()) SkateRide->StowImmediately();
        Movement->SetMovementMode(NetworkActivity.bFalling ? MOVE_Falling : MOVE_Walking);
        if (!Bike->ApplyNetworkActivity(NetworkActivity.Bike))
            if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
                Session->ReturnWithError(TEXT("The bike data does not match the host. Rejoin using the same build."));
        return;
    }
    if (NetworkActivity.Kind == EJapanActivity::Skate)
    {
        if (IsLocallyControlled())
        {
            Movement->SetMovementMode(NetworkActivity.bFalling ? MOVE_Falling : MOVE_Walking);
            TGuardValue<bool> Applying(bApplyingNetworkActivity, true);
            ToggleSkateboard(FInputActionValue(true));
            NetworkActivityRequestTime = GetWorld()->GetTimeSeconds();
        }
        else
        {
            // A remote rider is presentation only. It never creates the simulation or Chaos rider bodies.
            Movement->DisableMovement();
            GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        }
    }
}

bool AWandererCharacter::RequestNetworkSkate()
{
    if (!IsLocallyControlled() || bNetworkActivityPending) return true;
    if (NetworkActivity.Kind == EJapanActivity::Skate) return false; // The owning simulation handles dismount/bail buttons.
    if (NetworkActivity.Kind != EJapanActivity::OnFoot || !bReady || bMenuOpen || MovementLocked() || OnVehicle()) return true;
    bNetworkActivityPending = true;
    NetworkActivityRequestTime = GetWorld()->GetTimeSeconds();
    ServerRequestSkate(NetworkActivity.Epoch);
    return true;
}

void AWandererCharacter::ServerRequestSkate_Implementation(uint32 Epoch)
{
    auto* Combat = GetWorld()->GetSubsystem<UJapanCombatResolver>();
    if (!Combat) { ClientActivityRejected(TEXT("Combat state is unavailable.")); return; }
    if (Epoch == NetworkActivity.Epoch && Combat->HasPending(this))
    { ++Combat->PendingSkateRefusals; ClientActivityRejected(TEXT("Finish the incoming hit before skating.")); return; }
    const auto* Rules = GetWorld()->GetGameState<AJapanGameState>();
    if (Epoch != NetworkActivity.Epoch || NetworkActivity.Kind != EJapanActivity::OnFoot ||
        !Rules || !Rules->bTrustedSkating || !bReady || MovementLocked() || OnVehicle() ||
        GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this) ||
        GetWorld()->GetSubsystem<UJapanCombatResolver>()->HasPending(this))
    {
        ClientActivityRejected(TEXT("Skating is unavailable during this action."));
        return;
    }
    BeginNetworkActivity(EJapanActivity::Skate, GetCharacterMovement()->IsFalling());
}

void AWandererCharacter::ServerFinishSkate_Implementation(uint32 Epoch, FVector_NetQuantize100 Location,
    FRotator Rotation, FVector_NetQuantize100 Velocity, bool bFalling)
{
    if (Epoch != NetworkActivity.Epoch || NetworkActivity.Kind != EJapanActivity::Skate) return;
    // Private trusted-skating policy: bounded presentation/position authority, never health or combat authority.
    if (!FiniteInWorld(Location, 2000000.) || !FiniteInWorld(Velocity, 30000.) || Rotation.ContainsNaN() ||
        !NetworkSkate || !NetworkSkate->AcceptsRoot(Location))
    {
        BeginNetworkActivity(EJapanActivity::OnFoot, true);
        ClientActivityRejected(TEXT("Invalid skating handoff; returned to the last accepted position."));
        return;
    }
    SetActorLocationAndRotation(Location, FRotator(0.f, Rotation.Yaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
    GetCharacterMovement()->Velocity = Velocity;
    BeginNetworkActivity(EJapanActivity::OnFoot, bFalling);
}

void AWandererCharacter::ServerTravelTo_Implementation(FVector_NetQuantize100 Location, float Yaw, uint32 Epoch)
{
    // The host can already have recovered from water and advanced the epoch. Its
    // replicated handoff supersedes this late request; do not show a false failure.
    if (Epoch != NetworkActivity.Epoch) return;
    auto* Combat = GetWorld()->GetSubsystem<UJapanCombatResolver>();
    if (!Combat) { ClientActivityRejected(TEXT("Combat state is unavailable.")); return; }
    if (Combat->HasPending(this))
    { ++Combat->PendingTravelRefusals; ClientActivityRejected(TEXT("Finish the incoming hit before travelling.")); return; }
    if (!FiniteInWorld(Location, 2000000.) || !FMath::IsFinite(Yaw) ||
        GetWorld()->GetTimeSeconds() - LastNetworkTravel < 1.)
    { ClientActivityRejected(TEXT("Travel is unavailable just now.")); return; }
    if (GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this) ||
        GetWorld()->GetSubsystem<UJapanCombatResolver>()->HasPending(this))
    { ClientActivityRejected(TEXT("Finish or leave the encounter before travelling.")); return; }
    LastNetworkTravel = GetWorld()->GetTimeSeconds();
    if (!TravelTo(Location, Yaw, TEXT("player map"))) ClientActivityRejected(TEXT("Could not find a safe destination."));
}

void AWandererCharacter::ClientActivityRejected_Implementation(const FString& Reason)
{
    bNetworkActivityPending = false;
    if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>()) Session->SetSessionStatus(Reason);
}

void AWandererCharacter::TickNetworkActivity()
{
    if (AppliedActivityEpoch != NetworkActivity.Epoch) OnRep_NetworkActivity();
    TickNetworkBike();
    TickNetworkSail();
    if (!IsLocallyControlled()) return;
    if (bNetworkActivityPending && GetWorld()->GetTimeSeconds() - NetworkActivityRequestTime > 8.)
    {
        bNetworkActivityPending = false;
        if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->ReturnWithError(TEXT("The host did not acknowledge the activity change."));
        return;
    }
    if (NetworkActivity.Kind != EJapanActivity::Skate || bNetworkActivityPending) return;
    if (SkateRide->IsRiding()) bNetworkSkateObserved = true;
    else if (bNetworkSkateObserved || GetWorld()->GetTimeSeconds() - NetworkActivityRequestTime > .5)
    {
        // All exits converge here: dismount, bail/get-up, and the simulation BipedGround takeover.
        bNetworkActivityPending = true;
        NetworkActivityRequestTime = GetWorld()->GetTimeSeconds();
        auto* Movement = GetCharacterMovement();
        const FVector Velocity = Movement->Velocity;
        const bool Falling = Movement->IsFalling();
        // Hold this boundary while its reliable acknowledgement travels. Do not simulate unrecorded foot moves
        // and then teleport back to the reported position one round trip later.
        Movement->DisableMovement();
        ServerFinishSkate(NetworkActivity.Epoch, GetActorLocation(), GetActorRotation(), Velocity, Falling);
    }
}
