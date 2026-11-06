#include "HRRules.h"

#include "HRRandom.h"

// Port of the reference biology.ts (tissue loads, injuries, retirement) and training.ts progressAbility.
// Fixed point: U = 10000. Ages run on the horse clock (HRClock::LifeYear race days per horse year); loads, injuries
// and rest count race days.

using HRRandom::U;

namespace
{
	int64 Q(double V) { return HRRandom::Round(V); }

	int64 Maturity(const FHRHorse& H, int32 T)
	{
		const int32 A = T - H.BirthT;
		constexpr int32 Y = HRClock::LifeYear;
		return Q(U * (A < Y ? (0.8 * A) / Y : 0.8 + (0.2 * FMath::Min(T - H.ReadyT, Y)) / Y));
	}

	struct FThresholds
	{
		int64 Cap;
		int64 C;
		int64 K;
	};

	FThresholds Thresholds(const FHRHorse& H, int32 T, int32 Z)
	{
		const FHRZone& S = H.Zones[Z];
		const double M = (double)Maturity(H, T) / U;
		const int64 Cap = Q(0.25 * S.Structure * M);
		FThresholds R;
		R.Cap = Cap;
		R.C = FMath::Max<int64>(U, Q((0.75 * S.Structure * M + FMath::Min<int64>(S.Tolerance, Cap)) * (1 - 0.1 * S.Scars)));
		R.K = FMath::Max<int64>(U, Q(S.Acute * M * (1 - 0.08 * S.Scars)));
		return R;
	}

	void BandBounds(int64 N, const TArray<int32>& Bands, double& Low, double& High)
	{
		for (int32 I = 0; I < Bands.Num() - 1; ++I)
		{
			if (N < (int64)Bands[I + 1] * U)
			{
				Low = (double)Bands[I] * U;
				High = (double)Bands[I + 1] * U;
				return;
			}
		}
		Low = (double)Bands[Bands.Num() - 2] * U;
		High = (double)Bands[Bands.Num() - 1] * U;
	}

	TArray<int32> RawLoad(const FHRHorse& H, int32 Distance, int32 Surface, int32 Shape, int32 Preparation)
	{
		const int32 A[4] = {Distance <= 900 ? 2 : Distance <= 1300 ? 2 : 3, Distance <= 900 ? 1 : 2, Distance <= 900 ? 1 : Distance <= 1300 ? 2 : 3, Distance <= 900 ? 1 : Distance <= 1300 ? 1 : 2};
		static const int32 Surfaces[3][4] = {{0, 0, 2, 2}, {2, 1, 0, 0}, {1, 2, 1, 0}};
		static const int32 Shapes[3][4] = {{0, 0, 0, 0}, {0, 1, 0, 0}, {1, 3, 0, 0}};
		const int32 Speed = H.Abilities[HRAbility::Speed] <= 3 ? 0 : H.Abilities[HRAbility::Speed] <= 7 ? 1 : 2;
		static const int32 Fast[4] = {3, 0, 0, 3};
		static const int32 Safe[4] = {0, -1, 0, 0};
		TArray<int32> Out;
		for (int32 Z = 0; Z < 4; ++Z)
		{
			const int32 D = Preparation == 2 ? Fast[Z] : Preparation == 0 ? Safe[Z] : 0;
			Out.Add(FMath::Max(0, A[Z] + Surfaces[Surface][Z] + Shapes[Shape][Z] + D + ((Z == 0 || Z == 3) ? Speed : 0)));
		}
		return Out;
	}

	HRRules::FForecast ForecastRaw(const FHRHorse& H, const TArray<int32>& Raw, int32 T)
	{
		const double Condition = H.Condition == 3 ? 1
			: H.Condition == 2 ? 1.05
			: H.Condition == 1 ? 1.2 + 0.02 * (8 - H.Stress)
			: 1.4 + 0.02 * (8 - H.Stress);
		// The last horse year before retirement loads the tissues a little more, one step per horse month.
		const int32 LateMonths = HRClock::LifeMonths(H.ScheduledRetirementT - HRClock::LifeYear, T);
		const double AgeLoad = 1 + FMath::Max(0, FMath::Min(12, LateMonths)) / 50.0;
		HRRules::FForecast F;
		for (int32 Z = 0; Z < 4; ++Z)
		{
			F.Incoming.Add((int32)Q(Raw[Z] * U * Condition * AgeLoad));
		}
		double Low = 0, High = 0;
		int32 PermanentZone = 0, LowZone = 0, HighZone = 0;
		static const TArray<int32> CBands = {1, 4, 12, 24, 40, 64};
		static const TArray<int32> KBands = {1, 2, 6, 10, 12, 13, 14, 16, 24};
		for (int32 Z = 0; Z < 4; ++Z)
		{
			const FHRZone& S = H.Zones[Z];
			const FThresholds Th = Thresholds(H, T, Z);
			double C0, C1, K0, K1;
			BandBounds(Th.C, CBands, C0, C1);
			BandBounds(Th.K, KBands, K0, K1);
			const double Peak = (double)S.Load + F.Incoming[Z];
			const double ZoneLow = FMath::Max(Peak / C0, F.Incoming[Z] / K0);
			const double ZoneHigh = FMath::Max(Peak / C1, F.Incoming[Z] / K1);
			if (ZoneLow > Low) { Low = ZoneLow; LowZone = Z; }
			if (ZoneHigh > High) { High = ZoneHigh; HighZone = Z; }
			const double Damage = (FMath::Max(Peak / C0, F.Incoming[Z] / K0) - 1) * (1 + S.InflammationGene / 8.0) + 0.1 * S.Scars;
			if (F.Incoming[Z] > 0 && Damage > 1)
			{
				F.bPermanentRisk = true;
				PermanentZone = Z;
			}
		}
		F.Band = High > 1 ? TEXT("critical") : Low < 0.65 ? TEXT("green") : Low < 0.9 ? TEXT("amber") : TEXT("red");
		static const TCHAR* const ZoneNames[4] = {TEXT("front tendons"), TEXT("stifles"), TEXT("back"), TEXT("hind tendons")};
		const bool bEligible = HRRules::Runnable(H, T);
		if (!bEligible)
		{
			F.Reason = H.IsRetired() ? TEXT("Retired from racing.")
				: T < H.ReadyT ? FString::Printf(TEXT("Ready in %d race days."), H.ReadyT - T)
				: H.Placement != TEXT("active") ? TEXT("This horse must be at the stable.")
				: TEXT("Medical exclusion: rest and care needed.");
		}
		else if (F.Band == TEXT("critical"))
		{
			F.Reason = FString::Printf(TEXT("Critical load (%s): may not start."), ZoneNames[HighZone]);
		}
		else if (F.Band == TEXT("red"))
		{
			F.Reason = FString::Printf(TEXT("Strained zone: %s. Risk of injury."), ZoneNames[F.bPermanentRisk ? PermanentZone : LowZone]);
		}
		else
		{
			F.Reason = F.Band == TEXT("amber") ? TEXT("Careful load, no injury for this race.") : TEXT("Safe load for this race.");
		}
		F.bAllowed = bEligible && F.Band != TEXT("critical");
		return F;
	}
}

namespace HRRules
{
	bool Runnable(const FHRHorse& H, int32 T)
	{
		return H.Placement == TEXT("active") && T >= H.ReadyT && T < H.ScheduledRetirementT && !H.IsRetired() && !H.Injury.bActive;
	}

	FForecast Forecast(const FHRHorse& H, const HRContent::FEvent& E, int32 Distance, int32 Preparation, int32 T)
	{
		FForecast F = ForecastRaw(H, RawLoad(H, Distance, E.Surface, E.Shape, Preparation), T);
		if (Preparation == 2 && H.Condition == 0)
		{
			F.bAllowed = false;
			F.Reason = TEXT("No fast start when exhausted.");
		}
		return F;
	}

	void Retire(FHRHorse& H, int32 T)
	{
		if (H.IsRetired())
		{
			return;
		}
		H.RetiredT = T;
		// The horse may still breed until its history goes to the archives, two in-game years later.
		H.BreedingUntilT = T + HRClock::ArchiveDays;
		H.Placement = TEXT("retired");
	}

	FString Exert(FHRHorse& H, const FForecast& F, int32 T, bool bRace)
	{
		double Worst = 0;
		int32 Minimum = 0;
		FString Label;
		struct FOutcome { FThresholds Th; int64 Peak; double Damage; };
		TArray<FOutcome> Outcomes;
		bool bAnyDamage = false;
		for (int32 Z = 0; Z < 4; ++Z)
		{
			const FHRZone& S = H.Zones[Z];
			const FThresholds Th = Thresholds(H, T, Z);
			const int64 Peak = (int64)S.Load + F.Incoming[Z];
			double Damage = 0;
			if (F.Incoming[Z] > 0)
			{
				Damage = FMath::Max(0.0,
					(FMath::Max((double)Peak / Th.C, (double)F.Incoming[Z] / Th.K) - 1) * (1 + S.InflammationGene / 8.0) +
					0.1 * S.Scars * ((Peak > Th.C || F.Incoming[Z] > Th.K) ? 1 : 0));
			}
			bAnyDamage |= Damage > 0;
			Outcomes.Add({Th, Peak, Damage});
		}
		for (int32 Z = 0; Z < 4; ++Z)
		{
			FHRZone& S = H.Zones[Z];
			const FOutcome& O = Outcomes[Z];
			S.Load = (int32)O.Peak;
			if (O.Damage > 0)
			{
				int32 Inflammation = 1, Scar = 0, Gate = 1;
				FString Severity = TEXT("soreness");
				if (O.Damage > 1)
				{
					Inflammation = 8; Scar = 3; Gate = 99; Severity = TEXT("career-ending");
				}
				else if (O.Damage > 0.6)
				{
					Inflammation = 6 + S.InflammationGene / 4; Scar = 2; Gate = 6; Severity = TEXT("serious");
				}
				else if (O.Damage > 0.3)
				{
					Inflammation = 4 + S.InflammationGene / 4; Scar = 1; Gate = 3; Severity = TEXT("moderate");
				}
				else if (O.Damage > 0.1)
				{
					Inflammation = 2 + S.InflammationGene / 4; Gate = 1 + S.InflammationGene / 5; Severity = TEXT("light");
				}
				S.Inflammation = FMath::Min(8, FMath::Max(S.Inflammation, Inflammation));
				S.Scars = FMath::Min(3, S.Scars + Scar);
				Minimum = FMath::Max(Minimum, Gate);
				if (O.Damage > Worst)
				{
					Worst = O.Damage;
					Label = Severity;
				}
			}
			else if (!bAnyDamage && (F.Band == TEXT("green") || F.Band == TEXT("amber")) && F.Incoming[Z] > 0 && O.Th.Cap > 0)
			{
				S.Tolerance = (int32)FMath::Min<int64>(O.Th.Cap, S.Tolerance + Q(S.Adaptation * (1 - (double)S.Tolerance / O.Th.Cap)));
			}
		}
		if (Worst > 0)
		{
			H.Injury.bActive = true;
			H.Injury.Severity = Label;
			// Computer stables always choose progressive care.
			H.Injury.Plan = TEXT("progressive");
			H.Injury.Benches = 0;
			H.Injury.Minimum = Minimum;
			H.Injury.SinceT = T;
			if (Worst > 1)
			{
				Retire(H, T + (bRace ? 1 : 0));
			}
		}
		if (bRace)
		{
			H.Condition = FMath::Max(0, H.Condition - 2);
		}
		return Worst > 0 ? Label : FString();
	}

	void RecoverTissueLoad(FHRHorse& H)
	{
		if (H.Placement != TEXT("active"))
		{
			return;
		}
		for (FHRZone& Z : H.Zones)
		{
			Z.Load = (int32)FMath::Max<int64>(0, Z.Load - FMath::Max<int64>(U / 2, Q(Z.Recovery - U * 0.25 * Z.Inflammation)));
		}
	}

	void Bench(FHRHorse& H, int32 T)
	{
		if (H.Placement != TEXT("active"))
		{
			return;
		}
		RecoverTissueLoad(H);
		for (FHRZone& Z : H.Zones)
		{
			Z.Inflammation = FMath::Max(0, Z.Inflammation - 1);
		}
		if (H.Injury.bActive && !H.Injury.Plan.IsEmpty() && H.Injury.SinceT < T)
		{
			H.Injury.Benches++;
		}
	}

	void AdvanceHorse(FHRHorse& H, int32 T)
	{
		if (!H.IsRetired() && T >= H.ScheduledRetirementT)
		{
			Retire(H, H.ScheduledRetirementT);
		}
		if (H.BreedingUntilT >= 0 && T >= H.BreedingUntilT && H.Placement != TEXT("archive"))
		{
			H.Placement = TEXT("archive");
		}
		if (H.Injury.bActive && !H.Injury.Plan.IsEmpty())
		{
			const bool bExtended = H.Injury.Plan == TEXT("extended");
			bool bClear = H.Injury.Benches >= H.Injury.Minimum + (bExtended && H.Injury.Minimum >= 3 ? 2 : 0);
			for (int32 I = 0; I < 4 && bClear; ++I)
			{
				const FHRZone& Z = H.Zones[I];
				bClear = Z.Inflammation == 0 && Z.Load <= (bExtended ? 0 : Thresholds(H, T, I).C * 0.25);
			}
			if (bClear)
			{
				H.Injury = FHRInjury();
			}
		}
	}

	int32 ProgressAbility(FHRHorse& H, int32 A, int32 Base, int32 T)
	{
		const int32 Gap = H.Ceilings[A] - H.Abilities[A];
		if (Gap <= 0)
		{
			return 0;
		}
		constexpr int32 Threshold = 100 * U;
		const int64 Late = T >= H.ScheduledRetirementT - HRClock::LifeYear ? 80 : 100;
		const int64 Proximity = Gap >= 2 ? 100 : 60;
		const int64 Gain = ((int64)Base * U * H.Response[A] * Late * Proximity + 500000) / 1000000;
		H.Progress[A] += (int32)Gain;
		while (H.Progress[A] >= Threshold && H.Abilities[A] < H.Ceilings[A])
		{
			H.Progress[A] -= Threshold;
			H.Abilities[A]++;
		}
		if (H.Abilities[A] == H.Ceilings[A])
		{
			H.Progress[A] = 0;
		}
		return (int32)Gain;
	}

	bool CanBreed(const FHRWorldState& S, const FHRHorse& H)
	{
		return H.OwnerId != TEXT("market") && S.T - H.BirthT >= 2 * HRClock::LifeYear && S.T >= H.ReadyT && S.T >= H.NextBreedingT &&
			!H.Injury.bActive && (H.Placement == TEXT("active") || H.Placement == TEXT("pasture") || H.Placement == TEXT("retired")) &&
			(H.BreedingUntilT < 0 || S.T < H.BreedingUntilT) && !FindPregnancy(S, H.Id);
	}

	bool Related(const FHRWorldState& S, const FHRHorse& A, const FHRHorse& B)
	{
		auto Family = [&S](const FHRHorse& H)
		{
			TSet<FString> F;
			F.Add(H.Id);
			for (const FString& P : H.Parents)
			{
				F.Add(P);
				if (const FHRHorse* Parent = S.Horses.Find(P))
				{
					for (const FString& G : Parent->Parents) F.Add(G);
				}
			}
			return F;
		};
		const TSet<FString> X = Family(A);
		for (const FString& Id : Family(B))
		{
			if (X.Contains(Id)) return true;
		}
		return false;
	}
}
