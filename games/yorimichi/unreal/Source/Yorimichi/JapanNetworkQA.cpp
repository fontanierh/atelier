#include "JapanSession.h"
#include "JapanNetwork.h"
#include "JapanGameplayQA.h"
#include "JapanWorld.h"
#include "WandererCharacter.h"
#include "AtelierData.h"
#include "SkateRails.h"
#include "Containers/Ticker.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "Engine/NetDriver.h"
#include "EngineUtils.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

// These diagnostics exercise the real admission and travel paths. They never expose a
// network control endpoint, and do not substitute for a cooked dedicated-server test.
void UJapanGameInstance::StartNetworkQA()
{
    if (!FParse::Value(FCommandLine::Get(), TEXT("networkqa="), NetworkQARole)) return;
    if ((NetworkQARole != TEXT("server") && NetworkQARole != TEXT("client")) ||
        !FParse::Value(FCommandLine::Get(), TEXT("networkqadir="), NetworkQADirectory))
    {
        UE_LOG(LogTemp, Error, TEXT("NETWORK QA requires role server|client and an output directory"));
        FPlatformMisc::RequestExitWithStatus(false, 1); return;
    }
    IFileManager::Get().MakeDirectory(*NetworkQADirectory, true);
    NetworkQAStarted = FPlatformTime::Seconds();
    NetworkQATicker = FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateUObject(this, &UJapanGameInstance::TickNetworkQA));
}

bool UJapanGameInstance::WriteNetworkQA(const TCHAR* Stage, const FString& Error)
{
    auto Report = MakeShared<FJsonObject>();
    Report->SetStringField(TEXT("role"), NetworkQARole);
    Report->SetStringField(TEXT("stage"), Stage);
    Report->SetStringField(TEXT("error"), Error);
    Report->SetNumberField(TEXT("elapsed"), FPlatformTime::Seconds() - NetworkQAStarted);
    Report->SetNumberField(TEXT("local_players"), GetLocalPlayers().Num());
    UWorld* World = GetWorld();
    Report->SetNumberField(TEXT("net_mode"), World ? int32(World->GetNetMode()) : -1);
    if (World)
    {
#if DO_ENABLE_NET_TEST
        if (const UNetDriver* Driver = World->GetNetDriver())
        {
            // Record the live driver, not the requested command line: ignored emulation
            // flags must not turn a lag/loss acceptance run into a silent zero-lag pass.
            const FPacketSimulationSettings& Settings = Driver->PacketSimulationSettings;
            auto Emulation = MakeShared<FJsonObject>();
            Emulation->SetNumberField(TEXT("lag_ms"), Settings.PktLag);
            Emulation->SetNumberField(TEXT("variance_ms"), Settings.PktLagVariance);
            Emulation->SetNumberField(TEXT("loss_percent"), Settings.PktLoss);
            Emulation->SetNumberField(TEXT("order"), Settings.PktOrder);
            Emulation->SetNumberField(TEXT("duplicate_percent"), Settings.PktDup);
            Emulation->SetNumberField(TEXT("lag_min_ms"), Settings.PktLagMin);
            Emulation->SetNumberField(TEXT("lag_max_ms"), Settings.PktLagMax);
            Emulation->SetNumberField(TEXT("incoming_lag_min_ms"), Settings.PktIncomingLagMin);
            Emulation->SetNumberField(TEXT("incoming_lag_max_ms"), Settings.PktIncomingLagMax);
            Emulation->SetNumberField(TEXT("incoming_loss_percent"), Settings.PktIncomingLoss);
            Emulation->SetNumberField(TEXT("jitter_ms"), Settings.PktJitter);
            Report->SetObjectField(TEXT("emulation"), Emulation);
        }
#endif
        if (UNetDriver* Driver = World->GetNetDriver())
        {
            Report->SetStringField(TEXT("driver_class"), Driver->GetClass()->GetPathName());
            Report->SetStringField(TEXT("bound_endpoint"), Driver->LowLevelGetNetworkNumber());
        }
        int32 Pawns = 0;
        for (TActorIterator<AWandererCharacter> It(World); It; ++It) if (!It->IsNpc()) ++Pawns;
        Report->SetNumberField(TEXT("player_pawns"), Pawns);
        if (const auto* State = World->GetGameState<AJapanGameState>())
        {
            Report->SetStringField(TEXT("session"), State->SessionId);
            Report->SetStringField(TEXT("identity"), State->ContentIdentity);
            Report->SetNumberField(TEXT("players"), State->PlayerArray.Num());
            TArray<TSharedPtr<FJsonValue>> People;
            for (const APlayerState* Person : State->PlayerArray)
                if (const auto* P = Cast<AJapanPlayerState>(Person))
                {
                    auto Record = MakeShared<FJsonObject>();
                    Record->SetStringField(TEXT("id"), P->SessionPlayerId);
                    Record->SetStringField(TEXT("rider"), P->RiderName);
                    Record->SetBoolField(TEXT("ready"), P->bWorldReady);
                    People.Add(MakeShared<FJsonValueObject>(Record));
                }
            Report->SetArrayField(TEXT("people"), People);
        }
        if (AJapanWorld* Landscape = JapanNetwork::FindWorld(World))
        {
            Report->SetBoolField(TEXT("world_ready"), Landscape->bGameplayReady);
            Report->SetNumberField(TEXT("instances"), Landscape->TotalInstances);
            const auto* Rails = World->GetSubsystem<USkateRailSubsystem>();
            TArray<FString> Records;
            if (Rails) for (const FSkateRail& Rail : Rails->Rails)
            {
                FString Record = Rail.Id.ToString() + FString::Printf(TEXT(":%d:%.3f:"), int32(Rail.Kind), Rail.Radius);
                Record += FString::Printf(TEXT("side=%.3f,%.3f,%.3f:"), Rail.Side.X, Rail.Side.Y, Rail.Side.Z);
                for (const FVector& Point : Rail.Points) Record += FString::Printf(TEXT("%.3f,%.3f,%.3f;"), Point.X, Point.Y, Point.Z);
                Records.Add(Record);
            }
            Records.Sort();
            FTCHARToUTF8 Canonical(*FString::Join(Records, TEXT("\n")));
            uint8 Hash[20]; FSHA1::HashBuffer(Canonical.Get(), Canonical.Length(), Hash);
            Report->SetNumberField(TEXT("rails"), Records.Num());
            Report->SetStringField(TEXT("rail_digest"), BytesToHex(Hash, 20).ToLower());
            // Sample both simple and complex gameplay collision at every staged map stop.
            // Exact imported bytes and these samples are complementary evidence, not a
            // claim that a handful of traces establishes Native render/Chaos triangle parity.
            FString Text;
            TSharedPtr<FJsonObject> Map;
            TArray<TSharedPtr<FJsonValue>> Probes;
            const TArray<TSharedPtr<FJsonValue>>* Zones = nullptr;
            if (FFileHelper::LoadFileToString(Text, *AtelierDataPath(TEXT("map/map.json"))) &&
                FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Map) && Map &&
                Map->TryGetArrayField(TEXT("zones"), Zones))
                for (const auto& Zone : *Zones)
                {
                    const auto Z = Zone->AsObject();
                    const FVector At = AJapanWorld::ToUE(Z->GetNumberField(TEXT("x")), Z->GetNumberField(TEXT("y")), Z->GetNumberField(TEXT("z")));
                    for (bool bComplex : {false, true})
                    {
                        FHitResult Hit;
                        FCollisionQueryParams Query(SCENE_QUERY_STAT(NetworkParity), bComplex);
                        // Use the gameplay blocking channel: some fixed park meshes have the engine's
                        // default WorldDynamic object type. Exclude every pawn so a falling player capsule
                        // cannot replace the ground beneath the spawn stop.
                        for (TActorIterator<APawn> Pawn(World); Pawn; ++Pawn) Query.AddIgnoredActor(*Pawn);
                        const bool bHit = World->LineTraceSingleByChannel(Hit, At + FVector(0,0,300), At - FVector(0,0,1800),
                            ECC_WorldStatic, Query);
                        auto Probe = MakeShared<FJsonObject>();
                        Probe->SetStringField(TEXT("key"), Z->GetStringField(TEXT("key")));
                        Probe->SetBoolField(TEXT("complex"), bComplex);
                        Probe->SetBoolField(TEXT("hit"), bHit);
                        Probe->SetStringField(TEXT("actor_class"), Hit.GetActor() ? Hit.GetActor()->GetClass()->GetName() : FString());
                        Probe->SetNumberField(TEXT("z"), bHit ? Hit.ImpactPoint.Z : 0.);
                        Probe->SetNumberField(TEXT("normal_z"), bHit ? Hit.ImpactNormal.Z : 0.);
                        Probes.Add(MakeShared<FJsonValueObject>(Probe));
                    }
                }
            Report->SetArrayField(TEXT("collision_probes"), Probes);
        }
    }
    FString JSON;
    FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&JSON));
    const FString Path = NetworkQADirectory / (NetworkQARole + TEXT("-") + Stage + TEXT(".json"));
    const FString Temporary = Path + TEXT(".tmp");
    const bool bSaved = FFileHelper::SaveStringToFile(JSON, *Temporary) && IFileManager::Get().Move(*Path, *Temporary, true, true);
    UE_LOG(LogTemp, Display, TEXT("NETWORK QA %s %s saved=%d %s"), *NetworkQARole, Stage, bSaved, *Error);
    return bSaved;
}

bool UJapanGameInstance::TickNetworkQA(float)
{
    const double Now = FPlatformTime::Seconds();
    auto Fail = [this](const FString& Error)
    { WriteNetworkQA(TEXT("failed"), Error); FPlatformMisc::RequestExitWithStatus(false, 1); return false; };
    if (Now - NetworkQAStarted > 240.) return Fail(TEXT("Native session lifecycle deadline expired"));
    UWorld* World = GetWorld();
    if (!World || !World->HasBegunPlay()) return true;
    const auto* State = World->GetGameState<AJapanGameState>();
    const bool Listen = FParse::Param(FCommandLine::Get(), TEXT("networklisten"));
    bool GameplayDone = true;
    if (FParse::Param(FCommandLine::Get(), TEXT("networkgameplay")) && World->GetNetMode() != NM_Standalone)
    {
        FString Error;
        GameplayDone = JapanGameplayQA::Tick(World, NetworkQARole == TEXT("server"), NetworkQADirectory, Error);
        if (!Error.IsEmpty()) return Fail(Error);
    }
    if (NetworkQARole == TEXT("server"))
    {
        if (Listen ? (World->GetNetMode() != NM_ListenServer || GetLocalPlayers().Num() != 1)
                   : (World->GetNetMode() != NM_DedicatedServer || GetLocalPlayers().Num() != 0))
            return Fail(TEXT("The native server mode or local-player count is incorrect"));
        if (!State) return true;
        if (!State->StartupError.IsEmpty()) return Fail(State->StartupError);
        if (!bNetworkQAWorld && State->bWorldReady)
        { bNetworkQAWorld = WriteNetworkQA(TEXT("world")); if (!bNetworkQAWorld) return Fail(TEXT("Could not save world receipt")); }
        for (const APlayerState* P : State->PlayerArray)
            if (const auto* Person = Cast<AJapanPlayerState>(P); Person && Person->bWorldReady && !bNetworkQASawPeer &&
                (!Listen || (State->PlayerArray.Num() == 2 && Person->GetOwningController() && !Person->GetOwningController()->IsLocalController())))
            { bNetworkQASawPeer = true; if (!WriteNetworkQA(TEXT("connected"))) return Fail(TEXT("Could not save admission receipt")); }
        if (bNetworkQASawPeer && State->PlayerArray.Num() == (Listen ? 1 : 0))
        {
            for (TActorIterator<AWandererCharacter> It(World); It; ++It)
                if (!It->IsNpc() && (!Listen || !It->IsLocallyControlled())) return true; // wait for pawn destruction, not just PlayerState removal
            if (!WriteNetworkQA(TEXT("complete"))) return Fail(TEXT("Could not save teardown receipt"));
            FPlatformMisc::RequestExit(false); return false;
        }
    }
    else
    {
        if (NetworkQALeaving > 0)
        {
            if (World->GetNetMode() == NM_Standalone && GetFirstLocalPlayerController() && GetFirstLocalPlayerController()->GetPawn())
            {
                if (!WriteNetworkQA(TEXT("complete"))) return Fail(TEXT("Could not save return-to-solo receipt"));
                FPlatformMisc::RequestExit(false); return false;
            }
            return true;
        }
        auto* PC = Cast<AJapanPlayerController>(GetFirstLocalPlayerController());
        auto* Person = PC ? PC->GetPlayerState<AJapanPlayerState>() : nullptr;
        if (World->GetNetMode() == NM_Client && PC && PC->GetPawn() && Person && Person->bWorldReady &&
            !Person->SessionPlayerId.IsEmpty() && State && !State->SessionId.IsEmpty())
        {
            if (Listen)
            {
                int32 Pawns = 0;
                for (TActorIterator<AWandererCharacter> It(World); It; ++It) if (!It->IsNpc()) ++Pawns;
                if (State->PlayerArray.Num() != 2 || Pawns != 2) return true;
                for (const APlayerState* P : State->PlayerArray)
                    if (const auto* Peer = Cast<AJapanPlayerState>(P); !Peer || !Peer->bWorldReady || Peer->SessionPlayerId.IsEmpty()) return true;
            }
            if (NetworkQAConnected == 0)
            {
                if (!WriteNetworkQA(TEXT("connected"))) return Fail(TEXT("Could not save connected receipt"));
                NetworkQAConnected = Now;
            }
            if (GameplayDone && Now - NetworkQAConnected > 5.) { NetworkQALeaving = Now; LeaveGame(); }
        }
        else if (NetworkQAConnected > 0) return Fail(TEXT("Connection lost before intentional leave"));
    }
    return true;
}
