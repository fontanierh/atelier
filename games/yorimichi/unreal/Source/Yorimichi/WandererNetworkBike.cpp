#include "WandererCharacter.h"
#include "BikeComponent.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "JapanCharacterMovement.h"
#include "JapanEncounters.h"
#include "JapanCombatResolver.h"
#include "JapanVehicleTelemetry.h"
#include "JapanVehicleQA.h"
#include "AdventureMoveSet.h"
#include "Engine/World.h"

bool AWandererCharacter::RequestNetworkBike()
{
    const bool Exiting=NetworkActivity.Kind==EJapanActivity::Bike;
    const auto* Rules=GetWorld()->GetGameState<AJapanGameState>();
    if((!Rules||!Rules->bPredictedVehicles)&&!Exiting)return false;
    if(!Bike||!Bike->IsAvailable())
    {
        if(auto* Session=GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->SetSessionStatus(TEXT("Bike assets are unavailable in this build."));
        return false;
    }
    if(!IsLocallyControlled()||bNetworkActivityPending||!bReady||bMenuOpen)return false;
    if(NetworkActivity.Kind!=EJapanActivity::OnFoot&&NetworkActivity.Kind!=EJapanActivity::Bike)return false;
    bNetworkActivityPending=true;NetworkActivityRequestTime=GetWorld()->GetTimeSeconds();
    ServerRequestBike(NetworkActivity.Epoch);
    return true;
}

void AWandererCharacter::ServerRequestBike_Implementation(uint32 Epoch)
{
    auto* Combat=GetWorld()->GetSubsystem<UJapanCombatResolver>();
#if !UE_BUILD_SHIPPING
    JapanVehicleTelemetry::Request(this,true,Epoch,Combat->HasPending(this),MovementLocked(),
        GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this));
#endif
    const bool Exiting=NetworkActivity.Kind==EJapanActivity::Bike;
    const auto* Rules=GetWorld()->GetGameState<AJapanGameState>();
    if((!Rules||!Rules->bPredictedVehicles)&&!Exiting)
    {ClientActivityRejected(TEXT("The host has disabled vehicles."));return;}
    if(Epoch!=NetworkActivity.Epoch){ClientActivityRejected(TEXT("The activity changed; try the bike again."));return;}
    if(Combat->HasPending(this))
    {
        ++Combat->PendingBikeRefusals;
        ClientActivityRejected(TEXT("Wait for the incoming strike before changing vehicles."));
        return;
    }
    const bool OnBike=NetworkActivity.Kind==EJapanActivity::Bike;
    if((!OnBike&&NetworkActivity.Kind!=EJapanActivity::OnFoot)||!bReady||bMenuOpen||MovementLocked()||
        IsZeppelinPassenger()||(!OnBike&&OnVehicle())||
        (!OnBike&&GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this)))
    {ClientActivityRejected(TEXT("Finish the current action before using the bike."));return;}
    if(!Bike->Toggle()){ClientActivityRejected(Bike->GetStatus());return;}
    NetworkParkedBike.Visible=false;
    if(Moves)Moves->Reset();
    SetAction(NAME_None);JumpBuffer=0.f;bPendingTakeoff=false;StopJumping();
    BeginNetworkActivity(EJapanActivity::Bike,GetCharacterMovement()->IsFalling());
}

void AWandererCharacter::OnRep_NetworkParkedBike()
{
    if(!Bike||!Bike->IsAvailable()||NetworkActivity.Kind==EJapanActivity::Bike)return;
    if(NetworkParkedBike.Visible)Bike->ShowNetworkParked(NetworkParkedBike.Pose,NetworkParkedBike.Transform);
    else Bike->HideNetworkParked();
}

void AWandererCharacter::TickNetworkBike()
{
    if(!Bike||!Bike->IsAvailable())return;
    Bike->RefreshTickOrder();
    if(NetworkActivity.Kind==EJapanActivity::Bike)
    {
        if(HasAuthority()&&GetWorld()->GetTimeSeconds()-LastBikePublication>=.05)
        {
            NetworkBikePresentation.Epoch=NetworkActivity.Epoch;
            NetworkBikePresentation.Stamp=GetWorld()->GetTimeSeconds();
            NetworkBikePresentation.State=Bike->CaptureNetworkState();
            LastBikePublication=GetWorld()->GetTimeSeconds();
        }
        else if(!HasAuthority()&&!IsLocallyControlled())OnRep_NetworkBikePresentation();
    }
    // Terminal simulation only marks intent; actor Tick is outside any saved-move
    // replay and may safely reset the movement epoch and its prediction buffers.
    if(HasAuthority()&&NetworkActivity.Kind==EJapanActivity::Bike)JapanVehicleQA::BeforeBikePark(this);
    if(HasAuthority()&&NetworkActivity.Kind==EJapanActivity::Bike&&Bike->NeedsNetworkPark())
    {
        const FJapanBikeState Pose=Bike->CaptureNetworkState();
        if(Bike->CommitNetworkPark())
        {
            NetworkParkedBike.Visible=true;NetworkParkedBike.Pose=Pose;
            NetworkParkedBike.Transform=Bike->GetBikeTransform();
            BeginNetworkActivity(EJapanActivity::OnFoot,GetCharacterMovement()->IsFalling());
        }
        else
        {
            Bike->StowImmediately();NetworkParkedBike.Visible=false;
            BeginNetworkActivity(EJapanActivity::OnFoot,GetCharacterMovement()->IsFalling());
            ClientActivityRejected(TEXT("The bike could not be parked. You are back on foot."));
        }
    }
    if(NetworkActivity.Kind!=EJapanActivity::Bike&&NetworkParkedBike.Visible&&!Bike->IsParked())OnRep_NetworkParkedBike();
}

void AWandererCharacter::OnRep_NetworkBikePresentation()
{
    if(NetworkActivity.Kind==EJapanActivity::Bike&&Bike&&Bike->IsAvailable())
        Bike->ReceiveNetworkPresentation(NetworkBikePresentation.Epoch,NetworkBikePresentation.Stamp,NetworkBikePresentation.State);
}
