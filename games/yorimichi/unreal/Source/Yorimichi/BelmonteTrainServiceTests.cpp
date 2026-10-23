#include "BelmonteTrainService.h"
#include "BelmonteTrainRules.h"
#include "BelmonteTrainRecovery.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Components/BoxComponent.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBelmonteTrainLineTest, "Yorimichi.Belmonte.TrainLine",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// A 1 km straight line east with a 200 m loop 4 m to the north (Unreal -y), and two trains: A runs up 0 -> 1000 m in
// 100 s, B down 1000 -> 0 m over the same 100 s on the loop track; the cycle is 200 s.
static const TCHAR* LineJson = TEXT(R"({
 "line": {"main": [[0,0,0,0],[500,50000,0,1000],[1000,100000,0,0]],
          "loop": {"start": 400, "end": 600, "points": [[400,40000,0,800],[410,41000,-400,820],[590,59000,-400,820],[600,60000,0,800]]},
          "viewpoints": [{"s": 250}, {"s": 700, "start": 650, "end": 750, "class": "viaduct"},
                         {"s": 900, "start": 850, "end": 950, "class": "embankment"}]},
 "service": {"cycle_s": 200, "clock_start_s": 0, "trains": [
   {"name": "A", "t0": 0, "dt": 50, "s": [0,500,1000,1000], "loop_track": []},
   {"name": "B", "t0": 0, "dt": 50, "s": [1000,500,0,0], "loop_track": [[0,100]]}]}
})");

bool FBelmonteTrainLineTest::RunTest(const FString&)
{
    TSharedPtr<FJsonObject> Root;
    TestTrue(TEXT("Fixture parses"), FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(LineJson), Root));
    FBelmonteTrainLine Line; FString Error;
    TestTrue(TEXT("Line parses: ") + Error, Line.Parse(Root, Error));
    TestEqual(TEXT("Two trains"), Line.Trains.Num(), 2);
    TestTrue(TEXT("Chainage interpolates"), FMath::IsNearlyEqual(Line.Chainage(0, 25.), 250., 1e-6));
    TestTrue(TEXT("The cycle repeats"), FMath::IsNearlyEqual(Line.Chainage(0, 225.), 250., 1e-6));
    TestTrue(TEXT("Times before t0 wrap"), FMath::IsNearlyEqual(Line.Chainage(0, -175.), 250., 1e-6));
    TestTrue(TEXT("Up speed is positive, 10 m/s"), FMath::IsNearlyEqual(Line.Speed(0, 30.), 10., 1e-6));
    TestTrue(TEXT("Down speed is negative"), Line.Speed(1, 30.) < 0.);
    TestTrue(TEXT("Main line height interpolates"), FMath::IsNearlyEqual(Line.Point(250., false).Z, 500., 1e-6));
    TestTrue(TEXT("B is on the loop track"), Line.OnLoopTrack(1, 50.) && !Line.OnLoopTrack(0, 50.));
    TestTrue(TEXT("The loop track is offset from the main line"), FMath::IsNearlyEqual(Line.Point(500., true).Y, -400., 1e-6));
    TestTrue(TEXT("Outside the loop both tracks agree"), Line.Point(300., true).Equals(Line.Point(300., false)));
    double Where = 0.;
    const double Crossing = Line.NextCrossing(1., &Where);
    TestTrue(TEXT("The trains cross at mid-line, in the loop"), FMath::IsNearlyEqual(Crossing, 50., .51) && Where >= 400. && Where <= 600.);
    int32 Which = -1;
    TestTrue(TEXT("Next passing of 250 m"), FMath::IsNearlyEqual(Line.NextPassing(1., 250., &Which), 25., .51) && Which == 0);

    // A 24 m vehicle with bogies at +-8.5 m on the straight: its origin is its centre, on the rail, heading east (+x).
    const FTransform Flat = Line.Place(100., -8.5, 8.5, false);
    TestTrue(TEXT("Vehicle origin at its chainage"), Flat.GetLocation().Equals(FVector(10000., 0., 200.), .01));
    TestTrue(TEXT("Vehicle heads up the line"), FMath::IsNearlyEqual(Flat.Rotator().Yaw, 0., 1e-3));
    TestTrue(TEXT("Vehicle pitches up the grade"), Flat.Rotator().Pitch > 1.);
    // Asymmetric bogies (the brake van): the origin still sits at the vehicle's own chainage.
    const FTransform Van = Line.Place(100., -3.3, 3.55, false);
    TestTrue(TEXT("Asymmetric bogies keep the origin"), FMath::IsNearlyEqual(Van.GetLocation().X, 10000., .5));

    // Where nobody is set down beside a coach: the viaduct (from the viewpoints' class) and the track's tunnels.
    TestEqual(TEXT("Every viewpoint is still a viewpoint"), Line.Viewpoints.Num(), 3);
    TestEqual(TEXT("Only the viaduct stretch is enclosed"), Line.Enclosed.Num(), 1);
    TestTrue(TEXT("On the viaduct"), Line.IsEnclosed(700., 700.));
    TestTrue(TEXT("A coach overlapping the viaduct's end"), Line.IsEnclosed(630., 660.));
    TestFalse(TEXT("An embankment is open"), Line.IsEnclosed(900., 900.));
    TSharedPtr<FJsonObject> Track;
    TestTrue(TEXT("Track fixture parses"), FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(
        TEXT(R"({"tunnels": [{"name": "T1", "start": 300, "end": 200}, {"name": "broken"}]})")), Track));
    TestEqual(TEXT("One well-formed tunnel"), Line.AddTunnels(Track), 1);
    TestTrue(TEXT("In the tunnel (either order of its ends)"), Line.IsEnclosed(250., 250.));
    TestTrue(TEXT("Reversed range"), Line.IsEnclosed(320., 290.));
    TestFalse(TEXT("Between the tunnel and the viaduct"), Line.IsEnclosed(400., 600.));
    TestEqual(TEXT("No track data, no tunnels"), Line.AddTunnels(nullptr), 0);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBelmonteTrainRulesTest, "Yorimichi.Belmonte.TrainRules",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FBelmonteTrainRulesTest::RunTest(const FString&)
{
    using namespace BelmonteTrainRules;
    // On foot only: no vehicle comes out aboard, seated or stepping through a door; off the train nothing changes.
    TestTrue(TEXT("Off the train a vehicle may come out"), MayTakeOutVehicle(false, false));
    TestFalse(TEXT("Aboard, no vehicle"), MayTakeOutVehicle(true, false));
    TestFalse(TEXT("Seated or on the steps, no vehicle"), MayTakeOutVehicle(false, true));
    TestFalse(TEXT("Seated aboard, no vehicle"), MayTakeOutVehicle(true, true));
    TestTrue(TEXT("The refusal reads in English"), FString(Refusal()) == TEXT("Not aboard the train"));
    // Riding inside a running coach without the boarding walk: put back outside; passengers and door steps stay.
    TestTrue(TEXT("Riding inside without boarding is ejected"), MustEject(true, false, false, false, true, true));
    TestFalse(TEXT("A boarded passenger stays"), MustEject(true, true, false, false, true, true));
    TestFalse(TEXT("Stepping through the door stays"), MustEject(true, false, true, false, true, true));
    TestFalse(TEXT("Seated stays"), MustEject(true, false, false, true, true, true));
    TestFalse(TEXT("Outside the coach nothing happens"), MustEject(false, false, false, false, true, true));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBelmonteTrainAdmissionTest, "Yorimichi.Belmonte.TrainAdmission",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

namespace
{
// A rider entry as the roster helpers see it: a `Character` with Get() (the service uses TWeakObjectPtr).
struct FFakeRef { int32* P = nullptr; int32* Get() const { return P; } FFakeRef& operator=(int32* In) { P = In; return *this; } };
struct FFakeRider { FFakeRef Character; BelmonteTrainRules::FAdmission Admission; int32 Seat = INDEX_NONE; };
}

bool FBelmonteTrainAdmissionTest::RunTest(const FString&)
{
    using namespace BelmonteTrainRules;
    constexpr float Frame = 1.f / 60.f;
    auto Run = [Frame](FAdmission& A, bool bOnTrain, bool bHeld, float Seconds, bool bOwner)
    {
        bool bLapsed = false;
        for (float T = 0.f; T < Seconds; T += Frame) bLapsed |= A.Update(bOnTrain, bHeld, Frame, bOwner);
        return bLapsed;
    };
    FAdmission A;
    // The door walk: walking up (held, collision off, outside every room) neither grants nor loses anything...
    TestFalse(TEXT("No ticket on the platform"), Run(A, false, true, 2.f, true) || A.bAdmitted);
    // ...and its end admits (FinishBoarding up).
    A.Admit();
    TestTrue(TEXT("The walk up admits"), A.bAdmitted && A.Carries());
    // Gangway grace: a moment outside the rooms (a jump, a gangway) keeps the ticket and the carry.
    TestFalse(TEXT("A second off the rooms keeps the ticket"), Run(A, false, false, 1.f, true));
    TestTrue(TEXT("Still carried within the grace"), A.bAdmitted && A.Carries());
    TestFalse(TEXT("Back inside resets the grace"), Run(A, true, false, .1f, true) || A.Outside > 0.f);
    TestFalse(TEXT("Crossing a long gangway on its floor is the train"), Run(A, true, false, 30.f, true) || !A.bAdmitted);
    // Seats: held for as long as they sit, then standing up (inside) keeps it; cancelling a seat by Interact is standing up.
    TestFalse(TEXT("Seated for a whole run keeps the ticket"), Run(A, false, true, 600.f, true) || !A.bAdmitted);
    TestFalse(TEXT("Standing up inside keeps it"), Run(A, true, false, 1.f, true) || !A.bAdmitted);
    // The train's travel: on the train the whole way, whatever the time.
    TestFalse(TEXT("Riding the whole line keeps it"), Run(A, true, false, 900.f, true) || !A.bAdmitted);
    // A client never ends the host's ticket by itself, though it stops carrying after the grace.
    FAdmission Client = A;
    TestFalse(TEXT("A client does not revoke"), Run(Client, false, false, 5.f, false) || !Client.bAdmitted);
    TestFalse(TEXT("A client stops carrying after the grace"), Client.Carries());
    // Exit by walking out of an open door: the ticket ends after the grace, on the host.
    FAdmission Walked = A;
    TestTrue(TEXT("Off the train past the grace ends it"), Run(Walked, false, false, FAdmission::Grace + .1f, true));
    TestFalse(TEXT("Ended"), Walked.bAdmitted || Walked.Carries());
    // Exit by the walk down, a teleport, a respawn, the map's travel or an ejection: Revoke.
    FAdmission Down = A; Down.Revoke();
    TestFalse(TEXT("The walk down or a cancel ends it"), Down.bAdmitted || Down.Carries());
    TestFalse(TEXT("A revoked ticket does not come back on the train"), Run(Down, true, false, 5.f, true) || Down.bAdmitted);

    // Pawn replacement: the entry (ticket, seat) moves to the new pawn; the new pawn's own fresh entry is dropped first.
    int32 Old = 0, New = 1, Other = 2;
    TArray<FFakeRider> Riders;
    Riders.AddDefaulted_GetRef().Character = &New;      // made the frame the new pawn spawned, no ticket
    FFakeRider& Mine = Riders.AddDefaulted_GetRef(); Mine.Character = &Old; Mine.Admission.Admit(); Mine.Seat = 4;
    Riders.AddDefaulted_GetRef().Character = &Other;
    int32 Released = 0;
    const int32 Moved = MoveRider(Riders, &Old, &New, [&Released](FFakeRider&) { ++Released; });
    TestTrue(TEXT("The entry moved"), Riders.IsValidIndex(Moved) && Riders[Moved].Character.Get() == &New);
    TestEqual(TEXT("The duplicate is gone"), Riders.FilterByPredicate([&](const FFakeRider& R) { return R.Character.Get() == &New; }).Num(), 1);
    TestEqual(TEXT("The duplicate was released"), Released, 1);
    TestTrue(TEXT("The ticket and seat follow the player"), Riders.IsValidIndex(Moved) && Riders[Moved].Admission.bAdmitted && Riders[Moved].Seat == 4);
    TestFalse(TEXT("Nothing is left for the old pawn"), Riders.ContainsByPredicate([&](const FFakeRider& R) { return R.Character.Get() == &Old; }));
    TestEqual(TEXT("No entry, nothing to move"), MoveRider(Riders, &Old, &New, [](FFakeRider&) {}), int32(INDEX_NONE));
    TestEqual(TEXT("Not onto nobody"), MoveRider(Riders, &New, static_cast<int32*>(nullptr), [](FFakeRider&) {}), int32(INDEX_NONE));
    // Disconnect: the player's entry is released (seat, door) and dropped, ticket and all; others stay.
    for (FFakeRider& R : Riders) if (R.Character.Get() == &New) R.Character = nullptr;
    TArray<int32> Seats;
    TestEqual(TEXT("The disconnected player's entry goes"), DropVanished(Riders, [&Seats](FFakeRider& R) { Seats.Add(R.Seat); }), 1);
    TestTrue(TEXT("Their seat was released"), Seats.Num() == 1 && Seats[0] == 4);
    TestTrue(TEXT("The others stay"), Riders.Num() == 1 && Riders[0].Character.Get() == &Other);
    TestFalse(TEXT("A returning player has no ticket"), Riders.ContainsByPredicate([](const FFakeRider& R) { return R.Admission.bAdmitted; }));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBelmonteTrainEjectRulesTest, "Yorimichi.Belmonte.TrainEjectRules",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FBelmonteTrainEjectRulesTest::RunTest(const FString&)
{
    using namespace BelmonteTrainRules;
    // A coach at 15 m/s sweeping past a bystander standing still on the platform: they cross its frame at its speed.
    const double Coach = 1500.;
    TestFalse(TEXT("A bystander the coach sweeps through is not riding it"), MovesWithCoach(1500., Coach));
    TestFalse(TEXT("Nor one walking along the platform"), MovesWithCoach(1500. - 150., Coach));
    TestTrue(TEXT("Someone carried by the coach (jumping, skating inside) rides it"), MovesWithCoach(300., Coach));
    TestFalse(TEXT("A standing coach tells nothing"), MovesWithCoach(0., 0.));
    TestFalse(TEXT("Platform bystander inside a passing coach's room: not ejected"),
        MustEject(true, false, false, false, MovesWithCoach(1500., Coach), true));
    TestTrue(TEXT("A cyclist on the floor of a departing coach is ejected"), MustEject(true, false, false, false, true, true));
    TestFalse(TEXT("Not while the train stands at the platform with its doors free"), MustEject(true, false, false, false, true, false));

    // The recovery order: the platform first at a station, beside the coach in the open, never beside it when enclosed.
    const auto Station = RecoveryOrder(true, false);
    TestTrue(TEXT("At a platform: platform, then door side"), Station.Num() == 5 && Station[0] == ERecovery::Platform && Station[1] == ERecovery::DoorSide);
    const auto Open = RecoveryOrder(false, false);
    TestTrue(TEXT("In the open: door side first, then recorded points, then the next station"),
        Open.Num() == 4 && Open[0] == ERecovery::DoorSide && Open[1] == ERecovery::LastSafe && Open[2] == ERecovery::TrainLastSafe && Open[3] == ERecovery::NextStation);
    for (const bool bAtPlatform : {false, true})
    {
        const auto Enclosed = RecoveryOrder(bAtPlatform, true);
        TestFalse(TEXT("Tunnel or viaduct: never beside the coach"), Enclosed.Contains(ERecovery::DoorSide) || Enclosed.Contains(ERecovery::Platform));
        TestTrue(TEXT("Tunnel or viaduct: last safe, recorded door side, next station"),
            Enclosed.Num() == 3 && Enclosed[0] == ERecovery::LastSafe && Enclosed[1] == ERecovery::TrainLastSafe && Enclosed[2] == ERecovery::NextStation);
    }

    // Acceptance: walkable ground that is not the train, near the expected height, with standing room.
    FStandProbe Good;
    Good.bGround = true; Good.GroundNormalZ = 1.; Good.GroundOff = -40.; Good.bClear = true; Good.bFloor = true; Good.FloorNormalZ = 1.;
    TestTrue(TEXT("Flat clear ground is accepted"), AcceptStand(Good, .71, 300.));
    auto Without = [&](TFunctionRef<void(FStandProbe&)> Change) { FStandProbe P = Good; Change(P); return AcceptStand(P, .71, 300.); };
    TestFalse(TEXT("No ground (over a viaduct's drop)"), Without([](FStandProbe& P) { P.bGround = false; }));
    TestFalse(TEXT("The train's own roof or floor"), Without([](FStandProbe& P) { P.bGroundIsTrain = true; }));
    TestFalse(TEXT("A steep bank"), Without([](FStandProbe& P) { P.GroundNormalZ = .5; }));
    TestFalse(TEXT("Ground far below the expected height"), Without([](FStandProbe& P) { P.GroundOff = -900.; }));
    TestFalse(TEXT("No standing room (a tunnel's wall, a parapet)"), Without([](FStandProbe& P) { P.bClear = false; }));
    TestFalse(TEXT("The capsule finds no floor"), Without([](FStandProbe& P) { P.bFloor = false; }));
    TestFalse(TEXT("The capsule lands on the train"), Without([](FStandProbe& P) { P.bFloorIsTrain = true; }));
    TestFalse(TEXT("The capsule lands on an edge too steep"), Without([](FStandProbe& P) { P.FloorNormalZ = .3; }));

    // The next station: ahead in the train's direction; standing, the nearest; past the last, the nearest.
    const TArray<double> Stops = {75.5, 7320.};
    TestEqual(TEXT("Up the line: Belmonte"), NextStop(Stops, 3000., 12.), 1);
    TestEqual(TEXT("Down the line: Hidamari"), NextStop(Stops, 6000., -12.), 0);
    TestEqual(TEXT("Standing: the nearest"), NextStop(Stops, 6000., 0.), 1);
    TestEqual(TEXT("Past the last stop: the nearest"), NextStop(Stops, 7380., 5.), 1);
    TestEqual(TEXT("No stations"), NextStop(TArray<double>(), 10., 1.), int32(INDEX_NONE));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBelmonteTrainRecoveryProbeTest, "Yorimichi.Belmonte.TrainRecoveryProbe",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FBelmonteTrainRecoveryProbeTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("The recovery probe test has a game world"), World)) return false;
    FActorSpawnParameters Spawn; Spawn.ObjectFlags |= RF_Transient;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    // Far from anything in the map: a 10 m slab whose top is at Origin.z.
    const FVector Origin(0., 0., 100000.);
    TArray<AActor*> Made;
    ON_SCOPE_EXIT { for (AActor* A : Made) if (A) A->Destroy(); };
    // Plain collision boxes (a spawned static mesh actor's static component refuses a runtime mesh).
    auto Box = [&](const FVector& Centre, const FVector& Size, const FRotator& Rotation, ECollisionChannel Type) -> UBoxComponent*
    {
        AActor* A = World->SpawnActor<AActor>(Spawn);
        if (!A) return nullptr;
        Made.Add(A);
        auto* B = NewObject<UBoxComponent>(A);
        A->SetRootComponent(B); A->AddInstanceComponent(B);
        B->SetBoxExtent(Size / 2., false);
        B->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        B->SetCollisionObjectType(Type);
        B->SetCollisionResponseToAllChannels(ECR_Block);
        B->RegisterComponent();
        A->SetActorLocationAndRotation(Centre, Rotation);
        return B;
    };
    UBoxComponent* Slab = Box(Origin - FVector(0, 0, 10), FVector(1000, 1000, 20), FRotator::ZeroRotator, ECC_WorldStatic);
    UBoxComponent* Coach = Box(Origin + FVector(3000, 0, 140), FVector(2000, 300, 20), FRotator::ZeroRotator, ECC_Vehicle);
    UBoxComponent* Bank = Box(Origin + FVector(0, 3000, 0), FVector(1000, 1000, 20), FRotator(0, 0, 60), ECC_WorldStatic);
    if (!TestTrue(TEXT("Test geometry spawned"), Slab && Coach && Bank)) return false;
    BelmonteTrainRecovery::FStander Stander;
    auto IsTrain = [Coach](const UPrimitiveComponent* Part) { return Part == Coach; };
    FVector Feet;
    const auto Flat = BelmonteTrainRecovery::Probe(World, Origin + FVector(0, 0, 60), Origin.Z + 60., 200., Stander, IsTrain, Feet);
    AddInfo(FString::Printf(TEXT("flat probe ground=%d train=%d normal=%.2f off=%.1f clear=%d floor=%d floor_normal=%.2f feet_z=%.1f"),
        Flat.bGround, Flat.bGroundIsTrain, Flat.GroundNormalZ, Flat.GroundOff, Flat.bClear, Flat.bFloor, Flat.FloorNormalZ, Feet.Z - Origin.Z));
    TestTrue(TEXT("Flat clear slab: accepted"), BelmonteTrainRules::AcceptStand(Flat, Stander.WalkableZ, 200.));
    TestTrue(TEXT("Feet on the slab"), FMath::IsNearlyEqual(Feet.Z, Origin.Z, 3.));
    TestFalse(TEXT("A height off the slab beyond the allowance"),
        BelmonteTrainRecovery::SafeStand(World, Origin, Origin.Z + 500., 200., Stander, IsTrain, Feet));
    TestFalse(TEXT("Over nothing (a viaduct's drop)"),
        BelmonteTrainRecovery::SafeStand(World, Origin + FVector(0, -3000, 0), Origin.Z, 300., Stander, IsTrain, Feet));
    TestFalse(TEXT("On the train itself"),
        BelmonteTrainRecovery::SafeStand(World, Origin + FVector(3000, 0, 150), Origin.Z + 150., 100., Stander, IsTrain, Feet));
    const auto Steep = BelmonteTrainRecovery::Probe(World, Origin + FVector(0, 3000, 0), Origin.Z, 400., Stander, IsTrain, Feet);
    TestTrue(TEXT("A 60 degree bank is found but refused"), Steep.bGround && !BelmonteTrainRules::AcceptStand(Steep, Stander.WalkableZ, 400.));
    // A low roof (a tunnel's bore, under the coach): the height trace finds the slab, the capsule has no room.
    UBoxComponent* Roof = Box(Origin + FVector(-300, -300, 130), FVector(200, 200, 20), FRotator::ZeroRotator, ECC_WorldStatic);
    const auto Low = BelmonteTrainRecovery::Probe(World, Origin + FVector(-300, -300, 20), Origin.Z + 20., 60., Stander, IsTrain, Feet);
    TestTrue(TEXT("Under a low roof the ground trace alone would pass"), Roof && Low.bGround && FMath::Abs(Low.GroundOff) <= 60. && Low.GroundNormalZ > .99);
    TestFalse(TEXT("but the standing capsule refuses it"), Low.bClear || BelmonteTrainRules::AcceptStand(Low, Stander.WalkableZ, 60.));
    // A wall right beside the point (a parapet, a tunnel's side).
    UBoxComponent* Wall = Box(Origin + FVector(300, 300, 100), FVector(40, 400, 200), FRotator::ZeroRotator, ECC_WorldStatic);
    TestTrue(TEXT("A wall within the capsule's radius refuses the point"), Wall &&
        !BelmonteTrainRecovery::SafeStand(World, Origin + FVector(300 - 40, 300, 60), Origin.Z + 60., 100., Stander, IsTrain, Feet));
    TestTrue(TEXT("A step further from the wall is accepted"),
        BelmonteTrainRecovery::SafeStand(World, Origin + FVector(300 - 80, 300, 60), Origin.Z + 60., 100., Stander, IsTrain, Feet));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FBelmonteTrainBoardsTest, "Yorimichi.Belmonte.TrainBoards",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// Two trains shuttling 0 <-> 1000 m on a 400 s cycle, sampled every 10 s: each stands 100 s at each terminus. A stands at
// 1000 m from 190 to 290 s and at 0 m from 390 to 90 s (across the cycle's end); B runs the same 200 s later.
static FBelmonteTrainLine ShuttleLine()
{
    FBelmonteTrainLine Line;
    Line.Cycle = 400.;
    for (int32 Train = 0; Train < 2; ++Train)
    {
        FBelmonteTrainRun& Run = Line.Trains.AddDefaulted_GetRef();
        Run.Name = Train ? TEXT("B") : TEXT("A");
        Run.T0 = Train * 200.;
        Run.Dt = 10.;
        for (int32 K = 0; K < 40; ++K)
            Run.S.Add(K < 10 ? 0.f : K < 19 ? float((K - 9) * 100) : K < 30 ? 1000.f : float(1000 - (K - 29) * 100));
    }
    return Line;
}

bool FBelmonteTrainBoardsTest::RunTest(const FString&)
{
    const FBelmonteTrainLine Line = ShuttleLine();
    const TArray<FBelmonteTrainStop> Far = Line.Stops(1000.), Near = Line.Stops(0.);
    TestEqual(TEXT("Each train stands once a cycle at each end"), Far.Num(), 2);
    TestEqual(TEXT("... at both ends"), Near.Num(), 2);
    if (Far.Num() != 2 || Near.Num() != 2) return false;
    TestTrue(TEXT("A arrives at 1000 m at 190 s and leaves at 290 s"), Far[0].Train == 0 && FMath::IsNearlyEqual(Far[0].Arrive, 190.) && FMath::IsNearlyEqual(Far[0].Depart, 290.));
    TestTrue(TEXT("B arrives at 1000 m at 390 s and leaves across the cycle's end"), Far[1].Train == 1 && FMath::IsNearlyEqual(Far[1].Arrive, 390.) && FMath::IsNearlyEqual(Far[1].Depart, 90.));
    TestTrue(TEXT("A's stand at 0 m spans the cycle's end"), Near[1].Train == 0 && FMath::IsNearlyEqual(Near[1].Arrive, 390.) && FMath::IsNearlyEqual(Near[1].Depart, 90.));
    TestTrue(TEXT("B arrives at 0 m at 190 s"), Near[0].Train == 1 && FMath::IsNearlyEqual(Near[0].Arrive, 190.));

    auto Next = [&](const TArray<FBelmonteTrainStop>& Stops, double Time, int32 Count = 2) { return FBelmonteTrainLine::NextArrivals(Stops, Line.Cycle, Time, Count); };
    // Nobody at 1000 m at 100 s: A in 90 s, then B in 290 s.
    TArray<FBelmonteTrainArrival> A = Next(Far, 100.);
    TestTrue(TEXT("Next and after-next while the platform is empty"), A.Num() == 2 && A[0].Train == 0 && !A[0].bAtPlatform && FMath::IsNearlyEqual(A[0].In, 90.)
        && A[1].Train == 1 && FMath::IsNearlyEqual(A[1].In, 290.));
    // A standing (200 s): at the platform first, B next in 190 s.
    A = Next(Far, 200.);
    TestTrue(TEXT("A standing train comes first"), A.Num() == 2 && A[0].Train == 0 && A[0].bAtPlatform && A[0].In == 0. && A[1].Train == 1 && FMath::IsNearlyEqual(A[1].In, 190.));
    TestTrue(TEXT("At the very arrival the train is at the platform"), Next(Far, 190.)[0].bAtPlatform);
    TestTrue(TEXT("Once it has left, the other train is next"), !Next(Far, 291.)[0].bAtPlatform && Next(Far, 291.)[0].Train == 1);
    // B's stand across the cycle's end (50 s): at the platform, A next in 140 s.
    A = Next(Far, 50.);
    TestTrue(TEXT("A stand across the cycle's end"), A[0].Train == 1 && A[0].bAtPlatform && A[1].Train == 0 && FMath::IsNearlyEqual(A[1].In, 140.));
    // The cycle repeats, before and after.
    A = Next(Far, 100. + 3 * Line.Cycle);
    TestTrue(TEXT("Cycles later"), FMath::IsNearlyEqual(A[0].In, 90.) && FMath::IsNearlyEqual(A[1].In, 290.));
    A = Next(Far, 100. - 2 * Line.Cycle);
    TestTrue(TEXT("Before the clock's start"), FMath::IsNearlyEqual(A[0].In, 90.) && A[0].Train == 0);
    // More arrivals than trains: the next cycle's follow.
    A = Next(Far, 100., 3);
    TestTrue(TEXT("The third arrival is A's next one"), A.Num() == 3 && A[2].Train == 0 && FMath::IsNearlyEqual(A[2].In, 490.));
    TestTrue(TEXT("At 0 m at 100 s: B in 90 s, A in 290 s"), Next(Near, 100.)[0].Train == 1 && FMath::IsNearlyEqual(Next(Near, 100.)[1].In, 290.));
    TestEqual(TEXT("No stops, no arrivals"), FBelmonteTrainLine::NextArrivals({}, Line.Cycle, 0., 2).Num(), 0);

    // Real minutes: whole minutes left, "arriving" under one, "at platform" when standing; the dev clock speed divides.
    auto In = [](double Seconds) { FBelmonteTrainArrival R; R.Train = 0; R.In = Seconds; return R; };
    FBelmonteTrainArrival Standing; Standing.Train = 0; Standing.bAtPlatform = true;
    TestEqual(TEXT("Standing"), FBelmonteTrainLine::Countdown(Standing, 1.), FString(TEXT("at platform")));
    TestEqual(TEXT("Under a minute"), FBelmonteTrainLine::Countdown(In(59.), 1.), FString(TEXT("arriving")));
    TestEqual(TEXT("One minute"), FBelmonteTrainLine::Countdown(In(60.), 1.), FString(TEXT("in 1 min")));
    TestEqual(TEXT("Five minutes and a bit"), FBelmonteTrainLine::Countdown(In(5 * 60. + 59.), 1.), FString(TEXT("in 5 min")));
    TestEqual(TEXT("Clock ten times faster: 600 service s are one real minute"), FBelmonteTrainLine::Countdown(In(600.), 10.), FString(TEXT("in 1 min")));
    TestEqual(TEXT("... and 590 are under it"), FBelmonteTrainLine::Countdown(In(590.), 10.), FString(TEXT("arriving")));
    TestEqual(TEXT("Clock at half speed: 90 service s are three real minutes"), FBelmonteTrainLine::Countdown(In(90.), .5), FString(TEXT("in 3 min")));
    TestEqual(TEXT("No train"), FBelmonteTrainLine::Countdown(FBelmonteTrainArrival(), 1.), FString(TEXT("-")));

    // The countdown at a board follows the service clock: a minute of service time later (scale 1) it reads a minute less.
    TestEqual(TEXT("Board at 100 s"), FBelmonteTrainLine::Countdown(Next(Far, 100.)[0], 1.), FString(TEXT("in 1 min")));
    TestEqual(TEXT("Board at 140 s"), FBelmonteTrainLine::Countdown(Next(Far, 140.)[0], 1.), FString(TEXT("arriving")));
    TestEqual(TEXT("Board at 200 s"), FBelmonteTrainLine::Countdown(Next(Far, 200.)[0], 1.), FString(TEXT("at platform")));
    TestEqual(TEXT("Board at 200 s, the train after"), FBelmonteTrainLine::Countdown(Next(Far, 200.)[1], 1.), FString(TEXT("in 3 min")));
    return true;
}
#endif
