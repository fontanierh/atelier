#include "HRRules.h"

#include "HRRandom.h"
#include "HRSave.h"

// A full book must still save and load: under HRSave's ticket bound, with room in its JSON size bound (about 200
// characters a ticket).
static_assert(HRRules::MaxBookTickets <= HRSave::MaxTickets && int64(HRRules::MaxBookTickets) * 200 < HRSave::MaxJsonChars / 2,
	"the betting book must fit a saved world");

// Win bets in a pari-mutuel pool per race. A simulated crowd stakes on public replays of the field (never the day's form
// draw); every player's ticket on the race joins the same pool, so the odds move as players bet.

namespace
{
	int32 CrowdPool(const FHRWorldState& S)
	{
		return HRContent::EventForT(S.T).bGrandPrix ? 900 : 300;
	}
}

namespace HRRules
{
	double WinChance(const FHRRace& Race, const FString& HorseId)
	{
		const int32 N = Race.Entries.Num();
		const int32 Picked = Race.Entries.IndexOfByPredicate([&HorseId](const FHRRunner& R) { return R.HorseId == HorseId; });
		int64 Runs = 0;
		for (const FHROrderCount& O : Race.PublicOrders) Runs += FMath::Max(0, O.Count);
		Runs = FMath::Max<int64>(1, Runs);
		double Chance = 0;
		for (const FHROrderCount& O : Race.PublicOrders)
		{
			TArray<FString> Parts;
			O.Key.ParseIntoArray(Parts, TEXT(">"));
			if (Parts.Num() > 0 && FCString::Atoi(*Parts[0]) == Picked) Chance += (double)FMath::Max(0, O.Count) / (double)Runs;
		}
		return (1 - Longshot) * Chance + Longshot / FMath::Max(1, N);
	}

	void PoolShares(const FHRWorldState& S, const FHRRace& Race, const FString& HorseId, double& OutPool, double& OutOnHorse)
	{
		const int64 Pool = CrowdPool(S);
		// Pools are summed in int64: any number of tickets of any size keeps the odds finite and exact.
		int64 PlayerPool = 0, OnHorse = 0;
		for (const FHRTicket& T : S.Tickets)
		{
			if (T.T != S.T || T.RaceKey != Race.Key || T.Status == TEXT("refunded")) continue;
			PlayerPool += T.Stake;
			if (T.HorseId == HorseId) OnHorse += T.Stake;
		}
		OutPool = (double)(Pool + PlayerPool);
		OutOnHorse = (double)Pool * WinChance(Race, HorseId) + (double)OnHorse;
	}

	double RapportOf(double Pool, double OnHorse, int32 ExtraStake)
	{
		const double Extra = FMath::Max(ExtraStake, 0);
		const double OnOutcome = OnHorse + Extra;
		if (!(OnOutcome > 0)) return MinRapport;
		const double Value = ((Pool + Extra) * (1 - Take)) / OnOutcome;
		return FMath::Max(MinRapport, FMath::FloorToDouble(Value * 100) / 100);
	}

	double Rapport(const FHRWorldState& S, const FHRRace& Race, const FString& HorseId, int32 ExtraStake)
	{
		double Pool = 0, OnHorse = 0;
		PoolShares(S, Race, HorseId, Pool, OnHorse);
		return RapportOf(Pool, OnHorse, ExtraStake);
	}

	int32 Payout(int32 Stake, double Rapport)
	{
		const double Value = FMath::FloorToDouble((double)FMath::Max(Stake, 0) * Rapport);
		return FMath::IsFinite(Value) ? (int32)FMath::Clamp<double>(Value, 0., (double)MaxCoins) : 0;
	}

	int32 DayStake(const FHRWorldState& S, const FString& PlayerId)
	{
		int64 Sum = 0;
		for (const FHRTicket& T : S.Tickets)
			if (T.T == S.T && T.PlayerId == PlayerId) Sum += T.Stake;
		return (int32)FMath::Min<int64>(Sum, MAX_int32);
	}

	FString BetRefusal(const FHRWorldState& S, const FString& PlayerId, const FHRRace& Race, const FString& HorseId, int32 Stake)
	{
		const FHRPlayer* P = FindPlayer(S, PlayerId);
		if (!P) return TEXT("Unknown player.");
		if (Race.IsRun()) return TEXT("This race has been run.");
		if (Race.Entries.Num() < 2) return TEXT("Not enough runners to bet.");
		if (!Race.Entries.ContainsByPredicate([&HorseId](const FHRRunner& R) { return R.HorseId == HorseId; }))
			return TEXT("This horse is not declared to run.");
		if (Stake < FBetLimits::MinStake) return FString::Printf(TEXT("Stake at least %d coin."), FBetLimits::MinStake);
		if (Stake > P->Coins) return FString::Printf(TEXT("You have only %d coins."), P->Coins);
		if (S.Tickets.Num() >= MaxBookTickets)
		{
			// Unpaid winning tickets are never pruned: when they are part of what fills the book, say so.
			const bool bUnpaid = S.Tickets.ContainsByPredicate([](const FHRTicket& T) { return T.Unpaid; });
			return bUnpaid ? TEXT("The betting book is full for this season. Winning tickets stay in it until their winnings are collected.")
				: TEXT("The betting book is full for this season.");
		}
		return FString();
	}

	FString PlaceBet(FHRWorldState& S, const FString& PlayerId, const FString& RaceKey, const FString& HorseId, int32 Stake)
	{
		const FHRRace* Race = FindRace(S, RaceKey);
		if (!Race) return TEXT("Race not found.");
		const FString Refusal = BetRefusal(S, PlayerId, *Race, HorseId, Stake);
		if (!Refusal.IsEmpty()) return Refusal;
		FHRTicket T;
		T.Id = FString::Printf(TEXT("bet:%d:%d"), S.T, S.Serial++);
		T.PlayerId = PlayerId;
		T.T = S.T;
		T.RaceKey = RaceKey;
		T.HorseId = HorseId;
		T.Stake = Stake;
		T.Status = TEXT("open");
		FHRPlayer& P = *FindPlayer(S, PlayerId);
		P.Coins -= Stake;
		P.TotalStaked = Tally(P.TotalStaked, Stake);
		S.Tickets.Add(T);
		return FString();
	}

	void SettleRace(FHRWorldState& S, const FHRRace& Race)
	{
		// Only open tickets are settled, and settling marks them: a second call (or the day's close) pays nothing again. A
		// race still declared has no outcome yet: its tickets stay open.
		if (!Race.IsRun()) return;
		const FString Winner = Race.Finishes.Num() ? Race.Finishes[0].HorseId : FString();
		auto Open = [&S, &Race](const FHRTicket& T) { return T.T == S.T && T.RaceKey == Race.Key && T.Status == TEXT("open"); };
		// Refunds first (a race not run, or a declared horse that did not run), so every winner of the race is paid the
		// same odds whatever the tickets' order.
		for (FHRTicket& T : S.Tickets)
		{
			if (!Open(T)) continue;
			const bool bRan = Race.Finishes.ContainsByPredicate([&T](const FHRFinish& F) { return F.HorseId == T.HorseId; });
			if (Race.Status == TEXT("run") && bRan && Race.Finishes.Num() >= 2) continue;
			T.Status = TEXT("refunded");
			T.Payout = T.Stake;
			if (FHRPlayer* P = FindPlayer(S, T.PlayerId)) P->Coins = Credit(P->Coins, T.Stake);
		}
		for (FHRTicket& T : S.Tickets)
		{
			if (!Open(T)) continue;
			if (Winner != T.HorseId)
			{
				T.Status = TEXT("lost");
				T.Payout = 0;
				continue;
			}
			// The odds are fixed by the frozen field and every non-refunded player ticket in this pool.
			T.Rapport = Rapport(S, Race, Winner);
			T.Payout = Payout(T.Stake, T.Rapport);
			T.Status = TEXT("won");
			// The winnings wait to be collected (CollectWinnings); the player's record counts the win now.
			T.Unpaid = T.Payout > 0;
			if (FHRPlayer* P = FindPlayer(S, T.PlayerId))
			{
				P->TotalWon = Tally(P->TotalWon, T.Payout);
				P->TicketsWon++;
			}
		}
	}

	void CollectWinnings(FHRWorldState& S, const FString& PlayerId, int32& OutPaid, int32& OutTickets, const TFunction<bool(const FHRTicket&)>& Ready)
	{
		OutPaid = 0;
		OutTickets = 0;
		FHRPlayer* P = FindPlayer(S, PlayerId);
		if (!P) return;
		// Oldest first (the book is in the order the tickets were taken). A payout that does not fit under MaxCoins stops the
		// collection: that ticket and the later ones stay unpaid rather than lose coins to the cap.
		for (FHRTicket& T : S.Tickets)
		{
			if (!T.Unpaid || T.PlayerId != PlayerId || (Ready && !Ready(T))) continue;
			const int32 Payout = FMath::Max(T.Payout, 0);
			if ((int64)P->Coins + Payout > MaxCoins) break;
			P->Coins = Credit(P->Coins, Payout);
			T.Unpaid = false;
			OutPaid += Payout;
			OutTickets++;
		}
	}
}
