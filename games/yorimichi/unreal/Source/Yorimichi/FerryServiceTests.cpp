#include "FerryService.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/BoxComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"
#include "JapanSkateNetwork.h"
#include "AtelierData.h"
#include "Components/TextRenderComponent.h"
#include "Components/StaticMeshComponent.h"
#include "SkateComponent.h"

namespace
{
TSharedPtr<FJsonObject> FerryFixture()
{
    const TCHAR* Text = TEXT(R"({"line":{
      "cycle_s":8,"step_s":1,"clock_start_s":0,"ships":[{"name":"Ferry","offset_s":0}],
      "samples":[[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0],
                 [100,0,0,0,0,0,1,0],[200,0,0,0,0,0,0,0],[200,0,0,0,0,0,0,0],
                 [200,0,0,0,0,0,0,0],[100,0,0,0,0,0,1,0]],
      "phases":[[0,2,"berthed",0],[2,4,"cruise",-1],[4,6,"berthed",1],[6,8,"cruise",-1]],
      "brows":[[[0.1,0.5,1.5,1.9]],[[4.1,4.5,5.5,5.9]]]
    }})");
    TSharedPtr<FJsonObject> Root;
    FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root);
    return Root;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFerryProductionInitializationTest, "Yorimichi.Ferry.ProductionInitialization",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FFerryProductionInitializationTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Native game world"), World)) return false;
    const FString Path = AtelierDataPath(TEXT("ferry/service/service.json"));
    const auto Data = AtelierReadJson(Path);
    if (!TestTrue(TEXT("Current staged ferry data exists"), Data.IsValid())) return false;
    const bool bCreated = AFerryService::Find(World) == nullptr;
    AFerryService* Service = AFerryService::Spawn(World, Path);
    ON_SCOPE_EXIT { if (bCreated && Service) Service->Destroy(); };
    if (!TestNotNull(TEXT("Complete imported ferry service initializes"), Service)) return false;
    TArray<UTextRenderComponent*> Boards;
    Service->GetComponents(Boards);
    TestEqual(TEXT("Both terminal timetable texts exist"), Boards.Num(), 2);
    for (const auto& Value : Data->GetArrayField(TEXT("terminals")))
    {
        const auto Terminal = Value->AsObject();
        const FString Key = Terminal->GetStringField(TEXT("key"));
        for (const auto& Part : Terminal->GetArrayField(TEXT("parts")))
        {
            const FString Name = Key + TEXT("_") + Part->AsObject()->GetStringField(TEXT("name"));
            TestNotNull(TEXT("Every staged terminal mesh retains its stable component name"),
                FindObject<UStaticMeshComponent>(Service, *Name));
        }
        const FString TextName = Key + TEXT("_TimetableText");
        TestNotNull(TEXT("Timetable text has a distinct stable component name"),
            FindObject<UTextRenderComponent>(Service, *TextName));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFerryClockTest, "Yorimichi.Ferry.ClockAndBoarding",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FFerryClockTest::RunTest(const FString&)
{
    FFerryLine Line; FString Error;
    if (!TestTrue(TEXT("The single ferry parses"), Line.Parse(FerryFixture(), Error))) return false;
    TestEqual(TEXT("One shuttle"), Line.ShipNames.Num(), 1);
    TestTrue(TEXT("Hermite midpoint"), Line.State(0, 2.5).Location.Equals(FVector(50, 0, 0), .001));
    TestTrue(TEXT("The clock wraps"), Line.State(0, 10.5).Location.Equals(Line.State(0, 2.5).Location, .001));
    TestTrue(TEXT("Negative times wrap"), Line.State(0, -.5).Location.Equals(FVector(50, 0, 0), .001));
    TestEqual(TEXT("At Hidamari"), Line.State(0, 1.).Berth, 0);
    TestEqual(TEXT("At sea has no berth"), Line.State(0, 3.).Berth, INDEX_NONE);
    TestEqual(TEXT("At Brinecove"), Line.State(0, 5.).Berth, 1);
    TestTrue(TEXT("Brow down during boarding"), FMath::IsNearlyEqual(Line.BrowDown(0, 1.), 1.f));
    TestTrue(TEXT("Halfway through lowering"), FMath::IsNearlyEqual(Line.BrowDown(0, .3), .5f, .001f));
    TestTrue(TEXT("Halfway through raising"), FMath::IsNearlyEqual(Line.BrowDown(0, 1.7), .5f, .001f));
    TestEqual(TEXT("Sea gates cannot open"), Line.BrowDown(0, 3.), 0.f);
    TestEqual(TEXT("Other terminal remains closed"), Line.BrowDown(1, 1.), 0.f);
    TestTrue(TEXT("Next far-terminal arrival"), FMath::IsNearlyEqual(Line.NextAlongside(1, 1.), 4., .001));
    TestTrue(TEXT("A missed shuttle returns next cycle"), FMath::IsNearlyEqual(Line.NextAlongside(0, 1.), 8., .001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFerryInvalidLineTest, "Yorimichi.Ferry.InvalidLine",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FFerryInvalidLineTest::RunTest(const FString&)
{
    FFerryLine Line; FString Error;
    TestFalse(TEXT("Missing data refuses"), Line.Parse(nullptr, Error));
    auto Root = FerryFixture();
    auto Data = Root->GetObjectField(TEXT("line"));
    Data->SetNumberField(TEXT("cycle_s"), 9.);
    TestFalse(TEXT("Incomplete samples refuse"), Line.Parse(Root, Error));
    Root = FerryFixture(); Data = Root->GetObjectField(TEXT("line"));
    auto Ships = Data->GetArrayField(TEXT("ships"));
    const auto DuplicateShip = Ships[0]; Ships.Add(DuplicateShip);
    Data->SetArrayField(TEXT("ships"), Ships);
    TestFalse(TEXT("The draft's second ship refuses"), Line.Parse(Root, Error));
    Root = FerryFixture(); Data = Root->GetObjectField(TEXT("line"));
    auto Windows = Data->GetArrayField(TEXT("brows"));
    Windows[0] = MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
        MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
            MakeShared<FJsonValueNumber>(2.1), MakeShared<FJsonValueNumber>(2.5),
            MakeShared<FJsonValueNumber>(3.5), MakeShared<FJsonValueNumber>(3.9)})});
    Data->SetArrayField(TEXT("brows"), Windows);
    TestFalse(TEXT("A gangway opening at sea refuses"), Line.Parse(Root, Error));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTransportRiderTransitionTest, "Yorimichi.Ferry.SharedRiderTransitions",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FTransportRiderTransitionTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Native game world"), World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Character = World->SpawnActor<AWandererCharacter>(FVector(20000, 30000, 10000), FRotator::ZeroRotator, Spawn);
    if (!TestNotNull(TEXT("Deferred rider"), Character)) return false;
    FTransportRider Rider; Rider.Character = Character;
    ON_SCOPE_EXIT { FTransportRiders::SetAboard(Rider, false, false, Character->AboardVehicle); Character->Destroy(); };
    auto* Capsule = Character->GetCapsuleComponent();
    auto* Arm = Character->FindComponentByClass<USpringArmComponent>();
    if (!TestNotNull(TEXT("Rider camera arm"), Arm)) return false;
    Arm->bEnableCameraLag = true;
    const ECollisionResponse Original = Capsule->GetCollisionResponseToChannel(ECC_WorldStatic);
    TestTrue(TEXT("Train boards with its isolation"), FTransportRiders::SetAboard(Rider, true, true, ETransportVehicle::Train));
    TestEqual(TEXT("Train ignores static scenery"), Capsule->GetCollisionResponseToChannel(ECC_WorldStatic), ECR_Ignore);
    TestFalse(TEXT("Moving floor disables camera lag"), Arm->bEnableCameraLag);
    // Restoration uses the state captured at boarding, even if a caller passes the wrong isolation argument.
    TestTrue(TEXT("Leaving restores from captured state"), FTransportRiders::SetAboard(Rider, false, false, ETransportVehicle::Train));
    TestEqual(TEXT("Original capsule response restored"), Capsule->GetCollisionResponseToChannel(ECC_WorldStatic), Original);
    TestTrue(TEXT("Camera lag restored"), Arm->bEnableCameraLag);
    TestTrue(TEXT("Ferry boards without terrain isolation"), FTransportRiders::SetAboard(Rider, true, false, ETransportVehicle::Ferry));
    TestFalse(TEXT("Ferry keeps third person"), Character->IsTrainPassenger());
    TestEqual(TEXT("Ferry keeps ordinary world collision"), Capsule->GetCollisionResponseToChannel(ECC_WorldStatic), Original);
    TestTrue(TEXT("Leaving ferry"), FTransportRiders::SetAboard(Rider, false, true, ETransportVehicle::Ferry));
    TestTrue(TEXT("No stale vehicle identity"), Character->AboardVehicle == ETransportVehicle::None);
    TestFalse(TEXT("No stale aboard flag"), Character->bTrainAboard);
    TestTrue(TEXT("Train can board after ferry"), FTransportRiders::SetAboard(Rider, true, true, ETransportVehicle::Train));
    TestTrue(TEXT("Train passenger view remains available"), Character->IsTrainPassenger());

    // Station floors and cabins may have the same service owner; ownership is not a moving-base identity.
    auto* Service = World->SpawnActor<AActor>(Spawn);
    if (!TestNotNull(TEXT("Shared station and cabin owner"), Service)) return false;
    ON_SCOPE_EXIT { Character->SetBase(static_cast<UPrimitiveComponent*>(nullptr)); Service->Destroy(); };
    auto* Station = NewObject<UBoxComponent>(Service);
    auto* Body = NewObject<UBoxComponent>(Service);
    for (UBoxComponent* Part : {Station, Body})
    {
        Service->AddInstanceComponent(Part);
        Part->SetMobility(EComponentMobility::Movable);
        Part->RegisterComponent();
    }
    auto* Movement = Character->GetCharacterMovement();
    Movement->SetUpdatedComponent(Capsule);
    Movement->SetMovementMode(MOVE_Walking);
    Character->SetBase(Station);
    if (!TestTrue(TEXT("Rider initially bases on the service-owned station"), Character->GetMovementBase() == Station)) return false;
    const FTransform Previous = Body->GetComponentTransform();
    const FVector Before = Character->GetActorLocation();
    Body->SetWorldLocation(Previous.GetLocation() + FVector(25., 0., 0.));
    FTransportRiders::Carry(Rider, *Service, Body, Previous, true);
    TestTrue(TEXT("Station-based rider receives the cabin move"), Character->GetActorLocation().Equals(Before + FVector(25., 0., 0.), .001));
    TestTrue(TEXT("Station-based rider rebases to the exact cabin body"), Character->GetMovementBase() == Body);
    const FVector Based = Character->GetActorLocation();
    const FTransform BasedPrevious = Body->GetComponentTransform();
    Body->SetWorldLocation(BasedPrevious.GetLocation() + FVector(25., 0., 0.));
    FTransportRiders::Carry(Rider, *Service, Body, BasedPrevious, true);
    TestTrue(TEXT("The exact movement base is not manually applied twice"), Character->GetActorLocation().Equals(Based, .001));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFerryRemotePassengerTest, "Yorimichi.Ferry.RemotePassengerPresentation",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FFerryRemotePassengerTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Native game world"), World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = World->SpawnActor<AWandererCharacter>(FVector(20000, 30000, 10000), FRotator::ZeroRotator, Spawn);
    auto* Service = World->SpawnActor<AFerryService>(Spawn);
    ON_SCOPE_EXIT { if (Service) Service->Destroy(); if (Rider) Rider->Destroy(); };
    if (!TestNotNull(TEXT("Deferred remote rider"), Rider) || !TestNotNull(TEXT("Deferred ferry"), Service)) return false;
    auto* Skate = Rider->GetSkate();
    auto* Stream = Rider->FindComponentByClass<UJapanSkateNetwork>();
    if (!TestNotNull(TEXT("Remote board stream"), Stream)) return false;
    Stream->Rider = Rider;
    Skate->InitializeNetworkProxy(Rider);
    if (!TestTrue(TEXT("Imported board ready"), Skate->IsAvailable())) return false;
    FJapanBoardState Board;
    Board.Time = World->GetRealTimeSeconds(); Board.Sequence = 1;
    Board.Deck = FTransform(FRotator::ZeroRotator, Rider->GetActorLocation()); Board.Shown = 1.f;
    Stream->Boards = {Board};
    Stream->ShowBoard(World->GetRealTimeSeconds());
    TestEqual(TEXT("Retained frame initially shows board"), Skate->GetBoardShown(), 1.f);
    Service->Ships.AddDefaulted();
    Service->NetworkState.Serial = 1;
    FFerryPassenger& Passenger = Service->NetworkState.Passengers.AddDefaulted_GetRef();
    Passenger.Ship = 0;
    Service->OnRep_NetworkState();
    TestFalse(TEXT("Unresolved late-join reference waits"), Rider->IsOnTrain());
    Passenger.Rider = Rider;
    // No second OnRep and no owner hide packet: the regular resolution retry applies the original snapshot.
    Service->ApplyRemotePassengers();
    TestTrue(TEXT("Resolved peer membership marks ferry rider"), Rider->AboardVehicle == ETransportVehicle::Ferry);
    TestEqual(TEXT("Peer ship membership"), Service->ShipOf(Rider), 0);
    Stream->ShowBoard(World->GetRealTimeSeconds());
    TestEqual(TEXT("Snapshot masks the retained shown board"), Skate->GetBoardShown(), 0.f);
    TestFalse(TEXT("Ferry peer has no train passenger camera"), Rider->IsTrainPassenger());
    Service->NetworkState.Passengers.Reset(); ++Service->NetworkState.Serial;
    Service->OnRep_NetworkState();
    TestTrue(TEXT("Alighting clears peer identity"), Rider->AboardVehicle == ETransportVehicle::None);
    TestEqual(TEXT("No peer ship after alighting"), Service->ShipOf(Rider), INDEX_NONE);
    Stream->ShowBoard(World->GetRealTimeSeconds());
    TestEqual(TEXT("Ordinary retained presentation returns on shore"), Skate->GetBoardShown(), 1.f);
    return true;
}
#endif
