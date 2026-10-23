#include "RacingService.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "RacingBroadcast.h"
#include "HorseComponent.h"
#include "AtelierData.h"
#include "Dom/JsonObject.h"
#include "HRClock.h"
#include "HRRules.h"
#include "HRSave.h"
#include "HAL/FileManager.h"
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

namespace RacingTest
{
    /** belmonte_courses.json: the staged copy, else the committed source beside the Unreal project. */
    FString CoursesJson()
    {
        FString Text;
        if (FFileHelper::LoadFileToString(Text, *AtelierDataPath(TEXT("racing/belmonte_courses.json")))) return Text;
        FFileHelper::LoadFileToString(Text, *FPaths::Combine(FPaths::ProjectDir(), TEXT("../world/racing/belmonte_courses.json")));
        return Text;
    }

    /** Belmonte's region origin (world/regions/belmonte/layout.py ORIGIN, in Unreal cm). */
    const FVector BelmonteOrigin(550. * 100., -4500. * 100., 210. * 100.);

    /** A world one second before its first race of the day, the race run, and the snapshot a second after its start. */
    struct FRaceFixture
    {
        FHRWorldState World;
        double Start = 0.;
        FRacingNetState Snapshot;
        bool Make(FAutomationTestBase& Test)
        {
            World = HRRules::CreateWorld(TEXT("yorimichi-racing-test"));
            HRRules::StartClock(World, 1700000000);
            const FHRRace* First = nullptr;
            for (const FHRRace& R : World.Meeting.Races)
                if (R.Status == TEXT("declared") && R.Entries.Num() >= 2) { First = &R; break; }
            if (!Test.TestNotNull(TEXT("The day has a race"), First)) return false;
            Start = HRRules::RaceStartSeconds(World, First->Key);
            HRRules::AdvanceTo(World, Start + 1.);
            ARacingService::BuildSnapshot(World, Start + 1., FRacingNetResult(), Snapshot);
            return Test.TestTrue(TEXT("The race in focus has been run"), Snapshot.Race.bRun && Snapshot.Race.Runners.Num() >= 2);
        }
    };
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingHudGroundsTest, "Yorimichi.Racing.HudGrounds",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingHudGroundsTest::RunTest(const FString&)
{
    FRacingCourse Oval;
    Oval.Oval.Lap = 4. * Oval.Oval.Half + 2. * PI * Oval.Oval.Radius;
    Oval.Oval.Z = 40.;
    auto At = [&](double X, double Y, double Z = 0.) { return Oval.Oval.World(X, Y, Z); };
    TestFalse(TEXT("Loaded course without platform bounds hides the banner"), Oval.ContainsGrounds(At(600., 525.)));
    Oval.Oval.Grounds += At(476., 443.);
    Oval.Oval.Grounds += At(747., 589.);
    TestTrue(TEXT("Hidamari infield"), Oval.ContainsGrounds(At(600., 525.)));
    TestTrue(TEXT("Grandstand arrival"), Oval.ContainsGrounds(At(563.5, 458.5, 1.)));
    TestTrue(TEXT("Grandstand upper seats"), Oval.ContainsGrounds(At(600., 453., 15.)));
    TestFalse(TEXT("City street, inside old rendering radius"), Oval.ContainsGrounds(At(560., 343.)));
    TestFalse(TEXT("Approach lane"), Oval.ContainsGrounds(At(560., 442.)));
    TestFalse(TEXT("Beyond west platform edge"), Oval.ContainsGrounds(At(475., 525.)));
    TestFalse(TEXT("Beyond east platform edge"), Oval.ContainsGrounds(At(748., 525.)));
    TestFalse(TEXT("Beyond north platform edge"), Oval.ContainsGrounds(At(600., 590.)));
    TestFalse(TEXT("Flying over the venue"), Oval.ContainsGrounds(At(600., 525., 30.)));
    TestFalse(TEXT("Under the platform"), Oval.ContainsGrounds(At(600., 525., -10.)));
    Oval.Oval.Grounds = FBox(At(500., 500.), At(700., 600.));
    TestFalse(TEXT("Invalid bounds hide the banner"), Oval.ContainsGrounds(At(600., 525.)));

    ARacingService* Service = NewObject<ARacingService>(GetTransientPackage());
    FString Error;
    if (!TestTrue(TEXT("Belmonte loaded"), Service->LoadBelmonteCourses(RacingTest::CoursesJson(), RacingTest::BelmonteOrigin, Error))) return false;
    const FRacingCourse* Turf = Service->GetCourse(ERacingVenue::Belmonte);
    if (!TestNotNull(TEXT("Belmonte turf"), Turf)) return false;
    TestTrue(TEXT("Belmonte infield"), Turf->ContainsGrounds(Turf->Centre()));
    TestTrue(TEXT("Belmonte post spectator point"), Turf->ContainsGrounds(Turf->At(15., 9.)));
    TestFalse(TEXT("Belmonte countryside"), Turf->ContainsGrounds(Turf->At(15., 100.)));
    TestFalse(TEXT("Flying over Belmonte"), Turf->ContainsGrounds(Turf->Centre() + FVector(0., 0., 3000.)));
    FRacingCourse Empty;
    TestFalse(TEXT("Unloaded venue"), Empty.ContainsGrounds(FVector::ZeroVector));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingEnglishNameTest, "Yorimichi.Racing.EnglishName",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingEnglishNameTest::RunTest(const FString&)
{
    FHRRace Race;
    Race.EventId = TEXT("test-event");
    Race.Group = 1;
    const TCHAR* Rounds[] = {TEXT("final"), TEXT("semi"), TEXT("qualif"), TEXT("barrage"), TEXT("ordinary")};
    const TCHAR* Expected[] = {TEXT("final"), TEXT("semi-final 2"), TEXT("qualifying sprint 2"), TEXT("play-off 2"), TEXT("race 2")};
    for (int32 I = 0; I < UE_ARRAY_COUNT(Rounds); ++I)
    {
        Race.Round = Rounds[I];
        TestEqual(Rounds[I], ARacingService::RaceName(Race), FString(TEXT("test-event · ")) + Expected[I]);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingBelmonteCourseTest, "Yorimichi.Racing.BelmonteCourse",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingBelmonteCourseTest::RunTest(const FString&)
{
    const FString Json = RacingTest::CoursesJson();
    if (!TestFalse(TEXT("belmonte_courses.json is readable"), Json.IsEmpty())) return false;
    ARacingService* Service = NewObject<ARacingService>(GetTransientPackage());
    FString Error;
    const bool bLoaded = Service->LoadBelmonteCourses(Json, RacingTest::BelmonteOrigin, Error);
    if (!TestTrue(TEXT("The courses parse: ") + Error, bLoaded)) return false;
    const FRacingCourse* Turf = Service->GetCourse(ERacingVenue::Belmonte, 0);
    const FRacingCourse* Sand = Service->GetCourse(ERacingVenue::Belmonte, 1);
    if (!TestNotNull(TEXT("Turf"), Turf) || !TestNotNull(TEXT("Sand"), Sand)) return false;
    TestTrue(TEXT("Turf lap 1799.84 m"), FMath::IsNearlyEqual(Turf->Lap(), 1799.841, .01));
    TestTrue(TEXT("Sand lap 1703.71 m"), FMath::IsNearlyEqual(Sand->Lap(), 1703.707, .01));
    TestTrue(TEXT("Counter-clockwise"), Turf->Line.Turn > 0.);
    // The finish (S 0) is the lane-1 point 240 m from the first sample, (-155, 607.3) in the region's plan; the post
    // stands 3.6 m further out at (-155, 610.9).
    float Yaw = 0.f;
    const FVector Finish = Turf->At(0., 0., &Yaw);
    const FVector Expected = RacingTest::BelmonteOrigin + FVector(-155. * 100., -607.3 * 100., 30.08 * 100.);
    TestTrue(FString::Printf(TEXT("Finish point %s"), *Finish.ToString()), Finish.Equals(Expected, 1.));
    TestTrue(TEXT("The post is 3.6 m outwards"), Turf->At(0., 3.6).Equals(RacingTest::BelmonteOrigin + FVector(-155. * 100., -610.9 * 100., 30.08 * 100.), 2.));
    TestTrue(FString::Printf(TEXT("Running west past the post (yaw %.1f)"), Yaw), FMath::Abs(FMath::Abs(Yaw) - 180.f) < 1.f);
    TestTrue(TEXT("A lap closes"), Turf->At(Turf->Lap(), -4.).Equals(Turf->At(0., -4.), .5));
    // Continuous: samples every half metre along every lane stay about half a metre apart (more outside a bend, less inside).
    for (const FRacingCourse* Course : {Turf, Sand})
        for (const double Lane : {Course->InnerLane, 0.})
        {
            FVector Previous = Course->At(0., Lane);
            double Longest = 0., Shortest = 1e9;
            for (double S = .5; S <= Course->Lap() + .01; S += .5)
            {
                const FVector P = Course->At(S, Lane);
                const double Step = FVector::Dist2D(P, Previous) / 100.;
                Longest = FMath::Max(Longest, Step);
                Shortest = FMath::Min(Shortest, Step);
                Previous = P;
            }
            TestTrue(FString::Printf(TEXT("No jump along lane %.1f (longest step %.3f m)"), Lane, Longest), Longest < .6);
            TestTrue(FString::Printf(TEXT("No stall along lane %.1f (shortest step %.3f m)"), Lane, Shortest), Shortest > .25);
        }
    // Lanes run inside the outer rail (2.5 m out) and the inner one (12.8 m in).
    TestTrue(TEXT("Lanes between the rails"), Turf->InnerLane > -12.8 && Turf->OuterLane < 2.5);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingHippodromeCourseTest, "Yorimichi.Racing.HippodromeCourse",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingHippodromeCourseTest::RunTest(const FString&)
{
    FRacingCourse Course;
    Course.Oval.Lap = 4. * Course.Oval.Half + 2. * PI * Course.Oval.Radius;
    Course.InnerLane = -5.;
    Course.OuterLane = 5.;
    TestTrue(TEXT("Lap 554.2 m"), FMath::IsNearlyEqual(Course.Lap(), 554.159, .01));
    float Yaw = 0.f;
    TestTrue(TEXT("The post is at finish_x on the home straight"), Course.At(0., 0., &Yaw).Equals(FVector(600. * 100., -475. * 100., 0.), .01));
    TestTrue(TEXT("Running east past the post"), FMath::Abs(Yaw) < .01f);
    FVector Previous = Course.At(0., 3.);
    double Longest = 0.;
    for (double S = .5; S <= Course.Lap() + .01; S += .5)
    {
        const FVector P = Course.At(S, 3.);
        Longest = FMath::Max(Longest, FVector::Dist2D(P, Previous) / 100.);
        Previous = P;
    }
    TestTrue(FString::Printf(TEXT("Continuous (longest step %.3f m)"), Longest), Longest < .55);
    TestTrue(TEXT("Lanes spread across the field"), FMath::IsNearlyEqual(Course.LaneOffset(0, 6), -5.) && FMath::IsNearlyEqual(Course.LaneOffset(5, 6), 5.));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingMotionTest, "Yorimichi.Racing.Motion",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingMotionTest::RunTest(const FString&)
{
    RacingTest::FRaceFixture Fixture;
    if (!Fixture.Make(*this)) return false;
    // Twice from the world, and once from the snapshot as a client receives it (serialised and read back).
    FRacingNetState Again;
    ARacingService::BuildSnapshot(Fixture.World, Fixture.Start + 1., FRacingNetResult(), Again);
    TestTrue(TEXT("The snapshot is deterministic"), Again.SameContent(Fixture.Snapshot));
    TArray<uint8> Bytes;
    FMemoryWriter Writer(Bytes);
    FRacingNetState::StaticStruct()->SerializeBin(Writer, &Fixture.Snapshot);
    FRacingNetState Received;
    FMemoryReader Reader(Bytes);
    FRacingNetState::StaticStruct()->SerializeBin(Reader, &Received);
    TestTrue(TEXT("The snapshot survives the wire"), Received.SameContent(Fixture.Snapshot));
    const FRacingNetRace& Race = Fixture.Snapshot.Race;
    for (int32 I = 0; I < Race.Runners.Num(); ++I)
    {
        const RacingMotion::FPlan Host = Race.Runners[I].Plan(Race.Distance), Client = Received.Race.Runners[I].Plan(Race.Distance);
        TestTrue(TEXT("Four splits"), Host.IsRun());
        double Previous = -1e9;
        bool bSame = true, bMonotone = true;
        for (double T = -RacingMotion::ParadeSeconds; T <= HRClock::RaceSeconds; T += .25)
        {
            double V1 = 0., V2 = 0.;
            const double D = RacingMotion::Distance(Host, T, &V1);
            bSame &= D == RacingMotion::Distance(Client, T, &V2) && V1 == V2;
            bMonotone &= D >= Previous - 1e-9;
            Previous = D;
        }
        TestTrue(TEXT("Host and client place the runner alike"), bSame);
        TestTrue(TEXT("A runner never runs backwards"), bMonotone);
        TestTrue(TEXT("Standing at the start"), FMath::IsNearlyZero(RacingMotion::Distance(Host, 0.)));
        // The parade: walking to the start, then lined up and still for the whole TV build-up.
        double Walking = 0., Still = 1.;
        TestTrue(TEXT("Walking to the start"), RacingMotion::Distance(Host, -150., &Walking) < 0. && Walking > 1.);
        for (double T = -RacingTv::WindowSeconds; T < 0.; T += 1.)
            if (!FMath::IsNearlyZero(RacingMotion::Distance(Host, T, &Still)) || Still != 0.) { AddError(FString::Printf(TEXT("Not lined up at t=%.0f"), T)); break; }
        TestTrue(TEXT("At the post on its finishing time"), FMath::IsNearlyEqual(RacingMotion::Distance(Host, Host.FinishTime()), double(Race.Distance), .01));
        for (int32 K = 0; K < 3; ++K)
            TestTrue(TEXT("Through each stage on its split"),
                FMath::IsNearlyEqual(RacingMotion::Distance(Host, Host.Splits[K]), Race.Distance * RacingMotion::StageEnd[K], .01));
        double Speed = 0.;
        RacingMotion::Distance(Host, Host.FinishTime() * .6, &Speed);
        TestTrue(FString::Printf(TEXT("A racing speed mid-race (%.1f m/s)"), Speed), Speed > 8. && Speed < 25.);
    }
    // The finishing order is the official one: lower place, earlier finishing time.
    for (const FRacingNetRunner& A : Race.Runners)
        for (const FRacingNetRunner& B : Race.Runners)
            if (A.Place < B.Place) TestTrue(TEXT("Places follow finishing times"), A.SplitMs[3] <= B.SplitMs[3]);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingSnapshotTest, "Yorimichi.Racing.Snapshot",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingSnapshotTest::RunTest(const FString&)
{
    RacingTest::FRaceFixture Fixture;
    if (!Fixture.Make(*this)) return false;
    TArray<uint8> Bytes;
    FMemoryWriter Writer(Bytes);
    FRacingNetState::StaticStruct()->SerializeBin(Writer, &Fixture.Snapshot);
    const int32 Payload = Fixture.Snapshot.PayloadBytes();
    AddInfo(FString::Printf(TEXT("Snapshot payload %d bytes (%d as a binary archive), %d runners, %d standings"), Payload, Bytes.Num(),
        Fixture.Snapshot.Race.Runners.Num(), Fixture.Snapshot.Standings.Num()));
    TestTrue(FString::Printf(TEXT("The snapshot stays small (%d bytes)"), Payload), Payload > 0 && Payload < 2048);
    TestTrue(TEXT("At most the rules' field"), Fixture.Snapshot.Race.Runners.Num() <= HRRules::MaxRunners);
    TestTrue(TEXT("Standings"), Fixture.Snapshot.Standings.Num() > 0 && Fixture.Snapshot.Standings.Num() <= 6);
    // The venue rule: Grand Prix days at Belmonte, the ordinary days of a season alternating from Hidamari.
    int32 Hidamari = 0, Belmonte = 0;
    for (int32 T = 0; T < HRClock::DaysPerSeason; ++T)
    {
        const ERacingVenue V = ARacingService::VenueForDay(T);
        if (HRClock::IsGrandPrixDay(T)) TestTrue(TEXT("Grand Prix at Belmonte"), V == ERacingVenue::Belmonte);
        else (V == ERacingVenue::Hidamari ? Hidamari : Belmonte)++;
    }
    TestEqual(TEXT("Ordinary days shared evenly"), Hidamari, 4);
    // After the race is shown: the next race comes into focus and the podium stays as the last result.
    FRacingNetState Later;
    ARacingService::BuildSnapshot(Fixture.World, Fixture.Start + HRClock::RaceSeconds + 1., FRacingNetResult(), Later);
    TestEqual(TEXT("The last result is the race just run"), Later.Last.Key, Fixture.Snapshot.Race.Key);
    TestEqual(TEXT("A podium of three"), Later.Last.Top.Num(), FMath::Min(3, Fixture.Snapshot.Race.Runners.Num()));
    TestNotEqual(TEXT("The next race in focus"), Later.Race.Key, Fixture.Snapshot.Race.Key);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingSaveTest, "Yorimichi.Racing.Save",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingSaveTest::RunTest(const FString&)
{
    const FString Path = FPaths::ConvertRelativePathToFull(FPaths::AutomationTransientDir() / FString::Printf(TEXT("racing-%s/world.json"),
        *FGuid::NewGuid().ToString(EGuidFormats::Digits)));
    ARacingService* First = NewObject<ARacingService>(GetTransientPackage());
    TestTrue(TEXT("A new world is created"), First->OpenWorld(Path, TEXT("save-test")));
    TestTrue(TEXT("and saved"), FPaths::FileExists(Path));
    TestTrue(TEXT("Its clock is anchored"), First->GetWorldState().EpochUnix != 0);
    TestTrue(TEXT("A later save"), First->SaveNow());
    // Another session on the same machine: the saved world, not a new one from its own seed.
    ARacingService* Second = NewObject<ARacingService>(GetTransientPackage());
    TestTrue(TEXT("The world is loaded"), Second->OpenWorld(Path, TEXT("another-seed")));
    TestEqual(TEXT("Same seed"), Second->GetWorldState().Seed, FString(TEXT("save-test")));
    TestEqual(TEXT("Same world, byte for byte"), HRSave::ToJson(Second->GetWorldState()), HRSave::ToJson(First->GetWorldState()));
    FHRWorldState Untouched;
    TestFalse(TEXT("A missing file loads nothing"), ARacingService::LoadWorldFile(Path + TEXT(".missing"), Untouched));
    FFileHelper::SaveStringToFile(TEXT("not a world"), *(Path + TEXT(".bad")));
    TestFalse(TEXT("Nor does a broken one"), ARacingService::LoadWorldFile(Path + TEXT(".bad"), Untouched));
    IFileManager::Get().DeleteDirectory(*FPaths::GetPath(Path), false, true);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingSaveSafetyTest, "Yorimichi.Racing.SaveSafety",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingSaveSafetyTest::RunTest(const FString&)
{
    const FString Dir = FPaths::ConvertRelativePathToFull(FPaths::AutomationTransientDir() / FString::Printf(TEXT("racing-safety-%s"),
        *FGuid::NewGuid().ToString(EGuidFormats::Digits)));
    // The service reports each failure as an error: expected here.
    AddExpectedError(TEXT("is not an admissible world"), EAutomationExpectedErrorFlags::Contains, 2);
    AddExpectedError(TEXT("could not save the world"), EAutomationExpectedErrorFlags::Contains, 1);
    IFileManager& Files = IFileManager::Get();
    const double Now = double((FDateTime::UtcNow() - FDateTime(1970, 1, 1)).GetTotalSeconds());

    // A save that is not an admissible world is kept aside, then a new world is created.
    {
        const FString Path = Dir / TEXT("aside/world.json");
        FFileHelper::SaveStringToFile(TEXT("{\"rulesVersion\":\"something else\"}"), *Path);
        ARacingService* Service = NewObject<ARacingService>(GetTransientPackage());
        TestTrue(TEXT("A new world opens"), Service->OpenWorld(Path, TEXT("safety")));
        TArray<FString> Aside;
        Files.FindFiles(Aside, *(FPaths::GetPath(Path) / TEXT("world.json.unreadable-*")), true, false);
        TestEqual(TEXT("The unreadable save is kept aside"), Aside.Num(), 1);
        FString Kept;
        if (Aside.Num()) FFileHelper::LoadFileToString(Kept, *(FPaths::GetPath(Path) / Aside[0]));
        TestTrue(TEXT("unchanged"), Kept.Contains(TEXT("something else")));
        TestFalse(TEXT("No temporary file is left"), FPaths::FileExists(Path + TEXT(".tmp")));
        FHRWorldState Reloaded;
        TestTrue(TEXT("The new world is saved whole"), ARacingService::LoadWorldFile(Path, Reloaded));
    }

    // When it cannot be kept aside, it stays exactly where it is and no world opens.
    {
        const FString Path = Dir / TEXT("stuck/world.json");
        const FString Original = TEXT("{\"not\":\"a world\"}");
        FFileHelper::SaveStringToFile(Original, *Path);
        // Every aside name of the next minute is taken by a directory that a rename cannot replace.
        for (int32 S = -2; S < 60; ++S)
            FFileHelper::SaveStringToFile(TEXT("x"), *(Path + FString::Printf(TEXT(".unreadable-%lld/keep"), int64(Now) + S)));
        ARacingService* Service = NewObject<ARacingService>(GetTransientPackage());
        TestFalse(TEXT("No world opens"), Service->OpenWorld(Path, TEXT("safety")));
        TestFalse(TEXT("racing stays off"), Service->HasWorld());
        TestFalse(TEXT("and says why"), Service->GetPersistenceError().IsEmpty());
        FString Kept;
        FFileHelper::LoadFileToString(Kept, *Path);
        TestEqual(TEXT("The original save is untouched"), Kept, Original);
        TestFalse(TEXT("nothing is saved"), Service->SaveNow());
        FFileHelper::LoadFileToString(Kept, *Path);
        TestEqual(TEXT("still untouched"), Kept, Original);
    }

    // A failed save keeps the accepted world in memory and dirty; the next one writes it.
    {
        const FString Path = Dir / TEXT("retry/world.json");
        ARacingService* Service = NewObject<ARacingService>(GetTransientPackage());
        TestTrue(TEXT("A world opens"), Service->OpenWorld(Path, TEXT("safety")));
        const FString Accepted = HRSave::ToJson(Service->GetWorldState());
        FString OnDisk;
        FFileHelper::LoadFileToString(OnDisk, *Path);
        // The temporary file's name is taken by a directory: the write fails.
        FFileHelper::SaveStringToFile(TEXT("x"), *(Path + TEXT(".tmp/keep")));
        TestFalse(TEXT("The save fails"), Service->SaveNow());
        TestFalse(TEXT("and says why"), Service->GetPersistenceError().IsEmpty());
        TestTrue(TEXT("The world is still open"), Service->HasWorld());
        TestEqual(TEXT("unchanged in memory"), HRSave::ToJson(Service->GetWorldState()), Accepted);
        FString After;
        FFileHelper::LoadFileToString(After, *Path);
        TestEqual(TEXT("The previous save is intact"), After, OnDisk);
        Files.DeleteDirectory(*(Path + TEXT(".tmp")), false, true);
        TestTrue(TEXT("The next save succeeds"), Service->SaveNow());
        TestTrue(TEXT("and clears the error"), Service->GetPersistenceError().IsEmpty());
        FHRWorldState Reloaded;
        TestTrue(TEXT("The saved world loads"), ARacingService::LoadWorldFile(Path, Reloaded));
        TestEqual(TEXT("as accepted"), HRSave::ToJson(Reloaded), HRSave::ToJson(Service->GetWorldState()));
    }
    Files.DeleteDirectory(*Dir, false, true);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingGroundTest, "Yorimichi.Racing.Ground",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingGroundTest::RunTest(const FString&)
{
    using RacingGround::FHit;
    double Z = 0.;
    TestFalse(TEXT("No hit: the authored height"), RacingGround::Pick({}, 3000., Z));
    TestEqual(TEXT("no hit z"), Z, 3000.);
    const FHit Wall{3100., FVector(1., 0., 0.)};
    const FHit Rail{3050., FVector(0., .8, .2)};
    TestFalse(TEXT("A wall or a rail is not ground"), RacingGround::Pick({Wall, Rail}, 3000., Z));
    TestEqual(TEXT("and leaves the authored height"), Z, 3000.);
    const FHit Roof{3200., FVector::UpVector};
    const FHit Turf{2970., FVector(.1, 0., .99)};
    TestTrue(TEXT("The turf under a roof"), RacingGround::Pick({Roof, Wall, Turf}, 3000., Z));
    TestEqual(TEXT("is the ground"), Z, 2970.);
    TestTrue(TEXT("whatever the order"), RacingGround::Pick({Turf, Roof}, 3000., Z) && Z == 2970.);
    const FHit Deep{3000. - RacingGround::Below - 1., FVector::UpVector};
    const FHit High{3000. + RacingGround::Above + 1., FVector::UpVector};
    TestFalse(TEXT("Outside the window is not ground"), RacingGround::Pick({Deep, High}, 3000., Z));
    const FHit Steep{2990., FVector(.8, 0., .6)};
    TestFalse(TEXT("A slope steeper than 45 degrees is not ground"), RacingGround::Pick({Steep}, 3000., Z));
    const FHit Bank{2990., FVector(.6, 0., .8)};
    TestTrue(TEXT("A banked turn is"), RacingGround::Pick({Bank}, 3000., Z) && Z == 2990.);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingTvPlacementTest, "Yorimichi.Racing.TvPlacement",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingTvPlacementTest::RunTest(const FString&)
{
    const FVector Origin = RacingTest::BelmonteOrigin;
    const FString AuthoredJson = TEXT("{\"tv_spots\":[")
        TEXT("{\"id\":\"osteria_front\",\"pivot_cm\":[-2600,-190,248],\"yaw\":180,\"watch_cm\":[-3040,-160,18],\"watch_yaw\":-4,\"scale\":1.4},")
        TEXT("{\"id\":\"osteria_back\",\"pivot_cm\":[-4050,485,248],\"yaw\":0,\"watch_cm\":[-3700,160,18],\"watch_yaw\":136.2,\"scale\":1.4},")
        TEXT("{\"id\":\"salon_paris\",\"pivot_cm\":[7500,-29720,3255],\"yaw\":-90,\"watch_cm\":[7500,-30150,3015],\"watch_yaw\":90,\"scale\":1.4},")
        TEXT("{\"id\":\"salon_bar\",\"pivot_cm\":[5750,-31637.6,3305],\"yaw\":90,\"watch_cm\":[5750,-31160,3015],\"watch_yaw\":-90,\"scale\":1.3}]}");
    TArray<RacingTv::FSpot> Authored;
    FString Error;
    if (!TestTrue(TEXT("Authored runtime tv_spots parse"), RacingTv::ParseSpots(AuthoredJson, Authored, &Error) && Authored.Num() == 4))
        return false;
    const int32 Front = RacingTv::FindSpot(TEXT("osteria_front"), Authored);
    if (!TestTrue(TEXT("The osteria's front screen"), Authored.IsValidIndex(Front))) return false;
    const RacingTv::FSpot& Spot = Authored[Front];
    // Haras Valley's frame is the region's: its watch point (-3040, -160) cm is the osteria's map stop, plan (-30.4, 1.6) m.
    const FVector Watch = Origin + Spot.Watch;
    TestTrue(FString::Printf(TEXT("The watch point is the osteria stop (%s)"), *Watch.ToString()),
        Watch.Equals(Origin + FVector(-30.4 * 100., -1.6 * 100., 18.), .5));
    // The picture stands 11.2 cm off the wall, facing west into the taproom, 2.3 m over the floor.
    const FTransform Mount = RacingTv::SpotTransform(Spot, Origin);
    TestTrue(TEXT("Facing west"), Mount.GetRotation().GetForwardVector().Equals(FVector(-1., 0., 0.), 1e-4));
    TestTrue(TEXT("The picture's centre"), RacingTv::ScreenCentre(Spot, Origin).Equals(Origin + FVector(-2600. - RacingTv::PictureFront * Spot.Scale, -190., 248.), .01));
    TestTrue(TEXT("1.3 to 1.5 times Stud Valley's screen"), Spot.Scale >= 1.3f && Spot.Scale <= 1.5f);
    TestTrue(TEXT("2.3 m over the floor"), FMath::IsNearlyEqual(Spot.Pivot.Z - Spot.Watch.Z, 230., .01));
    for (const RacingTv::FSpot& S : Authored)
    {
        // Every watch point is in front of its screen, within the capture's 25 m, and faces it within 50 degrees.
        const FVector Centre = RacingTv::ScreenCentre(S, Origin), At = Origin + S.Watch;
        const FVector Facing = FRotator(0.f, S.Yaw, 0.f).Vector();
        TestTrue(FString::Printf(TEXT("%s: watched from the front"), S.Id), FVector::DotProduct(At - Centre, Facing) > 0.);
        TestTrue(FString::Printf(TEXT("%s: within 25 m"), S.Id), FVector::Dist(At, Centre) < 2500.);
        const float ToScreen = float(FMath::RadiansToDegrees(FMath::Atan2(Centre.Y - At.Y, Centre.X - At.X)));
        TestTrue(FString::Printf(TEXT("%s: the viewer faces it"), S.Id), FMath::Abs(FMath::FindDeltaAngleDegrees(S.WatchYaw, ToScreen)) < 50.f);
    }
    TArray<RacingTv::FSpot> Parsed;
    const FString CustomJson = TEXT("{\"tv_spots\":[")
        TEXT("{\"id\":\"osteria_front\",\"pivot_cm\":[-2500,-100,248],\"yaw\":175,\"watch_cm\":[-2940,-70,18],\"watch_yaw\":-9,\"scale\":1.4},")
        TEXT("{\"id\":\"osteria_back\",\"pivot_cm\":[-4050,485,248],\"yaw\":0,\"watch_cm\":[-3700,160,18],\"watch_yaw\":136.2,\"scale\":1.4},")
        TEXT("{\"id\":\"salon_paris\",\"pivot_cm\":[7500,-29720,3255],\"yaw\":-90,\"watch_cm\":[7500,-30150,3015],\"watch_yaw\":90,\"scale\":1.4},")
        TEXT("{\"id\":\"salon_bar\",\"pivot_cm\":[5750,-31637.6,3305],\"yaw\":90,\"watch_cm\":[5750,-31160,3015],\"watch_yaw\":-90,\"scale\":1.3}]}");
    if (!TestTrue(TEXT("ParseSpots accepts building-derived runtime JSON"), RacingTv::ParseSpots(CustomJson, Parsed, &Error) && Parsed.Num() == 4))
        return false;
    TestTrue(TEXT("ParseSpots updates pivot and yaw"), Parsed[0].Pivot.Equals(FVector(-2500., -100., 248.), .01) && FMath::IsNearlyEqual(Parsed[0].Yaw, 175.f));
    TestFalse(TEXT("ParseSpots rejects incomplete spots without fallback"), RacingTv::ParseSpots(TEXT("{\"tv_spots\":[]}"), Parsed, &Error));
    TestTrue(TEXT("Rejected ParseSpots clears output"), Parsed.IsEmpty() && !Error.IsEmpty());
    TestFalse(TEXT("ParseSpots rejects missing tv_spots key"), RacingTv::ParseSpots(TEXT("{\"version\":1}"), Parsed, &Error));
    TestFalse(TEXT("LoadSpots rejects missing file without fallback"), RacingTv::LoadSpots(TEXT("/nonexistent/belmonte/runtime.json"), Parsed, &Error) || !Parsed.IsEmpty());
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingSharedHorseGaitTest, "Yorimichi.Racing.SharedHorseGait",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingSharedHorseGaitTest::RunTest(const FString&)
{
    TestEqual(TEXT("Idle below 12 cm/s"), UHorseComponent::GaitForSpeed(11.9f), 0);
    TestEqual(TEXT("Walk at 12 cm/s"), UHorseComponent::GaitForSpeed(12.f), 1);
    TestEqual(TEXT("Sprint at 1180 cm/s"), UHorseComponent::GaitForSpeed(1180.f), 5);
    // Mounted walk starts at 10 cm/s; racing starts at 12 cm/s and caps sprint at 1.45x.
    TestTrue(TEXT("Mounted walk at 10 cm/s is 0.82"), FMath::IsNearlyEqual(UHorseComponent::PlayRateForGait(1, 10.f, false), .82f, 1e-4f));
    TestTrue(TEXT("Mounted walk at 135 cm/s is midpoint"), UHorseComponent::PlayRateForGait(1, 135.f, false) > UHorseComponent::PlayRateForGait(1, 135.f, true));
    TestTrue(TEXT("Mounted sprint clamps at 1.22"), FMath::IsNearlyEqual(UHorseComponent::PlayRateForGait(5, 1800.f, false), 1.22f, 1e-4f));
    TestTrue(TEXT("Racing sprint clamps at 1.45"), FMath::IsNearlyEqual(UHorseComponent::PlayRateForGait(5, 1800.f, true), 1.45f, 1e-4f));
    TSharedPtr<FJsonObject> Breed;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(TEXT("{\"contacts\":{\"saddle_root\":[0.04,0.12,1.6],\"seat_z\":1.43}}"));
    TestTrue(TEXT("Breed JSON parses"), FJsonSerializer::Deserialize(Reader, Breed) && Breed.IsValid());
    FVector Saddle = FVector::ZeroVector;
    double SeatZ = 0.;
    TestTrue(TEXT("ReadSeatContacts succeeds"), UHorseComponent::ReadSeatContacts(Breed, Saddle, SeatZ));
    TestTrue(TEXT("ReadSeatContacts converts metres to cm and negates Y"), Saddle.Equals(FVector(4., -12., 160.), 1e-3) && FMath::IsNearlyEqual(SeatZ, 143., 1e-3));
    TSharedPtr<FJsonObject> Empty = MakeShared<FJsonObject>();
    TestFalse(TEXT("ReadSeatContacts rejects missing contacts"), UHorseComponent::ReadSeatContacts(Empty, Saddle, SeatZ));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FRacingTvDirectorTest, "Yorimichi.Racing.TvDirector",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FRacingTvDirectorTest::RunTest(const FString&)
{
    // The shot list on its own: the build-up, the start, the race, the line, the field pulling up.
    using RacingTv::EShot;
    auto Shot = [](double T, double Run, double FirstHome = 90., double LastHome = 95., bool bStraight = false)
    {
        return RacingTv::ChooseShot(T, Run, 1600., FirstHome, LastHome, bStraight);
    };
    TestTrue(TEXT("The course from above first"), Shot(-115., 0.) == EShot::Course);
    TestTrue(TEXT("Then the stand"), Shot(-105., 0.) == EShot::Stands);
    TestTrue(TEXT("The crowd"), Shot(-95., 0.) == EShot::Crowd);
    TestTrue(TEXT("The field lined up"), Shot(-85., 0.) == EShot::Lineup);
    TestTrue(TEXT("Round again"), Shot(-75., 0.) == EShot::Course);
    TestTrue(TEXT("Start"), Shot(-5., 0.) == EShot::Start && Shot(-14., 0.) == EShot::Start);
    TestTrue(TEXT("Travelling"), Shot(30., 500.) == EShot::Travelling);
    TestTrue(TEXT("From above in the second stage"), Shot(25., 400.) == EShot::Aerial);
    TestTrue(TEXT("and in the third"), Shot(55., 900.) == EShot::Aerial);
    TestTrue(TEXT("Face on the straight"), Shot(70., 1300., 90., 95., true) == EShot::Face);
    TestTrue(TEXT("Not before the straight"), Shot(60., 1150., 90., 95., true) == EShot::Travelling);
    TestTrue(TEXT("Line"), Shot(86., 1540., 90., 95., true) == EShot::Line);
    TestTrue(TEXT("Line until the last is home"), Shot(98., 1640.) == EShot::Line);
    TestTrue(TEXT("Finish"), Shot(100., 1660.) == EShot::Finish);

    // A real race at Belmonte: the camera is the same for the same clock (every player sees one picture), the shots come in
    // order and never go back, and the field is in front of the camera and in frame.
    RacingTest::FRaceFixture Fixture;
    if (!Fixture.Make(*this)) return false;
    ARacingService* Service = NewObject<ARacingService>(GetTransientPackage());
    FString Error;
    const bool bLoaded = Service->LoadBelmonteCourses(RacingTest::CoursesJson(), RacingTest::BelmonteOrigin, Error);
    if (!TestTrue(TEXT("The courses parse: ") + Error, bLoaded)) return false;
    FRacingNetRace Race = Fixture.Snapshot.Race;
    Race.Venue = uint8(ERacingVenue::Belmonte);
    Race.Track = 0;
    // A player in the stand's last third: the crowd shot frames that part of it.
    const RacingTv::FVenueShots& Venue = RacingTv::VenueShots(Race.Venue);
    const FRacingCourse& Course = *Service->GetCourse(ERacingVenue::Belmonte, 0);
    const TArray<FVector> Players = {Course.At(Venue.StandS + Venue.StandHalf * .6, Venue.StandOut + 4.)};
    TestEqual(TEXT("The crowd camera finds the player"), RacingTv::CrowdCamera(Course, Venue, Players), 2);
    TestEqual(TEXT("The middle one with nobody there"), RacingTv::CrowdCamera(Course, Venue, {}), 1);
    TArray<EShot> Seen;
    int32 Framed = 0, Samples = 0;
    for (double T = -RacingTv::WindowSeconds + 1.; T <= HRClock::RaceSeconds; T += .5)
    {
        RacingTv::FCamera A, B;
        if (!TestTrue(TEXT("A camera"), RacingTv::Direct(*Service, Race, Race.Start + T, Players, A))) return false;
        RacingTv::Direct(*Service, Race, Race.Start + T, Players, B);
        if (!(A.Eye == B.Eye && A.Aim == B.Aim && A.Fov == B.Fov && A.Shot == B.Shot)) { AddError(FString::Printf(TEXT("Not deterministic at t=%.1f"), T)); return false; }
        if (Seen.IsEmpty() || Seen.Last() != A.Shot)
        {
            // From the start on, the race goes forward: never back to the start, nor from the line to the race.
            if (!Seen.IsEmpty() && T > 0. && (A.Shot == EShot::Start || (uint8(Seen.Last()) >= uint8(EShot::Line) && uint8(A.Shot) < uint8(Seen.Last()))))
                AddError(FString::Printf(TEXT("Back from %s to %s at t=%.1f"), RacingTv::ShotName(Seen.Last()), RacingTv::ShotName(A.Shot), T));
            Seen.Add(A.Shot);
        }
        TestTrue(TEXT("A sane field of view"), A.Fov >= 4.f && A.Fov <= 90.f);
        // The leader in front of the camera, inside the frame.
        int32 Leader = 0;
        double Lead = -1e9;
        for (int32 I = 0; I < Race.Runners.Num(); ++I)
        {
            const double D = RacingMotion::Distance(Race.Runners[I].Plan(Race.Distance), T);
            if (D > Lead) { Lead = D; Leader = I; }
        }
        FVector Where;
        float Yaw = 0.f;
        double Speed = 0.;
        Service->RunnerAt(Race, Leader, Race.Start + T, Where, Yaw, Speed);
        const FVector L = (A.Aim - A.Eye).Rotation().UnrotateVector(Where + FVector(0., 0., 130.) - A.Eye);
        // The leader is filmed during the race (the build-up films the stands and the paddock too).
        if (T < 6. || A.Shot == EShot::Aerial) continue;
        ++Samples;
        if (L.X > 0. && FMath::RadiansToDegrees(FMath::Atan(FMath::Abs(L.Y) / L.X)) <= A.Fov * .5f) ++Framed;
    }
    FString Order;
    for (const EShot S : Seen) Order += FString(Order.IsEmpty() ? TEXT("") : TEXT(" > ")) + RacingTv::ShotName(S);
    AddInfo(TEXT("Shots: ") + Order);
    for (const EShot S : {EShot::Course, EShot::Stands, EShot::Crowd, EShot::Lineup, EShot::Start, EShot::Travelling, EShot::Aerial, EShot::Line, EShot::Finish})
        TestTrue(FString::Printf(TEXT("The %s shot is used: %s"), RacingTv::ShotName(S), *Order), Seen.Contains(S));
    // The leader is always in frame but for the line (fixed on the post, the field enters it) and the pull-up (the group).
    TestTrue(FString::Printf(TEXT("The leader is in frame most of the time (%d of %d)"), Framed, Samples), Framed >= Samples * 3 / 4);
    return true;
}
#endif
