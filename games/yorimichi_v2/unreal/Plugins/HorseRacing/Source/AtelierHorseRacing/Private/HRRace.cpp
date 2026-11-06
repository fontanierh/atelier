#include "HRRules.h"

#include "HRRandom.h"

// Port of the reference race.ts: gallop-1 pace and the open-1 variance model
// (day form for the whole race, wider swings at each stage, rare incidents).

namespace
{
	constexpr int32 BaseSpeed = 13000; // gallop-1, mm/s
	constexpr int32 DayScale = 3;
	constexpr int32 Noise = 8;
	constexpr int32 IncidentPercent = 12;
	constexpr int32 IncidentScale = 2;
	const TArray<int64> DayWeights = {10, 20, 40, 20, 10};

	struct FIncidentDef { int32 Beat; const TCHAR* Kind; int32 Cost; };
	const FIncidentDef Incidents[4] = {{0, TEXT("start"), 6}, {1, TEXT("bumped"), 4}, {2, TEXT("boxed"), 5}, {3, TEXT("faded"), 4}};

	struct FForms
	{
		int32 F[4];
		int32 IncidentIndex = -1;
	};

	FForms OpenForms(const FHRHorse& H, int32 Preparation, const FString& Seed)
	{
		FForms Out;
		const int32 Day = (HRRandom::PickWeighted(Seed, FString::Printf(TEXT("day:%s"), *H.Id), DayWeights) - 2) * DayScale;
		static const TArray<int64> StageWeights = []
		{
			TArray<int64> W;
			for (int32 I = 0; I < 2 * Noise + 1; ++I) W.Add(Noise + 1 - FMath::Abs(I - Noise));
			return W;
		}();
		for (int32 I = 0; I < 4; ++I)
		{
			Out.F[I] = Day + HRRandom::PickWeighted(Seed, FString::Printf(TEXT("form:%s:%d"), *H.Id, I), StageWeights) - Noise;
		}
		if (HRRandom::Draw(Seed, FString::Printf(TEXT("incident:%s"), *H.Id), 100) < IncidentPercent)
		{
			const int32 Index = HRRandom::Draw(Seed, FString::Printf(TEXT("incident-stage:%s"), *H.Id), 4);
			Out.F[Incidents[Index].Beat] -= Incidents[Index].Cost * IncidentScale;
			Out.IncidentIndex = Index;
		}
		// The protections keep their size (+1 or +2 towards zero), never a full erase of a bad stage.
		auto Soften = [&Out](int32 I, int32 By) { if (Out.F[I] < 0) Out.F[I] = FMath::Min(0, Out.F[I] + By); };
		if (H.Abilities[HRAbility::Composure] >= 8)
			for (int32 I = 0; I < 4; ++I) Soften(I, 1);
		if (Preparation == 0) Soften(2, 2);
		if (H.Trait == TEXT("quiet"))
		{
			if (H.Mastery == 1) { Soften(0, 2); Soften(2, 2); }
			else if (H.Mastery == 2) { Soften(1, 2); Soften(3, 2); }
			else
			{
				int32 Worst = 0;
				for (int32 I = 1; I < 4; ++I) if (Out.F[I] < Out.F[Worst]) Worst = I;
				Soften(Worst, 2);
			}
		}
		return Out;
	}

	int32 Performance(const FHRHorse& H, int32 P, const HRContent::FEvent& E, int32 Distance, int32 Beat, int32 Form,
		int32 BreakRank, int32 ChallengeRank, int32 Pressure, int32 Rider = 0)
	{
		const TArray<int32>& A = H.Abilities;
		const int32 Acc = A[0], Spd = A[1], End = A[2], Cmp = A[3];
		const int32 Base[4] = {2 * Acc + Cmp, 2 * Spd + End, 2 * Cmp + Spd, 2 * End + Spd};
		// racing-3: the rider's stage bonus (small, legends excepted).
		int32 Score = Base[Beat] + Form + Rider;
		if (Beat == 2 && Pressure) Score += (Cmp - 5) * Pressure;
		if (E.bObstacles && (Beat == 1 || Beat == 2))
			Score += 2 * Cmp + (Distance >= 1400 ? End : Acc) - 16;
		const int32 M = H.Mastery;
		if (Beat == 1 || Beat == 2)
			Score += E.Surface == H.Favorite ? 2 : E.Surface == H.Difficult ? (Beat == 2 && P == 0 ? 0 : -2) : 0;
		if (P == 0) { const int32 D[4] = {0, -1, 3, 0}; Score += D[Beat]; }
		if (P == 1) { const int32 D[4] = {-2, 0, E.Shape == 2 ? -1 : 0, 5}; Score += D[Beat]; }
		if (P == 2)
		{
			int32 Start = 5, End2 = -2;
			if (H.Trait == TEXT("gate"))
			{
				Start += M == 1 ? 4 : M == 2 ? 2 : 3;
				End2 = M == 1 ? -4 : M == 2 ? -1 : -3;
			}
			const int32 D[4] = {Start, 0, 0, End2};
			Score += D[Beat];
		}
		if (Beat == 3)
		{
			const int32 Conditions[4] = {-6, -3, 0, 1};
			int32 Condition = Conditions[FMath::Clamp(H.Condition, 0, 3)];
			if (H.Trait == TEXT("breath"))
			{
				const int32 Threshold = M == 2 ? 1200 : 1400;
				if (Distance >= Threshold)
				{
					Score += M == 1 ? 4 : M == 2 ? 2 : 3;
					if (M != 1 && H.Condition <= 1) Condition += 3;
				}
			}
			if (H.Trait == TEXT("wise") && H.Condition <= 1)
				Condition = FMath::Min(0, Condition + (M == 1 ? 2 : M == 2 ? 4 : 3));
			Score += Condition;
			if (H.Trait == TEXT("solar") && ChallengeRank >= (M == 1 ? 4 : M == 2 ? 2 : 3))
				Score += M == 1 ? 6 : M == 2 ? 3 : 4;
			if (H.Trait == TEXT("clear") && M == 1 && BreakRank == 1) Score--;
		}
		if (Beat == 2 && H.Trait == TEXT("wise") && H.Condition <= 1) Score += M == 1 ? 2 : M == 2 ? 0 : 1;
		if (Beat == 1 && H.Trait == TEXT("clear") && BreakRank <= (M == 2 ? 2 : 1))
			Score += M == 1 ? 5 : M == 2 ? 2 : 4;
		return FMath::Max(0, Score);
	}

	void StageWeights(int32 Distance, int32 Out[4])
	{
		if (Distance <= 900) { Out[0] = 125; Out[1] = 115; Out[2] = 85; Out[3] = 75; }
		else if (Distance >= 1400) { Out[0] = 80; Out[1] = 100; Out[2] = 100; Out[3] = 125; }
		else { Out[0] = Out[1] = Out[2] = Out[3] = 100; }
	}

	int64 StageDuration(double Length, int32 Score, int32 Weight, bool bTechnicalTurn)
	{
		const double Units = (double)FMath::Max(0, Score) * Weight * (bTechnicalTurn ? 120 : 100);
		const double Speed = BaseSpeed + Units / 50;
		return (int64)FMath::CeilToDouble((Length * 1000 * 1000000) / Speed);
	}

	/** A player riding: named in the result as "player:<id>". */
	void NamePlayerRider(const FHRWorldState& S, const FString& PlayerId, FHRFinish& F)
	{
		const FHRPlayer* P = HRRules::FindPlayer(S, PlayerId);
		F.RiderId = TEXT("player:") + PlayerId;
		F.RiderName = P && !P->Name.IsEmpty() ? P->Name : PlayerId;
	}

	/** No crowd model yet: Grand Prix pressure uses the reference planning value (2, 3 with obstacles). */
	int32 PressureFor(const HRContent::FEvent& E)
	{
		return E.bGrandPrix ? (E.bObstacles ? 3 : 2) : 0;
	}
}

namespace HRRules
{
	bool IsHeatRound(const FString& Round)
	{
		return Round == TEXT("semi") || Round == TEXT("qualif") || Round == TEXT("barrage");
	}

	int32 RaceDistance(const HRContent::FEvent& E, const FString& Round)
	{
		if (!E.bGrandPrix) return E.Distance;
		return Round == TEXT("final") ? E.FinalDistance : E.EliminatoryDistance;
	}

	int64 PlanningTime(const FHRHorse& H, int32 Preparation, const HRContent::FEvent& E, int32 Distance)
	{
		int32 W[4];
		StageWeights(Distance, W);
		static const int32 Fractions[4] = {15, 35, 25, 25};
		int64 Time = 0;
		for (int32 Beat = 0; Beat < 4; ++Beat)
		{
			// Neutral third place deliberately does not predict a future field or trait trigger.
			const int32 Score = Performance(H, Preparation, E, Distance, Beat, 0, 3, 3, PressureFor(E));
			Time += StageDuration((Distance * Fractions[Beat]) / 100.0, Score, W[Beat], Beat == 2 && E.Shape == 2);
		}
		return Time;
	}

	void ResolveRace(FHRWorldState& S, FHRRace& Race)
	{
		const HRContent::FEvent* EventPtr = HRContent::FindEvent(Race.EventId);
		const FString Id = FString::Printf(TEXT("%s:T%d:%s"), *S.Seed, S.T, *Race.Key);
		Race.Incidents.Reset();
		Race.Finishes.Reset();
		bool bMissingHorse = false;
		TSet<FString> Seen;
		for (const FHRRunner& R : Race.Entries)
		{
			bool bDuplicate = false;
			Seen.Add(R.HorseId, &bDuplicate);
			bMissingHorse |= !S.Horses.Contains(R.HorseId) || bDuplicate;
		}
		// The payout tables hold six places: a bigger or duplicated field (hand-edited save) is never run.
		if (!EventPtr || bMissingHorse || Race.Entries.Num() > MaxRunners)
		{
			// Inconsistent data (content renamed, dangling horse): never crash, the race is simply not run.
			UE_LOG(LogTemp, Warning, TEXT("HorseRacing: race %s has an unknown event, an invalid field or a runner problem; marked uncontested."), *Race.Key);
			Race.Status = TEXT("uncontested");
			return;
		}
		const HRContent::FEvent& E = *EventPtr;
		// A sprint qualifier is a time trial: a lone contender still runs for a time.
		if (Race.Entries.Num() < (Race.Round == TEXT("qualif") ? 1 : 2))
		{
			Race.Status = (Race.Round == TEXT("semi") && Race.Entries.Num() == 1) ? TEXT("bye") : TEXT("uncontested");
			return;
		}
		Race.Status = TEXT("run");
		Race.Runs.Reset();
		TArray<FString> HorseIds;
		for (const FHRRunner& R : Race.Entries) HorseIds.Add(R.HorseId);
		const TArray<FString> TieOrder = HRRandom::Shuffled(HorseIds, S.Seed, Id + TEXT(":tie"));

		struct FRow
		{
			int32 Entry;
			FHRHorse Snapshot;
			FForms Forms;
			TArray<FHRSegment> Segments;
			int64 Total = 0;
			int32 BreakRank = 0;
			int32 ChallengeRank = 0;
			int32 BestRun = 0;
			TArray<int64> RunTimes;
			int32 Rider[4] = {0, 0, 0, 0};
		};
		auto RiderBonuses = [&S, &Race](int32 Entry, int32 Out[4])
		{
			for (int32 B = 0; B < 4; ++B) Out[B] = RunnerRiderBonus(S, Race.Entries[Entry], B, Race.Distance);
		};
		// One run of the field: its own form draws (run 1 keeps the single-run seed, so one-run events are unchanged).
		auto SimulateRun = [&](int32 Run) -> TArray<FRow>
		{
			const FString RunId = Run == 0 ? Id : FString::Printf(TEXT("%s:run%d"), *Id, Run + 1);
			TArray<FRow> Rows;
			const FString FormSeed = FString::Printf(TEXT("%s:%s"), *S.Seed, *RunId);
			for (int32 I = 0; I < Race.Entries.Num(); ++I)
			{
				FRow Row;
				Row.Entry = I;
				Row.Snapshot = S.Horses.FindChecked(Race.Entries[I].HorseId);
				Row.Forms = OpenForms(Row.Snapshot, Race.Entries[I].Preparation, FormSeed);
				RiderBonuses(I, Row.Rider);
				if (Row.Forms.IncidentIndex >= 0)
				{
					FHRIncident Incident;
					Incident.HorseId = Row.Snapshot.Id;
					Incident.Beat = Incidents[Row.Forms.IncidentIndex].Beat;
					Incident.Kind = Incidents[Row.Forms.IncidentIndex].Kind;
					Incident.Run = Run;
					Race.Incidents.Add(Incident);
				}
				Rows.Add(MoveTemp(Row));
			}
			int32 W[4];
			StageWeights(Race.Distance, W);
			static const int32 Fractions[4] = {15, 35, 25, 25};
			for (int32 Beat = 0; Beat < 4; ++Beat)
			{
				const double Length = (Race.Distance * Fractions[Beat]) / 100.0;
				for (FRow& X : Rows)
				{
					const int32 Score = Performance(X.Snapshot, Race.Entries[X.Entry].Preparation, E, Race.Distance, Beat,
						X.Forms.F[Beat], X.BreakRank, X.ChallengeRank, PressureFor(E), X.Rider[Beat]);
					const int64 Duration = StageDuration(Length, Score, W[Beat], Beat == 2 && E.Shape == 2);
					X.Total += Duration;
					FHRSegment Seg;
					Seg.Distance = Length;
					Seg.DurationUs = Duration;
					Seg.CumulativeUs = X.Total;
					Seg.Form = X.Forms.F[Beat];
					X.Segments.Add(Seg);
				}
				Rows.Sort([&](const FRow& A, const FRow& B)
				{
					if (A.Total != B.Total) return A.Total < B.Total;
					if (A.Segments[Beat].DurationUs != B.Segments[Beat].DurationUs) return A.Segments[Beat].DurationUs < B.Segments[Beat].DurationUs;
					if (A.Snapshot.Abilities[3] != B.Snapshot.Abilities[3]) return A.Snapshot.Abilities[3] > B.Snapshot.Abilities[3];
					return TieOrder.IndexOfByKey(A.Snapshot.Id) < TieOrder.IndexOfByKey(B.Snapshot.Id);
				});
				for (int32 I = 0; I < Rows.Num(); ++I)
				{
					Rows[I].Segments[Beat].Rank = I + 1;
					if (Beat == 0) Rows[I].BreakRank = I + 1;
					if (Beat == 2) Rows[I].ChallengeRank = I + 1;
				}
			}
			return Rows;
		};

		TArray<FRow> Rows = SimulateRun(0);
		const int32 NumRuns = E.Runs;
		if (NumRuns > 1)
		{
			// Every horse runs again; the official order is each horse's best time (then its other run, composure,
			// the race's tie order). Both runs are kept for the replays and the live stand.
			TArray<TArray<FRow>> AllRuns = {Rows};
			for (int32 Run = 1; Run < NumRuns; ++Run) AllRuns.Add(SimulateRun(Run));
			for (int32 Run = 0; Run < NumRuns; ++Run)
			{
				FHRRaceRun& Out = Race.Runs.AddDefaulted_GetRef();
				for (int32 I = 0; I < AllRuns[Run].Num(); ++I)
				{
					const FRow& X = AllRuns[Run][I];
					const FHRStable* Stable = FindStable(S, Race.Entries[X.Entry].StableId);
					FHRFinish F;
					F.HorseId = X.Snapshot.Id;
					F.StableId = Race.Entries[X.Entry].StableId;
					F.HorseName = X.Snapshot.Name;
					F.StableName = Stable ? Stable->Name : FString();
					F.Preparation = Race.Entries[X.Entry].Preparation;
					F.Place = I + 1;
					F.TimeUs = X.Total;
					F.Segments = X.Segments;
					if (!Race.Entries[X.Entry].RiderPlayerId.IsEmpty()) NamePlayerRider(S, Race.Entries[X.Entry].RiderPlayerId, F);
					else if (const FHRRider* Rider = RiderOf(S, F.HorseId)) { F.RiderId = Rider->Id; F.RiderName = Rider->FullName(); }
					Out.Finishes.Add(F);
				}
			}
			TArray<FRow> Best;
			for (int32 Entry = 0; Entry < Race.Entries.Num(); ++Entry)
			{
				FRow Row;
				for (int32 Run = 0; Run < NumRuns; ++Run)
				{
					const FRow* X = AllRuns[Run].FindByPredicate([Entry](const FRow& R) { return R.Entry == Entry; });
					if (Run == 0 || X->Total < Row.Total)
					{
						TArray<int64> Times = Row.RunTimes;
						Row = *X;
						Row.RunTimes = Times;
						Row.BestRun = Run;
					}
					Row.RunTimes.Add(X->Total);
				}
				Best.Add(MoveTemp(Row));
			}
			auto Other = [](const FRow& R) { int64 Sum = 0; for (int64 T : R.RunTimes) Sum += T; return Sum - R.Total; };
			Best.Sort([&](const FRow& A, const FRow& B)
			{
				if (A.Total != B.Total) return A.Total < B.Total;
				if (Other(A) != Other(B)) return Other(A) < Other(B);
				if (A.Snapshot.Abilities[3] != B.Snapshot.Abilities[3]) return A.Snapshot.Abilities[3] > B.Snapshot.Abilities[3];
				return TieOrder.IndexOfByKey(A.Snapshot.Id) < TieOrder.IndexOfByKey(B.Snapshot.Id);
			});
			Rows = MoveTemp(Best);
		}

		const bool bVillage = Race.Round == TEXT("village");
		const bool bSemi = IsHeatRound(Race.Round);
		const bool bBarrage = Race.Round == TEXT("barrage");
		for (int32 I = 0; I < Rows.Num(); ++I)
		{
			const FRow& X = Rows[I];
			const FHRRunner& Entry = Race.Entries[X.Entry];
			FHRHorse& H = S.Horses.FindChecked(Entry.HorseId);
			const FHRStable* Stable = FindStable(S, Entry.StableId);
			// Six-runner village races pay a sixth place.
			static const int32 VillageGross[6] = {22, 20, 18, 16, 14, 12};
			static const int32 FinalGross[6] = {40, 34, 28, 24, 20, 16};
			static const int32 VillagePoints[6] = {20, 12, 7, 3, 1, 0};
			static const int32 FinalPoints[6] = {100, 60, 35, 15, 5, 0};
			static const int32 VillagePrestige[6] = {5, 3, 1, 0, 0, 0};
			static const int32 FinalPrestige[6] = {20, 12, 7, 3, 0, 0};
			static const int32 Xp[6] = {7, 6, 5, 4, 4, 4};
			// A finalist's heat already paid 14: the final pays the difference.
			// A barrage pays nothing more: the qualifier already paid.
			const int32 Gross = bVillage ? VillageGross[I] : bBarrage ? 0 : bSemi ? 14 : FMath::Max(0, FinalGross[I] - 14);
			const FForecast F = Forecast(H, E, Race.Distance, Entry.Preparation, S.T);
			const FString Injury = Exert(H, F, S.T, true);
			H.Starts++;
			H.Earnings = Tally(H.Earnings, Gross);
			if (!bSemi && I == 0)
			{
				H.Wins++;
				if (Race.Round == TEXT("final")) H.GpWins++;
			}
			if (!bSemi && I < 3) H.Podiums++;
			FHRCareerLine Line;
			Line.T = S.T;
			Line.EventName = E.Name;
			Line.Round = Race.Round;
			Line.Place = I + 1;
			Line.Runners = Rows.Num();
			Line.Gross = Gross;
			Line.StableId = Entry.StableId;
			Line.RaceKey = Race.Key;
			H.Career.Add(Line);

			FHRFinish Finish;
			Finish.HorseId = H.Id;
			Finish.StableId = Entry.StableId;
			Finish.HorseName = H.Name;
			Finish.StableName = Stable ? Stable->Name : FString();
			Finish.Preparation = Entry.Preparation;
			Finish.Place = I + 1;
			Finish.TimeUs = X.Total;
			Finish.Segments = X.Segments;
			Finish.Gross = Gross;
			Finish.Points = bSemi ? 0 : bVillage ? VillagePoints[I] : FinalPoints[I];
			Finish.Prestige = bSemi ? 0 : bVillage ? VillagePrestige[I] : FinalPrestige[I];
			Finish.Xp = bSemi ? 4 : Xp[I];
			Finish.Injury = Injury;
			if (!Race.Entries[X.Entry].RiderPlayerId.IsEmpty()) NamePlayerRider(S, Race.Entries[X.Entry].RiderPlayerId, Finish);
			else if (const FHRRider* Rider = RiderOf(S, H.Id)) { Finish.RiderId = Rider->Id; Finish.RiderName = Rider->FullName(); }
			if (NumRuns > 1)
			{
				Finish.RunTimesUs = X.RunTimes;
				Finish.BestRun = X.BestRun;
			}
			Race.Finishes.Add(Finish);
		}
		for (const FHRRunner& R : Race.Entries)
			if (!R.RiderPlayerId.IsEmpty()) PlayerRode(S, R.RiderPlayerId);
	}

	TArray<FHROrderCount> PublicOrders(const FHRWorldState& S, const FHRRace& Race, int32 Runs)
	{
		TMap<FString, int32> Counts;
		const HRContent::FEvent* EventPtr = HRContent::FindEvent(Race.EventId);
		for (const FHRRunner& R : Race.Entries)
		{
			if (!S.Horses.Contains(R.HorseId)) EventPtr = nullptr;
		}
		if (!EventPtr) return {};
		const HRContent::FEvent& E = *EventPtr;
		int32 W[4];
		StageWeights(Race.Distance, W);
		static const int32 Fractions[4] = {15, 35, 25, 25};
		struct FRow
		{
			int32 Index;
			const FHRHorse* Horse;
			int32 Preparation;
			FForms Forms;
			int64 Total = 0;
			int64 Last = 0;
			int32 BreakRank = 0;
			int32 ChallengeRank = 0;
			int32 Rider[4] = {0, 0, 0, 0};
		};
		const int32 RunsEach = E.Runs;
		for (int32 Run = 0; Run < Runs; ++Run)
		{
			TArray<FRow> Field;
			// Two-run races: the public judges each horse on the better of two fresh runs.
			for (int32 Leg = 0; Leg < RunsEach; ++Leg)
			{
				// Fresh public form draws: never the race's own seed.
				const FString Seed = Leg == 0 ? FString::Printf(TEXT("%s:public:%d:%s:%d"), *S.Seed, S.T, *Race.Key, Run)
					: FString::Printf(TEXT("%s:public:%d:%s:%d:leg%d"), *S.Seed, S.T, *Race.Key, Run, Leg);
				TArray<FRow> Leg1;
				for (int32 I = 0; I < Race.Entries.Num(); ++I)
				{
					FRow Row;
					Row.Index = I;
					Row.Horse = &S.Horses.FindChecked(Race.Entries[I].HorseId);
					Row.Preparation = Race.Entries[I].Preparation;
					Row.Forms = OpenForms(*Row.Horse, Row.Preparation, Seed);
					// The public knows the riders (the player included): their bonus is in the odds.
					for (int32 B = 0; B < 4; ++B) Row.Rider[B] = RunnerRiderBonus(S, Race.Entries[I], B, Race.Distance);
					Leg1.Add(Row);
				}
				for (int32 Beat = 0; Beat < 4; ++Beat)
				{
					const double Length = (Race.Distance * Fractions[Beat]) / 100.0;
					for (FRow& X : Leg1)
					{
						const int32 Score = Performance(*X.Horse, X.Preparation, E, Race.Distance, Beat, X.Forms.F[Beat], X.BreakRank, X.ChallengeRank, PressureFor(E), X.Rider[Beat]);
						X.Last = StageDuration(Length, Score, W[Beat], Beat == 2 && E.Shape == 2);
						X.Total += X.Last;
					}
					Leg1.Sort([](const FRow& A, const FRow& B)
					{
						if (A.Total != B.Total) return A.Total < B.Total;
						if (A.Last != B.Last) return A.Last < B.Last;
						return A.Index < B.Index;
					});
					for (int32 I = 0; I < Leg1.Num(); ++I)
					{
						if (Beat == 0) Leg1[I].BreakRank = I + 1;
						if (Beat == 2) Leg1[I].ChallengeRank = I + 1;
					}
				}
				if (Leg == 0) { Field = MoveTemp(Leg1); continue; }
				for (FRow& X : Field)
				{
					const FRow* Again = Leg1.FindByPredicate([&X](const FRow& R) { return R.Index == X.Index; });
					if (Again && Again->Total < X.Total) { X.Total = Again->Total; X.Last = Again->Last; }
				}
				Field.Sort([](const FRow& A, const FRow& B)
				{
					if (A.Total != B.Total) return A.Total < B.Total;
					return A.Index < B.Index;
				});
			}
			TArray<FString> Top;
			for (int32 I = 0; I < FMath::Min(3, Field.Num()); ++I) Top.Add(FString::FromInt(Field[I].Index));
			Counts.FindOrAdd(FString::Join(Top, TEXT(">")))++;
		}
		TArray<FHROrderCount> Out;
		for (const TPair<FString, int32>& C : Counts)
		{
			FHROrderCount O;
			O.Key = C.Key;
			O.Count = C.Value;
			Out.Add(O);
		}
		Out.Sort([](const FHROrderCount& A, const FHROrderCount& B) { return A.Count > B.Count || (A.Count == B.Count && A.Key < B.Key); });
		return Out;
	}
}
