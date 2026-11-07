#include "JapanAudioPreferences.h"
#include "JapanFootsteps.h"
#include "SkateComponent.h"
#include "Engine/World.h"
#include "UObject/UObjectIterator.h"

namespace
{
template<class T> TArray<T*> Ready(UWorld* World)
{
    TArray<T*> Result;
    for(TObjectIterator<T> It;It;++It)
        if(IsValid(*It) && !It->IsTemplate() && It->GetWorld()==World && It->IsAudioReady()) Result.Add(*It);
    return Result;
}
}

void UJapanAudioPreferences::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    if(GetWorld()->GetNetMode()==NM_DedicatedServer) return;
    FootHandle=UJapanFootstepComponent::AudioReady.AddUObject(this,&ThisClass::FootReady);
    SkateHandle=USkateComponent::AudioReady.AddUObject(this,&ThisClass::SkateReady);
}
void UJapanAudioPreferences::Deinitialize()
{
    bShuttingDown=true;
    UJapanFootstepComponent::AudioReady.Remove(FootHandle);
    USkateComponent::AudioReady.Remove(SkateHandle);
    Super::Deinitialize();
}
void UJapanAudioPreferences::SetFootstepPreferences(bool bSoften,float Volume)
{
    if(!IsInGameThread() || bShuttingDown || !FMath::IsFinite(Volume)) return;
    bSoftenFootsteps=bSoften;
    FootstepVolume=FMath::Clamp(Volume,0.f,1.f);
    for(auto* Component:Ready<UJapanFootstepComponent>(GetWorld()))
        Component->SetAudioPreferences(bSoftenFootsteps,FootstepVolume);
}
void UJapanAudioPreferences::FootReady(UJapanFootstepComponent* Component)
{
    if(bShuttingDown || !IsValid(Component) || Component->GetWorld()!=GetWorld()) return;
    Component->SetAudioPreferences(bSoftenFootsteps,FootstepVolume);
}
void UJapanAudioPreferences::SetSkatePreferences(bool bSoften,float Volume)
{
    if(!IsInGameThread() || bShuttingDown || !FMath::IsFinite(Volume)) return;
    bSoftenSkate=bSoften;
    SkateVolume=FMath::Clamp(Volume,0.f,1.f);
    for(auto* Component:Ready<USkateComponent>(GetWorld()))
        Component->SetAudioPreferences(bSoftenSkate,SkateVolume);
}
void UJapanAudioPreferences::SkateReady(USkateComponent* Component)
{
    if(bShuttingDown || !IsValid(Component) || Component->GetWorld()!=GetWorld()) return;
    Component->SetAudioPreferences(bSoftenSkate,SkateVolume);
}
