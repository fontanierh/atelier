#include "HRTestUtil.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

// Riders: three per stable, looks, careers on the rider clock, transfers, legends and their limits.

namespace
{
	int32 ActiveLegends(const FHRWorldState& S, const FString& Legend)
	{
		int32 N = 0;
		for (const TPair<FString, FHRRider>& It : S.Riders) N += It.Value.Legend == Legend && !It.Value.IsRetired() ? 1 : 0;
		return N;
	}

	const TCHAR* const LegendIds[4] = {TEXT("sprinter"), TEXT("flyer"), TEXT("maestro"), TEXT("stayer")};
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRRiderCareerTest, "Atelier.HorseRacing.Riders.Career", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRRiderCareerTest::RunTest(const FString&)
{
	FHRWorldState S = HRRules::CreateWorld(TEXT("riders-1"));
	TestEqual(TEXT("deterministic world"), HRTest::ToJson(S), HRTest::ToJson(HRRules::CreateWorld(TEXT("riders-1"))));

	// Three jockeys per stable, on race days too.
	for (const FHRStable& St : S.Stables)
		TestEqual(St.Id + TEXT(" keeps three riders"), HRRules::StableRiders(S, St.Id).Num(), HRRules::RidersPerStable);
	int32 Ridden = 0, Runners = 0;
	for (const FHRRace& R : S.Meeting.Races)
		for (const FHRRunner& E : R.Entries) { Runners++; Ridden += HRRules::RiderOf(S, E.HorseId) ? 1 : 0; }
	TestTrue(TEXT("most runners have their stable's rider"), Runners > 0 && Ridden * 10 >= Runners * 8);
	for (const TPair<FString, FString>& It : S.Meeting.Riders)
		TestEqual(TEXT("a rider rides for the horse's stable"), S.Riders[It.Value].OwnerId, S.Horses[It.Key].OwnerId);

	// Looks: women and men, small and tall; names unique among active riders.
	int32 Women = 0, MinH = 999, MaxH = 0;
	TSet<FString> Names;
	for (const TPair<FString, FHRRider>& It : S.Riders)
	{
		const FHRRider& R = It.Value;
		if (R.IsRetired()) continue;
		Women += R.bFemale ? 1 : 0;
		MinH = FMath::Min(MinH, R.Height);
		MaxH = FMath::Max(MaxH, R.Height);
		bool bDup = false;
		Names.Add(R.FullName(), &bDup);
		TestFalse(TEXT("unique name ") + R.FullName(), bDup);
	}
	TestTrue(TEXT("both sexes"), Women > 0 && Women < Names.Num());
	TestTrue(TEXT("heights vary by 15 cm or more"), MaxH - MinH >= 15);

	// Reload: the JSON round trip plays on identically.
	FHRWorldState Reloaded;
	TestTrue(TEXT("json reload"), HRSave::FromJson(HRTest::ToJson(S), Reloaded));
	HRRules::AdvanceDay(S);
	HRRules::AdvanceDay(Reloaded);
	TestEqual(TEXT("reloaded world continues identically"), HRTest::ToJson(Reloaded), HRTest::ToJson(S));

	// Thirty seasons: riders retire, move and sign; rosters stay full; legends stay unique; wages stay fixed.
	TSet<FString> KnownLegends;
	for (const TPair<FString, FHRRider>& It : S.Riders) if (!It.Value.Legend.IsEmpty()) KnownLegends.Add(It.Key);
	for (int32 Day = 0; Day < 30 * HRClock::DaysPerSeason; ++Day)
	{
		const TMap<FString, int32> Cooldowns = S.LegendCooldownUntil;
		TMap<FString, TPair<FString, int32>> Contracts;
		for (const TPair<FString, FHRRider>& It : S.Riders) Contracts.Add(It.Key, TPair<FString, int32>(It.Value.OwnerId, It.Value.Wage));
		HRRules::AdvanceDay(S);
		for (const TCHAR* L : LegendIds) TestTrue(FString(L) + TEXT(" at most once"), ActiveLegends(S, L) <= 1);
		for (const TPair<FString, FHRRider>& It : S.Riders)
		{
			const TPair<FString, int32>* Was = Contracts.Find(It.Key);
			if (Was && !It.Value.IsRetired() && !Was->Key.IsEmpty() && Was->Key == It.Value.OwnerId)
				TestEqual(TEXT("a salary is fixed for the length of a contract"), It.Value.Wage, Was->Value);
			if (It.Value.Legend.IsEmpty() || KnownLegends.Contains(It.Key)) continue;
			KnownLegends.Add(It.Key);
			TestTrue(It.Value.Legend + TEXT(" not reborn during its cooldown"), S.T >= Cooldowns.FindRef(It.Value.Legend));
		}
		for (const FHRStable& St : S.Stables)
			if (St.IsComputer()) TestEqual(St.Id + TEXT(" keeps three riders"), HRRules::StableRiders(S, St.Id).Num(), HRRules::RidersPerStable);
	}
	int32 Transfers = 0, Retired = 0, Free = 0;
	for (const FHRNews& N : S.News) Transfers += N.Kind == TEXT("transfer") ? 1 : 0;
	for (const TPair<FString, FHRRider>& It : S.Riders)
	{
		Retired += It.Value.IsRetired() ? 1 : 0;
		Free += !It.Value.IsRetired() && It.Value.OwnerId.IsEmpty() ? 1 : 0;
	}
	AddInfo(FString::Printf(TEXT("30 seasons: %d riders, %d retired, %d free agents, %d transfers in the recent news"), S.Riders.Num(), Retired, Free, Transfers));
	// Riders age on the horse clock (one year a week): thirty seasons are about four rider years, so only a few retire.
	TestTrue(TEXT("riders retire"), Retired >= 1);
	for (const TPair<FString, FHRRider>& It : S.Riders)
		if (!It.Value.IsRetired()) TestTrue(TEXT("no active rider past retirement age"), HRRules::RiderAgeMonths(It.Value, S.T) < It.Value.RetireAge);
	TestTrue(TEXT("riders are transferred"), Transfers >= 1);

	// Career curves, rider month by rider month: growth, a peak, then a decline before retirement.
	int32 Shaped = 0, Measured = 0;
	const FHRWorldState Young = HRRules::CreateWorld(TEXT("riders-2"));
	for (const TPair<FString, FHRRider>& It : Young.Riders)
	{
		FHRRider R = It.Value;
		int32 Age = HRRules::RiderAgeMonths(R, Young.T);
		if (Age >= R.PeakAge) continue;
		Measured++;
		int32 Best = HRRules::RiderOverall(R), BestAge = Age;
		for (; Age < R.RetireAge; ++Age)
		{
			HRRules::StepRiderCurve(R, Age, 1);
			if (HRRules::RiderOverall(R) > Best) { Best = HRRules::RiderOverall(R); BestAge = Age; }
		}
		Shaped += Best >= HRRules::RiderOverall(R) + 2 && BestAge >= 20 * 12 ? 1 : 0;
	}
	AddInfo(FString::Printf(TEXT("%d/%d full careers peaked then declined"), Shaped, Measured));
	TestTrue(TEXT("careers peak then decline"), Measured > 0 && Shaped * 10 >= Measured * 8);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRRiderLegendTest, "Atelier.HorseRacing.Riders.Legends", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRRiderLegendTest::RunTest(const FString&)
{
	// Specialties.
	FHRRider R;
	R.Skill = {500, 500, 500, 500};
	R.DebutT = 0;
	for (int32 Stage = 0; Stage < 4; ++Stage) TestEqual(TEXT("an average rider is neutral"), HRRules::RiderBonus(R, Stage, 1200, 0), 0);
	R.Skill = {1000, 100, 1000, 100};
	TestEqual(TEXT("bonus capped at +2"), HRRules::RiderBonus(R, 0, 1200, 0), 2);
	TestEqual(TEXT("bonus capped at -2"), HRRules::RiderBonus(R, 1, 1200, 0), -2);
	R.Skill = {500, 500, 500, 500};
	R.Legend = TEXT("sprinter");
	const int32 Sprint[4] = {1, 2, 4, 6};
	for (int32 Season = 0; Season < 5; ++Season)
		TestEqual(TEXT("the sprinter's exponential start"), HRRules::RiderBonus(R, 0, 1200, Season * HRClock::DaysPerSeason), Sprint[FMath::Min(Season, 3)]);
	TestEqual(TEXT("the sprinter on short races"), HRRules::RiderBonus(R, 1, 900, 3 * HRClock::DaysPerSeason), 6);
	TestEqual(TEXT("not on longer ones"), HRRules::RiderBonus(R, 1, 1200, 3 * HRClock::DaysPerSeason), 0);
	R.Legend = TEXT("flyer");
	TestTrue(TEXT("the flyer: start and composure"), HRRules::RiderBonus(R, 0, 1200, 0) == 3 && HRRules::RiderBonus(R, 2, 1200, 0) == 3 && HRRules::RiderBonus(R, 3, 1200, 0) == 0);
	R.Legend = TEXT("maestro");
	for (int32 Stage = 0; Stage < 4; ++Stage) TestEqual(TEXT("the maestro: every stage"), HRRules::RiderBonus(R, Stage, 1200, 0), 3);
	R.Legend = TEXT("stayer");
	TestTrue(TEXT("the stayer: the finish"), HRRules::RiderBonus(R, 3, 1200, 0) == 5 && HRRules::RiderBonus(R, 3, 1600, 0) == 7 && HRRules::RiderBonus(R, 0, 1600, 0) == 0);
	for (const TCHAR* L : LegendIds) TestFalse(FString(L) + TEXT(" has a title"), HRRules::LegendTitle(L).IsEmpty());

	// Rarity over many worlds: the stable for sale starts with a legend in about one world out of three, a world never
	// starts with two of the same, and every legend shows up somewhere.
	const int32 Worlds = 120;
	int32 ForSaleLegend = 0;
	TMap<FString, int32> Seen;
	for (int32 W = 0; W < Worlds; ++W)
	{
		const FHRWorldState S = HRRules::CreateWorld(FString::Printf(TEXT("legend-%d"), W));
		bool bForSale = false;
		for (const TPair<FString, FHRRider>& It : S.Riders)
		{
			if (It.Value.Legend.IsEmpty()) continue;
			Seen.FindOrAdd(It.Value.Legend)++;
			bForSale |= It.Value.OwnerId == S.Stables[0].Id;
			TestFalse(TEXT("a legend has a drawn name"), It.Value.FirstName.IsEmpty() || It.Value.LastName.IsEmpty());
		}
		ForSaleLegend += bForSale ? 1 : 0;
		for (const TCHAR* L : LegendIds) TestTrue(TEXT("one of each at a time"), ActiveLegends(S, L) <= 1);
	}
	AddInfo(FString::Printf(TEXT("%d worlds: the stable for sale starts with a legend in %d; seen sprinter %d, flyer %d, maestro %d, stayer %d."), Worlds, ForSaleLegend,
		Seen.FindRef(TEXT("sprinter")), Seen.FindRef(TEXT("flyer")), Seen.FindRef(TEXT("maestro")), Seen.FindRef(TEXT("stayer"))));
	TestTrue(TEXT("a legend at the stable for sale: not rare, not always (20-45 %)"), ForSaleLegend * 100 >= Worlds * 20 && ForSaleLegend * 100 <= Worlds * 45);
	for (const TCHAR* L : LegendIds) TestTrue(FString(L) + TEXT(" appears"), Seen.FindRef(L) > 0);

	// Cooldown: a retired legend cannot be drawn again within a season.
	FHRWorldState S = HRRules::CreateWorld(TEXT("legend-cooldown"));
	S.LegendCooldownUntil.Add(TEXT("flyer"), S.T + HRRules::LegendCooldownDays);
	for (TPair<FString, FHRRider>& It : S.Riders)
		if (It.Value.Legend == TEXT("flyer")) It.Value.RetiredT = S.T;
	// Force 100 % legend academy draws across multiple seeds while flyer is on cooldown.
	for (int32 K = 0; K < 12; ++K)
	{
		FHRWorldState Probe = S;
		Probe.Seed = FString::Printf(TEXT("legend-cooldown-probe-%d"), K);
		for (TPair<FString, FHRRider>& It : Probe.Riders)
			if (It.Value.OwnerId == Probe.Stables[0].Id) It.Value.RetiredT = Probe.T;
		TestEqual(TEXT("forced academy signings"), HRRules::SignAcademyRiders(Probe, Probe.Stables[0].Id, 1000), HRRules::RidersPerStable);
		TestEqual(TEXT("forced legend draw never picks flyer during cooldown"), ActiveLegends(Probe, TEXT("flyer")), 0);
	}
	for (int32 Day = 0; Day < HRRules::LegendCooldownDays - 1; ++Day)
	{
		HRRules::AdvanceDay(S);
		TestEqual(TEXT("no flyer during the cooldown"), ActiveLegends(S, TEXT("flyer")), 0);
	}
	return true;
}

// The effect stays small but real: a top rider instead of an average one on the same horse, same fields.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRRiderImpactTest, "Atelier.HorseRacing.Riders.Impact", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRRiderImpactTest::RunTest(const FString&)
{
	const FHRWorldState Base = HRRules::CreateWorld(TEXT("rider-impact"));
	FHRRider Avg;
	Avg.Id = TEXT("probe:avg");
	Avg.Skill = {500, 500, 500, 500};
	FHRRider Top = Avg;
	Top.Id = TEXT("probe:top");
	Top.Skill = {1000, 1000, 1000, 1000};
	int32 Races = 0, WinsAvg = 0, WinsTop = 0;
	for (int32 K = 0; K < 300; ++K)
	{
		for (int32 Side = 0; Side < 2; ++Side)
		{
			FHRWorldState S = Base;
			S.Seed = FString::Printf(TEXT("impact-%d"), K);
			FHRRace* Race = S.Meeting.Races.FindByPredicate([](const FHRRace& R) { return R.Entries.Num() >= 4; });
			if (!TestNotNull(TEXT("a race of four"), Race)) return false;
			S.Riders.Add(Avg.Id, Avg);
			S.Riders.Add(Top.Id, Top);
			S.Meeting.Riders.Reset();
			for (const FHRRunner& E : Race->Entries) S.Meeting.Riders.Add(E.HorseId, Avg.Id);
			const FString Probe = Race->Entries[0].HorseId;
			S.Meeting.Riders.Add(Probe, Side ? Top.Id : Avg.Id);
			HRRules::ResolveRace(S, *Race);
			const bool bWon = Race->Finishes.Num() && Race->Finishes[0].HorseId == Probe;
			(Side ? WinsTop : WinsAvg) += bWon ? 1 : 0;
			Races += Side;
		}
	}
	const double Swing = double(WinsTop - WinsAvg) / Races;
	AddInfo(FString::Printf(TEXT("%d races, wins %d with an average rider, %d with a top rider (swing %.1f %%)."), Races, WinsAvg, WinsTop, Swing * 100.0));
	TestTrue(TEXT("a top rider helps"), WinsTop > WinsAvg);
	TestTrue(TEXT("but stays small (under 15 points of win share)"), Swing < 0.15);
	return true;
}

#endif
