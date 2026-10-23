#include "WandererCharacter.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "JapanSession.h"
#include "JapanSkateNetwork.h"
#include "SkateComponent.h"
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "Engine/Engine.h"
#include "Engine/World.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTrainVehicleAdmissionTest, "Yorimichi.Network.TrainVehicleAdmission",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FTrainVehicleAdmissionTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Native game world"), World)) return false;
    auto* Session = World->GetGameInstance<UJapanGameInstance>();
    if (!TestNotNull(TEXT("Owner refusal status"), Session)) return false;
    const FString PreviousStatus = Session->GetSessionStatus();
    auto* PreviousRules = World->GetGameState();
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient;
    Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = World->SpawnActor<AWandererCharacter>(FVector(20000,30000,10000), FRotator::ZeroRotator, Spawn);
    auto* Rules = World->SpawnActor<AJapanGameState>(Spawn);
    ON_SCOPE_EXIT
    {
        World->SetGameState(PreviousRules);
        Session->SetSessionStatus(PreviousStatus);
        if (Rider) Rider->Destroy();
        if (Rules) Rules->Destroy();
    };
    if (!TestNotNull(TEXT("Deferred rider"), Rider) || !TestNotNull(TEXT("Rules"), Rules)) return false;
    World->SetGameState(Rules);
    Rules->bPredictedVehicles = Rules->bTrustedSkating = true;
    Rider->bReady = true;
    Rider->NetworkActivity.Kind = EJapanActivity::OnFoot;
    Rider->NetworkActivity.Epoch = 31;
    UJapanSkateNetwork* Stream = Rider->NetworkSkate;
    if (!TestNotNull(TEXT("Owner board transport"), Stream)) return false;
    Stream->Rider = Rider; // Deferred fixture: exercise the real RPC without running art-dependent BeginPlay.
    FJapanBoardState Board;
    const TCHAR* Refusal = TEXT("Not aboard the train");
    auto CheckRefused = [&](const TCHAR* Action, TFunction<void()> Request)
    {
        Session->SetSessionStatus(TEXT("sentinel"));
        Request();
        TestEqual(FString(Action) + TEXT(" explains the train refusal"), Session->GetSessionStatus(), FString(Refusal));
        TestEqual(FString(Action) + TEXT(" preserves the activity epoch"), Rider->GetActivityEpoch(), 31u);
        TestTrue(FString(Action) + TEXT(" preserves the foot activity"), Rider->GetNetworkActivity() == EJapanActivity::OnFoot);
    };
    for (const FIntPoint Flags : {FIntPoint(1,0), FIntPoint(0,1), FIntPoint(1,1)})
    {
        Rider->bTrainAboard = Flags.X != 0;
        Rider->bTrainDriving = Flags.Y != 0;
        TestFalse(TEXT("Carried boards are unavailable on the train"), Rider->CanCarrySkateBoard());
        const uint32 Before = Stream->Board.Sequence;
        ++Board.Sequence; Board.Shown = 1.f;
        Stream->ServerBoard_Implementation(Board);
        TestEqual(TEXT("Visible board transport is refused aboard/boarding"), Stream->Board.Sequence, Before);
        ++Board.Sequence; Board.Shown = 0.f;
        Stream->ServerBoard_Implementation(Board);
        TestEqual(TEXT("Hide transport still advances aboard/boarding"), Stream->Board.Sequence, Board.Sequence);
        TestEqual(TEXT("Accepted hide remains hidden"), Stream->Board.Shown, 0.f);
        CheckRefused(TEXT("Local skateboard"), [&]{ Rider->ToggleSkateboard(FInputActionValue()); });
        CheckRefused(TEXT("Local carried board"), [&]{ Rider->SkateboardHand(FInputActionValue()); });
        CheckRefused(TEXT("Local bike"), [&]{ Rider->ToggleBike(FInputActionValue()); });
        CheckRefused(TEXT("Local horse"), [&]{ Rider->ToggleHorse(FInputActionValue()); });
        CheckRefused(TEXT("Local sailboat"), [&]{ Rider->ToggleSailboat(FInputActionValue()); });
        // Call the actual authority handlers; client input restrictions alone are insufficient.
        CheckRefused(TEXT("Host skateboard"), [&]{ Rider->ServerRequestSkate_Implementation(31); });
        CheckRefused(TEXT("Host bike"), [&]{ Rider->ServerRequestBike_Implementation(31); });
        CheckRefused(TEXT("Host horse"), [&]{ Rider->ServerRequestHorse_Implementation(31); });
        CheckRefused(TEXT("Host sailboat"), [&]{ Rider->ServerRequestSail_Implementation(31); });
    }
    Session->SetSessionStatus(TEXT("sentinel"));
    Rider->ServerRequestBike_Implementation(30);
    TestTrue(TEXT("A stale request retains the existing epoch refusal"), Session->GetSessionStatus().Contains(TEXT("activity changed")));
    TestEqual(TEXT("Stale requests do not alter the epoch"), Rider->GetActivityEpoch(), 31u);
    // The train check must not capture exits; other existing exit admission still applies.
    for (EJapanActivity Kind : {EJapanActivity::Bike, EJapanActivity::Horse, EJapanActivity::Sailboat})
    {
        Rider->NetworkActivity.Kind = Kind;
        Session->SetSessionStatus(TEXT("sentinel"));
        if (Kind == EJapanActivity::Bike) Rider->ServerRequestBike_Implementation(31);
        else if (Kind == EJapanActivity::Horse) Rider->ServerRequestHorse_Implementation(31);
        else Rider->ServerRequestSail_Implementation(31);
        TestTrue(TEXT("A stow request bypasses the train deployment refusal"), Session->GetSessionStatus() != Refusal);
    }
    Rider->bTrainAboard = Rider->bTrainDriving = false;
    TestFalse(TEXT("The train gate releases when the rider leaves"), Rider->RefuseVehicleOnTrain());
    ++Board.Sequence; Board.Shown = 1.f;
    Stream->ServerBoard_Implementation(Board);
    TestEqual(TEXT("Visible board transport resumes after leaving"), Stream->Board.Shown, 1.f);
    --Board.Sequence; Board.Shown = 0.f;
    Stream->ServerBoard_Implementation(Board);
    TestEqual(TEXT("Stale transport still cannot replace the accepted board"), Stream->Board.Shown, 1.f);
    auto* Skate = Rider->GetSkate();
    Skate->InitializeNetworkProxy(Rider);
    if (!TestTrue(TEXT("Normal imported board meshes are ready for visibility checks"), Skate->IsAvailable())) return false;
    // Already admitted before boarding. No new owner packet is delivered below.
    Stream->Boards = {Stream->Board};
    Stream->ShowBoard(World->GetRealTimeSeconds());
    TestEqual(TEXT("The retained board is initially visible"), Skate->GetBoardShown(), 1.f);
    for (const FIntPoint Flags : {FIntPoint(1,0), FIntPoint(0,1), FIntPoint(1,1)})
    {
        Rider->bTrainAboard = Flags.X != 0;
        Rider->bTrainDriving = Flags.Y != 0;
        Skate->ApplyNetworkBoard(Board.Deck, 1.f);
        Stream->ShowBoard(World->GetRealTimeSeconds());
        TestEqual(TEXT("Boarding masks retained visible presentation without a hide packet"), Skate->GetBoardShown(), 0.f);
    }
    Rider->bTrainAboard = Rider->bTrainDriving = false;
    Stream->ShowBoard(World->GetRealTimeSeconds());
    TestEqual(TEXT("Leaving restores the ordinary retained-board presentation"), Skate->GetBoardShown(), 1.f);
    Stream->Boards.Reset(); Rider->bTrainAboard = true;
    Stream->ShowBoard(World->GetRealTimeSeconds());
    TestEqual(TEXT("An orphaned visible presentation is hidden even without buffered packets"), Skate->GetBoardShown(), 0.f);
    return true;
}
#endif
