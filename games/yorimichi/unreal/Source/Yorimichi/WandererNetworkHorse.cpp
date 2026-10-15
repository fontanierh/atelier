#include "WandererCharacter.h"
#include "HorseComponent.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "JapanCharacterMovement.h"
#include "JapanEncounters.h"
#include "JapanCombatResolver.h"
#include "JapanVehicleTelemetry.h"
#include "AdventureMoveSet.h"
#include "Engine/World.h"

// The horse in a shared game, as WandererNetworkBike.cpp: the owner asks, the host toggles and hands the activity over.

bool AWandererCharacter::RequestNetworkHorse()
{
    const bool Exiting = NetworkActivity.Kind == EJapanActivity::Horse;
    const auto* Rules = GetWorld()->GetGameState<AJapanGameState>();
    if ((!Rules || !Rules->bPredictedVehicles) && !Exiting)
    {
        if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->SetSessionStatus(TEXT("The host has disabled vehicles."));
        return false;
    }
    if (!Horse || !Horse->IsAvailable())
    {
        if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->SetSessionStatus(TEXT("Horse assets are unavailable in this build."));
        return false;
    }
    if (!IsLocallyControlled() || bNetworkActivityPending || !bReady || bMenuOpen) return false;
    if (NetworkActivity.Kind != EJapanActivity::OnFoot && NetworkActivity.Kind != EJapanActivity::Horse) return false;
    bNetworkActivityPending = true; NetworkActivityRequestTime = GetWorld()->GetTimeSeconds();
    ServerRequestHorse(NetworkActivity.Epoch);
    return true;
}

void AWandererCharacter::ServerRequestHorse_Implementation(uint32 Epoch)
{
    auto* Combat = GetWorld()->GetSubsystem<UJapanCombatResolver>();
#if !UE_BUILD_SHIPPING
    JapanVehicleTelemetry::Request(this, TEXT("horse"), Epoch, Combat->HasPending(this), MovementLocked(),
        GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this));
#endif
    const bool Exiting = NetworkActivity.Kind == EJapanActivity::Horse;
    const auto* Rules = GetWorld()->GetGameState<AJapanGameState>();
    if ((!Rules || !Rules->bPredictedVehicles) && !Exiting)
    { ClientActivityRejected(TEXT("The host has disabled vehicles.")); return; }
    if (Epoch != NetworkActivity.Epoch) { ClientActivityRejected(TEXT("The activity changed; try the horse again.")); return; }
    if (Combat->HasPending(this))
    {
        ++Combat->PendingHorseRefusals;
        ClientActivityRejected(TEXT("Wait for the incoming strike before changing vehicles."));
        return;
    }
    const bool Riding = NetworkActivity.Kind == EJapanActivity::Horse;
    if ((!Riding && NetworkActivity.Kind != EJapanActivity::OnFoot) || !bReady || bMenuOpen || MovementLocked() ||
        IsZeppelinPassenger() || (!Riding && OnVehicle()) ||
        (!Riding && GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this)))
    { ClientActivityRejected(TEXT("Finish the current action before riding the horse.")); return; }
    // Mounts standing on the ground, not crouching; dismounts once stopped, on the ground (UHorseComponent::Toggle).
    if (!Horse->Toggle()) { ClientActivityRejected(Horse->GetStatus()); return; }
    if (Moves) Moves->Reset();
    SetAction(NAME_None); JumpBuffer = 0.f; bPendingTakeoff = false; StopJumping();
    BeginNetworkActivity(EJapanActivity::Horse, GetCharacterMovement()->IsFalling());
}

void AWandererCharacter::TickNetworkHorse()
{
    if (!Horse || !Horse->IsAvailable()) return;
    Horse->RefreshTickOrder();
    // An accepted look that arrived before the horse was installed (or with the replacement pawn) is shown now.
    if (NetworkHorseAppearance.bChosen && !Horse->GetAppearance().SameLook(NetworkHorseAppearance) &&
        Horse->IsValidAppearance(NetworkHorseAppearance))
        Horse->ApplyAppearance(NetworkHorseAppearance);
    if (NetworkActivity.Kind != EJapanActivity::Horse) return;
    if (HasAuthority() && GetWorld()->GetTimeSeconds() - LastHorsePublication >= .05)
    {
        NetworkHorsePresentation.Epoch = NetworkActivity.Epoch;
        NetworkHorsePresentation.Stamp = GetWorld()->GetTimeSeconds();
        NetworkHorsePresentation.State = Horse->CaptureNetworkState();
        LastHorsePublication = GetWorld()->GetTimeSeconds();
    }
    else if (!HasAuthority() && !IsLocallyControlled()) OnRep_NetworkHorsePresentation();
    // Terminal simulation only marks intent; actor Tick is outside any saved-move replay and may safely reset the
    // movement epoch and its prediction buffers. No parked horse: it goes as he steps off.
    if (HasAuthority() && Horse->NeedsNetworkStow())
    {
        Horse->StowImmediately();
        BeginNetworkActivity(EJapanActivity::OnFoot, GetCharacterMovement()->IsFalling());
    }
}

void AWandererCharacter::OnRep_NetworkHorsePresentation()
{
    if (NetworkActivity.Kind == EJapanActivity::Horse && Horse && Horse->IsAvailable())
        Horse->ReceiveNetworkPresentation(NetworkHorsePresentation.Epoch, NetworkHorsePresentation.Stamp, NetworkHorsePresentation.State);
}

bool AWandererCharacter::RequestHorseAppearance(const FJapanHorseAppearance& Appearance)
{
    if (!Horse || !Horse->IsAvailable() || !Horse->IsValidAppearance(Appearance)) return false;
    if (!JapanNetwork::IsOnline(GetWorld())) return Horse->ApplyAppearance(Appearance);
    // The owner does not predict a look: it changes when the host's copy replicates back.
    if (!IsLocallyControlled() || !bReady || bMenuOpen) return false;
    ServerSetHorseAppearance(Appearance);
    return true;
}

void AWandererCharacter::ServerSetHorseAppearance_Implementation(const FJapanHorseAppearance& Appearance)
{
    // Indices only, checked against the host's roster (the same content at admission), at most one change per 0.15 s.
    const double Now = GetWorld()->GetTimeSeconds();
    if (!bReady || !Horse || !Horse->IsAvailable() || Now - LastHorseAppearanceAt < .15 || !Horse->IsValidAppearance(Appearance))
    {
        UE_LOG(LogTemp, Warning, TEXT("NETWORK horse appearance refused for %s"), *GetName());
        return;
    }
    LastHorseAppearanceAt = Now;
    NetworkHorseAppearance = Appearance;
    NetworkHorseAppearance.bChosen = true;
    Horse->ApplyAppearance(NetworkHorseAppearance);
    ForceNetUpdate();
}

void AWandererCharacter::OnRep_NetworkHorseAppearance()
{
    // Before the horse is installed TickNetworkHorse applies it; an index outside this build's roster is a content mismatch.
    if (!NetworkHorseAppearance.bChosen || !Horse || !Horse->IsAvailable()) return;
    if (!Horse->ApplyAppearance(NetworkHorseAppearance))
        if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->ReturnWithError(TEXT("The horse data does not match the host. Rejoin using the same build."));
}
