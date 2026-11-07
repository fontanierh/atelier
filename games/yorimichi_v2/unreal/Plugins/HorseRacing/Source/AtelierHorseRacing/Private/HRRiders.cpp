#include "HRRules.h"

#include "HRRandom.h"
#include "HRRiderNames.inl"

// Riders: every stable keeps three jockeys on fixed salaries, each with a hidden career curve (growth, peak, decline,
// retirement) that steps once per rider month. Their effect is small (-2..+2 per race stage); four legends have their
// own look and specialty, one of each at a time, with a season of cooldown after a retirement. Riders move between
// stables through the transfer list: a listed rider goes to whichever stable pays the price.

namespace
{
	struct FPool
	{
		const TCHAR* Culture;
		int32 Weight;
		TArrayView<const TCHAR* const> Male, Female, Last;
		/** Countries shown for this pool, the first one most often. */
		TArray<const TCHAR*> Countries;
	};

	const TArray<FPool>& Pools()
	{
		static const TArray<FPool> P = {
			{TEXT("fr"), 30, GHRRider_fr_Male, GHRRider_fr_Female, GHRRider_fr_Last, {TEXT("FR"), TEXT("FR"), TEXT("FR"), TEXT("BE"), TEXT("CH")}},
			{TEXT("gb"), 20, GHRRider_gb_Male, GHRRider_gb_Female, GHRRider_gb_Last, {TEXT("GB"), TEXT("GB"), TEXT("GB"), TEXT("IE")}},
			{TEXT("us"), 20, GHRRider_us_Male, GHRRider_us_Female, GHRRider_us_Last, {TEXT("US"), TEXT("US"), TEXT("US"), TEXT("CA")}},
			{TEXT("la"), 15, GHRRider_la_Male, GHRRider_la_Female, GHRRider_la_Last, {TEXT("MX"), TEXT("AR"), TEXT("ES"), TEXT("CO"), TEXT("CL"), TEXT("PE")}},
			{TEXT("jp"), 4, GHRRider_jp_Male, GHRRider_jp_Female, GHRRider_jp_Last, {TEXT("JP")}},
			{TEXT("kr"), 4, GHRRider_kr_Male, GHRRider_kr_Female, GHRRider_kr_Last, {TEXT("KR")}},
			{TEXT("cn"), 4, GHRRider_cn_Male, GHRRider_cn_Female, GHRRider_cn_Last, {TEXT("CN")}},
			{TEXT("vn"), 3, GHRRider_vn_Male, GHRRider_vn_Female, GHRRider_vn_Last, {TEXT("VN")}},
		};
		return P;
	}

	/** The four legends: a specialty, a look and a curve. The maestro is the strongest, so the rarest. Their names are
	 * drawn like anyone's. */
	struct FLegendDef
	{
		const TCHAR* Id;
		const TCHAR* Culture;
		bool bFemale;
		int32 Weight;
		int32 Potential[4];
		int32 Height, Build, Head, Hair, HairColor, Skin, Beard;
	};
	const FLegendDef Legends[4] = {
		// Very short and stocky, a long braided beard.
		{TEXT("sprinter"), TEXT("us"), false, 30, {880, 640, 600, 620}, 150, 2, 3, 3, 5, 1, 4},
		// Tall and athletic, shaved head, goatee.
		{TEXT("flyer"), TEXT("us"), false, 30, {930, 700, 930, 700}, 198, 0, 1, 4, 0, 5, 2},
		// Long brown hair and a full beard.
		{TEXT("maestro"), TEXT("fr"), false, 10, {850, 850, 850, 850}, 178, 0, 2, 1, 2, 2, 3},
		// Tall, slim and elegant.
		{TEXT("stayer"), TEXT("fr"), true, 30, {680, 820, 700, 950}, 186, 0, 0, 1, 1, 2, 0},
	};

	FString StableName(const FHRWorldState& S, const FString& Id)
	{
		const FHRStable* St = HRRules::FindStable(S, Id);
		return St ? St->Name : Id;
	}

	bool LegendAvailable(const FHRWorldState& S, const FString& Id)
	{
		if (S.LegendCooldownUntil.FindRef(Id) > S.T) return false;
		for (const TPair<FString, FHRRider>& It : S.Riders)
			if (It.Value.Legend == Id && !It.Value.IsRetired()) return false;
		return true;
	}

	bool NameTaken(const FHRWorldState& S, const FString& First, const FString& Last)
	{
		for (const TPair<FString, FHRRider>& It : S.Riders)
			if (!It.Value.IsRetired() && It.Value.FirstName == First && It.Value.LastName == Last) return true;
		return false;
	}

	int32 Noise(const FHRRider& R, int32 Age, int32 Stat)
	{
		return HRRandom::Draw(R.Seed, FString::Printf(TEXT("noise:%d:%d"), Age, Stat), 7) - 3;
	}

	/** The salary a rider signs for, fixed for as long as they stay. */
	int32 SigningWage(const FHRRider& R)
	{
		if (!R.Legend.IsEmpty()) return 12;
		return FMath::Clamp(HRRules::RiderOverall(R) / 4 - 4, 1, 6);
	}

	struct FRiderOptions
	{
		FString OwnerId;
		/** Age in rider months when generated (17 years for an academy rider). */
		int32 Age = 17 * 12;
		int32 LegendPerMille = HRRules::RiderLegendPerMille;
	};

	FHRRider& NewRider(FHRWorldState& S, const FRiderOptions& O)
	{
		FHRRider R;
		R.Id = FString::Printf(TEXT("rider:%d"), ++S.RiderSerial);
		R.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *R.Id);
		R.OwnerId = O.OwnerId;

		const FLegendDef* Legend = nullptr;
		if (HRRandom::Draw(R.Seed, TEXT("legend"), 1000) < O.LegendPerMille)
		{
			TArray<int64> W;
			for (const FLegendDef& L : Legends) W.Add(LegendAvailable(S, L.Id) ? L.Weight : 0);
			int64 Sum = 0;
			for (int64 X : W) Sum += X;
			if (Sum > 0) Legend = &Legends[HRRandom::PickWeighted(R.Seed, TEXT("legend:which"), W)];
		}

		const TArray<FPool>& P = Pools();
		TArray<int64> W;
		for (const FPool& X : P) W.Add(X.Weight);
		const FPool* Pool = &P[HRRandom::PickWeighted(R.Seed, TEXT("culture"), W)];
		if (Legend) Pool = P.FindByPredicate([Legend](const FPool& X) { return FCString::Strcmp(X.Culture, Legend->Culture) == 0; });
		R.Culture = Pool->Culture;
		R.Country = Pool->Countries[HRRandom::Draw(R.Seed, TEXT("country"), Pool->Countries.Num())];
		R.bFemale = Legend ? Legend->bFemale : HRRandom::Draw(R.Seed, TEXT("sex"), 100) < 40;
		// Mostly a first and last name of the same culture; 15 % of riders have a mixed family.
		const FPool& LastPool = HRRandom::Draw(R.Seed, TEXT("mixed"), 100) < 15 ? P[HRRandom::PickWeighted(R.Seed, TEXT("culture:last"), W)] : *Pool;
		const TArrayView<const TCHAR* const> Firsts = R.bFemale ? Pool->Female : Pool->Male;
		for (int32 Try = 0; Try < 40; ++Try)
		{
			R.FirstName = Firsts[HRRandom::Draw(R.Seed, FString::Printf(TEXT("first:%d"), Try), Firsts.Num())];
			R.LastName = LastPool.Last[HRRandom::Draw(R.Seed, FString::Printf(TEXT("last:%d"), Try), LastPool.Last.Num())];
			if (!NameTaken(S, R.FirstName, R.LastName)) break;
		}

		if (Legend)
		{
			R.Legend = Legend->Id;
			for (int32 I = 0; I < 4; ++I) R.Potential.Add(Legend->Potential[I]);
			R.Growth = 40;
			R.PeakAge = 27 * 12;
			R.PeakMonths = 60;
			R.Decline = 3;
			R.RetireAge = 41 * 12;
			R.Height = Legend->Height;
			R.Build = Legend->Build;
			R.Head = Legend->Head;
			R.Hair = Legend->Hair;
			R.HairColor = Legend->HairColor;
			R.Skin = Legend->Skin;
			R.Beard = Legend->Beard;
		}
		else
		{
			const int32 Talent = 380 + HRRandom::Draw(R.Seed, TEXT("talent"), 420);
			for (int32 I = 0; I < 4; ++I)
				R.Potential.Add(FMath::Clamp(Talent + HRRandom::Draw(R.Seed, FString::Printf(TEXT("pot:%d"), I), 301) - 150, 250, 980));
			R.Growth = 15 + HRRandom::Draw(R.Seed, TEXT("growth"), 26);
			R.PeakAge = (26 + HRRandom::Draw(R.Seed, TEXT("peak"), 7)) * 12;
			// A peak can be short or long.
			static const TArray<int64> Lengths = {30, 45, 25};
			const int32 Band = HRRandom::PickWeighted(R.Seed, TEXT("peak:band"), Lengths);
			R.PeakMonths = (Band == 0 ? 12 : Band == 1 ? 36 : 60) + HRRandom::Draw(R.Seed, TEXT("peak:len"), 13);
			R.Decline = 3 + HRRandom::Draw(R.Seed, TEXT("decline"), 4);
			R.RetireAge = (36 + HRRandom::Draw(R.Seed, TEXT("retire"), 7)) * 12;
			// Jockeys are mostly small and light; a few tall riders stand out.
			const int32 Tall = HRRandom::Draw(R.Seed, TEXT("tall"), 100) < 12 ? 12 : 0;
			R.Height = (R.bFemale ? 152 : 158) + HRRandom::Draw(R.Seed, TEXT("height"), 15) + HRRandom::Draw(R.Seed, TEXT("height2"), 10) + Tall;
			R.Build = HRRandom::PickWeighted(R.Seed, TEXT("build"), {45, 40, 15});
			R.Head = HRRandom::Draw(R.Seed, TEXT("head"), 4);
			R.Hair = R.bFemale ? HRRandom::PickWeighted(R.Seed, TEXT("hair"), {6, 20, 20, 14, 1, 10, 20, 9})
				: HRRandom::PickWeighted(R.Seed, TEXT("hair"), {40, 6, 2, 1, 14, 16, 2, 19});
			const bool bAsian = R.Culture == TEXT("jp") || R.Culture == TEXT("kr") || R.Culture == TEXT("cn") || R.Culture == TEXT("vn");
			const bool bLatino = R.Culture == TEXT("la");
			R.HairColor = bAsian ? HRRandom::PickWeighted(R.Seed, TEXT("haircol"), {85, 15, 0, 0, 0, 0})
				: bLatino ? HRRandom::PickWeighted(R.Seed, TEXT("haircol"), {35, 40, 20, 3, 2, 0})
				: HRRandom::PickWeighted(R.Seed, TEXT("haircol"), {12, 26, 22, 12, 20, 8});
			R.Skin = bAsian ? HRRandom::PickWeighted(R.Seed, TEXT("skin"), {0, 30, 60, 10, 0, 0})
				: bLatino ? HRRandom::PickWeighted(R.Seed, TEXT("skin"), {5, 15, 35, 30, 10, 5})
				: R.Culture == TEXT("us") ? HRRandom::PickWeighted(R.Seed, TEXT("skin"), {25, 25, 12, 10, 14, 14})
				: HRRandom::PickWeighted(R.Seed, TEXT("skin"), {35, 33, 12, 8, 6, 6});
			R.Beard = R.bFemale ? 0 : HRRandom::PickWeighted(R.Seed, TEXT("beard"), {68, 15, 8, 9, 0});
		}

		// The rider starts at 17 and has already lived the curve up to the requested age; a legend always starts young.
		const int32 StartAge = Legend ? FMath::Min(O.Age, 19 * 12) : O.Age;
		R.BirthT = S.T - StartAge * HRClock::LifeMonth;
		for (int32 I = 0; I < 4; ++I) R.Skill.Add(FMath::Max(150, R.Potential[I] * 45 / 100));
		for (int32 Age = 17 * 12; Age < StartAge; ++Age) HRRules::StepRiderCurve(R, Age, Age >= 18 * 12 ? 1 : 0);
		R.SeasonSkill = R.Skill;
		R.DebutT = S.T - FMath::Max(0, StartAge - 18 * 12) * HRClock::LifeMonth;
		R.Wage = SigningWage(R);
		if (!R.OwnerId.IsEmpty()) R.Stables.Add(R.OwnerId);
		else R.FreeSinceT = S.T;
		const FString Id = R.Id;
		return S.Riders.Add(Id, MoveTemp(R));
	}

	TArray<FHRRider*> Roster(FHRWorldState& S, const FString& StableId)
	{
		TArray<FHRRider*> Out;
		for (TPair<FString, FHRRider>& It : S.Riders)
			if (It.Value.OwnerId == StableId && !It.Value.IsRetired()) Out.Add(&It.Value);
		Out.Sort([](const FHRRider& A, const FHRRider& B)
		{
			const int32 OA = HRRules::RiderOverall(A) + (A.Legend.IsEmpty() ? 0 : 100), OB = HRRules::RiderOverall(B) + (B.Legend.IsEmpty() ? 0 : 100);
			return OA != OB ? OA > OB : A.Id < B.Id;
		});
		return Out;
	}

	void LegendNews(FHRWorldState& S, const FHRRider& R)
	{
		if (R.Legend.IsEmpty()) return;
		HRRules::AddNews(S, TEXT("rider"),
			FString::Printf(TEXT("A legend! %s, %s, signs for %s."), *R.FullName(), *HRRules::LegendTitle(R.Legend).ToLower(), *StableName(S, R.OwnerId)),
			{}, {R.OwnerId});
	}

	/** The buyer pays the listed price to the seller (a player's stable passes it on at the day's sweep). */
	void Transfer(FHRWorldState& S, FHRRider& R, FHRStable& Buyer)
	{
		const FString From = R.OwnerId;
		const int32 Price = R.ListedPrice;
		Buyer.Coins -= Price;
		if (FHRStable* Seller = HRRules::FindStable(S, From)) Seller->Coins = HRRules::Credit(Seller->Coins, Price);
		HRRules::AddNews(S, TEXT("transfer"),
			FString::Printf(TEXT("Transfer: %s leaves %s for %s (%d coins)."), *R.FullName(), *StableName(S, From), *Buyer.Name, Price),
			{}, {From, Buyer.Id});
		R.OwnerId = Buyer.Id;
		R.ListedPrice = 0;
		R.FreeSinceT = -1;
		R.Wage = SigningWage(R);
		R.Stables.Add(Buyer.Id);
	}

	void Free(FHRWorldState& S, FHRRider& R)
	{
		R.OwnerId.Reset();
		R.ListedPrice = 0;
		R.FreeSinceT = S.T;
	}
}

namespace HRRules
{
	int32 RiderAgeMonths(const FHRRider& R, int32 T)
	{
		return HRClock::LifeMonths(R.BirthT, T);
	}

	int32 RiderOverall(const FHRRider& R)
	{
		int32 Sum = 0;
		for (int32 V : R.Skill) Sum += RiderStat(V);
		return Sum;
	}

	int32 RiderValue(const FHRRider& R, int32 T)
	{
		const int32 Avg = RiderOverall(R);  // 4..40
		int32 Value = 10 + FMath::Square(FMath::Max(0, Avg - 12)) / 4;
		const int32 Age = RiderAgeMonths(R, T);
		if (Age >= R.PeakAge + R.PeakMonths) Value = Value * 6 / 10;
		else if (Age < R.PeakAge) Value = Value * 11 / 10;
		if (!R.Legend.IsEmpty()) Value *= 3;
		return Value;
	}

	void StepRiderCurve(FHRRider& R, int32 Age, int32 Rides)
	{
		const int32 DeclineStart = R.PeakAge + R.PeakMonths;
		for (int32 I = 0; I < 4; ++I)
		{
			int32& V = R.Skill[I];
			const int32 Pot = R.Potential[I];
			if (Age < R.PeakAge)
			{
				// Racing experience adds a little growth.
				V += FMath::Max(0, (Pot - V) * R.Growth / 1000) + FMath::Min(Rides, 3) + Noise(R, Age, I);
				V = FMath::Min(V, Pot);
			}
			else if (Age < DeclineStart)
			{
				V = FMath::Min(Pot, V + Noise(R, Age, I));
			}
			else
			{
				// A slow decline that speeds up with the years (about 2 stat points over the first three years).
				V -= R.Decline * (48 + Age - DeclineStart) / 48 - Noise(R, Age, I);
			}
			V = FMath::Clamp(V, 100, 1000);
		}
	}

	TArray<const FHRRider*> StableRiders(const FHRWorldState& S, const FString& StableId)
	{
		TArray<FHRRider*> Mut = Roster(const_cast<FHRWorldState&>(S), StableId);
		return TArray<const FHRRider*>(Mut);
	}

	const FHRRider* RiderOf(const FHRWorldState& S, const FString& HorseId)
	{
		const FString* Id = S.Meeting.Riders.Find(HorseId);
		return Id ? S.Riders.Find(*Id) : nullptr;
	}

	int32 RiderBonus(const FHRRider& R, int32 Stage, int32 Distance, int32 T)
	{
		int32 Bonus = 0;
		if (R.Skill.IsValidIndex(Stage))
			Bonus = FMath::Clamp((int32)HRRandom::Round((R.Skill[Stage] - 500) / 250.0), -2, 2);
		if (R.Legend == TEXT("sprinter"))
		{
			// An exponential start: +1 in the first season, then +2, +4 and +6.
			static const int32 Curve[4] = {1, 2, 4, 6};
			const int32 Season = FMath::Clamp((T - R.DebutT) / HRClock::DaysPerSeason, 0, 3);
			if (Stage == 0 || (Stage == 1 && Distance <= 900)) Bonus += Curve[Season];
		}
		else if (R.Legend == TEXT("flyer"))
		{
			if (Stage == 0 || Stage == 2) Bonus += 3;
		}
		else if (R.Legend == TEXT("maestro"))
		{
			Bonus += 3;
		}
		else if (R.Legend == TEXT("stayer"))
		{
			if (Stage == 3) Bonus += Distance >= 1400 ? 7 : 5;
		}
		return Bonus;
	}

	FString LegendTitle(const FString& Legend)
	{
		if (Legend == TEXT("sprinter")) return TEXT("The Mountain Sprinter");
		if (Legend == TEXT("flyer")) return TEXT("His Airness");
		if (Legend == TEXT("maestro")) return TEXT("The Maestro of the Track");
		if (Legend == TEXT("stayer")) return TEXT("The Queen of Endurance");
		return FString();
	}

	void CreateRiders(FHRWorldState& S)
	{
		// A stable for sale keeps its staff; they come with the stable when it is bought.
		for (FHRStable& St : S.Stables)
		{
			if (!St.bForSale) continue;
			for (int32 I = 0; I < RidersPerStable; ++I)
			{
				FRiderOptions O;
				O.OwnerId = St.Id;
				O.Age = (19 + HRRandom::Draw(S.Seed, FString::Printf(TEXT("riders:%s:%d"), *St.Id, I), 8)) * 12;
				O.LegendPerMille = ForSaleLegendPerMille;
				NewRider(S, O);
			}
		}
		bool bLegend = false;
		for (const TPair<FString, FHRRider>& It : S.Riders) bLegend |= !It.Value.Legend.IsEmpty();
		for (FHRStable& St : S.Stables)
		{
			if (St.bForSale) continue;
			for (int32 I = 0; I < RidersPerStable; ++I)
			{
				FRiderOptions O;
				O.OwnerId = St.Id;
				// A mixed roster: from young prospects to veterans near retirement.
				O.Age = (18 + HRRandom::Draw(S.Seed, FString::Printf(TEXT("riders:%s:%d"), *St.Id, I), 19)) * 12 +
					HRRandom::Draw(S.Seed, FString::Printf(TEXT("riders:%s:%d:m"), *St.Id, I), 12);
				// A world starts with at most one legend in all.
				O.LegendPerMille = bLegend ? 0 : RiderLegendPerMille;
				bLegend |= !NewRider(S, O).Legend.IsEmpty();
			}
		}
	}

	int32 SignAcademyRiders(FHRWorldState& S, const FString& StableId, int32 LegendPerMille)
	{
		int32 Signed = 0;
		while (StableRiders(S, StableId).Num() < RidersPerStable)
		{
			FRiderOptions O;
			O.OwnerId = StableId;
			O.Age = (17 + HRRandom::Draw(S.Seed, FString::Printf(TEXT("academy:%s:%d:%d"), *StableId, S.T, Signed), 3)) * 12;
			O.LegendPerMille = LegendPerMille;
			LegendNews(S, NewRider(S, O));
			Signed++;
		}
		return Signed;
	}

	void AssignRiders(FHRWorldState& S, const TArray<FHRRunner>& Entries)
	{
		S.Meeting.Riders.Reset();
		for (const FHRStable& St : S.Stables)
		{
			if (St.bForSale) continue;
			TArray<FHRRider*> Riders = Roster(S, St.Id);
			int32 Next = 0;
			// Entries arrive best first for each stable: the best rider gets the best entry.
			for (const FHRRunner& R : Entries)
			{
				if (R.StableId != St.Id || !R.RiderPlayerId.IsEmpty() || Next >= Riders.Num()) continue;
				S.Meeting.Riders.Add(R.HorseId, Riders[Next++]->Id);
			}
		}
	}

	void AdvanceRiders(FHRWorldState& S)
	{
		// Rides and wins of the race day that is closing (S.T is still that day).
		for (const FHRRace& Race : S.Meeting.Races)
		{
			for (const FHRFinish& F : Race.Finishes)
			{
				FHRRider* R = F.RiderId.IsEmpty() ? nullptr : S.Riders.Find(F.RiderId);
				if (!R) continue;
				R->Rides++;
				if (F.Place == 1 && !IsHeatRound(Race.Round)) R->Wins++;
			}
		}
		const int32 NextT = S.T + 1;
		TArray<FString> Ids;
		S.Riders.GetKeys(Ids);
		Ids.Sort();
		for (const FString& Id : Ids)
		{
			FHRRider& R = S.Riders[Id];
			if (R.IsRetired()) continue;
			// The curve steps once per rider month: when the next day starts a new month of age.
			const int32 Age = RiderAgeMonths(R, S.T), NextAge = RiderAgeMonths(R, NextT);
			if (NextAge > Age)
			{
				StepRiderCurve(R, Age, R.Rides - R.CurveRides);
				R.CurveRides = R.Rides;
			}
			const bool bWorn = NextAge >= R.PeakAge + R.PeakMonths && RiderOverall(R) < 12;
			const bool bUnsigned = R.OwnerId.IsEmpty() && R.FreeSinceT >= 0 && NextT - R.FreeSinceT >= FreeAgentDays;
			if (NextAge >= R.RetireAge || bWorn || bUnsigned)
			{
				const FString Owner = R.OwnerId;
				R.RetiredT = NextT;
				R.OwnerId.Reset();
				R.ListedPrice = 0;
				if (!R.Legend.IsEmpty())
				{
					S.LegendCooldownUntil.Add(R.Legend, NextT + LegendCooldownDays);
					AddNews(S, TEXT("rider"),
						FString::Printf(TEXT("%s, %s, retires after %d rides and %d wins. The legend could return next season."),
							*R.FullName(), *LegendTitle(R.Legend).ToLower(), R.Rides, R.Wins), {}, Owner.IsEmpty() ? TArray<FString>() : TArray<FString>{Owner});
				}
				else if (R.Rides >= 24 && !Owner.IsEmpty())
				{
					AddNews(S, TEXT("rider"),
						FString::Printf(TEXT("%s (%s) retires after %d rides and %d wins."), *R.FullName(), *StableName(S, Owner), R.Rides, R.Wins),
						{}, {Owner});
				}
			}
			else if (NextT % HRClock::DaysPerSeason == 0)
			{
				R.SeasonSkill = R.Skill;
			}
		}
	}

	void ManageRiders(FHRWorldState& S)
	{
		TArray<FHRStable*> Order;
		for (FHRStable& St : S.Stables)
			if (St.IsComputer()) Order.Add(&St);  // players hire, list and release their own riders
		Order.Sort([](const FHRStable& A, const FHRStable& B) { return A.Id < B.Id; });
		const bool bWindow = S.T % HRClock::DaysPerSeason == 0;
		// 1. The transfer list and upgrades, for stables with a full roster.
		for (FHRStable* StPtr : Order)
		{
			FHRStable& St = *StPtr;
			TArray<FHRRider*> Riders = Roster(S, St.Id);
			// More than three (a returning rider, an edited save): the weakest go free.
			while (Riders.Num() > RidersPerStable) Free(S, *Riders.Pop());
			if (Riders.Num() < RidersPerStable) continue;
			// The season's transfer window: last season's unsold listing is withdrawn and the weakest rider is listed.
			if (bWindow)
			{
				for (FHRRider* R : Riders) R->ListedPrice = 0;
				Riders.Last()->ListedPrice = RiderValue(*Riders.Last(), S.T);
			}
			// A well-off stable signs a clearly better listed rider and lets its weakest go.
			if (St.Coins >= 150 && St.Debt == 0)
			{
				FHRRider* Weakest = Riders.Last();
				FHRRider* Best = nullptr;
				for (TPair<FString, FHRRider>& It : S.Riders)
				{
					FHRRider& R = It.Value;
					if (R.IsRetired() || R.ListedPrice <= 0 || R.OwnerId == St.Id || (int64)R.ListedPrice + 90 > St.Coins) continue;
					if (RiderOverall(R) >= RiderOverall(*Weakest) + 4 && (!Best || RiderOverall(R) > RiderOverall(*Best) || (RiderOverall(R) == RiderOverall(*Best) && R.Id < Best->Id))) Best = &R;
				}
				if (Best)
				{
					Transfer(S, *Best, St);
					Free(S, *Weakest);
				}
			}
		}
		// 2. Every roster back to three: the best free agent, a clearly better listed rider when the coins allow it
		// (keeping a recovery reserve), else a young rider from the stable's own academy. A stable a transfer left
		// short is filled by the last pass, from free agents and the academy only, so every roster ends the day full.
		for (const bool bMarket : {true, false})
		{
			for (FHRStable* StPtr : Order)
			{
				FHRStable& St = *StPtr;
				for (int32 Guard = 0; Guard < RidersPerStable && Roster(S, St.Id).Num() < RidersPerStable; ++Guard)
				{
					FHRRider* Pick = nullptr;
					for (TPair<FString, FHRRider>& It : S.Riders)
					{
						FHRRider& R = It.Value;
						if (R.IsRetired() || !R.OwnerId.IsEmpty()) continue;
						if (!Pick || RiderOverall(R) > RiderOverall(*Pick) || (RiderOverall(R) == RiderOverall(*Pick) && R.Id < Pick->Id)) Pick = &R;
					}
					FHRRider* Bought = nullptr;
					for (TPair<FString, FHRRider>& It : S.Riders)
					{
						FHRRider& R = It.Value;
						if (!bMarket || R.IsRetired() || R.ListedPrice <= 0 || R.OwnerId == St.Id || St.Coins < (int64)R.ListedPrice + 60) continue;
						if ((!Pick || RiderOverall(R) > RiderOverall(*Pick) + 3) && (!Bought || RiderOverall(R) > RiderOverall(*Bought) || (RiderOverall(R) == RiderOverall(*Bought) && R.Id < Bought->Id))) Bought = &R;
					}
					if (Bought) Transfer(S, *Bought, St);
					else if (Pick)
					{
						Pick->OwnerId = St.Id;
						Pick->FreeSinceT = -1;
						Pick->Wage = SigningWage(*Pick);
						Pick->Stables.Add(St.Id);
						if (!Pick->Legend.IsEmpty()) LegendNews(S, *Pick);
					}
					else
					{
						FRiderOptions O;
						O.OwnerId = St.Id;
						O.Age = (17 + HRRandom::Draw(S.Seed, FString::Printf(TEXT("academy:%s:%d:%d"), *St.Id, S.T, Guard), 3)) * 12;
						LegendNews(S, NewRider(S, O));
					}
				}
			}
		}
	}

	int32 RiderWages(const FHRWorldState& S, const FString& StableId)
	{
		int64 Sum = 0;
		for (const TPair<FString, FHRRider>& It : S.Riders)
			if (It.Value.OwnerId == StableId && !It.Value.IsRetired()) Sum += FMath::Max(0, It.Value.Wage);
		return (int32)FMath::Clamp<int64>(Sum, 0, MaxCoins);
	}
}
