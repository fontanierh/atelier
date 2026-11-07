#include "HRTestUtil.h"
#include "JsonObjectConverter.h"
#include "Misc/AutomationTest.h"
#include <limits>

#if WITH_DEV_AUTOMATION_TESTS

// Save admission (HRSave::FromJson) and the economy's invariants: settlement, refunds, balances, saturation and bounded
// catch-up.

namespace HRAdmissionTest
{
	/** The horse as the save writes it (one JSON object). */
	FString HorseJson(const FHRHorse& H)
	{
		FString Json;
		FJsonObjectConverter::UStructToJsonObjectString(H, Json, 0, 0, 0, nullptr, false);
		return Json;
	}

	/** Every stable, player and debt within 0..MaxCoins. */
	bool BalancesValid(const FHRWorldState& S, FString& Why)
	{
		for (const FHRStable& St : S.Stables)
			if (St.Coins < 0 || St.Debt < 0 || St.Coins > HRRules::MaxCoins)
			{
				Why = FString::Printf(TEXT("stable %s: coins %d, debt %d"), *St.Id, St.Coins, St.Debt);
				return false;
			}
		for (const TPair<FString, FHRPlayer>& It : S.Players)
			if (It.Value.Coins < 0 || It.Value.Coins > HRRules::MaxCoins)
			{
				Why = FString::Printf(TEXT("player %s: coins %d"), *It.Key, It.Value.Coins);
				return false;
			}
		return true;
	}

	/** The first race of today with a field, run or not. */
	const FHRRace* FieldRace(const FHRWorldState& S, bool bRun)
	{
		return S.Meeting.Races.FindByPredicate([bRun](const FHRRace& R)
		{
			return R.Entries.Num() >= 2 && (bRun ? R.Status == TEXT("run") && R.Finishes.Num() >= 2 : R.Status == TEXT("declared"));
		});
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRSaveAdmissionTest, "Atelier.HorseRacing.Save.Admission", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRSaveAdmissionTest::RunTest(const FString&)
{
	FHRWorldState S = HRRules::CreateWorld(TEXT("admission-1"));
	HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada"));
	HRRules::StartClock(S, 1800000000);
	const FHRRace* Race = HRAdmissionTest::FieldRace(S, false);
	if (!TestNotNull(TEXT("a race to bet on"), Race)) return false;
	TestTrue(TEXT("a ticket"), HRRules::PlaceBet(S, TEXT("p1"), Race->Key, Race->Entries[0].HorseId, 5).IsEmpty());
	const FString Good = HRSave::ToJson(S);
	TestEqual(TEXT("a world of these rules is admissible"), HRSave::Validate(S), FString());
	FHRWorldState Loaded;
	FString Error;
	TestTrue(TEXT("and loads: ") + Error, HRSave::FromJson(Good, Loaded, Error));

	// A refused load names the reason and leaves the destination as it was.
	FHRWorldState Untouched = S;
	const FString Before = HRSave::ToJson(Untouched);
	auto Refused = [&](const TCHAR* What, const FString& Json, const TCHAR* Expected)
	{
		FString Why;
		const bool bLoaded = HRSave::FromJson(Json, Untouched, Why);
		TestFalse(FString::Printf(TEXT("%s is refused"), What), bLoaded);
		TestTrue(FString::Printf(TEXT("%s: the reason (%s) mentions \"%s\""), What, *Why, Expected), Why.Contains(Expected));
		TestTrue(FString::Printf(TEXT("%s leaves the world untouched"), What), HRSave::ToJson(Untouched) == Before);
	};
	auto Mutated = [&S](TFunctionRef<void(FHRWorldState&)> Change)
	{
		FHRWorldState Copy = S;
		Change(Copy);
		return HRSave::ToJson(Copy);
	};
	FString HorseId, ParentlessId, OtherHorseId;
	for (const TPair<FString, FHRHorse>& It : S.Horses)
	{
		if (HorseId.IsEmpty()) HorseId = It.Key;
		if (ParentlessId.IsEmpty() && It.Value.Parents.IsEmpty()) ParentlessId = It.Key;
		else if (OtherHorseId.IsEmpty() && It.Key != ParentlessId) OtherHorseId = It.Key;
	}
	const FString RiderId = S.Riders.CreateConstIterator()->Key;

	// Versions and required fields.
	Refused(TEXT("not JSON"), TEXT("not json"), TEXT("JSON"));
	Refused(TEXT("another rules version"), Mutated([](FHRWorldState& W) { W.RulesVersion = TEXT("atelier-horse-racing-0"); }), TEXT("rules version"));
	Refused(TEXT("another schema version"), Mutated([](FHRWorldState& W) { W.SchemaVersion = 2; }), TEXT("schema version"));
	{
		FString NoHorses = Good;
		NoHorses.ReplaceInline(TEXT("\"horses\":"), TEXT("\"horsez\":"), ESearchCase::CaseSensitive);
		Refused(TEXT("a save without horses"), NoHorses, TEXT("horses"));
	}

	// Unique ids.
	{
		FString Twice = Good;
		const FString Field = FString::Printf(TEXT("\"horses\":{"));
		const int32 At = Twice.Find(Field, ESearchCase::CaseSensitive);
		if (TestTrue(TEXT("the save has a horse map"), At != INDEX_NONE))
		{
			Twice.InsertAt(At + Field.Len(), FString::Printf(TEXT("\"%s\":%s,"), *HorseId, *HRAdmissionTest::HorseJson(S.Horses[HorseId])));
			Refused(TEXT("a horse id twice"), Twice, TEXT("appears twice"));
		}
		FString SeedTwice = Good;
		SeedTwice.InsertAt(1, TEXT("\"seed\":\"other\","));
		Refused(TEXT("a field twice"), SeedTwice, TEXT("appears twice"));
	}
	Refused(TEXT("a stable twice"), Mutated([](FHRWorldState& W) { const FHRStable Copy = W.Stables[1]; W.Stables.Add(Copy); }), TEXT("appears twice"));
	Refused(TEXT("a horse under another id"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].Id = TEXT("someone-else"); }), TEXT("does not match"));
	Refused(TEXT("a race twice"), Mutated([](FHRWorldState& W) { const FHRRace Copy = W.Meeting.Races[0]; W.Meeting.Races.Add(Copy); }), TEXT("appears twice"));
	Refused(TEXT("a ticket twice"), Mutated([](FHRWorldState& W) { const FHRTicket Copy = W.Tickets[0]; W.Tickets.Add(Copy); }), TEXT("appears twice"));

	// Dangling references.
	Refused(TEXT("an unknown owner"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].OwnerId = TEXT("nobody"); }), TEXT("unknown owner"));
	Refused(TEXT("an unknown dam"), Mutated([&ParentlessId](FHRWorldState& W) { W.Horses[ParentlessId].Parents = {TEXT("ghost-a"), TEXT("ghost-b")}; }), TEXT("unknown parent"));
	Refused(TEXT("an unknown rider's stable"), Mutated([&RiderId](FHRWorldState& W) { W.Riders[RiderId].OwnerId = TEXT("nowhere"); }), TEXT("unknown stable"));
	Refused(TEXT("an unknown entrant"), Mutated([](FHRWorldState& W) { W.Meeting.Races[0].Entries[0].HorseId = TEXT("ghost"); }), TEXT("unknown entrant"));
	Refused(TEXT("an unknown race day rider"), Mutated([&HorseId](FHRWorldState& W) { W.Meeting.Riders.Add(HorseId, TEXT("ghost-rider")); }), TEXT("unknown horse or rider"));
	Refused(TEXT("a ticket of an unknown player"), Mutated([](FHRWorldState& W) { W.Tickets[0].PlayerId = TEXT("ghost"); }), TEXT("unknown player"));
	Refused(TEXT("a stable of an unknown player"), Mutated([](FHRWorldState& W) { W.Stables[0].OwnerPlayerId = TEXT("ghost"); }), TEXT("unknown player"));
	Refused(TEXT("two stables owned by one player"), Mutated([](FHRWorldState& W) { W.Stables[0].OwnerPlayerId = W.Stables[1].OwnerPlayerId = TEXT("p1"); }), TEXT("shares its owner"));
	Refused(TEXT("a listing whose seller does not own the horse"), Mutated([&HorseId](FHRWorldState& W)
	{
		FHRSaleListing L;
		L.HorseId = HorseId;
		L.SellerId = W.Stables[0].Id == W.Horses[HorseId].OwnerId ? W.Stables[1].Id : W.Stables[0].Id;
		L.Price = 50;
		W.Listings.Add(L);
	}), TEXT("seller does not own"));
	Refused(TEXT("a pregnancy with the same horse as mare and sire"), Mutated([&HorseId](FHRWorldState& W)
	{
		FHRPregnancy P;
		P.MareId = P.SireId = HorseId;
		P.BreederId = W.Stables[0].Id;
		P.DueT = W.T + 10;
		W.Pregnancies.Add(P);
	}), TEXT("mare and a sire"));
	Refused(TEXT("a rider with empty potential"), Mutated([&RiderId](FHRWorldState& W) { W.Riders[RiderId].Potential.Reset(); }), TEXT("potential"));
	Refused(TEXT("a rider serial behind an existing rider id"), Mutated([](FHRWorldState& W) { W.RiderSerial = 0; }), TEXT("rider serial"));
	Refused(TEXT("a bet serial behind today's ticket"), Mutated([](FHRWorldState& W) { W.Serial = 0; }), TEXT("serial"));
	{
		FString OverflowCoins = Good;
		OverflowCoins.ReplaceInline(TEXT("\"coins\":155"), TEXT("\"coins\":4294967396"), ESearchCase::CaseSensitive);
		Refused(TEXT("int32 overflow in JSON"), OverflowCoins, TEXT("int32"));
		FString FloatCoins = Good;
		FloatCoins.ReplaceInline(TEXT("\"coins\":155"), TEXT("\"coins\":155.5"), ESearchCase::CaseSensitive);
		Refused(TEXT("fractional integer in JSON"), FloatCoins, TEXT("integer"));
		FString StringCoins = Good;
		StringCoins.ReplaceInline(TEXT("\"coins\":155"), TEXT("\"coins\":\"155abc\""), ESearchCase::CaseSensitive);
		Refused(TEXT("string number in JSON"), StringCoins, TEXT("number"));
		FString NullField = Good;
		NullField.ReplaceInline(TEXT("\"seed\":\"admission-1\""), TEXT("\"seed\":null"), ESearchCase::CaseSensitive);
		Refused(TEXT("null field in JSON"), NullField, TEXT("null"));
	}

	// Ranges.
	Refused(TEXT("a negative ability"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].Abilities[1] = -5; }), TEXT("abilities[1]"));
	Refused(TEXT("a huge ability"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].Abilities[0] = 1000000; }), TEXT("abilities[0]"));
	Refused(TEXT("a condition of 9"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].Condition = 9; }), TEXT("condition"));
	Refused(TEXT("an allele beyond the breeds"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].Genome.FindOrAdd(TEXT("breed")).A = 7; }), TEXT("gene breed"));
	Refused(TEXT("negative coins"), Mutated([](FHRWorldState& W) { W.Players[TEXT("p1")].Coins = -1; }), TEXT("coins"));
	Refused(TEXT("coins beyond the cap"), Mutated([](FHRWorldState& W) { W.Players[TEXT("p1")].Coins = HRRules::MaxCoins + 1; }), TEXT("coins"));
	Refused(TEXT("a stake beyond the limit"), Mutated([](FHRWorldState& W) { W.Tickets[0].Stake = 1000; }), TEXT("stake"));
	Refused(TEXT("a day in the future of the race day"), Mutated([](FHRWorldState& W) { W.Meeting.T = W.T + 1; }), TEXT("race day"));

	// Collection sizes.
	Refused(TEXT("a huge ability list"), Mutated([&HorseId](FHRWorldState& W) { W.Horses[HorseId].Abilities.Init(1, 5000); }), TEXT("abilities"));
	Refused(TEXT("three parents"), Mutated([&ParentlessId, &HorseId](FHRWorldState& W) { W.Horses[ParentlessId].Parents = {HorseId, HorseId, HorseId}; }), TEXT("two"));
	Refused(TEXT("a parent born no earlier than its foal"), Mutated([&ParentlessId, &OtherHorseId](FHRWorldState& W)
	{
		W.Horses[OtherHorseId].BirthT = W.Horses[ParentlessId].BirthT;
		W.Horses[ParentlessId].Parents = {OtherHorseId, OtherHorseId};
	}), TEXT("parent born no earlier"));
	Refused(TEXT("too much news"), Mutated([](FHRWorldState& W)
	{
		FHRNews N;
		N.Text = TEXT("x");
		W.News.Init(N, HRSave::MaxNews + 1);
	}), TEXT("news"));
	Refused(TEXT("too many runners"), Mutated([](FHRWorldState& W)
	{
		FHRRace& R = W.Meeting.Races[0];
		const FHRRunner Copy = R.Entries[0];
		while (R.Entries.Num() <= HRSave::MaxEntries) R.Entries.Add(Copy);
	}), TEXT("entries"));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHREconomyTest, "Atelier.HorseRacing.Economy.Invariants", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHREconomyTest::RunTest(const FString&)
{
	const FHRWorldState Base = HRRules::CreateWorld(TEXT("economy-1"));

	// Saturating arithmetic.
	TestEqual(TEXT("a credit saturates at the cap"), HRRules::Credit(HRRules::MaxCoins - 1, 1000000000000LL), HRRules::MaxCoins);
	TestEqual(TEXT("a credit is never negative"), HRRules::Credit(10, -50), 10);
	TestEqual(TEXT("a tally saturates at int32"), HRRules::Tally(MAX_int32 - 1, 10), MAX_int32);

	// A ticket is settled once: settling again, or closing the day, pays nothing more.
	{
		FHRWorldState S = Base;
		HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada"));
		const FHRRace* Race = HRAdmissionTest::FieldRace(S, false);
		if (!TestNotNull(TEXT("a race to bet on"), Race)) return false;
		const FString Key = Race->Key;
		for (int32 I = 0; I < 2; ++I) TestTrue(TEXT("a ticket"), HRRules::PlaceBet(S, TEXT("p1"), Key, Race->Entries[I].HorseId, 5).IsEmpty());
		HRRules::SettleRace(S, *HRRules::FindRace(S, Key));
		TestTrue(TEXT("a declared race settles nothing"), !S.Tickets.ContainsByPredicate([](const FHRTicket& T) { return T.Status != TEXT("open"); }));
		while (!HRRules::FindRace(S, Key)->IsRun()) HRRules::RunNextRace(S);
		const int32 Coins = S.Players[TEXT("p1")].Coins;
		const TArray<FHRTicket> Settled = S.Tickets;
		TestTrue(TEXT("both tickets are settled"), !Settled.ContainsByPredicate([](const FHRTicket& T) { return T.Status == TEXT("open"); }));
		HRRules::SettleRace(S, *HRRules::FindRace(S, Key));
		TestEqual(TEXT("settling again pays nothing"), S.Players[TEXT("p1")].Coins, Coins);
		const int32 Income = HRRules::PlayerDailyIncome;
		HRRules::AdvanceDay(S);
		TestEqual(TEXT("the day's close pays only the daily income"), S.Players[TEXT("p1")].Coins, Coins + Income);
		for (int32 I = 0; I < Settled.Num(); ++I)
			TestEqual(TEXT("a settled ticket keeps its outcome"), S.Tickets[I].Status, Settled[I].Status);
	}

	// A void race refunds every stake.
	{
		FHRWorldState S = Base;
		HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada"));
		const FHRRace* Race = HRAdmissionTest::FieldRace(S, false);
		const FString Key = Race->Key;
		const int32 Before = S.Players[TEXT("p1")].Coins;
		TestTrue(TEXT("a ticket"), HRRules::PlaceBet(S, TEXT("p1"), Key, Race->Entries[0].HorseId, 7).IsEmpty());
		FHRRace& Void = *HRRules::FindRace(S, Key);
		Void.Status = TEXT("uncontested");
		Void.Finishes.Reset();
		HRRules::SettleRace(S, Void);
		TestEqual(TEXT("refunded"), S.Tickets.Last().Status, FString(TEXT("refunded")));
		TestEqual(TEXT("the stake is back"), S.Players[TEXT("p1")].Coins, Before);
		HRRules::SettleRace(S, Void);
		TestEqual(TEXT("refunded once"), S.Players[TEXT("p1")].Coins, Before);
	}

	// Non-runner tickets placed before a winning ticket are refunded before winner odds are calculated, and
	// rider transfer listing/hiring refuses prices above MaxCoins without int32 overflow.
	{
		FHRWorldState S = Base;
		HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada")).Coins = 500;
		HRRules::AddPlayer(S, TEXT("p2"), TEXT("Bo")).Coins = 500;
		TestTrue(TEXT("p1 buys stable"), HRRules::BuyStable(S, TEXT("p1"), S.Stables[0].Id, true).IsEmpty());
		const TArray<const FHRRider*> Staff = HRRules::StableRiders(S, S.Stables[0].Id);
		if (TestTrue(TEXT("stable has riders"), Staff.Num() > 0))
		{
			TestFalse(TEXT("ListRider refuses price > MaxCoins"), HRRules::ListRider(S, TEXT("p1"), Staff[0]->Id, true, MAX_int32).IsEmpty());
			TestTrue(TEXT("ListRider accepts MaxCoins"), HRRules::ListRider(S, TEXT("p1"), Staff[0]->Id, true, HRRules::MaxCoins).IsEmpty());
			TestTrue(TEXT("p2 founds stable"), HRRules::FoundStable(S, TEXT("p2"), TEXT("Beta"), TEXT("224466")).IsEmpty());
			const TArray<const FHRRider*> BetaStaff = HRRules::StableRiders(S, TEXT("player:p2"));
			if (BetaStaff.Num() > 0) HRRules::ReleaseRider(S, TEXT("p2"), BetaStaff[0]->Id);
			TestFalse(TEXT("HireRider does not overflow Fee + Wage"), HRRules::HireRider(S, TEXT("p2"), Staff[0]->Id).IsEmpty());
		}
		while (!HRAdmissionTest::FieldRace(S, true) && !HRRules::RunNextRace(S).IsEmpty()) {}
		const FHRRace* Run = HRAdmissionTest::FieldRace(S, true);
		if (TestTrue(TEXT("a race was run with finishes"), Run && Run->Finishes.Num() > 0))
		{
			FHRWorldState WithScratched = S, WithoutScratched = S;
			FHRTicket Scratched;
			Scratched.Id = TEXT("bet:scratched"); Scratched.PlayerId = TEXT("p1"); Scratched.T = S.T;
			Scratched.RaceKey = Run->Key; Scratched.HorseId = TEXT("scratched:horse"); Scratched.Stake = 20; Scratched.Status = TEXT("open");
			FHRTicket Win;
			Win.Id = TEXT("bet:win"); Win.PlayerId = TEXT("p2"); Win.T = S.T;
			Win.RaceKey = Run->Key; Win.HorseId = Run->Finishes[0].HorseId; Win.Stake = 10; Win.Status = TEXT("open");
			WithScratched.Tickets.Add(Scratched); WithScratched.Tickets.Add(Win);
			WithoutScratched.Tickets.Add(Win);
			HRRules::SettleRace(WithScratched, *Run);
			HRRules::SettleRace(WithoutScratched, *Run);
			if (TestTrue(TEXT("two tickets settled"), WithScratched.Tickets.Num() >= 2 && WithoutScratched.Tickets.Num() >= 1))
			{
				TestEqual(TEXT("scratched ticket refunded first"), WithScratched.Tickets[WithScratched.Tickets.Num() - 2].Status, FString(TEXT("refunded")));
				TestEqual(TEXT("winner odds exclude the scratched ticket"), WithScratched.Tickets.Last().Rapport, WithoutScratched.Tickets.Last().Rapport);
				TestEqual(TEXT("winner payout excludes the scratched ticket"), WithScratched.Tickets.Last().Payout, WithoutScratched.Tickets.Last().Payout);
			}
		}
	}

	// A winning ticket on a balance at the cap saturates; the daily income too.
	{
		FHRWorldState S = Base;
		HRRules::AddPlayer(S, TEXT("p1"), TEXT("Ada"));
		HRRules::RunNextRace(S);
		while (!HRAdmissionTest::FieldRace(S, true) && !HRRules::RunNextRace(S).IsEmpty()) {}
		const FHRRace* Run = HRAdmissionTest::FieldRace(S, true);
		if (TestNotNull(TEXT("a race was run"), Run))
		{
			FHRTicket T;
			T.Id = TEXT("bet:manual");
			T.PlayerId = TEXT("p1");
			T.T = S.T;
			T.RaceKey = Run->Key;
			T.HorseId = Run->Finishes[0].HorseId;
			T.Stake = 10;
			T.Status = TEXT("open");
			S.Tickets.Add(T);
			S.Players[TEXT("p1")].Coins = HRRules::MaxCoins - 3;
			HRRules::SettleRace(S, *Run);
			TestEqual(TEXT("won"), S.Tickets.Last().Status, FString(TEXT("won")));
			TestEqual(TEXT("the payout saturates at the cap"), S.Players[TEXT("p1")].Coins, HRRules::MaxCoins);
		}
		HRRules::AdvanceDay(S);
		TestEqual(TEXT("the income saturates at the cap"), S.Players[TEXT("p1")].Coins, HRRules::MaxCoins);
	}

	// Two seasons with players betting and owning: no balance goes negative and every day's world is admissible.
	{
		FHRWorldState S = Base;
		HRRules::AddPlayer(S, TEXT("owner"), TEXT("Ada")).Coins = 600;
		HRRules::AddPlayer(S, TEXT("punter"), TEXT("Bo"));
		TestTrue(TEXT("the owner buys the stable for sale"), HRRules::BuyStable(S, TEXT("owner"), S.Stables[0].Id, true).IsEmpty());
		bool bValid = true;
		for (int32 Day = 0; Day < 2 * HRClock::DaysPerSeason && bValid; ++Day)
		{
			for (const FHRRace& R : S.Meeting.Races)
			{
				if (R.Status != TEXT("declared") || R.Entries.Num() < 2) continue;
				HRRules::PlaceBet(S, TEXT("punter"), R.Key, R.Entries.Last().HorseId, 10);
				HRRules::PlaceBet(S, TEXT("owner"), R.Key, R.Entries[0].HorseId, 3);
				break;
			}
			HRRules::AdvanceDay(S);
			FString Why;
			bValid = HRAdmissionTest::BalancesValid(S, Why);
			TestTrue(FString::Printf(TEXT("day %d: balances within 0..cap (%s)"), S.T, *Why), bValid);
			const FString Admission = HRSave::Validate(S);
			TestTrue(FString::Printf(TEXT("day %d: the world is admissible (%s)"), S.T, *Admission), Admission.IsEmpty());
			bValid &= Admission.IsEmpty();
		}
	}

	// A long absence: the catch-up is bounded, deterministic, and moves the clock anchor by whole days.
	{
		FHRWorldState A = Base;
		HRRules::StartClock(A, 1800000000);
		FHRWorldState B = A;
		const int32 T0 = A.T;
		const int64 Epoch = A.EpochUnix;
		const double Far = HRClock::DayStart(T0 + 1000) + 1234.;
		constexpr int32 Cap = 4;
		HRRules::AdvanceTo(A, Far, Cap);
		HRRules::AdvanceTo(B, Far, Cap);
		TestTrue(FString::Printf(TEXT("at most %d days simulated (%d)"), Cap, A.T - T0), A.T - T0 <= Cap && A.T - T0 >= Cap - 1);
		TestTrue(TEXT("deterministic"), HRSave::ToJson(A) == HRSave::ToJson(B));
		TestEqual(TEXT("the anchor moved by whole days"), (A.EpochUnix - Epoch) % (int64)HRClock::DaySeconds, (int64)0);
		const double Resumed = HRRules::WorldSeconds(A, 1800000000.0 + (Far - HRClock::DayStart(T0)));
		TestTrue(TEXT("the world resumes on its present day"), Resumed >= HRClock::DayStart(A.T) && Resumed < HRClock::DayStart(A.T + 1));
		const FString Once = HRSave::ToJson(A);
		HRRules::AdvanceTo(A, std::numeric_limits<double>::quiet_NaN());
		HRRules::AdvanceTo(A, 1e300);
		TestTrue(TEXT("a non-finite or absurd time changes nothing"), HRSave::ToJson(A) == Once);
		TestEqual(TEXT("the default cap is one real week"), HRRules::MaxCatchUpDays, 84);
	}

	// Refunds happen before winner payouts so a non-runner ticket placed before a winning ticket does not change the winner's odds.
	{
		FHRWorldState S = HRRules::CreateWorld(TEXT("refund-order"));
		HRRules::AddPlayer(S, TEXT("winner"), TEXT("Ada")).Coins = 100;
		HRRules::AddPlayer(S, TEXT("scratched"), TEXT("Bo")).Coins = 100;
		if (TestTrue(TEXT("first race has at least 3 runners"), S.Meeting.Races.Num() > 0 && S.Meeting.Races[0].Entries.Num() >= 3))
		{
			const FString RaceKey = S.Meeting.Races[0].Key;
			const FString Runner0 = S.Meeting.Races[0].Entries[0].HorseId;
			const FString Runner1 = S.Meeting.Races[0].Entries[1].HorseId;

			FHRWorldState Probe = S;
			Probe.Meeting.Races[0].Entries.RemoveAll([&Runner1](const FHRRunner& E) { return E.HorseId == Runner1; });
			TestTrue(TEXT("winner bet placed cleanly"), HRRules::PlaceBet(Probe, TEXT("winner"), RaceKey, Runner0, 10).IsEmpty());
			HRRules::RunNextRace(Probe);
			if (TestTrue(TEXT("probe race finished"), Probe.Meeting.Races[0].Finishes.Num() > 0))
			{
				const FString ActualWinner = Probe.Meeting.Races[0].Finishes[0].HorseId;

				FHRWorldState Clean = S;
				Clean.Meeting.Races[0].Entries.RemoveAll([&Runner1](const FHRRunner& E) { return E.HorseId == Runner1; });
				TestTrue(TEXT("bet on actual winner (clean)"), HRRules::PlaceBet(Clean, TEXT("winner"), RaceKey, ActualWinner, 10).IsEmpty());
				HRRules::RunNextRace(Clean);

				FHRWorldState WithScratch = S;
				TestTrue(TEXT("bet on scratched runner first"), HRRules::PlaceBet(WithScratch, TEXT("scratched"), RaceKey, Runner1, 10).IsEmpty());
				TestTrue(TEXT("bet on actual winner second"), HRRules::PlaceBet(WithScratch, TEXT("winner"), RaceKey, ActualWinner, 10).IsEmpty());
				WithScratch.Meeting.Races[0].Entries.RemoveAll([&Runner1](const FHRRunner& E) { return E.HorseId == Runner1; });
				HRRules::RunNextRace(WithScratch);
				if (TestTrue(TEXT("both tickets exist"), WithScratch.Tickets.Num() == 2 && Clean.Tickets.Num() == 1))
				{
					TestEqual(TEXT("scratched ticket refunded"), WithScratch.Tickets[0].Status, FString(TEXT("refunded")));
					TestEqual(TEXT("winner rapport matches clean run"), WithScratch.Tickets[1].Rapport, Clean.Tickets[0].Rapport);
					TestEqual(TEXT("winner payout matches clean run"), WithScratch.Tickets[1].Payout, Clean.Tickets[0].Payout);
				}
			}
		}
	}
	return true;
}

#endif
