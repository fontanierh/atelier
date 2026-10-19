#include "JapanSoundBankNetworkQA.h"
#include "Misc/CommandLine.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "JapanSoundBanks.h"
#include "JapanSoundBank.h"
#include "JapanFootsteps.h"
#include "JapanSkateNetwork.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "SkateComponent.h"
#include "SkateSoundSet.h"
#include "Sound/SoundBase.h"
#include "Components/AudioComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
struct FProbe
{
    TWeakObjectPtr<UWorld> World;
    double Began = 0.;
    int32 Phase = 1;
    bool Requested = false;
    TMap<TWeakObjectPtr<UAudioComponent>, TWeakObjectPtr<USoundBase>> Original;
};
FProbe Probe;
const TCHAR* Keys[] = {TEXT("roll"),TEXT("grind"),TEXT("slide"),TEXT("skid"),TEXT("scrape"),
    TEXT("roll_wood"),TEXT("roll_metal"),TEXT("roll_asphalt"),TEXT("roll_stone"),TEXT("roll_dirt"),TEXT("roll_grass"),TEXT("roll_sand")};

bool Save(const FString& File, const TSharedRef<FJsonObject>& Data)
{
    FString Text;
    return FJsonSerializer::Serialize(Data,TJsonWriterFactory<>::Create(&Text)) &&
        FFileHelper::SaveStringToFile(Text,*(File+TEXT(".tmp"))) &&
        IFileManager::Get().Move(*File,*(File+TEXT(".tmp")),true,true);
}

// Read only real actor-owned emitters. No new audio component, wave assignment,
// forced Play, velocity injection or remote-pawn input belongs in this probe.
TSharedPtr<FJsonObject> Observe(AWandererCharacter* Local, int32 Selection, bool Capture)
{
    auto* World=Local->GetWorld();
    auto* Bank=Selection==2 ? LoadObject<UJapanSoundBank>(nullptr,TEXT("/Game/AudioBanks/dry_street/DA_Bank.DA_Bank")) : nullptr;
    const auto* Set=Bank ? Cast<USkateSoundSet>(Bank->Skate.Get()) : nullptr;
    if(Selection==2 && (!Bank || !Set)) return nullptr;
    TArray<TSharedPtr<FJsonValue>> Actors;
    int32 Locals=0,Remotes=0;
    for(TActorIterator<AWandererCharacter> It(World);It;++It)
    {
        auto* Pawn=*It;
        if(Pawn->IsNpc()) continue;
        auto* Skate=Pawn->GetSkate(); auto* Foot=Pawn->GetFootsteps();
        auto* Person=Pawn->GetPlayerState<AJapanPlayerState>();
        auto* Net=Pawn->FindComponentByClass<UJapanSkateNetwork>();
        if(!Person || Person->SessionPlayerId.IsEmpty() || !Person->bWorldReady || !Skate || !Foot ||
            !Skate->IsAudioReady() || !Foot->IsAudioReady() || Foot->GetSoundBank()!=Bank || Skate->GetSoundSet()!=Set) return nullptr;
        const bool IsLocal=Pawn->IsLocallyControlled();
        if(IsLocal) { ++Locals; if(!Skate->IsRiding() || Skate->GetSpeed()<100.f) return nullptr; }
        else { ++Remotes; if(!Net || Net->GetAppliedFrameCount()==0) return nullptr; }
        auto Actor=MakeShared<FJsonObject>();
        Actor->SetStringField(TEXT("player"),Person->SessionPlayerId);
        Actor->SetStringField(TEXT("pawn"),Pawn->GetPathName());
        Actor->SetBoolField(TEXT("local"),IsLocal);
        Actor->SetNumberField(TEXT("role"),int32(Pawn->GetLocalRole()));
        Actor->SetStringField(TEXT("foot_bank"),GetPathNameSafe(Foot->GetSoundBank()));
        Actor->SetStringField(TEXT("skate_set"),GetPathNameSafe(Skate->GetSoundSet()));
        Actor->SetNumberField(TEXT("received_frames"),Net ? Net->GetReceivedFrameCount() : 0);
        Actor->SetNumberField(TEXT("applied_frames"),Net ? Net->GetAppliedFrameCount() : 0);
        TArray<UAudioComponent*> Components; Pawn->GetComponents(Components);
        TArray<TSharedPtr<FJsonValue>> Loops;
        bool PlayingRoll=false;
        for(int32 Index=0;Index<UE_ARRAY_COUNT(Keys);++Index)
        {
            const FName Name(*FString::Printf(TEXT("SkateLoop%d"),Index));
            UAudioComponent* Audio=nullptr;
            for(auto* C:Components) if(C->GetFName()==Name) { if(Audio) return nullptr; Audio=C; }
            if(!Audio || Audio->GetOwner()!=Pawn || Audio->GetWorld()!=World || !Audio->Sound) return nullptr;
            if(Capture) Probe.Original.Add(Audio,Audio->Sound.Get());
            const auto* Before=Probe.Original.Find(Audio);
            if(Selection==0 && (!Before || Before->Get()!=Audio->Sound.Get())) return nullptr;
            if(Set)
            {
                if(const auto* Expected=Set->Loops.Find(FName(Keys[Index])); Expected && Expected->Get()!=Audio->Sound.Get()) return nullptr;
            }
            auto Loop=MakeShared<FJsonObject>();
            Loop->SetStringField(TEXT("component"),Audio->GetPathName());
            Loop->SetNumberField(TEXT("component_id"),Audio->GetUniqueID());
            Loop->SetStringField(TEXT("slot"),Keys[Index]);
            Loop->SetStringField(TEXT("wave"),Audio->Sound->GetPathName());
            Loop->SetBoolField(TEXT("playing"),Audio->IsPlaying());
            Loop->SetNumberField(TEXT("volume"),Audio->VolumeMultiplier);
            PlayingRoll |= (Index==0 || Index>=5) && Audio->IsPlaying() && Audio->VolumeMultiplier>.001f;
            Loops.Add(MakeShared<FJsonValueObject>(Loop));
        }
        if(!PlayingRoll) return nullptr;
        Actor->SetArrayField(TEXT("loops"),Loops);
        Actors.Add(MakeShared<FJsonValueObject>(Actor));
    }
    if(Locals!=1 || Remotes!=1) return nullptr;
    auto Result=MakeShared<FJsonObject>();
    Result->SetBoolField(TEXT("passed"),true);
    Result->SetNumberField(TEXT("selection"),Selection);
    Result->SetNumberField(TEXT("net_mode"),int32(World->GetNetMode()));
    Result->SetStringField(TEXT("world"),World->GetPathName());
    Result->SetArrayField(TEXT("actors"),Actors);
    return Result;
}
}
#endif

bool JapanSoundBankNetworkQA::Tick(AWandererCharacter* Local,FString& Error)
{
    if(!FParse::Param(FCommandLine::Get(),TEXT("networksoundbanks"))) return true;
#if WITH_DEV_AUTOMATION_TESTS
    auto* World=Local->GetWorld();
    const bool Host=World->GetNetMode()==NM_ListenServer;
    if(!Local->IsLocallyControlled() || (!Host && World->GetNetMode()!=NM_Client))
    { Error=TEXT("Soundbank QA requires actual listen/client local pawns"); return false; }
    if(Probe.World.Get()!=World) { Probe=FProbe(); Probe.World=World; Probe.Began=FPlatformTime::Seconds(); }
    if(FPlatformTime::Seconds()-Probe.Began>45.)
    { Error=TEXT("Soundbank QA did not observe both real playing roll emitters and all swaps within45s"); Local->GetSkate()->SetScriptedInput(nullptr); return false; }
    // Exercise ordinary push physics and owner pose replication, never Launch/PlaceAt.
    FSkateInput Input; Input.bPush=Local->GetSkate()->GetSpeed()<450.f;
    Local->GetSkate()->SetScriptedInput(&Input);
    FString Folder;
    if(!FParse::Value(FCommandLine::Get(),TEXT("networkqadir="),Folder))
    { Error=TEXT("Soundbank QA requires the fresh native receipt directory"); return false; }
    auto* Banks=World->GetSubsystem<UJapanSoundBanks>();
    if(!Banks) { Error=TEXT("Soundbank subsystem missing from actual network world"); return false; }
    if(!Banks->Error().IsEmpty()) { Error=Banks->Error(); return false; }
    if(!Host && !Probe.Requested) { Banks->Select(2); Probe.Requested=true; }
    const int32 Selection=Host && Probe.Phase!=2 ? 0 : 2;
    const FString HostFile=Folder/FString::Printf(TEXT("server-soundbanks-%d.json"),Probe.Phase);
    const FString GuestFile=Folder/FString::Printf(TEXT("client-soundbanks-%d.json"),Probe.Phase);
    if(Probe.Phase==3 && !Host && IFileManager::Get().FileExists(*GuestFile) &&
        IFileManager::Get().FileExists(*(Folder/TEXT("server-soundbanks-complete.json"))))
    { Local->GetSkate()->SetScriptedInput(nullptr); return true; }
    if(!Host && !IFileManager::Get().FileExists(*HostFile)) return false;
    if(Banks->Selection()!=Selection) return false;
    auto Snapshot=Observe(Local,Selection,Host && Probe.Phase==1);
    if(!Snapshot) return false;
    const FString OwnFile=Host?HostFile:GuestFile;
    if(!IFileManager::Get().FileExists(*OwnFile) && !Save(OwnFile,Snapshot.ToSharedRef()))
    { Error=TEXT("Could not publish actual soundbank component receipt"); return false; }
    if(Host && !IFileManager::Get().FileExists(*GuestFile)) return false;
    if(Probe.Phase==3)
    {
        // Guest remains riding until the host has consumed its final acknowledgment.
        const FString Done=Folder/TEXT("server-soundbanks-complete.json");
        auto Complete=MakeShared<FJsonObject>(); Complete->SetBoolField(TEXT("passed"),true); Complete->SetNumberField(TEXT("phases"),3);
        if(Host && !Save(Done,Complete)) { Error=TEXT("Could not save soundbank completion"); return false; }
        if(!Host && !IFileManager::Get().FileExists(*Done)) return false;
        Local->GetSkate()->SetScriptedInput(nullptr);
        return true;
    }
    ++Probe.Phase;
    if(Host) Banks->Select(Probe.Phase==2?2:0);
    return false;
#else
    Error=TEXT("Soundbank network proof requires development automation support");
    return false;
#endif
}
