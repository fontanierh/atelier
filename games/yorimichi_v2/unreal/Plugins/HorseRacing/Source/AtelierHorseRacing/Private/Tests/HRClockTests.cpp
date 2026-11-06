#include "HRClock.h"
#include "HRTestUtil.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRClockScheduleTest, "Atelier.HorseRacing.Clock.Schedule",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FHRClockScheduleTest::RunTest(const FString&)
{
    TestEqual(TEXT("Two real hours per race day"), HRClock::DaySeconds, 7200.);
    TestEqual(TEXT("A season lasts one real day"), HRClock::DaysPerSeason * HRClock::DaySeconds, 86400.);
    TestEqual(TEXT("Horse year lasts one real week"), HRClock::LifeYear * HRClock::DaySeconds, 604800.);
    TestEqual(TEXT("Retired archive interval"), HRClock::ArchiveDays * HRClock::DaySeconds, 172800.);
    TestEqual(TEXT("Before day zero uses floor semantics"), HRClock::DayAt(-1.), -1);
    TestEqual(TEXT("Last instant of day zero"), HRClock::DayAt(7199.99), 0);
    TestEqual(TEXT("Next day starts at the boundary"), HRClock::DayAt(7200.), 1);
    TestEqual(TEXT("Negative day belongs to previous season"), HRClock::SeasonOf(-1), -1);
    TestEqual(TEXT("Negative day index wraps"), HRClock::DayOfSeason(-1), 11);
    TestEqual(TEXT("Age subtraction cannot overflow before division"), HRClock::LifeMonths(MIN_int32, MAX_int32), 613566756);
    int32 GrandPrix = 0;
    for (int32 Day = 0; Day < 12; ++Day)
    {
        const bool Expected = Day == 2 || Day == 5 || Day == 8 || Day == 11;
        TestTrue(TEXT("Reference Grand Prix calendar"), HRClock::IsGrandPrixDay(Day) == Expected);
        GrandPrix += HRClock::IsGrandPrixDay(Day) ? 1 : 0;
    }
    TestEqual(TEXT("Four Grand Prix dates"), GrandPrix, HRClock::GrandPrixPerSeason);
    for (int32 Count : {6,9,14})
        for (int32 Slot = 0; Slot < Count; ++Slot)
        {
            const double Start = HRClock::SlotStart(26, Slot, Count);
            const auto Before = HRClock::ScheduleAt(Start - 1e-6, Count);
            const auto At = HRClock::ScheduleAt(Start, Count);
            TestEqual(TEXT("Exact boundary selects the new slot"), At.Slot, Slot);
            TestEqual(TEXT("Before the boundary retains the preceding slot"), Before.Slot, FMath::Max(0, Slot - 1));
            TestTrue(TEXT("Boundary starts running"), At.Phase == HRClock::EHRRacePhase::Running);
            TestTrue(TEXT("Running phase is half open"), HRClock::PhaseAt(Start, Start + HRClock::RaceSeconds) == HRClock::EHRRacePhase::Finished);
            TestTrue(TEXT("A slot finishes within its day"), Start + HRClock::RaceSeconds < HRClock::DayStart(27));
        }
    TestEqual(TEXT("Grand Prix reserves final and barrage slots"), HRClock::SlotCount(5, true), 7);
    TestEqual(TEXT("Small meetings retain six slots"), HRClock::SlotCount(2, false), 6);
    HRClock::FSlot Large;
    TestTrue(TEXT("Large schedule is searched in bounded work"), HRClock::TryScheduleAt(3000., MAX_int32, Large));
    TestTrue(TEXT("Large schedule upper bound is correct"), Large.Start <= 3000. &&
        HRClock::SlotStart(0, Large.Slot + 1, MAX_int32) > 3000.);
    HRClock::FSlot Out;
    Out.T = 73;
    for (double Time : {std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(),
             -std::numeric_limits<double>::infinity(), HRClock::DayStart(MAX_int32) + HRClock::DaySeconds,
             HRClock::DayStart(MIN_int32) - HRClock::DaySeconds})
    {
        TestFalse(TEXT("Invalid external time is rejected"), HRClock::TryScheduleAt(Time, 6, Out));
        TestEqual(TEXT("Failed admission preserves the output"), Out.T, 73);
    }
    TestFalse(TEXT("Negative counts are rejected"), HRClock::TryScheduleAt(0., -1, Out));
    TestEqual(TEXT("Bad count preserves the output"), Out.T, 73);
    return true;
}

using HRClock::EHRRacePhase;

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRAdvanceToTest, "Atelier.HorseRacing.Clock.AdvanceTo",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRAdvanceToTest::RunTest(const FString&)
{
    FHRWorldState W = HRRules::CreateWorld(TEXT("clock-1"));
    constexpr int64 Now = 1'800'000'000;
    HRRules::StartClock(W, Now);
    TestEqual(TEXT("the clock anchor"), HRRules::WorldSeconds(W, (double)Now), HRClock::DayStart(W.T));
    TestEqual(TEXT("an hour later"), HRRules::WorldSeconds(W, (double)Now + 3600), HRClock::DayStart(W.T) + 3600);
    const int32 T0 = W.T;

    FHRWorldState A = W;
    HRRules::AdvanceTo(A, HRClock::DayStart(T0) + 599);
    TestTrue(TEXT("no race before the first slot"), !A.Meeting.Races[0].IsRun());
    const FString First = A.Meeting.Races[0].Key;
    const double Start = HRRules::RaceStartSeconds(A, First);
    TestEqual(TEXT("the first race's start"), Start, HRClock::SlotStart(T0, 0, HRRules::DaySlotCount(A)));
    TestTrue(TEXT("upcoming"), HRRules::RacePhase(A, First, Start - 1) == EHRRacePhase::Upcoming);
    HRRules::AdvanceTo(A, Start);
    TestTrue(TEXT("the first race is run at its start"), A.Meeting.Races[0].IsRun());
    if (A.Meeting.Races.Num() > 1) TestFalse(TEXT("the second one is not yet"), A.Meeting.Races[1].IsRun());
    TestTrue(TEXT("running"), HRRules::RacePhase(A, First, Start + 1) == EHRRacePhase::Running);
    TestTrue(TEXT("finished"), HRRules::RacePhase(A, First, Start + HRClock::RaceSeconds) == EHRRacePhase::Finished);
    TestEqual(TEXT("still the same day"), A.T, T0);

    // Three days at once, step by step every ten minutes, or day by day: the same world.
    const double Target = HRClock::DayStart(T0 + 3) + 1;
    FHRWorldState B = W, C = W, D = W;
    HRRules::AdvanceTo(B, Target);
    for (double S = HRClock::DayStart(T0); S <= Target; S += 600) HRRules::AdvanceTo(C, S);
    HRRules::AdvanceTo(C, Target);
    for (int32 K = 0; K < 3; ++K) HRRules::AdvanceDay(D);
    HRRules::AdvanceTo(D, Target);
    TestEqual(TEXT("three days later"), B.T, T0 + 3);
    TestTrue(TEXT("catching up equals stepping"), HRTest::ToJson(B) == HRTest::ToJson(C));
    TestTrue(TEXT("catching up equals closing day by day"), HRTest::ToJson(B) == HRTest::ToJson(D));
    const FString Once = HRTest::ToJson(B);
    HRRules::AdvanceTo(B, Target);
    HRRules::AdvanceTo(B, Target - 3600);
    TestTrue(TEXT("idempotent, and the clock never runs back"), HRTest::ToJson(B) == Once);

    // A Grand Prix day: the final appears once the heats are run and runs in the last slot.
    FHRWorldState G = W;
    int32 GpDay = G.T;
    while (!HRClock::IsGrandPrixDay(GpDay)) ++GpDay;
    HRRules::AdvanceTo(G, HRClock::DayStart(GpDay));
    const int32 Count = HRRules::DaySlotCount(G);
    HRRules::AdvanceTo(G, HRClock::SlotStart(GpDay, Count - 2, Count) - 1);
    TestTrue(TEXT("every heat is run"), !G.Meeting.Races.ContainsByPredicate([](const FHRRace& R) { return HRRules::IsHeatRound(R.Round) && R.Round != TEXT("barrage") && !R.IsRun(); }));
    const FHRRace* Final = HRRules::FindRace(G, TEXT("final:0"));
    if (TestNotNull(TEXT("the final is declared after the heats"), Final))
    {
        TestFalse(TEXT("but not run before its slot"), Final->IsRun());
        TestEqual(TEXT("in the last slot"), HRRules::RaceSlot(G, *Final), Count - 1);
        HRRules::AdvanceTo(G, HRClock::SlotStart(GpDay, Count - 1, Count));
        TestTrue(TEXT("run at its slot"), HRRules::FindRace(G, TEXT("final:0"))->IsRun());
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRAgeingTest, "Atelier.HorseRacing.Clock.Ageing",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRAgeingTest::RunTest(const FString&)
{
    FHRWorldState S = HRRules::CreateWorld(TEXT("ageing-1"));
    const FHRHorse* Mare = nullptr;
    const FHRHorse* Sire = nullptr;
    for (const TPair<FString, FHRHorse>& It : S.Horses)
    {
        if (It.Value.bMare && !Mare) Mare = &It.Value;
        if (!It.Value.bMare && !Sire) Sire = &It.Value;
    }
    if (!TestTrue(TEXT("parents"), Mare && Sire)) return false;
    HRRules::FGenerationOptions O;
    O.Id = TEXT("ageing:foal");
    O.Seed = TEXT("ageing-1:foal");
    O.OwnerId = Mare->OwnerId;
    O.T = S.T;
    O.Origin = TEXT("foal");
    O.Mother = Mare;
    O.Father = Sire;
    FHRHorse Foal = HRRules::GenerateHorse(O);
    TestEqual(TEXT("born today"), Foal.BirthT, S.T);
    TestEqual(TEXT("an adult one real week after its birth"), HRClock::DayStart(Foal.ReadyT) - HRClock::DayStart(Foal.BirthT), 7.0 * 24 * 3600);
    TestFalse(TEXT("not ready the day before"), HRRules::Runnable(Foal, Foal.ReadyT - 1));
    TestTrue(TEXT("ready on its first birthday"), HRRules::Runnable(Foal, Foal.ReadyT));
    TestEqual(TEXT("twelve horse months old after a week"), HRRules::HorseAgeMonths(Foal, Foal.ReadyT), 12);
    TestEqual(TEXT("one horse month is fourteen real hours"), HRClock::LifeMonth * HRClock::DaySeconds, 14.0 * 3600);
    const int32 CareerDays = Foal.ScheduledRetirementT - Foal.ReadyT;
    TestTrue(TEXT("a career of six to nine horse years (weeks)"), CareerDays % HRClock::LifeYear == 0 && CareerDays >= 6 * HRClock::LifeYear && CareerDays <= 9 * HRClock::LifeYear);
    TestEqual(TEXT("a newborn looks like a foal"), HRVisual::ResolvePhenotypeAt(Foal, Foal.BirthT).Juvenile, 1.0);
    TestTrue(TEXT("a yearling still grows"), HRVisual::ResolvePhenotypeAt(Foal, Foal.ReadyT).Juvenile > 0);
    TestEqual(TEXT("fully grown at two horse years (two weeks)"), HRVisual::ResolvePhenotypeAt(Foal, Foal.BirthT + 2 * HRClock::LifeYear).Juvenile, 0.0);
    TestEqual(TEXT("gestation: three horse months, 42 real hours"), HRRules::GestationDays * HRClock::DaySeconds, 42.0 * 3600);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRArchiveTest, "Atelier.HorseRacing.Clock.Archive",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRArchiveTest::RunTest(const FString&)
{
    FHRWorldState S = HRRules::CreateWorld(TEXT("archive-1"));
    FHRHorse H = S.Horses.CreateConstIterator()->Value;
    const int32 T0 = S.T;
    HRRules::Retire(H, T0);
    TestTrue(TEXT("retired"), H.IsRetired() && H.Placement == TEXT("retired"));
    HRRules::AdvanceHorse(H, T0 + HRClock::ArchiveDays - 1);
    TestEqual(TEXT("not archived 46 hours later"), H.Placement, FString(TEXT("retired")));
    HRRules::AdvanceHorse(H, T0 + HRClock::ArchiveDays);
    TestEqual(TEXT("archived 48 hours later"), H.Placement, FString(TEXT("archive")));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRSaveTest, "Atelier.HorseRacing.Save.RoundTrip",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRSaveTest::RunTest(const FString&)
{
    FHRWorldState S = HRRules::CreateWorld(TEXT("save-1"));
    HRRules::StartClock(S, 1'800'000'000);
    HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada")).Coins = 1000;
    HRRules::AddPlayer(S, TEXT("p2"), TEXT("Bo")).Coins = 1000;
    TestTrue(TEXT("p1 buys the stable for sale"), HRRules::BuyStable(S, TEXT("p1"), S.Stables[0].Id, true).IsEmpty());
    TestTrue(TEXT("p2 founds one"), HRRules::FoundStable(S, TEXT("p2"), TEXT("Blue Barn"), TEXT("3366cc")).IsEmpty());
    const FHRRace& R = S.Meeting.Races[0];
    TestTrue(TEXT("a bet"), HRRules::PlaceBet(S, TEXT("p2"), R.Key, R.Entries[0].HorseId, 5).IsEmpty());
    HRRules::AdvanceTo(S, HRClock::SlotStart(S.T, 1, HRRules::DaySlotCount(S)));

    const FString Json = HRSave::ToJson(S);
    FHRWorldState Loaded;
    TestTrue(TEXT("parses"), HRSave::FromJson(Json, Loaded));
    TestEqual(TEXT("lossless"), HRSave::ToJson(Loaded), Json);
    TestEqual(TEXT("players kept"), Loaded.Players.Num(), 2);
    TestEqual(TEXT("clock anchor kept"), Loaded.EpochUnix, S.EpochUnix);
    TestEqual(TEXT("the owner kept"), Loaded.Stables[0].OwnerPlayerId, FString(TEXT("p1")));
    const double Later = HRClock::DayStart(S.T + 2) + 2000;
    HRRules::AdvanceTo(S, Later);
    HRRules::AdvanceTo(Loaded, Later);
    TestEqual(TEXT("the reloaded world plays on identically"), HRSave::ToJson(Loaded), HRSave::ToJson(S));
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRDeterminismTest, "Atelier.HorseRacing.Determinism",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRDeterminismTest::RunTest(const FString&)
{
    const FHRWorldState A = HRRules::CreateWorld(TEXT("same-seed"));
    const FHRWorldState B = HRRules::CreateWorld(TEXT("same-seed"));
    TestTrue(TEXT("same seed, same world"), HRTest::ToJson(A) == HRTest::ToJson(B));
    TestFalse(TEXT("another seed, another world"), HRTest::ToJson(A) == HRTest::ToJson(HRRules::CreateWorld(TEXT("other-seed"))));
    return true;
}
#endif
