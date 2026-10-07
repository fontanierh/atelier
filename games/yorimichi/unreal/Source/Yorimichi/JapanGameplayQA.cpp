#include "JapanGameplayQA.h"
#include "JapanCharacterMovement.h"
#include "JapanActivityState.h"
#include "JapanSession.h"
#include "Misc/CommandLine.h"
#include "JapanSkateNetwork.h"
#include "WandererCharacter.h"
#include "SkateComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "Serialization/JsonWriter.h"
#include "Serialization/JsonSerializer.h"

namespace
{
struct FScript
{
    TWeakObjectPtr<UWorld> World;
    int32 Step = 0;
    double Began = 0.;
    FVector Start = FVector::ZeroVector, Foot = FVector::ZeroVector;
    float WalkDistance = 0.f, JumpHeight = 0.f, SkateSeconds = 0.f;
    uint32 HighestEpoch = 1, AcceptedFrames = 0, MaximumSavedMoves = 0, PeerFrames = 0, ReceivedPeerFrames = 0;
    bool SawPlayer = false, SawSkate = false, Finished = false, JumpReleased = false;
};
FScript Scripts[2];

bool Save(const FString& Folder, bool Server, const FScript& State)
{
    auto Data = MakeShared<FJsonObject>();
    Data->SetBoolField(TEXT("passed"), true);
    Data->SetNumberField(TEXT("applied_peer_frames"), State.PeerFrames);
    Data->SetNumberField(TEXT("received_peer_frames"), State.ReceivedPeerFrames);
    Data->SetNumberField(TEXT("walk_cm"), State.WalkDistance);
    Data->SetNumberField(TEXT("jump_cm"), State.JumpHeight);
    Data->SetNumberField(TEXT("skate_seconds"), State.SkateSeconds);
    Data->SetNumberField(TEXT("activity_epoch"), State.HighestEpoch);
    Data->SetNumberField(TEXT("accepted_pose_frames"), State.AcceptedFrames);
    Data->SetNumberField(TEXT("maximum_saved_skate_moves"), State.MaximumSavedMoves);
    FString Text; FJsonSerializer::Serialize(Data, TJsonWriterFactory<>::Create(&Text));
    IFileManager::Get().MakeDirectory(*Folder, true);
    const FString File = Folder / (Server ? TEXT("server-gameplay.json") : TEXT("client-gameplay.json"));
    return FFileHelper::SaveStringToFile(Text, *(File + TEXT(".tmp"))) && IFileManager::Get().Move(*File, *(File + TEXT(".tmp")), true, true);
}
}

bool JapanGameplayQA::Tick(UWorld* World, bool Server, const FString& Folder, FString& Error)
{
    const bool Listen = FParse::Param(FCommandLine::Get(), TEXT("networklisten"));
    if (Listen)
    {
        const auto* State = World->GetGameState<AJapanGameState>();
        bool Ready = State && State->PlayerArray.Num() == 2;
        if (State) for (const auto* P : State->PlayerArray)
            Ready &= Cast<AJapanPlayerState>(P) && Cast<AJapanPlayerState>(P)->bWorldReady;
        // Once started the monitor must also observe teardown with just the host left.
        if (!Ready && !Scripts[1].SawPlayer && !Scripts[0].SawPlayer) return false;
        if (Server && World->GetNetMode() == NM_ListenServer)
            Tick(World, false, Folder / TEXT("host"), Error);
        if (!Error.IsEmpty()) return false;
    }
    FScript& Script = Scripts[Server ? 1 : 0];
    if (Script.World.Get() != World) { Script = FScript(); Script.World = World; }
    if (Script.Finished) return true;
    AWandererCharacter* Player = nullptr;
    for (TActorIterator<AWandererCharacter> It(World); It; ++It)
        if (!It->IsNpc() && (Server ? (!Listen || !It->IsLocallyControlled()) : It->IsLocallyControlled())) { Player = *It; break; }
    if (!Player || !Player->IsReady())
    {
        if (Server && Script.SawPlayer && !Player)
        {
            if (!Script.SawSkate || Script.HighestEpoch < 3 || Script.AcceptedFrames < 60 || Script.WalkDistance < 60.f)
                Error = TEXT("Host did not observe walking, sustained skate poses and the on-foot handoff");
            else if (!Save(Folder, true, Script)) Error = TEXT("Could not save host gameplay receipt");
            else Script.Finished = true;
        }
        return Script.Finished;
    }
    if (!Server && Listen)
        for (TActorIterator<AWandererCharacter> It(World); It; ++It)
            if (!It->IsNpc() && *It != Player)
                if (const auto* Stream = It->FindComponentByClass<UJapanSkateNetwork>())
                {
                    Script.PeerFrames = FMath::Max(Script.PeerFrames, Stream->GetAppliedFrameCount());
                    Script.ReceivedPeerFrames = FMath::Max(Script.ReceivedPeerFrames, Stream->GetReceivedFrameCount());
                }
    const double Now = World->GetTimeSeconds();
    auto* Movement = CastChecked<UJapanCharacterMovement>(Player->GetCharacterMovement());
    if (!Script.SawPlayer) { Script.SawPlayer = true; Script.Start = Player->GetActorLocation(); Script.Began = Now; }
    Script.HighestEpoch = FMath::Max(Script.HighestEpoch, Player->GetActivityEpoch());
    if (Server)
    {
        if (!Script.SawSkate && Player->GetNetworkActivity() == EJapanActivity::OnFoot)
            Script.WalkDistance = FMath::Max(Script.WalkDistance, float(FVector::Dist2D(Script.Start, Player->GetActorLocation())));
        Script.SawSkate |= Player->GetNetworkActivity() == EJapanActivity::Skate;
        if (const auto* Net = Player->FindComponentByClass<UJapanSkateNetwork>())
            Script.AcceptedFrames = Net->GetAcceptedFrameCount();
        return false;
    }
    const double Elapsed = Now - Script.Began;
    const auto Next = [&]() { ++Script.Step; Script.Began = Now; };
    switch (Script.Step)
    {
    case 0:
        Player->Live_Drive(FVector2D(0,1), 0);
        if (Elapsed > 1.5)
        {
            Player->Live_Drive(FVector2D::ZeroVector, 1);
            Script.WalkDistance = FVector::Dist2D(Script.Start, Player->GetActorLocation());
            if (Script.WalkDistance < 60.f) { Error = TEXT("Predicted walking did not move 60 cm"); return false; }
            Next();
        }
        break;
    case 1:
        if (Elapsed > .5) { Script.Foot = Player->GetActorLocation(); Player->Live_Press(TEXT("jump")); Next(); }
        break;
    case 2:
        Script.JumpHeight = FMath::Max(Script.JumpHeight, float(Player->GetActorLocation().Z - Script.Foot.Z));
        if (Elapsed > .2 && !Script.JumpReleased) { Player->Live_Press(TEXT("jump_release")); Script.JumpReleased = true; }
        if (Elapsed > 3.)
        {
            if (Script.JumpHeight < 25.f) { Error = TEXT("Predicted jump did not rise 25 cm"); return false; }
            Player->RequestNetworkSkate(); Next();
        }
        break;
    case 3:
        if (Player->GetNetworkActivity() == EJapanActivity::Skate && Player->GetSkate()->IsRiding()) Next();
        else if (Elapsed > 12.) Error = TEXT("Skate activity was not admitted within 12 seconds");
        break;
    case 4:
        if (Player->GetNetworkActivity() != EJapanActivity::Skate) { Error = TEXT("Skate epoch ended unexpectedly during sustained ride"); break; }
        Script.SkateSeconds = Elapsed;
        Script.MaximumSavedMoves = FMath::Max(Script.MaximumSavedMoves, uint32(Movement->GetPredictionData_Client_Character()->SavedMoves.Num()));
        if (Elapsed > 12. && Listen && Script.PeerFrames < 60) { Error = TEXT("The observer did not successfully apply 60 distinct peer pose frames"); break; }
        if (Elapsed > 5. && (!Listen || Script.PeerFrames >= 60))
        {
            if (Script.MaximumSavedMoves > 0) { Error = TEXT("CMC saved moves accumulated during trusted skating"); break; }
            Player->GetSkate()->Toggle(); Next();
        }
        break;
    case 5:
        if (Player->GetNetworkActivity() == EJapanActivity::OnFoot && !Player->IsNetworkActivityPending())
        {
            if (Script.HighestEpoch < 3) { Error = TEXT("Skate handoff did not advance the activity epoch"); break; }
            if (!Save(Folder, false, Script)) Error = TEXT("Could not save client gameplay receipt");
            else { Script.Finished = true; UE_LOG(LogTemp, Display, TEXT("NETWORK gameplay walking/jump/skate/handoff PASS")); }
        }
        else if (Elapsed > 12.) Error = TEXT("Skate dismount did not return to predicted walking");
        break;
    }
    return Script.Finished;
}
