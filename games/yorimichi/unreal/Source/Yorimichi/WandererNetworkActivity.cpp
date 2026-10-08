#include "WandererCharacter.h"
#include "JapanCharacterMovement.h"
#include "JapanNetwork.h"
#include "JapanEncounters.h"
#include "JapanCombatResolver.h"
#include "JapanSession.h"
#include "JapanSkateNetwork.h"
#include "BotwMoveSet.h"
#include "SkateComponent.h"
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

void AWandererCharacter::BeginNetworkActivity(EJapanActivity Kind, bool bFalling, uint8 ClockCorrection)
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
    OnRep_NetworkActivity();
    ForceNetUpdate();
}

void AWandererCharacter::OnRep_NetworkActivity()
{
    if (AppliedActivityEpoch == NetworkActivity.Epoch) return;
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
        Movement->SetMovementMode(NetworkActivity.bFalling ? MOVE_Falling : MOVE_Walking);
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
            // A remote rider is presentation only. It never creates Native or Chaos rider bodies.
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
        // All exits converge here: dismount, bail/get-up, and Native BipedGround takeover.
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
