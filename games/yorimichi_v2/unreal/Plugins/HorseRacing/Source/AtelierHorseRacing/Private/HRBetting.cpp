#include "HRRules.h"

#include "HRRandom.h"

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

	double Rapport(const FHRWorldState& S, const FHRRace& Race, const FString& HorseId, int32 ExtraStake)
	{
		const int64 Pool = CrowdPool(S);
		// Pools are summed in int64: any number of tickets keeps the odds finite and exact.
		int64 PlayerPool = FMath::Max(ExtraStake, 0);
		int64 OnHorse = PlayerPool;
		for (const FHRTicket& T : S.Tickets)
		{
			if (T.T != S.T || T.RaceKey != Race.Key || T.Status == TEXT("refunded")) continue;
			PlayerPool += T.Stake;
			if (T.HorseId == HorseId) OnHorse += T.Stake;
		}
		const double OnOutcome = (double)Pool * WinChance(Race, HorseId) + (double)OnHorse;
		if (OnOutcome <= 0) return MinRapport;
		const double Value = ((double)(Pool + PlayerPool) * (1 - Take)) / OnOutcome;
		return FMath::Max(MinRapport, FMath::FloorToDouble(Value * 100) / 100);
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
		if (Stake < FBetLimits::MinStake || Stake > FBetLimits::MaxStake)
			return FString::Printf(TEXT("Stake between %d and %d coins."), FBetLimits::MinStake, FBetLimits::MaxStake);
		if ((int64)DayStake(S, PlayerId) + Stake > FBetLimits::PerDay)
			return FString::Printf(TEXT("No more than %d coins of bets a day."), FBetLimits::PerDay);
		if (P->Coins < Stake) return FString::Printf(TEXT("It takes %d coins."), Stake);
		int32 OnRace = 0;
		for (const FHRTicket& T : S.Tickets)
			if (T.T == S.T && T.RaceKey == Race.Key && T.PlayerId == PlayerId) OnRace++;
		if (OnRace >= FBetLimits::TicketsPerRace)
			return FString::Printf(TEXT("No more than %d tickets per race."), FBetLimits::TicketsPerRace);
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
			T.Payout = (int32)FMath::Clamp<double>(FMath::FloorToDouble(T.Stake * T.Rapport), 0., (double)MaxCoins);
			T.Status = TEXT("won");
			if (FHRPlayer* P = FindPlayer(S, T.PlayerId))
			{
				P->Coins = Credit(P->Coins, T.Payout);
				P->TotalWon = Tally(P->TotalWon, T.Payout);
				P->TicketsWon++;
			}
		}
	}
}
