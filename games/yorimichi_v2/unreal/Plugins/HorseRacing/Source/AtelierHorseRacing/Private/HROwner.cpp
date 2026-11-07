#include "HRRules.h"

#include "HRRandom.h"

// Players and the stables they own. A player is an opaque id the game chooses; any number of them share one world. A
// player bets from the start and may buy a stable listed for sale, or found a new one. An owner decides: horses from
// the market, which horses rest on a race day, riders (hire, list, release), whether they ride themselves, training
// sessions and breeding. Races are always simulated from the horses' stats and the riders' skills, the player's
// included; the interactive part is training. An owned stable's money is its owner's coins.
namespace HRRules
{
	namespace
	{
		void Own(FHRWorldState& S, FHRHorse& H, FHRStable& St)
		{
			H.OwnerId = St.Id;
			int32 Active = 0;
			for (const TPair<FString, FHRHorse>& It : S.Horses)
				if (It.Value.OwnerId == St.Id && It.Value.Placement == TEXT("active") && &It.Value != &H) ++Active;
			H.Placement = Active < 6 ? TEXT("active") : TEXT("pasture");
			if (H.Owners.Num() == 0 || H.Owners.Last() != St.Id) H.Owners.Add(St.Id);
			St.AcquisitionT = S.T;
		}

		FGenerationOptions RecruitOptions(const FHRWorldState& S, const FString& PlayerId, int32 Slot)
		{
			FGenerationOptions O;
			O.Id = FString::Printf(TEXT("market:%s:%d:%d"), *PlayerId, S.T, Slot);
			O.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *O.Id);
			O.OwnerId = TEXT("market");
			O.T = S.T;
			O.Origin = TEXT("recruit");
			O.Slot = Slot;
			return O;
		}

		FString PlayerName(const FHRWorldState& S, const FString& PlayerId)
		{
			const FHRPlayer* P = FindPlayer(S, PlayerId);
			return P && !P->Name.IsEmpty() ? P->Name : PlayerId;
		}

		/** The starter horse: a modest all-round adult, ready to race. */
		FHRHorse& GiveStarter(FHRWorldState& S, FHRStable& St)
		{
			FGenerationOptions O;
			O.Id = FString::Printf(TEXT("%s:starter:%d"), *St.Id, S.T);
			O.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *O.Id);
			O.OwnerId = St.Id;
			O.T = S.T;
			O.Origin = TEXT("recruit");
			O.Slot = 1;
			O.Prospect = TEXT("modest");
			FHRHorse& H = AddHorse(S, GenerateHorse(O));
			Own(S, H, St);
			H.Placement = TEXT("active");
			return H;
		}

		FString OwnerRefusal(const FHRWorldState& S, const FString& PlayerId)
		{
			const FHRPlayer* P = FindPlayer(S, PlayerId);
			if (!P) return TEXT("Unknown player.");
			if (PlayerStable(S, PlayerId)) return TEXT("You already own a stable.");
			if (P->Coins < StablePrice) return FString::Printf(TEXT("A stable costs %d coins."), StablePrice);
			return FString();
		}

		void GrowSkill(FHRPlayer& P, int32 Stage, int32 By)
		{
			while (P.RiderSkill.Num() < 4) P.RiderSkill.Add(PlayerStartSkill);
			int32& V = P.RiderSkill[Stage];
			V = FMath::Clamp(V + By, 0, FMath::Max(V, PlayerMaxSkill));
		}

		/** Race stage that rides on each ability: start (acceleration), rhythm (speed), finish (endurance), attack (composure). */
		constexpr int32 StageOfAbility[4] = {0, 1, 3, 2};
	}

	FHRPlayer& AddPlayer(FHRWorldState& S, const FString& PlayerId, const FString& Name)
	{
		if (FHRPlayer* P = S.Players.Find(PlayerId)) return *P;
		FHRPlayer P;
		P.Id = PlayerId;
		P.Name = Name;
		return S.Players.Add(PlayerId, P);
	}

	FHRPlayer* FindPlayer(FHRWorldState& S, const FString& PlayerId)
	{
		return S.Players.Find(PlayerId);
	}

	const FHRPlayer* FindPlayer(const FHRWorldState& S, const FString& PlayerId)
	{
		return S.Players.Find(PlayerId);
	}

	FHRStable* PlayerStable(FHRWorldState& S, const FString& PlayerId)
	{
		if (PlayerId.IsEmpty()) return nullptr;
		return S.Stables.FindByPredicate([&PlayerId](const FHRStable& St) { return St.OwnerPlayerId == PlayerId; });
	}

	const FHRStable* PlayerStable(const FHRWorldState& S, const FString& PlayerId)
	{
		if (PlayerId.IsEmpty()) return nullptr;
		return S.Stables.FindByPredicate([&PlayerId](const FHRStable& St) { return St.OwnerPlayerId == PlayerId; });
	}

	FString BuyStable(FHRWorldState& S, const FString& PlayerId, const FString& StableId, bool bKeepRiders)
	{
		FHRStable* St = FindStable(S, StableId);
		if (!St || !St->bForSale) return TEXT("This stable is not for sale.");
		const FString Why = OwnerRefusal(S, PlayerId);
		if (!Why.IsEmpty()) return Why;
		FHRPlayer& P = *FindPlayer(S, PlayerId);
		P.Coins -= StablePrice;
		St->bForSale = false;
		St->OwnerPlayerId = PlayerId;
		St->Coins = 0;
		St->Debt = 0;
		St->Profile = TEXT("player");
		St->Motto = TEXT("A new story begins.");
		int32 Kept = 0;
		for (TPair<FString, FHRRider>& It : S.Riders)
		{
			FHRRider& R = It.Value;
			if (R.OwnerId != St->Id || R.IsRetired()) continue;
			if (bKeepRiders) { ++Kept; R.ListedPrice = 0; }
			else { R.OwnerId.Reset(); R.FreeSinceT = S.T; R.ListedPrice = 0; }
		}
		P.bRides = !bKeepRiders || Kept == 0;
		const FHRHorse& H = GiveStarter(S, *St);
		AddNews(S, TEXT("purchase"),
			FString::Printf(TEXT("%s has a new owner: %s, %s. First horse: %s."), *St->Name, *PlayerName(S, PlayerId),
				bKeepRiders && Kept ? *FString::Printf(TEXT("who keeps its %d riders"), Kept) : TEXT("who will ride the horses"), *H.Name),
			{H.Id}, {St->Id});
		return FString();
	}

	FString FoundStable(FHRWorldState& S, const FString& PlayerId, const FString& Name, const FString& Color)
	{
		const FString Why = OwnerRefusal(S, PlayerId);
		if (!Why.IsEmpty()) return Why;
		const FString Id = TEXT("player:") + PlayerId;
		if (FindStable(S, Id)) return TEXT("This stable already exists.");
		FHRPlayer& P = *FindPlayer(S, PlayerId);
		P.Coins -= StablePrice;
		FHRStable St;
		St.Id = Id;
		St.Name = Name.TrimStartAndEnd().IsEmpty() ? PlayerName(S, PlayerId) + TEXT("'s Stable") : Name.TrimStartAndEnd().Left(40);
		St.Color = Color.IsEmpty() ? FString(TEXT("8a8478")) : Color;
		St.Profile = TEXT("player");
		St.Motto = TEXT("A new story begins.");
		St.OwnerPlayerId = PlayerId;
		S.Stables.Add(St);
		const int32 Signed = SignAcademyRiders(S, Id);
		FHRStable& Mine = S.Stables.Last();
		P.bRides = true;
		const FHRHorse& H = GiveStarter(S, Mine);
		AddNews(S, TEXT("purchase"),
			FString::Printf(TEXT("%s founds %s, with %d young riders. First horse: %s."), *PlayerName(S, PlayerId), *Mine.Name,
				Signed, *H.Name),
			{H.Id}, {Id});
		return FString();
	}

	TArray<FHRHorse> MarketRecruits(const FHRWorldState& S, const FString& PlayerId)
	{
		TArray<FHRHorse> Out;
		for (int32 Slot = 0; Slot < 2; ++Slot)
		{
			const FGenerationOptions O = RecruitOptions(S, PlayerId, Slot);
			if (S.Horses.Contains(O.Id)) continue;  // already bought today
			Out.Add(GenerateHorse(O));
		}
		return Out;
	}

	FString BuyHorse(FHRWorldState& S, const FString& PlayerId, const FString& Key)
	{
		FHRStable* St = PlayerStable(S, PlayerId);
		FHRPlayer* P = FindPlayer(S, PlayerId);
		if (!St || !P) return TEXT("Buy a stable first.");
		if (Key.StartsWith(TEXT("market:")))
		{
			const int32 Slot = Key == TEXT("market:prospect") ? 0 : 1;
			const int32 Price = Slot == 0 ? ProspectPrice : AdultPrice;
			const FGenerationOptions O = RecruitOptions(S, PlayerId, Slot);
			if (S.Horses.Contains(O.Id)) return TEXT("This horse is already sold.");
			if (P->Coins < Price) return FString::Printf(TEXT("It costs %d coins."), Price);
			P->Coins -= Price;
			FHRHorse& H = AddHorse(S, GenerateHorse(O));
			St->Purchases++;
			Own(S, H, *St);
			AddNews(S, TEXT("purchase"), FString::Printf(TEXT("%s buys %s at the market for %d coins."), *St->Name, *H.Name, Price), {H.Id}, {St->Id});
			return FString();
		}
		const int32 I = S.Listings.IndexOfByPredicate([&Key](const FHRSaleListing& L) { return L.HorseId == Key; });
		if (I == INDEX_NONE) return TEXT("This horse is no longer for sale.");
		const FHRSaleListing L = S.Listings[I];
		if (L.SellerId == St->Id) return TEXT("This horse is already yours.");
		if (P->Coins < L.Price) return FString::Printf(TEXT("It costs %d coins."), L.Price);
		S.Listings.RemoveAt(I);
		P->Coins -= L.Price;
		FHRHorse& H = S.Horses.FindChecked(L.HorseId);
		FHRStable* Seller = FindStable(S, L.SellerId);
		if (Seller) { Seller->Coins = Credit(Seller->Coins, L.Price); Seller->Sales++; }
		St->Purchases++;
		Own(S, H, *St);
		AddNews(S, TEXT("sale"), FString::Printf(TEXT("Sale: %s leaves %s for %s, %d coins."), *H.Name,
			Seller ? *Seller->Name : TEXT("a breeder"), *St->Name, L.Price), {H.Id}, {L.SellerId, St->Id});
		SweepOwnerCoins(S);
		return FString();
	}

	FString ListHorse(FHRWorldState& S, const FString& PlayerId, const FString& HorseId, bool bList)
	{
		FHRStable* St = PlayerStable(S, PlayerId);
		FHRHorse* H = S.Horses.Find(HorseId);
		if (!St || !H || H->OwnerId != St->Id) return TEXT("This horse is not yours.");
		const int32 I = S.Listings.IndexOfByPredicate([&HorseId](const FHRSaleListing& L) { return L.HorseId == HorseId; });
		if (!bList)
		{
			if (I != INDEX_NONE) S.Listings.RemoveAt(I);
			return FString();
		}
		if (I != INDEX_NONE) return FString();
		if (H->IsRetired() || H->Injury.bActive) return TEXT("A retired or injured horse cannot be sold.");
		FHRSaleListing L;
		L.HorseId = HorseId;
		L.SellerId = St->Id;
		L.SinceT = S.T;
		L.Price = SaleValue(S, *H);
		S.Listings.Add(L);
		AddNews(S, TEXT("listing"), FString::Printf(TEXT("%s puts %s up for sale for %d coins."), *St->Name, *H->Name, L.Price), {H->Id}, {St->Id});
		return FString();
	}

	void SetResting(FHRWorldState& S, const FString& PlayerId, const FString& HorseId, bool bResting)
	{
		FHRPlayer* P = FindPlayer(S, PlayerId);
		if (!P) return;
		if (bResting) P->Resting.AddUnique(HorseId);
		else P->Resting.Remove(HorseId);
	}

	FString HireRider(FHRWorldState& S, const FString& PlayerId, const FString& RiderId)
	{
		FHRStable* St = PlayerStable(S, PlayerId);
		FHRPlayer* P = FindPlayer(S, PlayerId);
		FHRRider* R = S.Riders.Find(RiderId);
		if (!St || !P) return TEXT("Buy a stable first.");
		if (!R || R->IsRetired()) return TEXT("This rider is no longer available.");
		if (R->OwnerId == St->Id) return TEXT("This rider already rides for you.");
		if (StableRiders(S, St->Id).Num() >= RidersPerStable) return FString::Printf(TEXT("A stable keeps %d riders: release one first."), RidersPerStable);
		const int32 Fee = R->OwnerId.IsEmpty() ? 0 : R->ListedPrice;
		if (!R->OwnerId.IsEmpty() && R->ListedPrice <= 0) return TEXT("This rider is not on the transfer list.");
		const int64 TotalCost = (int64)Fee + (int64)R->Wage;
		if (P->Coins < TotalCost) return FString::Printf(TEXT("It costs %lld coins (transfer and first wage)."), TotalCost);
		P->Coins -= Fee;
		const FString From = R->OwnerId;
		if (FHRStable* Seller = From.IsEmpty() ? nullptr : FindStable(S, From)) Seller->Coins = Credit(Seller->Coins, Fee);
		R->OwnerId = St->Id;
		R->ListedPrice = 0;
		R->FreeSinceT = -1;
		R->Stables.Add(St->Id);
		AddNews(S, Fee ? TEXT("transfer") : TEXT("rider"), Fee ? FString::Printf(TEXT("Transfer: %s joins %s for %d coins (%d a day)."), *R->FullName(), *St->Name, Fee, R->Wage)
			: FString::Printf(TEXT("%s signs for %s (%d coins a day)."), *R->FullName(), *St->Name, R->Wage),
			{}, From.IsEmpty() ? TArray<FString>{St->Id} : TArray<FString>{From, St->Id});
		SweepOwnerCoins(S);
		return FString();
	}

	FString ReleaseRider(FHRWorldState& S, const FString& PlayerId, const FString& RiderId)
	{
		FHRStable* St = PlayerStable(S, PlayerId);
		FHRRider* R = S.Riders.Find(RiderId);
		if (!St || !R || R->OwnerId != St->Id) return TEXT("This rider does not ride for you.");
		R->OwnerId.Reset();
		R->FreeSinceT = S.T;
		R->ListedPrice = 0;
		AddNews(S, TEXT("rider"), FString::Printf(TEXT("%s leaves %s, free to sign elsewhere."), *R->FullName(), *St->Name), {}, {St->Id});
		return FString();
	}

	FString ListRider(FHRWorldState& S, const FString& PlayerId, const FString& RiderId, bool bList, int32 Price)
	{
		FHRStable* St = PlayerStable(S, PlayerId);
		FHRRider* R = S.Riders.Find(RiderId);
		if (!St || !R || R->OwnerId != St->Id) return TEXT("This rider does not ride for you.");
		if (!bList)
		{
			R->ListedPrice = 0;
			return FString();
		}
		if (Price < 0 || Price > MaxCoins) return FString::Printf(TEXT("List price between 0 and %d coins."), MaxCoins);
		R->ListedPrice = Price > 0 ? Price : FMath::Clamp(RiderValue(*R, S.T), 1, MaxCoins);
		AddNews(S, TEXT("listing"), FString::Printf(TEXT("%s puts %s on the transfer list for %d coins."), *St->Name, *R->FullName(), R->ListedPrice), {}, {St->Id});
		return FString();
	}

	void SetPlayerRides(FHRWorldState& S, const FString& PlayerId, bool bRides)
	{
		if (FHRPlayer* P = FindPlayer(S, PlayerId)) P->bRides = bRides;
	}

	const FHRRunner* PlayerRunner(const FHRRace& Race, const FString& PlayerId)
	{
		return Race.Entries.FindByPredicate([&PlayerId](const FHRRunner& R) { return !PlayerId.IsEmpty() && R.RiderPlayerId == PlayerId; });
	}

	void SweepOwnerCoins(FHRWorldState& S)
	{
		for (FHRStable& St : S.Stables)
		{
			FHRPlayer* P = St.IsPlayerOwned() ? FindPlayer(S, St.OwnerPlayerId) : nullptr;
			if (!P) continue;
			if (St.Coins > 0) P->Coins = Credit(P->Coins, St.Coins);
			St.Coins = 0;
			St.Debt = 0;
		}
	}

	void CloseOwnerDay(FHRWorldState& S, FHRStable& St, int32 Gross)
	{
		FHRPlayer* P = St.IsPlayerOwned() ? FindPlayer(S, St.OwnerPlayerId) : nullptr;
		if (!P) return;
		SweepOwnerCoins(S);
		if (Gross > 0)
			AddNews(S, TEXT("result"), FString::Printf(TEXT("%s earns %d coins in prize money today."), *St.Name, Gross), {}, {St.Id});
		// Running costs first (the horses), then the wages: a rider who cannot be paid leaves, the costliest first.
		const int32 Upkeep = FMath::Max(0, DailyUpkeep(S, St) - RiderWages(S, St.Id));
		const int32 Paid = FMath::Min(P->Coins, Upkeep);
		P->Coins -= Paid;
		St.UpkeepPaid = Tally(St.UpkeepPaid, Paid);
		if (Paid < Upkeep)
			AddNews(S, TEXT("debt"), FString::Printf(TEXT("%s's horses cost %d coins to keep today: %d are missing. Sell a horse or win races!"), *St.Name, Upkeep, Upkeep - Paid), {}, {St.Id});
		TArray<FHRRider*> Staff;
		for (TPair<FString, FHRRider>& It : S.Riders)
			if (It.Value.OwnerId == St.Id && !It.Value.IsRetired()) Staff.Add(&It.Value);
		Staff.Sort([](const FHRRider& A, const FHRRider& B) { return A.Wage != B.Wage ? A.Wage < B.Wage : A.Id < B.Id; });
		for (FHRRider* R : Staff)
		{
			if (P->Coins >= R->Wage) { P->Coins -= R->Wage; continue; }
			R->OwnerId.Reset();
			R->FreeSinceT = S.T;
			R->ListedPrice = 0;
			AddNews(S, TEXT("rider"), FString::Printf(TEXT("%s was not paid and leaves %s."), *R->FullName(), *St.Name), {}, {St.Id});
		}
	}

	// ------------------------------------------------------------------ the player as a rider

	int32 PlayerRiderSkill(const FHRWorldState& S, const FString& PlayerId, int32 Stage)
	{
		const FHRPlayer* P = FindPlayer(S, PlayerId);
		return P && P->RiderSkill.IsValidIndex(Stage) ? P->RiderSkill[Stage] : PlayerStartSkill;
	}

	int32 PlayerRiderBonus(const FHRWorldState& S, const FString& PlayerId, int32 Stage)
	{
		// The same scale as the riders' (HRRiders.cpp RiderBonus): 500 is 0, 250 points per step, within -2..+2.
		return FMath::Clamp((int32)HRRandom::Round((PlayerRiderSkill(S, PlayerId, Stage) - 500) / 250.0), -2, 2);
	}

	int32 RunnerRiderBonus(const FHRWorldState& S, const FHRRunner& R, int32 Stage, int32 Distance)
	{
		if (!R.RiderPlayerId.IsEmpty()) return PlayerRiderBonus(S, R.RiderPlayerId, Stage);
		const FHRRider* Rider = RiderOf(S, R.HorseId);
		return Rider ? RiderBonus(*Rider, Stage, Distance, S.T) : 0;
	}

	void PlayerRode(FHRWorldState& S, const FString& PlayerId)
	{
		FHRPlayer* P = FindPlayer(S, PlayerId);
		if (!P) return;
		for (int32 Stage = 0; Stage < 4; ++Stage) GrowSkill(*P, Stage, PlayerRaceXp);
		P->Rides++;
	}

	// ------------------------------------------------------------------ training sessions

	int32 TrainingGain(int32 Grade)
	{
		static const int32 Gains[5] = {12, 18, 25, 32, 40};  // 25: the staff's (and the computer stables') session
		return Gains[FMath::Clamp(Grade, -2, 2) + 2];
	}

	int32 TrainingSessionsLeft(const FHRWorldState& S, const FString& PlayerId)
	{
		const FHRStable* St = PlayerStable(S, PlayerId);
		if (!St) return 0;
		return FMath::Max(0, TrainingSlots - (St->TrainingT == S.T ? St->TrainingUsed : 0));
	}

	FString TrainingRefusal(const FHRWorldState& S, const FString& PlayerId, const FString& HorseId, int32 Ability)
	{
		const FHRStable* St = PlayerStable(S, PlayerId);
		const FHRPlayer* P = FindPlayer(S, PlayerId);
		const FHRHorse* H = S.Horses.Find(HorseId);
		if (!St || !P || !H || H->OwnerId != St->Id) return TEXT("This horse is not yours.");
		if (Ability < 0 || Ability > 3) return TEXT("Unknown exercise.");
		if (H->IsRetired()) return TEXT("It has retired.");
		if (H->Injury.bActive) return TEXT("It is injured: complete rest.");
		if (!Runnable(*H, S.T)) return TEXT("Too young or not fit to work.");
		if (P->TrainedT == S.T && P->Trained.Contains(HorseId)) return TEXT("It has already worked today.");
		if (TrainingSessionsLeft(S, PlayerId) <= 0) return FString::Printf(TEXT("Today's %d sessions are done."), TrainingSlots);
		if (H->Abilities[Ability] >= H->Ceilings[Ability]) return TEXT("It has reached its ceiling in this ability.");
		if (P->Coins < TrainingCost) return FString::Printf(TEXT("A session costs %d coins."), TrainingCost);
		return FString();
	}

	FString TrainHorse(FHRWorldState& S, const FString& PlayerId, const FString& HorseId, int32 Ability, int32 Grade, int32* OutGain)
	{
		const FString Why = TrainingRefusal(S, PlayerId, HorseId, Ability);
		if (!Why.IsEmpty()) return Why;
		FHRStable& St = *PlayerStable(S, PlayerId);
		FHRPlayer& P = *FindPlayer(S, PlayerId);
		if (St.TrainingT != S.T) { St.TrainingT = S.T; St.TrainingUsed = 0; }
		if (P.TrainedT != S.T) { P.TrainedT = S.T; P.Trained.Reset(); }
		St.TrainingUsed++;
		P.Trained.Add(HorseId);
		P.Coins -= TrainingCost;
		const int32 Gain = ProgressAbility(S.Horses.FindChecked(HorseId), Ability, TrainingGain(Grade), S.T);
		if (OutGain) *OutGain = Gain / 10000;  // fixed point (HRBiology.cpp): 100 = one whole point
		// The player rides the exercise: the matching race stage of their riding improves too.
		static const int32 SkillGain[5] = {1, 2, 3, 6, 9};
		GrowSkill(P, StageOfAbility[Ability], SkillGain[FMath::Clamp(Grade, -2, 2) + 2]);
		return FString();
	}
}
