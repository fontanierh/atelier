#include "HRTestUtil.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

// A player as an owner: buying a stable, the market, entries, riders and wages, riding their own horses (the player's
// rider skill), training sessions and breeding.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHROwnerTest, "Atelier.HorseRacing.Owner.Stable", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHROwnerTest::RunTest(const FString&)
{
	const FString Me = TEXT("p1");
	FHRWorldState S = HRRules::CreateWorld(TEXT("owner-1"));
	HRRules::AddPlayer(S, Me, TEXT("Ada"));
	const FString ForSale = S.Stables[0].Id;
	TestFalse(TEXT("too poor at arrival"), HRRules::BuyStable(S, Me, ForSale, true).IsEmpty());
	TestTrue(TEXT("no stable yet"), HRRules::PlayerStable(S, Me) == nullptr);
	S.Players[Me].Coins = 500;
	const int32 Before = S.Players[Me].Coins;
	const int32 Staff = HRRules::StableRiders(S, ForSale).Num();
	TestEqual(TEXT("the stable for sale keeps three riders"), Staff, HRRules::RidersPerStable);
	TestFalse(TEXT("a computer stable is not for sale"), HRRules::BuyStable(S, Me, S.Stables[1].Id, true).IsEmpty());
	TestTrue(TEXT("bought"), HRRules::BuyStable(S, Me, ForSale, true).IsEmpty());
	const FHRStable* St = HRRules::PlayerStable(S, Me);
	if (!TestNotNull(TEXT("player stable"), St)) return false;
	TestEqual(TEXT("price paid"), S.Players[Me].Coins, Before - HRRules::StablePrice);
	TestEqual(TEXT("one starter horse"), HRRules::StableHorses(S, St->Id).Num(), 1);
	TestEqual(TEXT("riders kept"), HRRules::StableRiders(S, St->Id).Num(), Staff);
	TestFalse(TEXT("keeping riders: they ride"), S.Players[Me].bRides);
	TestFalse(TEXT("one stable per player"), HRRules::FoundStable(S, Me, TEXT("Second"), FString()).IsEmpty());

	// Without riders: they become free agents and the player rides.
	FHRWorldState S2 = HRRules::CreateWorld(TEXT("owner-1"));
	HRRules::AddPlayer(S2, Me, TEXT("Ada")).Coins = 500;
	TestTrue(TEXT("bought without riders"), HRRules::BuyStable(S2, Me, ForSale, false).IsEmpty());
	TestEqual(TEXT("no riders"), HRRules::StableRiders(S2, ForSale).Num(), 0);
	TestTrue(TEXT("the owner rides"), S2.Players[Me].bRides);

	// Market: a recruit, then a race day: the player's horses race and the player rides them.
	S2.Players[Me].Coins = 500;
	TestTrue(TEXT("recruit bought"), HRRules::BuyHorse(S2, Me, TEXT("market:adult")).IsEmpty());
	TestFalse(TEXT("same recruit twice"), HRRules::BuyHorse(S2, Me, TEXT("market:adult")).IsEmpty());
	TestEqual(TEXT("one recruit left on today's market"), HRRules::MarketRecruits(S2, Me).Num(), 1);
	TestEqual(TEXT("two horses"), HRRules::StableHorses(S2, ForSale).Num(), 2);
	HRRules::AdvanceDay(S2);
	int32 Mine = 0, Ridden = 0;
	for (const FHRRace& R : S2.Meeting.Races)
		for (const FHRRunner& E : R.Entries)
			if (E.StableId == ForSale) { ++Mine; Ridden += E.RiderPlayerId == Me ? 1 : 0; }
	TestTrue(TEXT("the player's horses are entered"), Mine >= 1);
	TestEqual(TEXT("the player rides every runner"), Ridden, Mine);

	// One of the player's horses per race: give the stable more horses than there are races.
	{
		FHRWorldState M = S2;
		for (int32 K = 0; K < 3; ++K)
		{
			M.Players[Me].Coins = 2000;
			HRRules::BuyHorse(M, Me, TEXT("market:adult"));
			HRRules::BuyHorse(M, Me, TEXT("market:prospect"));
			HRRules::AdvanceDay(M);
		}
		for (int32 Day = 0; Day < 12; ++Day)
		{
			M.Players[Me].Coins = FMath::Max(M.Players[Me].Coins, 500);
			for (const FHRRace& R : M.Meeting.Races)
			{
				int32 N = 0;
				for (const FHRRunner& E : R.Entries) N += E.StableId == ForSale ? 1 : 0;
				TestTrue(FString::Printf(TEXT("at most one of the player's horses in %s (day %d)"), *R.Key, Day), N <= 1);
			}
			while (!HRRules::RunNextRace(M).IsEmpty())
				for (const FHRRace& R : M.Meeting.Races)
				{
					int32 N = 0;
					for (const FHRRunner& E : R.Entries) N += E.StableId == ForSale ? 1 : 0;
					TestTrue(TEXT("also in finals"), N <= 1);
				}
			HRRules::AdvanceDay(M);
		}
	}

	// Resting horses sit the race day out.
	for (const FHRHorse* H : HRRules::StableHorses(S2, ForSale)) HRRules::SetResting(S2, Me, H->Id, true);
	HRRules::AdvanceDay(S2);
	TestEqual(TEXT("resting horses do not run"), HRTest::EntriesOf(S2, ForSale), 0);

	// The player rides: a good ride beats a bad one on the same race (same seed, same field).
	for (const FHRHorse* H : HRRules::StableHorses(S2, ForSale)) HRRules::SetResting(S2, Me, H->Id, false);
	HRRules::AdvanceDay(S2);
	const FHRRace* Race = S2.Meeting.Races.FindByPredicate([&Me](const FHRRace& R) { return HRRules::PlayerRunner(R, Me) != nullptr; });
	TestNotNull(TEXT("a race with the player"), Race);
	if (Race)
	{
		const FString Key = Race->Key, Horse = HRRules::PlayerRunner(*Race, Me)->HorseId;
		auto TimeWith = [&](int32 Skill)
		{
			FHRWorldState C = S2;
			C.Players[Me].RiderSkill.Init(Skill, 4);
			for (int32 G = 0; G < 32 && !HRRules::FindRace(C, Key)->IsRun(); ++G) HRRules::RunNextRace(C);
			const FHRRace* Done = HRRules::FindRace(C, Key);
			const FHRFinish* F = Done->Finishes.FindByPredicate([&](const FHRFinish& X) { return X.HorseId == Horse; });
			return F ? F->TimeUs : 0;
		};
		const int64 Good = TimeWith(950), Bad = TimeWith(50), Avg = TimeWith(HRRules::PlayerStartSkill);
		TestTrue(TEXT("a better rider is faster"), Good > 0 && Good < Avg && Avg < Bad);
		FHRWorldState C = S2;
		const int32 SkillBefore = HRRules::PlayerRiderSkill(C, Me, 0);
		for (int32 G = 0; G < 32 && !HRRules::FindRace(C, Key)->IsRun(); ++G) HRRules::RunNextRace(C);
		const FHRFinish* F = HRRules::FindRace(C, Key)->Finishes.FindByPredicate([&](const FHRFinish& X) { return X.HorseId == Horse; });
		TestTrue(TEXT("the player is named as the rider"), F && F->RiderId == TEXT("player:p1") && F->RiderName == TEXT("Ada"));
		TestEqual(TEXT("riding a race is experience"), HRRules::PlayerRiderSkill(C, Me, 0), SkillBefore + HRRules::PlayerRaceXp);
		TestTrue(TEXT("rides counted"), C.Players[Me].Rides >= 1);
	}

	// Training: a session per horse a day, the grade sets the gain; the staff plays the sessions left.
	{
		FHRWorldState M = S2;
		M.Players[Me].Coins = 100;
		const FHRHorse* Fit = nullptr;
		int32 Ability = -1;
		for (const FHRHorse* H : HRRules::StableHorses(M, ForSale))
			for (int32 A = 0; A < 4 && !Fit; ++A)
				if (HRRules::TrainingRefusal(M, Me, H->Id, A).IsEmpty()) { Fit = H; Ability = A; }
		TestNotNull(TEXT("a horse can train"), Fit);
		if (Fit)
		{
			const FString Id = Fit->Id;
			const int32 Stage = Ability == 0 ? 0 : Ability == 1 ? 1 : Ability == 2 ? 3 : 2;
			auto GainWith = [&](int32 Grade) { FHRWorldState C = M; int32 Gain = 0; HRRules::TrainHorse(C, Me, Id, Ability, Grade, &Gain); return Gain; };
			TestTrue(TEXT("a better exercise trains more"), GainWith(2) > GainWith(0) && GainWith(0) > GainWith(-2) && GainWith(-2) > 0);
			const int32 Coins = M.Players[Me].Coins, Skill = HRRules::PlayerRiderSkill(M, Me, Stage);
			TestTrue(TEXT("trained"), HRRules::TrainHorse(M, Me, Id, Ability, 2).IsEmpty());
			TestEqual(TEXT("a session costs"), M.Players[Me].Coins, Coins - HRRules::TrainingCost);
			TestTrue(TEXT("the player's riding improves"), HRRules::PlayerRiderSkill(M, Me, Stage) > Skill);
			TestFalse(TEXT("once a day per horse"), HRRules::TrainHorse(M, Me, Id, Ability, 2).IsEmpty());
			TestEqual(TEXT("sessions left"), HRRules::TrainingSessionsLeft(M, Me), HRRules::TrainingSlots - 1);
			HRRules::StaffTraining(M);
			TestTrue(TEXT("the staff does the rest"), HRRules::TrainingSessionsLeft(M, Me) <= HRRules::TrainingSlots - 1);
		}
	}

	// Breeding: one of the player's horses with another stable's partner; the fee goes to its owner, the foal is ours.
	{
		FHRWorldState M = S2;
		M.Players[Me].Coins = 1000;
		const FHRHorse* MyHorse = nullptr;
		const FHRHorse* Partner = nullptr;
		for (int32 Day = 0; Day < 30 && !Partner; ++Day)
		{
			for (const FHRHorse* H : HRRules::StableHorses(M, ForSale))
				if (HRRules::BreedingAvailability(M, *H).IsEmpty()) { MyHorse = H; break; }
			if (MyHorse)
				for (const TPair<FString, FHRHorse>& It : M.Horses)
					if (It.Value.OwnerId != ForSale && HRRules::BreedingRefusal(M, Me, *MyHorse, It.Value).IsEmpty()) { Partner = &It.Value; break; }
			if (!Partner) { MyHorse = nullptr; HRRules::AdvanceDay(M); M.Players[Me].Coins = 1000; }
		}
		TestNotNull(TEXT("a pairing is possible"), Partner);
		if (MyHorse && Partner)
		{
			const FString MineId = MyHorse->Id, PartnerId = Partner->Id, OwnerId = Partner->OwnerId;
			const int32 Cost = HRRules::BreedingCost(M, Me, *Partner), Fee = HRRules::BreedingFee(*Partner);
			const int32 OwnerCoins = HRRules::FindStable(M, OwnerId)->Coins;
			const HRRules::FFoalOutlook O = HRRules::FoalOutlook(M, MyHorse->bMare ? *MyHorse : *Partner, MyHorse->bMare ? *Partner : *MyHorse);
			TestTrue(TEXT("outlook ordered"), O.Low[1] <= O.Mid[1] && O.Mid[1] <= O.High[1] && O.High[1] > 0);
			TestTrue(TEXT("bred"), HRRules::BreedPlayer(M, Me, MineId, PartnerId, TEXT("Little Thunder")).IsEmpty());
			TestEqual(TEXT("paid"), M.Players[Me].Coins, 1000 - Cost);
			TestEqual(TEXT("the fee goes to the owner"), HRRules::FindStable(M, OwnerId)->Coins, OwnerCoins + Fee);
			TestFalse(TEXT("one covering a day"), HRRules::BreedPlayer(M, Me, MineId, PartnerId, FString()).IsEmpty());
			for (int32 K = 0; K < HRRules::GestationDays; ++K) { M.Players[Me].Coins = FMath::Max(M.Players[Me].Coins, 300); HRRules::AdvanceDay(M); }
			const FHRHorse* Foal = nullptr;
			for (const TPair<FString, FHRHorse>& It : M.Horses)
				if (It.Value.Parents.Contains(MineId) && It.Value.Parents.Contains(PartnerId)) Foal = &It.Value;
			TestNotNull(TEXT("the foal is born after 21 race days"), Foal);
			TestTrue(TEXT("ours, with its chosen name"), Foal && Foal->OwnerId == ForSale && Foal->Name == TEXT("Little Thunder"));
		}
	}

	// Riders: three at most, wages, an unpaid rider leaves (no debt).
	{
		S2.Players[Me].Coins = 300;
		const TMap<FString, FHRRider> Pool = S2.Riders;  // hiring changes the riders: walk a copy
		for (const TPair<FString, FHRRider>& It : Pool)
		{
			if (HRRules::StableRiders(S2, ForSale).Num() >= HRRules::RidersPerStable) break;
			if (It.Value.OwnerId.IsEmpty() && !It.Value.IsRetired()) TestTrue(TEXT("hired"), HRRules::HireRider(S2, Me, It.Key).IsEmpty());
		}
		HRRules::SignAcademyRiders(S2, ForSale);  // in case the free agents ran out
		TestEqual(TEXT("a full roster"), HRRules::StableRiders(S2, ForSale).Num(), HRRules::RidersPerStable);
		FHRRider* Other = nullptr;
		for (TPair<FString, FHRRider>& It : S2.Riders)
			if (!Other && !It.Value.IsRetired() && !It.Value.OwnerId.IsEmpty() && It.Value.OwnerId != ForSale) Other = &It.Value;
		if (TestNotNull(TEXT("another stable's rider"), Other))
		{
			Other->ListedPrice = 1;
			TestFalse(TEXT("a fourth rider is refused"), HRRules::HireRider(S2, Me, Other->Id).IsEmpty());
			Other->ListedPrice = 0;
		}
		HRRules::SetPlayerRides(S2, Me, false);
		HRRules::AdvanceDay(S2);
		for (const FHRRace& R : S2.Meeting.Races)
			for (const FHRRunner& E : R.Entries)
				if (E.StableId == ForSale) TestTrue(TEXT("the stable's riders ride"), E.RiderPlayerId.IsEmpty() && HRRules::RiderOf(S2, E.HorseId) != nullptr);
		S2.Players[Me].Coins = 0;
		HRRules::CloseOwnerDay(S2, *HRRules::PlayerStable(S2, Me), 0);
		TestTrue(TEXT("unpaid riders leave"), HRRules::StableRiders(S2, ForSale).Num() < HRRules::RidersPerStable);
		TestTrue(TEXT("no debt"), S2.Players[Me].Coins >= 0 && HRRules::PlayerStable(S2, Me)->Debt == 0);
	}

	// A whole season stays consistent and deterministic.
	FHRWorldState A = S, B = S;
	for (int32 Day = 0; Day < HRClock::DaysPerSeason; ++Day) { HRRules::AdvanceDay(A); HRRules::AdvanceDay(B); }
	TestEqual(TEXT("deterministic"), HRTest::ToJson(A), HRTest::ToJson(B));
	TestTrue(TEXT("coins never negative"), A.Players[Me].Coins >= 0);
	return true;
}

// Several players share one world: two own stables (one bought, one founded), a third only bets; horses and riders change
// hands between them for coins, and every player's bet joins the same pool.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRMultiPlayerTest, "Atelier.HorseRacing.Owner.MultiPlayer", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRMultiPlayerTest::RunTest(const FString&)
{
	const FString P1 = TEXT("steam:111"), P2 = TEXT("epic:222"), P3 = TEXT("guest-3");
	FHRWorldState S = HRRules::CreateWorld(TEXT("multi-1"));
	HRRules::AddPlayer(S, P1, TEXT("Ada")).Coins = 1000;
	HRRules::AddPlayer(S, P2, TEXT("Bo")).Coins = 1000;
	HRRules::AddPlayer(S, P3, TEXT("Cy"));
	TestEqual(TEXT("adding a player twice keeps them"), HRRules::AddPlayer(S, P1, TEXT("Other")).Name, FString(TEXT("Ada")));
	TestTrue(TEXT("p1 buys the stable for sale"), HRRules::BuyStable(S, P1, S.Stables[0].Id, true).IsEmpty());
	TestFalse(TEXT("it is no longer for sale"), HRRules::BuyStable(S, P2, S.Stables[0].Id, true).IsEmpty());
	TestTrue(TEXT("p2 founds a stable"), HRRules::FoundStable(S, P2, TEXT("Blue Barn"), TEXT("3366cc")).IsEmpty());
	const FHRStable* A = HRRules::PlayerStable(S, P1);
	const FHRStable* B = HRRules::PlayerStable(S, P2);
	if (!TestTrue(TEXT("two owned stables"), A && B && A != B)) return false;
	const FString IdA = A->Id, IdB = B->Id;
	TestEqual(TEXT("the founded stable's id"), IdB, TEXT("player:") + P2);
	TestEqual(TEXT("three academy riders"), HRRules::StableRiders(S, IdB).Num(), HRRules::RidersPerStable);
	TestTrue(TEXT("p3 owns nothing"), HRRules::PlayerStable(S, P3) == nullptr);
	TestEqual(TEXT("a stable is owned by its player"), HRRules::FindStable(S, IdB)->OwnerPlayerId, P2);

	// Both stables race; each player rides their own runners or puts their riders up. A lone starter sits out the days
	// its tissues are strained, so wait for a day it can start.
	HRRules::SetPlayerRides(S, P2, false);
	HRRules::AdvanceDay(S);
	TestTrue(TEXT("p1's stable races"), HRTest::EntriesOf(S, IdA) >= 1);
	for (int32 Day = 0; Day < HRClock::DaysPerSeason && HRTest::EntriesOf(S, IdB) == 0; ++Day) HRRules::AdvanceDay(S);
	TestTrue(TEXT("p2's stable races within a season"), HRTest::EntriesOf(S, IdB) >= 1);
	for (const FHRRace& R : S.Meeting.Races)
		for (const FHRRunner& E : R.Entries)
		{
			if (E.StableId == IdB) TestTrue(TEXT("p2's riders ride"), E.RiderPlayerId.IsEmpty() && HRRules::RiderOf(S, E.HorseId) != nullptr);
			if (E.StableId != IdA && E.StableId != IdB) TestTrue(TEXT("no player rides a computer horse"), E.RiderPlayerId.IsEmpty());
		}

	// A rider transfer between players: listed by p1, bought by p2 once it has room.
	const FString Rider = HRRules::StableRiders(S, IdA)[0]->Id;
	TestTrue(TEXT("p1 lists a rider"), HRRules::ListRider(S, P1, Rider, true, 40).IsEmpty());
	TestFalse(TEXT("p2's roster is full"), HRRules::HireRider(S, P2, Rider).IsEmpty());
	TestTrue(TEXT("p2 releases one"), HRRules::ReleaseRider(S, P2, HRRules::StableRiders(S, IdB).Last()->Id).IsEmpty());
	const int32 Coins1 = S.Players[P1].Coins, Coins2 = S.Players[P2].Coins;
	TestTrue(TEXT("p2 buys the listed rider"), HRRules::HireRider(S, P2, Rider).IsEmpty());
	TestEqual(TEXT("the rider moves"), S.Riders[Rider].OwnerId, IdB);
	TestEqual(TEXT("p1 is paid"), S.Players[P1].Coins, Coins1 + 40);
	TestEqual(TEXT("p2 pays"), S.Players[P2].Coins, Coins2 - 40);

	// A horse sale between players.
	FString Horse;
	for (const FHRHorse* H : HRRules::StableHorses(S, IdA))
		if (Horse.IsEmpty() && !H->IsRetired() && !H->Injury.bActive) Horse = H->Id;
	TestTrue(TEXT("p1 lists a horse"), HRRules::ListHorse(S, P1, Horse, true).IsEmpty());
	const FHRSaleListing* L = S.Listings.FindByPredicate([&Horse](const FHRSaleListing& X) { return X.HorseId == Horse; });
	if (TestNotNull(TEXT("listed"), L))
	{
		const int32 Price = L->Price, Before1 = S.Players[P1].Coins;
		TestTrue(TEXT("p2 buys it"), HRRules::BuyHorse(S, P2, Horse).IsEmpty());
		TestEqual(TEXT("the horse moves"), S.Horses[Horse].OwnerId, IdB);
		TestEqual(TEXT("p1 receives the price"), S.Players[P1].Coins, Before1 + Price);
	}

	// One pool for everyone: p3's stake shortens the odds p1 sees.
	const FHRRace* Race = S.Meeting.Races.FindByPredicate([](const FHRRace& R) { return !R.IsRun() && R.Entries.Num() >= 2; });
	if (TestNotNull(TEXT("a race to bet on"), Race))
	{
		const FString Key = Race->Key, Pick = Race->Entries[0].HorseId;
		const double Before = HRRules::Rapport(S, *Race, Pick);
		TestTrue(TEXT("p3 bets"), HRRules::PlaceBet(S, P3, Key, Pick, 10).IsEmpty());
		TestTrue(TEXT("the odds shorten for everyone"), HRRules::Rapport(S, *HRRules::FindRace(S, Key), Pick) < Before);
		TestTrue(TEXT("p1 bets on the same race"), HRRules::PlaceBet(S, P1, Key, Pick, 10).IsEmpty());
		TestEqual(TEXT("caps are per player"), HRRules::DayStake(S, P3), 10);
	}

	// The shared world saves and replays for every player.
	FHRWorldState Loaded;
	TestTrue(TEXT("saved and loaded"), HRSave::FromJson(HRSave::ToJson(S), Loaded));
	for (int32 Day = 0; Day < 4; ++Day) { HRRules::AdvanceDay(S); HRRules::AdvanceDay(Loaded); }
	TestEqual(TEXT("identical after four days"), HRSave::ToJson(Loaded), HRSave::ToJson(S));
	for (const TPair<FString, FHRPlayer>& It : S.Players) TestTrue(It.Key + TEXT(" never negative"), It.Value.Coins >= 0);
	return true;
}

#endif
