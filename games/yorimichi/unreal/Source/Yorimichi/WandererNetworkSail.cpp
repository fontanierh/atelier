#include "WandererCharacter.h"
#include "SailboatComponent.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "JapanCharacterMovement.h"
#include "JapanEncounters.h"
#include "JapanCombatResolver.h"
#include "JapanVehicleTelemetry.h"
#include "BotwMoveSet.h"
#include "Engine/World.h"

bool AWandererCharacter::RequestNetworkSail()
{
    const bool Exiting=NetworkActivity.Kind==EJapanActivity::Sailboat;
    const auto* Rules=GetWorld()->GetGameState<AJapanGameState>();
    if((!Rules||!Rules->bPredictedVehicles)&&!Exiting)return false;
    if(!Sailboat||!Sailboat->IsAvailable())
    {
        if(auto* Session=GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->SetSessionStatus(TEXT("Sailboat assets are unavailable in this build."));
        return false;
    }
    if(!IsLocallyControlled()||bNetworkActivityPending||!bReady||bMenuOpen)return false;
    if(NetworkActivity.Kind!=EJapanActivity::OnFoot&&NetworkActivity.Kind!=EJapanActivity::Sailboat)return false;
    bNetworkActivityPending=true;NetworkActivityRequestTime=GetWorld()->GetTimeSeconds();
    ServerRequestSail(NetworkActivity.Epoch);return true;
}
void AWandererCharacter::ServerRequestSail_Implementation(uint32 Epoch)
{
    auto* Combat=GetWorld()->GetSubsystem<UJapanCombatResolver>();
#if !UE_BUILD_SHIPPING
    JapanVehicleTelemetry::Request(this,false,Epoch,Combat->HasPending(this),MovementLocked(),
        GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this));
#endif
    const bool Exiting=NetworkActivity.Kind==EJapanActivity::Sailboat;
    const auto* Rules=GetWorld()->GetGameState<AJapanGameState>();
    if((!Rules||!Rules->bPredictedVehicles)&&!Exiting)
    {ClientActivityRejected(TEXT("The host has disabled vehicles."));return;}
    if(Epoch!=NetworkActivity.Epoch){ClientActivityRejected(TEXT("The activity changed; try the boat again."));return;}
    if(Combat->HasPending(this))
    {
        ++Combat->PendingSailRefusals;
        ClientActivityRejected(TEXT("Wait for the incoming strike before changing vehicles."));
        return;
    }
    const bool Sailing=NetworkActivity.Kind==EJapanActivity::Sailboat;
    if((!Sailing&&NetworkActivity.Kind!=EJapanActivity::OnFoot)||!bReady||bMenuOpen||MovementLocked()||IsZeppelinPassenger()||
        (!Sailing&&OnVehicle())||(!Sailing&&GetWorld()->GetSubsystem<UJapanEncounters>()->HoldsPlayer(this)))
    {ClientActivityRejected(TEXT("Finish the current action before sailing."));return;}
    if(!Sailboat->Toggle()){ClientActivityRejected(Sailboat->GetStatus());return;}
    if(Moves)Moves->Reset();SetAction(NAME_None);JumpBuffer=0.f;bPendingTakeoff=false;StopJumping();
    BeginNetworkActivity(Sailboat->IsEquipped()?EJapanActivity::Sailboat:EJapanActivity::OnFoot,GetCharacterMovement()->IsFalling());
}
void AWandererCharacter::TickNetworkSail()
{
    if(!Sailboat||!Sailboat->IsAvailable()||NetworkActivity.Kind!=EJapanActivity::Sailboat)return;
    if(HasAuthority()&&GetWorld()->GetTimeSeconds()-LastSailPublication>=.05)
    {
        NetworkSailPresentation.Epoch=NetworkActivity.Epoch;NetworkSailPresentation.Stamp=GetWorld()->GetTimeSeconds();
        NetworkSailPresentation.State=Sailboat->CaptureNetworkState();LastSailPublication=GetWorld()->GetTimeSeconds();
    }
    else if(!HasAuthority()&&!IsLocallyControlled())OnRep_NetworkSailPresentation();
}
void AWandererCharacter::OnRep_NetworkSailPresentation()
{
    if(NetworkActivity.Kind==EJapanActivity::Sailboat&&Sailboat&&Sailboat->IsAvailable())
        Sailboat->ReceiveNetworkPresentation(NetworkSailPresentation.Epoch,NetworkSailPresentation.Stamp,NetworkSailPresentation.State);
}
