#include "HRBreeds.h"
#include "HRRandom.h"
#include "HRTestUtil.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

// Same seeds as the reference implementation give the same numbers (hash, draws, genomes, abilities, zones, names).
// Ages are re-based on the horse clock: a reference month is HRClock::LifeMonth race days here.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRReferenceParityTest, "Atelier.HorseRacing.Parity.Reference", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRReferenceParityTest::RunTest(const FString&)
{
	const TSharedPtr<FJsonObject> P = HRTest::LoadParity(TEXT("reference-parity.json"));
	if (!TestNotNull(TEXT("parity file"), P.Get())) return false;

	for (const TPair<FString, TSharedPtr<FJsonValue>>& It : P->GetObjectField(TEXT("hashes"))->Values)
	{
		TestEqual(FString::Printf(TEXT("hash(%s)"), *It.Key), (int64)HRRandom::Hash(It.Key), (int64)It.Value->AsNumber());
	}
	for (const TSharedPtr<FJsonValue>& V : P->GetArrayField(TEXT("draws")))
	{
		const TSharedPtr<FJsonObject> D = V->AsObject();
		TestEqual(TEXT("draw"), HRRandom::Draw(D->GetStringField(TEXT("s")), D->GetStringField(TEXT("t")), (int64)D->GetNumberField(TEXT("n"))), (int32)D->GetNumberField(TEXT("v")));
	}
	TestEqual(TEXT("name pool size"), HRContent::HorseNamePool().Num(), (int32)P->GetNumberField(TEXT("poolSize")));
	TestEqual(TEXT("name pool last"), HRContent::HorseNamePool().Last(), P->GetStringField(TEXT("poolLast")));
	const TArray<TSharedPtr<FJsonValue>>& Names = P->GetArrayField(TEXT("names"));
	const TCHAR* NameSeeds[3] = {TEXT("haras-1:a"), TEXT("haras-1:b"), TEXT("z")};
	for (int32 I = 0; I < 3; ++I) TestEqual(TEXT("generated name"), HRContent::GeneratedHorseName(NameSeeds[I]), Names[I]->AsString());

	const TArray<FHRHorse> Generated = HRTest::MakeParityHorses();
	static const TCHAR* const AbilityKeys[4] = {TEXT("acceleration"), TEXT("speed"), TEXT("endurance"), TEXT("composure")};
	static const TCHAR* const Surfaces[3] = {TEXT("firm"), TEXT("soft"), TEXT("sand")};
	const TArray<TSharedPtr<FJsonValue>>& Horses = P->GetArrayField(TEXT("horses"));
	for (int32 I = 0; I < 5; ++I)
	{
		const TSharedPtr<FJsonObject> X = Horses[I]->AsObject();
		const FHRHorse& H = Generated[I];
		const FString What = X->GetStringField(TEXT("id"));
		const int32 Day = HRTest::ParityDays[I];
		const int32 RefBirth = (int32)X->GetNumberField(TEXT("birthT")), RefRetirement = (int32)X->GetNumberField(TEXT("ret"));
		const int32 Birth = Day - (Day - RefBirth) * HRClock::LifeMonth;
		TestEqual(What + TEXT(" sex"), H.bMare ? FString(TEXT("mare")) : FString(TEXT("stallion")), X->GetStringField(TEXT("sex")));
		TestEqual(What + TEXT(" birth (horse clock)"), H.BirthT, Birth);
		TestEqual(What + TEXT(" retirement (horse clock)"), H.ScheduledRetirementT, Birth + (RefRetirement - RefBirth) * HRClock::LifeMonth);
		TestEqual(What + TEXT(" ready one horse year after birth"), H.ReadyT - H.BirthT, HRClock::LifeYear);
		TestEqual(What + TEXT(" trait"), H.Trait, X->GetStringField(TEXT("trait")));
		TestEqual(What + TEXT(" favorite"), FString(Surfaces[H.Favorite]), X->GetStringField(TEXT("favorite")));
		TestEqual(What + TEXT(" difficult"), FString(Surfaces[H.Difficult]), X->GetStringField(TEXT("difficult")));
		TestEqual(What + TEXT(" stress"), H.Stress, (int32)X->GetNumberField(TEXT("stress")));
		TestEqual(What + TEXT(" coat"), TEXT("#") + H.Appearance.Coat, X->GetStringField(TEXT("coat")));
		for (int32 Ab = 0; Ab < 4; ++Ab)
		{
			TestEqual(What + TEXT(" ability"), H.Abilities[Ab], (int32)X->GetObjectField(TEXT("abilities"))->GetNumberField(AbilityKeys[Ab]));
			TestEqual(What + TEXT(" ceiling"), H.Ceilings[Ab], (int32)X->GetObjectField(TEXT("ceilings"))->GetNumberField(AbilityKeys[Ab]));
			TestEqual(What + TEXT(" response"), H.Response[Ab], (int32)FMath::RoundToInt(X->GetObjectField(TEXT("response"))->GetNumberField(AbilityKeys[Ab]) * 100));
		}
		const TArray<TSharedPtr<FJsonValue>>& Zones = X->GetArrayField(TEXT("zones"));
		for (int32 Z = 0; Z < 4; ++Z)
		{
			const TArray<TSharedPtr<FJsonValue>>& V = Zones[Z]->AsArray();
			TestEqual(What + TEXT(" structure"), H.Zones[Z].Structure, (int32)V[0]->AsNumber());
			TestEqual(What + TEXT(" acute"), H.Zones[Z].Acute, (int32)V[1]->AsNumber());
			TestEqual(What + TEXT(" recovery"), H.Zones[Z].Recovery, (int32)V[2]->AsNumber());
			TestEqual(What + TEXT(" adaptation"), H.Zones[Z].Adaptation, (int32)V[3]->AsNumber());
			TestEqual(What + TEXT(" inflammation gene"), H.Zones[Z].InflammationGene, (int32)V[4]->AsNumber());
		}
		// Every reference gene, the 61 visual loci included, exists here with the same alleles.
		int32 Compared = 0;
		const auto& RefGenome = X->GetObjectField(TEXT("genome"))->Values;
		for (const TPair<FString, TSharedPtr<FJsonValue>>& G : RefGenome)
		{
			const FHRGenePair* Pair = H.Genome.Find(G.Key);
			if (!TestNotNull(What + TEXT(" has gene ") + G.Key, Pair)) continue;
			const TArray<TSharedPtr<FJsonValue>>& V = G.Value->AsArray();
			TestTrue(What + TEXT(" gene ") + G.Key, Pair->A == (int32)V[0]->AsNumber() && Pair->B == (int32)V[1]->AsNumber());
			Compared++;
		}
		// The breed gene is this plugin's own (HRBreeds.h): every other gene is the reference's.
		const int32 RefGenes = H.Genome.Num() - (H.Genome.Contains(HRBreeds::Gene) ? 1 : 0);
		TestTrue(What + TEXT(" has the breed gene"), H.Genome.Contains(HRBreeds::Gene));
		TestEqual(What + TEXT(" genes compared"), Compared, RefGenes);
		TestEqual(What + TEXT(" reference gene count"), RefGenome.Num(), RefGenes);
		TestTrue(What + TEXT(" carries the 61 visual loci"), HRVisual::HasAllLoci(H.Genome));
	}
	return true;
}

// The world respects its rules: six runners at most, readiness one horse year after birth, gestation, breeding windows,
// no racing after retirement, deterministic replays and lossless saves.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRWorldRulesTest, "Atelier.HorseRacing.World.Rules", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRWorldRulesTest::RunTest(const FString&)
{
	FHRWorldState S = HRRules::CreateWorld(TEXT("rules-test"));
	TestEqual(TEXT("opens after one earlier season"), S.T, HRClock::DaysPerSeason);
	TestTrue(TEXT("first stable for sale"), S.Stables[0].bForSale);
	TestEqual(TEXT("the stable for sale has no horse"), HRRules::StableHorses(S, S.Stables[0].Id, true).Num(), 0);
	TestEqual(TEXT("no player yet"), S.Players.Num(), 0);
	HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada"));

	TMap<FString, int32> LastFoalAsMother, LastFoalAsFather;
	TArray<int32> FinalSizes;
	int32 CrossBreedings = 0, Sales = 0, Births = 0, Races = 0, GpFinals = 0, Results = 0, Uncontested = 0, Retirements = 0, Listings = 0;
	const int32 StartT = S.T;
	TMap<FString, int32> WinsByStable;
	int32 TotalWins = 0, FavouriteWins = 0, FavouriteRaces = 0;
	TSet<FString> ListedOnce;
	constexpr int32 Days = 48;
	for (int32 Day = 0; Day < Days; ++Day)
	{
		for (const FHRRace& R : S.Meeting.Races)
		{
			TestTrue(TEXT("at most six runners"), R.Entries.Num() <= HRRules::MaxRunners);
			TSet<FString> Unique;
			for (const FHRRunner& E : R.Entries)
			{
				const FHRHorse& H = S.Horses.FindChecked(E.HorseId);
				TestTrue(TEXT("runner is ready"), S.T >= H.ReadyT);
				TestTrue(TEXT("runner not retired"), !H.IsRetired() && S.T < H.ScheduledRetirementT);
				TestTrue(TEXT("runner belongs to its stable"), H.OwnerId == E.StableId);
				TestFalse(TEXT("a stable for sale never runs"), E.StableId == S.Stables[0].Id);
				Unique.Add(E.HorseId);
			}
			TestEqual(TEXT("a horse runs once per race"), Unique.Num(), R.Entries.Num());
		}
		// Favourite (lowest win odds before the race) win rate in this world.
		while (FHRRace* Next = HRRules::NextRace(S))
		{
			FString Favourite;
			double Best = TNumericLimits<double>::Max();
			for (const FHRRunner& E : Next->Entries)
			{
				const double Odds = HRRules::Rapport(S, *Next, E.HorseId);
				if (Odds < Best) { Best = Odds; Favourite = E.HorseId; }
			}
			const FString Key = HRRules::RunNextRace(S);
			const FHRRace* Done = HRRules::FindRace(S, Key);
			if (Done && Done->Status == TEXT("run") && Done->Finishes.Num())
			{
				FavouriteRaces++;
				FavouriteWins += Done->Finishes[0].HorseId == Favourite ? 1 : 0;
			}
		}
		for (const FHRRace& R : S.Meeting.Races)
		{
			Races += R.Status == TEXT("run") ? 1 : 0;
			Uncontested += R.Status == TEXT("uncontested") ? 1 : 0;
			if (R.Status == TEXT("run") && R.Finishes.Num() && !HRRules::IsHeatRound(R.Round))
			{
				WinsByStable.FindOrAdd(R.Finishes[0].StableId)++;
				TotalWins++;
			}
			GpFinals += R.Round == TEXT("final") ? 1 : 0;
			if (R.Round == TEXT("final"))
			{
				int32 Heats = 0;
				for (const FHRRace& X : S.Meeting.Races) Heats += HRRules::IsHeatRound(X.Round) && X.Round != TEXT("barrage") ? 1 : 0;
				FinalSizes.Add(R.Entries.Num());
				for (const FHRRunner& E : R.Entries)
				{
					const bool bRanHeat = S.Meeting.Races.ContainsByPredicate([&E](const FHRRace& X)
					{
						return HRRules::IsHeatRound(X.Round) && X.Entries.ContainsByPredicate([&E](const FHRRunner& Y) { return Y.HorseId == E.HorseId; });
					});
					TestTrue(TEXT("finalists come from the heats"), bRanHeat);
				}
				TestTrue(TEXT("final keeps four runners when the heats allow it"), R.Entries.Num() <= 4 && (Heats < 2 || R.Entries.Num() >= 3));
			}
		}
		const TArray<FHRPregnancy> Before = S.Pregnancies;
		HRRules::AdvanceDay(S);
		TSet<FString> InFoal;
		for (const FHRPregnancy& P : S.Pregnancies)
		{
			TestFalse(TEXT("one pregnancy per mare at a time"), InFoal.Contains(P.MareId));
			InFoal.Add(P.MareId);
			TestEqual(TEXT("gestation lasts three horse months"), P.DueT - P.ConceivedT, HRRules::GestationDays);
			const FHRHorse& M = S.Horses.FindChecked(P.MareId);
			const FHRHorse& F = S.Horses.FindChecked(P.SireId);
			TestTrue(TEXT("conceived within the mare's breeding window"), M.BreedingUntilT < 0 || P.ConceivedT < M.BreedingUntilT);
			TestTrue(TEXT("conceived within the stallion's breeding window"), F.BreedingUntilT < 0 || P.ConceivedT < F.BreedingUntilT);
			if (P.ConceivedT == S.T)
			{
				if (const int32* Prev = LastFoalAsFather.Find(F.Id)) TestTrue(TEXT("stallion cooldown one day"), P.ConceivedT - *Prev >= 1);
				LastFoalAsFather.Add(F.Id, P.ConceivedT);
			}
		}
		for (const TPair<FString, FHRHorse>& It : S.Horses)
		{
			const FHRHorse& H = It.Value;
			TestEqual(TEXT("ready after exactly one horse year"), H.ReadyT - H.BirthT, HRClock::LifeYear);
			if (H.Origin == TEXT("foal") && H.BirthT == S.T)
			{
				Births++;
				const FHRHorse& M = S.Horses.FindChecked(H.Parents[0]);
				const FHRHorse& F = S.Horses.FindChecked(H.Parents[1]);
				TestTrue(TEXT("mother is a mare"), M.bMare);
				TestFalse(TEXT("father is a stallion"), F.bMare);
				const bool bExpected = Before.ContainsByPredicate([&](const FHRPregnancy& P)
				{
					return P.MareId == M.Id && P.SireId == F.Id && P.DueT == S.T && P.ConceivedT == S.T - HRRules::GestationDays && P.BreederId == H.OwnerId;
				});
				TestTrue(TEXT("foal born at the end of its gestation"), bExpected);
				if (const int32* Prev = LastFoalAsMother.Find(M.Id)) TestTrue(TEXT("mare foals at most once per gestation"), H.BirthT - *Prev >= HRRules::GestationDays);
				LastFoalAsMother.Add(M.Id, H.BirthT);
			}
		}
	}
	for (const FHRNews& N : S.News)
	{
		const bool bInWindow = N.T >= StartT;
		CrossBreedings += bInWindow && N.Kind == TEXT("breeding") && N.StableIds.Num() == 2 ? 1 : 0;
		Sales += bInWindow && N.Kind == TEXT("sale") ? 1 : 0;
		Retirements += bInWindow && N.Kind == TEXT("retire") ? 1 : 0;
		Listings += bInWindow && N.Kind == TEXT("listing") && N.HorseIds.Num() ? 1 : 0;
		Results += N.Kind == TEXT("result") || N.Kind == TEXT("upset") || N.Kind == TEXT("title") ? 1 : 0;
		if (N.Kind == TEXT("listing") && N.HorseIds.Num())
		{
			TestFalse(TEXT("a horse's listing is announced once"), ListedOnce.Contains(N.HorseIds[0]));
			ListedOnce.Add(N.HorseIds[0]);
		}
	}
	TestTrue(TEXT("the news reports race results"), Results > 0);
	{
		FString Sizes;
		for (int32 N : FinalSizes) Sizes += FString::Printf(TEXT("%d "), N);
		AddInfo(FString::Printf(TEXT("Grand Prix final sizes: %s"), *Sizes));
	}
	AddInfo(FString::Printf(TEXT("%d days: %d races, %d GP finals, %d births, %d cross-stable breedings, %d sales between stables, %d horses"),
		Days, Races, GpFinals, Births, CrossBreedings, Sales, S.Horses.Num()));
	TestTrue(TEXT("races run"), Races > Days);
	TestEqual(TEXT("one final per Grand Prix"), GpFinals, Days / HRClock::DaysPerSeason * HRClock::GrandPrixPerSeason);
	TestTrue(TEXT("stables breed"), Births > 0);
	TestEqual(TEXT("without bets a player only receives the daily income"), S.Players[TEXT("p1")].Coins, 160 + Days * HRRules::PlayerDailyIncome);
	int32 LiveMin = MAX_int32, LiveMax = 0, LiveSum = 0, CoinsMin = MAX_int32, CoinsMax = 0, TopWins = 0, Computer = 0;
	for (const FHRStable& St : S.Stables)
	{
		if (!St.IsComputer()) continue;
		Computer++;
		int32 Live = 0;
		for (const FHRHorse* H : HRRules::StableHorses(S, St.Id)) Live += H->IsRetired() ? 0 : 1;
		LiveMin = FMath::Min(LiveMin, Live);
		LiveMax = FMath::Max(LiveMax, Live);
		LiveSum += Live;
		CoinsMin = FMath::Min(CoinsMin, St.Coins);
		CoinsMax = FMath::Max(CoinsMax, St.Coins);
		TopWins = FMath::Max(TopWins, WinsByStable.FindRef(St.Id));
	}
	AddInfo(FString::Printf(TEXT("Dashboard (%d days): live horses per stable %d/%.1f/%d (min/mean/max), %d retirements, %d listings, coins %d..%d, top stable %.0f%% of event wins, favourite wins %.0f%% of %d races, %d uncontested races"),
		Days, LiveMin, (double)LiveSum / FMath::Max(1, Computer), LiveMax, Retirements, Listings, CoinsMin, CoinsMax,
		100.0 * TopWins / FMath::Max(1, TotalWins), 100.0 * FavouriteWins / FMath::Max(1, FavouriteRaces), FavouriteRaces, Uncontested));

	// Robustness: a hand-edited field above six runners, or a duplicated runner, is never run.
	{
		FHRWorldState Bad = HRRules::CreateWorld(TEXT("robust-test"));
		FHRRace& R = Bad.Meeting.Races[0];
		const FHRRunner First = R.Entries[0];
		while (R.Entries.Num() <= HRRules::MaxRunners) R.Entries.Add(First);
		HRRules::ResolveRace(Bad, R);
		TestEqual(TEXT("oversized or duplicated field is not run"), R.Status, FString(TEXT("uncontested")));
		TestEqual(TEXT("no finish for an invalid field"), R.Finishes.Num(), 0);
	}

	// Determinism and save round trip.
	FHRWorldState Again = HRRules::CreateWorld(TEXT("rules-test"));
	HRRules::AddPlayer(Again, TEXT("p1"), TEXT("Ada"));
	for (int32 Day = 0; Day < Days; ++Day) HRRules::AdvanceDay(Again);
	TestTrue(TEXT("same seed, same world"), HRTest::ToJson(S) == HRTest::ToJson(Again));
	FHRWorldState Loaded;
	TestTrue(TEXT("save parses"), HRSave::FromJson(HRTest::ToJson(S), Loaded));
	TestTrue(TEXT("save is lossless"), HRTest::ToJson(Loaded) == HRTest::ToJson(S));
	HRRules::AdvanceDay(S);
	HRRules::AdvanceDay(Loaded);
	TestTrue(TEXT("reloaded world continues identically"), HRTest::ToJson(S) == HRTest::ToJson(Loaded));
	return true;
}

// Win bets: limits, refunds, settlement, a pool shared by every player, and no simple strategy wins on average.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRBettingTest, "Atelier.HorseRacing.Betting", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRBettingTest::RunTest(const FString&)
{
	FHRWorldState S = HRRules::CreateWorld(TEXT("bet-test"));
	const FString P1 = TEXT("p1"), P2 = TEXT("p2");
	HRRules::AddPlayer(S, P1, TEXT("Ada"));
	HRRules::AddPlayer(S, P2, TEXT("Bo"));
	const FHRRace& First = S.Meeting.Races[0];
	const FString One = First.Entries[0].HorseId;
	TestFalse(TEXT("unknown player refused"), HRRules::PlaceBet(S, TEXT("nobody"), First.Key, One, 2).IsEmpty());
	TestFalse(TEXT("stake above 10 refused"), HRRules::PlaceBet(S, P1, First.Key, One, 11).IsEmpty());
	TestFalse(TEXT("a horse not declared is refused"), HRRules::PlaceBet(S, P1, First.Key, TEXT("not-a-horse"), 2).IsEmpty());
	const double Before = HRRules::Rapport(S, First, One);
	TestTrue(TEXT("valid ticket"), HRRules::PlaceBet(S, P1, First.Key, One, 10).IsEmpty());
	TestTrue(TEXT("a stake on a horse shortens its odds for everyone"), HRRules::Rapport(S, First, One) < Before);
	TestTrue(TEXT("second ticket"), HRRules::PlaceBet(S, P1, First.Key, First.Entries.Last().HorseId, 10).IsEmpty());
	TestTrue(TEXT("third ticket"), HRRules::PlaceBet(S, P1, First.Key, First.Entries[1].HorseId, 5).IsEmpty());
	TestFalse(TEXT("fourth ticket on a race refused"), HRRules::PlaceBet(S, P1, First.Key, One, 1).IsEmpty());
	TestTrue(TEXT("another player bets on the same race"), HRRules::PlaceBet(S, P2, First.Key, One, 4).IsEmpty());
	TestEqual(TEXT("coins debited"), S.Players[P1].Coins, 160 - 25);
	TestEqual(TEXT("each player has a daily cap"), HRRules::DayStake(S, P2), 4);
	TestFalse(TEXT("daily cap"), HRRules::PlaceBet(S, P1, S.Meeting.Races.Last().Key, S.Meeting.Races.Last().Entries[0].HorseId, 6).IsEmpty());
	const int32 Coins1 = S.Players[P1].Coins, Coins2 = S.Players[P2].Coins;
	HRRules::RunNextRace(S);
	int32 Paid1 = 0, Paid2 = 0;
	for (const FHRTicket& T : S.Tickets)
	{
		TestTrue(TEXT("settled after the race"), T.Status != TEXT("open"));
		(T.PlayerId == P1 ? Paid1 : Paid2) += T.Payout;
	}
	TestEqual(TEXT("payouts credited to their players"), S.Players[P1].Coins - Coins1 + S.Players[P2].Coins - Coins2, Paid1 + Paid2);
	TestFalse(TEXT("no bet on a run race"), HRRules::PlaceBet(S, P1, First.Key, One, 1).IsEmpty());

	// A ticket on a horse that does not start is refunded.
	{
		FHRWorldState W = HRRules::CreateWorld(TEXT("bet-refund"));
		HRRules::AddPlayer(W, P1, TEXT("Ada"));
		FHRRace& R = W.Meeting.Races[0];
		const FString Key = R.Key, Gone = R.Entries.Last().HorseId;
		TestTrue(TEXT("ticket placed"), HRRules::PlaceBet(W, P1, Key, Gone, 3).IsEmpty());
		R.Entries.Pop();  // withdrawn before the off
		HRRules::RunNextRace(W);
		TestEqual(TEXT("non-runner refunded"), W.Tickets.Last().Status, FString(TEXT("refunded")));
		TestEqual(TEXT("stake back"), W.Players[P1].Coins, 160);
	}

	// Return per coin of simple strategies over many race days (no player tickets in the pools).
	int32 Favourite = 0, RacesSeen = 0;
	double Staked = 0, ReturnFav = 0, ReturnSecond = 0, ReturnOutsider = 0;
	TArray<double> Odds;
	for (int32 World = 0; World < 8; ++World)
	{
		FHRWorldState W = HRRules::CreateWorld(FString::Printf(TEXT("probe-%d"), World));
		for (int32 Day = 0; Day < 24; ++Day)
		{
			while (FHRRace* R = HRRules::NextRace(W))
			{
				if (R->Entries.Num() < 3) { HRRules::RunNextRace(W); continue; }
				TArray<TPair<double, FString>> Board;
				for (const FHRRunner& E : R->Entries) Board.Emplace(HRRules::Rapport(W, *R, E.HorseId), E.HorseId);
				Board.Sort([](const TPair<double, FString>& A, const TPair<double, FString>& B) { return A.Key < B.Key; });
				for (const auto& B : Board) Odds.Add(B.Key);
				const FString Key = R->Key;
				HRRules::RunNextRace(W);
				const FHRRace& Done = *HRRules::FindRace(W, Key);
				if (Done.Status != TEXT("run")) continue;
				RacesSeen++;
				Staked += 1;
				const FString Winner = Done.Finishes[0].HorseId;
				Favourite += Winner == Board[0].Value;
				ReturnFav += Winner == Board[0].Value ? FMath::FloorToDouble(10 * Board[0].Key) / 10 : 0;
				ReturnSecond += Winner == Board[1].Value ? FMath::FloorToDouble(10 * Board[1].Key) / 10 : 0;
				ReturnOutsider += Winner == Board.Last().Value ? FMath::FloorToDouble(10 * Board.Last().Key) / 10 : 0;
			}
			HRRules::AdvanceDay(W);
		}
	}
	Odds.Sort();
	const auto Pct = [&Odds](double Q) { return Odds.Num() ? Odds[FMath::Min(Odds.Num() - 1, (int32)(Q * Odds.Num()))] : 0.0; };
	AddInfo(FString::Printf(TEXT("%d races: favourite wins %.0f%%; win odds p10/p50/p90 %.2f/%.2f/%.2f; return per coin: favourite %.2f, second %.2f, outsider %.2f"),
		RacesSeen, 100.0 * Favourite / FMath::Max(1, RacesSeen), Pct(0.1), Pct(0.5), Pct(0.9),
		ReturnFav / Staked, ReturnSecond / Staked, ReturnOutsider / Staked));
	TestTrue(TEXT("no winning favourite strategy"), ReturnFav / Staked < 1.0);
	TestTrue(TEXT("no winning outsider strategy"), ReturnOutsider / Staked < 1.0);
	return true;
}

// The two-run Grand Prix: every race is run twice, each horse is classed on its best time.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRTwoRunsTest, "Atelier.HorseRacing.World.TwoRuns", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRTwoRunsTest::RunTest(const FString&)
{
	FHRWorldState S = HRRules::CreateWorld(TEXT("two-runs-test"));
	int32 TwoRunRaces = 0, BestFromSecond = 0, Reordered = 0;
	for (int32 Day = 0; Day < 36; ++Day)
	{
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		const bool bTwo = E.Runs == 2;
		// Same day replayed from a copy: identical runs (deterministic, reload-safe).
		FHRWorldState Copy = S;
		while (!HRRules::RunNextRace(S).IsEmpty()) {}
		while (!HRRules::RunNextRace(Copy).IsEmpty()) {}
		TestTrue(TEXT("two-run day is deterministic"), HRTest::ToJson(S) == HRTest::ToJson(Copy));
		for (const FHRRace& R : S.Meeting.Races)
		{
			if (R.Status != TEXT("run")) continue;
			if (!bTwo)
			{
				TestEqual(TEXT("single-run race keeps no runs"), R.Runs.Num(), 0);
				continue;
			}
			TwoRunRaces++;
			TestEqual(TEXT("two runs kept"), R.Runs.Num(), 2);
			TestEqual(TEXT("the sprint is 500 m"), R.Distance, 500);
			for (const FHRRaceRun& Run : R.Runs)
			{
				TestEqual(TEXT("every runner runs each run"), Run.Finishes.Num(), R.Entries.Num());
				for (int32 I = 1; I < Run.Finishes.Num(); ++I) TestTrue(TEXT("run order by time"), Run.Finishes[I - 1].TimeUs <= Run.Finishes[I].TimeUs);
			}
			bool bSameAsFirst = true;
			for (int32 I = 0; I < R.Finishes.Num(); ++I)
			{
				const FHRFinish& F = R.Finishes[I];
				bSameAsFirst &= R.Runs[0].Finishes[I].HorseId == F.HorseId;
				if (!TestEqual(TEXT("both run times recorded"), F.RunTimesUs.Num(), 2)) continue;
				TestEqual(TEXT("official time is the best run"), F.TimeUs, FMath::Min(F.RunTimesUs[0], F.RunTimesUs[1]));
				TestEqual(TEXT("best run index"), F.RunTimesUs[F.BestRun], F.TimeUs);
				const FHRFinish* InRun = R.Runs[F.BestRun].Finishes.FindByPredicate([&F](const FHRFinish& X) { return X.HorseId == F.HorseId; });
				TestTrue(TEXT("segments come from the best run"), InRun && InRun->Segments.Num() == F.Segments.Num() && InRun->TimeUs == F.TimeUs);
				if (I) TestTrue(TEXT("official order by best time"), R.Finishes[I - 1].TimeUs <= F.TimeUs);
				TestEqual(TEXT("places in order"), F.Place, I + 1);
				BestFromSecond += F.BestRun == 1 ? 1 : 0;
			}
			Reordered += bSameAsFirst ? 0 : 1;
		}
		HRRules::AdvanceDay(S);
	}
	AddInfo(FString::Printf(TEXT("%d two-run races, %d best times from the second run, %d results differ from the first run"), TwoRunRaces, BestFromSecond, Reordered));

	// Calibration: the public's two-run model (odds) matches the two-run races. One declared heat is resolved under 400
	// different world seeds; each horse's win share is compared with the public's estimate.
	FHRWorldState P = HRRules::CreateWorld(TEXT("two-runs-calibration"));
	for (int32 Guard = 0; Guard < 12 && HRContent::EventForT(P.T).Runs != 2; ++Guard) HRRules::AdvanceDay(P);
	const FHRRace* Heat = HRRules::NextRace(P);
	if (TestNotNull(TEXT("a two-run heat"), Heat))
	{
		const TArray<FHROrderCount> Public = HRRules::PublicOrders(P, *Heat, 400);
		TMap<int32, double> PublicWin, Seen;
		int32 PublicRuns = 0;
		for (const FHROrderCount& O : Public)
		{
			PublicWin.FindOrAdd(FCString::Atoi(*O.Key)) += O.Count;
			PublicRuns += O.Count;
		}
		const FString Key = Heat->Key;
		constexpr int32 Trials = 400;
		for (int32 Trial = 0; Trial < Trials; ++Trial)
		{
			FHRWorldState Q = P;
			Q.Seed = FString::Printf(TEXT("calibration-%d"), Trial);
			HRRules::RunNextRace(Q);
			const FHRRace* Done = HRRules::FindRace(Q, Key);
			if (!Done || Done->Finishes.Num() == 0) continue;
			const int32 Index = Done->Entries.IndexOfByPredicate([Done](const FHRRunner& R) { return R.HorseId == Done->Finishes[0].HorseId; });
			Seen.FindOrAdd(Index) += 1;
		}
		double Worst = 0;
		for (int32 I = 0; I < Heat->Entries.Num(); ++I)
		{
			const double A = PublicWin.FindRef(I) / FMath::Max(1, PublicRuns), B = Seen.FindRef(I) / Trials;
			Worst = FMath::Max(Worst, FMath::Abs(A - B));
		}
		AddInfo(FString::Printf(TEXT("two-run calibration: largest win-share gap public vs races %.3f"), Worst));
		TestTrue(TEXT("public odds model the two runs"), Worst < 0.07);
	}
	TestTrue(TEXT("two-run Grand Prix days were run"), TwoRunRaces >= 6);
	TestTrue(TEXT("the second run matters"), BestFromSecond > 0 && Reordered > 0);
	return true;
}

// The sprint tournament: qualifying sprints, the best times go to a one-lap final, ties re-run in barrages.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRTournamentTest, "Atelier.HorseRacing.World.Tournament", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRTournamentTest::RunTest(const FString&)
{
	auto ToTournamentDay = [](FHRWorldState& S)
	{
		for (int32 Guard = 0; Guard < 13 && !HRContent::EventForT(S.T).bSprintQualifiers; ++Guard) HRRules::AdvanceDay(S);
	};
	auto QualifTime = [](const FHRWorldState& S, const FString& HorseId) -> int64
	{
		for (const FHRRace& R : S.Meeting.Races)
			if (R.Round == TEXT("qualif"))
				for (const FHRFinish& F : R.Finishes) if (F.HorseId == HorseId) return HRRules::Hundredths(F.TimeUs);
		return -1;
	};
	int32 Days = 0, Barrages = 0;
	for (int32 World = 0; World < 6; ++World)
	{
		FHRWorldState S = HRRules::CreateWorld(FString::Printf(TEXT("tournament-%d"), World));
		ToTournamentDay(S);
		if (!TestTrue(TEXT("a tournament day"), HRContent::EventForT(S.T).bSprintQualifiers)) return false;
		TSet<FString> Contenders;
		for (const FHRRace& R : S.Meeting.Races)
		{
			TestEqual(TEXT("only sprint qualifiers are declared first"), R.Round, FString(TEXT("qualif")));
			TestEqual(TEXT("qualifiers are 600 m sprints"), R.Distance, 600);
			TestTrue(TEXT("six at most per sprint"), R.Entries.Num() <= HRRules::MaxRunners);
			for (const FHRRunner& E : R.Entries)
			{
				bool bTwice = false;
				Contenders.Add(E.HorseId, &bTwice);
				TestFalse(TEXT("each contender runs one sprint"), bTwice);
			}
		}
		// Snapshot when the final is declared (before it is run: the finalists are still fresh).
		while (!HRRules::FindRace(S, TEXT("final:0")) && !HRRules::RunNextRace(S).IsEmpty()) {}
		const FHRWorldState AtDeclare = S;
		while (!HRRules::RunNextRace(S).IsEmpty()) {}
		const FHRRace* Final = HRRules::FindRace(S, TEXT("final:0"));
		if (!TestNotNull(TEXT("final declared"), Final)) continue;
		Days++;
		TestEqual(TEXT("final is one lap"), Final->Distance, 1800);
		TestTrue(TEXT("four finalists at most"), Final->Entries.Num() <= HRContent::SprintFinalists && Final->Entries.Num() >= FMath::Min(3, Contenders.Num()));
		int64 Worst = 0;
		TSet<FString> InFinal;
		for (const FHRRunner& E : Final->Entries)
		{
			TestTrue(TEXT("finalists ran a sprint"), Contenders.Contains(E.HorseId));
			Worst = FMath::Max(Worst, QualifTime(S, E.HorseId));
			InFinal.Add(E.HorseId);
		}
		const bool bBarrage = HRRules::FindRace(S, TEXT("barrage:0")) != nullptr;
		Barrages += bBarrage ? 1 : 0;
		// Without a barrage, nobody faster than the slowest finalist was left out unless it withdrew (tired).
		for (const FString& Id : Contenders)
		{
			if (InFinal.Contains(Id) || bBarrage) continue;
			if (QualifTime(S, Id) < Worst)
			{
				const bool bWithdrew = S.News.ContainsByPredicate([&Id](const FHRNews& N) { return N.HorseIds.Contains(Id) && N.Text.Contains(TEXT("withdraws")); });
				TestTrue(TEXT("a faster sprinter is in the final unless it withdrew"), bWithdrew);
			}
		}

		// Forced tie at the cut: the next sprinter equals the slowest finalist's time -> a barrage between those two.
		if (World > 1) continue;
		FHRWorldState Base = AtDeclare;
		Base.Meeting.Races.RemoveAll([](const FHRRace& R) { return R.Round == TEXT("final") || R.Round == TEXT("barrage"); });
		FString SlowFinalist, NextOut;
		int64 SlowTime = -1, SlowUs = 0;
		for (const FString& Id : InFinal) { const int64 Q = QualifTime(Base, Id); if (Q > SlowTime) { SlowTime = Q; SlowFinalist = Id; } }
		for (const FHRRace& R : Base.Meeting.Races) for (const FHRFinish& F : R.Finishes) if (F.HorseId == SlowFinalist && R.Round == TEXT("qualif")) SlowUs = F.TimeUs;
		TArray<FString> Others;
		for (const FString& Id : Contenders) if (!InFinal.Contains(Id) && QualifTime(Base, Id) >= SlowTime) Others.Add(Id);
		Others.Sort([&](const FString& A, const FString& B) { return QualifTime(Base, A) < QualifTime(Base, B); });
		FHRWorldState T;
		const FHRRace* B = nullptr;
		for (const FString& Id : Others)
		{
			T = Base;
			for (FHRRace& R : T.Meeting.Races) for (FHRFinish& F : R.Finishes) if (F.HorseId == Id && R.Round == TEXT("qualif")) F.TimeUs = SlowUs;
			HRRules::DeclareFinalIfReady(T);
			B = HRRules::FindRace(T, TEXT("barrage:0"));
			if (B) { NextOut = Id; break; }
		}
		if (!TestNotNull(TEXT("a forced tie at the cut declares a barrage"), B)) continue;
		TestEqual(TEXT("barrages take the second last slot"), HRRules::RaceSlot(T, *B), HRRules::DaySlotCount(T) - 2);
		// A tie again in the barrage -> a second barrage.
		FHRWorldState U = T;
		HRRules::RunNextRace(U);
		U.Meeting.Races.RemoveAll([](const FHRRace& R) { return R.Round == TEXT("final"); });
		for (FHRRace& R : U.Meeting.Races) if (R.Key == TEXT("barrage:0")) for (FHRFinish& F : R.Finishes) F.TimeUs = 36000000;
		HRRules::DeclareFinalIfReady(U);
		TestNotNull(TEXT("tie again -> new barrage"), HRRules::FindRace(U, TEXT("barrage:1")));
		// The barrage settles it: four finalists, exactly one of the two tied horses.
		HRRules::RunNextRace(T);
		const FHRRace* F2 = HRRules::FindRace(T, TEXT("final:0"));
		if (TestNotNull(TEXT("final after the barrage"), F2))
		{
			const bool A = F2->Entries.ContainsByPredicate([&](const FHRRunner& E) { return E.HorseId == SlowFinalist; });
			const bool C = F2->Entries.ContainsByPredicate([&](const FHRRunner& E) { return E.HorseId == NextOut; });
			TestTrue(TEXT("one of the tied horses goes to the final"), A != C);
			TestEqual(TEXT("final keeps four"), F2->Entries.Num(), Final->Entries.Num());
			TestEqual(TEXT("the final takes the last slot"), HRRules::RaceSlot(T, *F2), HRRules::DaySlotCount(T) - 1);
		}
	}
	AddInfo(FString::Printf(TEXT("%d tournament days, %d natural barrages"), Days, Barrages));
	return true;
}

#endif
