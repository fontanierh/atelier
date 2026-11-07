#include "HRRules.h"

#include "HRSave.h"

#include "HRRandom.h"
#include "Misc/ScopeExit.h"

// The living world: computer stables race every race day, train, breed (also with horses of other stables, for a
// fee) and trade horses and riders with each other. Player-owned stables race beside them; players bet. Ported from
// the reference world.ts, rivalPolicy.ts, livingWorld.ts and training.ts.

namespace
{
	const TCHAR* const ForSaleProfile = TEXT("forsale");

	/** Care and training are automatic for every stable that races, a player's too. */
	bool IsManaged(const FHRStable& S) { return !S.bForSale; }
	bool IsPlayerRunner(const FHRWorldState& S, const FHRRunner& R)
	{
		const FHRStable* St = HRRules::FindStable(S, R.StableId);
		return St && St->IsPlayerOwned();
	}

	/** Whether the owner of a player's stable rides its runners: by choice, or because the stable has no rider. */
	bool OwnerRides(const FHRWorldState& S, const FHRStable& St);

	/**
	 * At most one horse of each player's stable in a race. An extra one swaps places with a computer runner from a race
	 * of the same round that has none of that stable's horses; with no such race it sits the race day out. The changed
	 * fields get their public odds again.
	 */
	void OnePlayerHorsePerRace(FHRWorldState& S)
	{
		TSet<int32> Changed;
		for (int32 A = 0; A < S.Meeting.Races.Num(); ++A)
		{
			FHRRace& RA = S.Meeting.Races[A];
			if (RA.IsRun()) continue;
			TSet<FString> Seen;
			for (int32 I = 0; I < RA.Entries.Num(); ++I)
			{
				if (!IsPlayerRunner(S, RA.Entries[I])) continue;
				const FString Stable = RA.Entries[I].StableId;
				bool bAlready = false;
				Seen.Add(Stable, &bAlready);
				if (!bAlready) continue;
				bool bSwapped = false;
				for (int32 B = 0; B < S.Meeting.Races.Num() && !bSwapped; ++B)
				{
					FHRRace& RB = S.Meeting.Races[B];
					if (B == A || RB.IsRun() || RB.Round != RA.Round || RB.Entries.Num() == 0) continue;
					if (RB.Entries.ContainsByPredicate([&Stable](const FHRRunner& X) { return X.StableId == Stable; })) continue;
					// The runner coming back must not break the rule in this race either.
					const FHRRunner& Back = RB.Entries.Last();
					if (IsPlayerRunner(S, Back) && RA.Entries.ContainsByPredicate([&Back](const FHRRunner& X) { return X.StableId == Back.StableId; })) continue;
					Swap(RA.Entries[I], RB.Entries.Last());
					Changed.Add(A);
					Changed.Add(B);
					bSwapped = true;
				}
				if (!bSwapped)
				{
					RA.Entries.RemoveAt(I--);
					Changed.Add(A);
				}
			}
		}
		for (const int32 R : Changed) S.Meeting.Races[R].PublicOrders = HRRules::PublicOrders(S, S.Meeting.Races[R]);
	}

	bool HasRiders(const FHRWorldState& S, const FString& StableId)
	{
		for (const TPair<FString, FHRRider>& It : S.Riders)
			if (It.Value.OwnerId == StableId && !It.Value.IsRetired()) return true;
		return false;
	}

	bool OwnerRides(const FHRWorldState& S, const FHRStable& St)
	{
		const FHRPlayer* P = HRRules::FindPlayer(S, St.OwnerPlayerId);
		return P && (P->bRides || !HasRiders(S, St.Id));
	}

	int32 Capacity(const FHRStable& S)
	{
		return S.Renown >= 40 ? 12 : S.Renown >= 16 ? 10 : 8;
	}

	TArray<FHRHorse*> Owned(FHRWorldState& S, const FString& StableId)
	{
		TArray<FHRHorse*> Out;
		for (TPair<FString, FHRHorse>& It : S.Horses)
		{
			FHRHorse& H = It.Value;
			if (H.OwnerId == StableId && H.Placement != TEXT("offer") && H.Placement != TEXT("archive"))
			{
				Out.Add(&H);
			}
		}
		Out.Sort([](const FHRHorse& A, const FHRHorse& B) { return A.Id < B.Id; });
		return Out;
	}

	TArray<FHRHorse*> Live(FHRWorldState& S, const FString& StableId)
	{
		TArray<FHRHorse*> Out = Owned(S, StableId);
		Out.RemoveAll([](const FHRHorse* H) { return H->IsRetired(); });
		return Out;
	}

	struct FChoice
	{
		FHRHorse* Horse = nullptr;
		int32 Preparation = 0;
		bool bGreen = false;
		int64 Time = 0;
	};

	/** Best publicly safe preparation for this race; never reads a future form draw. */
	bool BestChoice(FHRHorse& H, const HRContent::FEvent& E, int32 Distance, int32 T, FChoice& Out, bool bAsIfActive = false)
	{
		bool bFound = false;
		FHRHorse Probe;
		const FHRHorse* View = &H;
		if (bAsIfActive && H.Placement == TEXT("pasture"))
		{
			Probe = H;
			Probe.Placement = TEXT("active");
			View = &Probe;
		}
		for (int32 P = 0; P < 3; ++P)
		{
			const HRRules::FForecast F = HRRules::Forecast(*View, E, Distance, P, T);
			if (!F.bAllowed || (F.Band != TEXT("green") && F.Band != TEXT("amber"))) continue;
			FChoice C;
			C.Horse = &H;
			C.Preparation = P;
			C.bGreen = F.Band == TEXT("green");
			C.Time = HRRules::PlanningTime(*View, P, E, Distance);
			if (!bFound || (C.bGreen && !Out.bGreen) || (C.bGreen == Out.bGreen && C.Time < Out.Time))
			{
				Out = C;
				bFound = true;
			}
		}
		return bFound;
	}

	bool IsSafe(FHRWorldState& S, FHRHorse& H)
	{
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		FChoice C;
		return BestChoice(H, E, HRRules::RaceDistance(E, E.bGrandPrix ? (E.bSprintQualifiers ? TEXT("qualif") : TEXT("semi")) : TEXT("village")), S.T, C, true);
	}

	FString StableName(const FHRWorldState& S, const FString& Id)
	{
		const FHRStable* St = HRRules::FindStable(S, Id);
		return St ? St->Name : Id;
	}

	bool IsListed(const FHRWorldState& S, const FString& HorseId)
	{
		return S.Listings.ContainsByPredicate([&HorseId](const FHRSaleListing& L) { return L.HorseId == HorseId; });
	}

	void Acquire(FHRWorldState& S, FHRHorse& H, FHRStable& St)
	{
		H.OwnerId = St.Id;
		int32 Active = 0;
		for (const FHRHorse* X : Owned(S, St.Id))
			if (X->Placement == TEXT("active") && X != &H) Active++;
		H.Placement = Active < Capacity(St) ? TEXT("active") : TEXT("pasture");
		if (H.Owners.Num() == 0 || H.Owners.Last() != St.Id) H.Owners.Add(St.Id);
		St.AcquisitionT = S.T;
	}

	// ------------------------------------------------------------------ race day
	void DealIntoRaces(FHRWorldState& S, TArray<FHRRunner>& Entries, int32 Races, const FString& Round, const HRContent::FEvent& E)
	{
		// Spread each stable's horses over different races: stables in a drawn order, dealt one race at a time.
		TArray<FString> StableOrder;
		for (const FHRStable& St : S.Stables) StableOrder.Add(St.Id);
		StableOrder = HRRandom::Shuffled(StableOrder, S.Seed, FString::Printf(TEXT("groups:%d:%s"), S.T, *Round));
		Entries.Sort([&StableOrder](const FHRRunner& A, const FHRRunner& B)
		{
			const int32 IA = StableOrder.IndexOfByKey(A.StableId), IB = StableOrder.IndexOfByKey(B.StableId);
			return IA != IB ? IA < IB : A.HorseId < B.HorseId;
		});
		TArray<FHRRace> Out;
		Out.SetNum(Races);
		for (int32 I = 0; I < Entries.Num(); ++I)
		{
			// Snake order keeps the fields balanced in size.
			const int32 Lap = I / Races, Pos = I % Races;
			Out[Lap % 2 == 0 ? Pos : Races - 1 - Pos].Entries.Add(Entries[I]);
		}
		for (int32 G = 0; G < Races; ++G)
		{
			FHRRace& R = Out[G];
			R.Key = FString::Printf(TEXT("%s:%d"), *Round, G);
			R.Round = Round;
			R.Group = G;
			R.EventId = E.Id;
			R.Distance = HRRules::RaceDistance(E, Round);
			R.Status = TEXT("declared");
			R.PublicOrders = HRRules::PublicOrders(S, R);
			S.Meeting.Races.Add(R);
		}
	}

	/** One stable's sessions: the fittest horses first, each on its weakest useful ability (training.ts). */
	void TrainStable(FHRWorldState& S, FHRStable& St, const TArray<FString>& Skip)
	{
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		const int32 Useful = E.Distance >= 1400 ? HRAbility::Endurance : E.Distance <= 900 ? HRAbility::Acceleration : HRAbility::Speed;
		if (St.TrainingT != S.T) { St.TrainingT = S.T; St.TrainingUsed = 0; }
		TArray<FHRHorse*> Horses = Owned(S, St.Id);
		Horses.RemoveAll([&S, &Skip](const FHRHorse* H) { return !HRRules::Runnable(*H, S.T) || Skip.Contains(H->Id); });
		Horses.Sort([](const FHRHorse& A, const FHRHorse& B) { return A.Condition != B.Condition ? A.Condition > B.Condition : A.Id < B.Id; });
		for (FHRHorse* H : Horses)
		{
			// Keep the price of a usable replacement available; debt also warrants restraint.
			if (St.Coins < 60 + HRRules::TrainingCost || St.Debt > 0 || St.TrainingUsed >= HRRules::TrainingSlots) break;
			TArray<int32> Choices = {0, 1, 2, 3};
			Choices.Sort([H, Useful](int32 A, int32 B)
			{
				const int32 VA = H->Abilities[A] - (A == Useful ? 1 : 0), VB = H->Abilities[B] - (B == Useful ? 1 : 0);
				return VA != VB ? VA < VB : A < B;
			});
			for (int32 A : Choices)
			{
				if (H->Abilities[A] >= H->Ceilings[A]) continue;
				HRRules::ProgressAbility(*H, A, HRRules::TrainingGain(0), S.T);
				St.Coins -= HRRules::TrainingCost;
				St.TrainingUsed++;
				break;
			}
		}
	}

	void RunTraining(FHRWorldState& S)
	{
		// A player's stable trains during the day (sessions its owner plays) and its staff does the rest at the day's
		// close (HRRules::StaffTraining).
		for (FHRStable& St : S.Stables)
			if (St.IsComputer()) TrainStable(S, St, {});
	}

	void OpenDay(FHRWorldState& S)
	{
		S.Meeting = FHRMeeting();
		S.Meeting.T = S.T;
		S.Meeting.EventIndex = HRClock::DayOfSeason(S.T);
		RunTraining(S);
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		const FString Round = !E.bGrandPrix ? TEXT("village") : E.bSprintQualifiers ? TEXT("qualif") : TEXT("semi");
		const int32 Distance = HRRules::RaceDistance(E, Round);
		TArray<FHRRunner> Entries;
		for (const FHRStable& St : S.Stables)
		{
			if (!IsManaged(St)) continue;
			const FHRPlayer* Owner = HRRules::FindPlayer(S, St.OwnerPlayerId);
			const bool bOwnerRides = St.IsPlayerOwned() && OwnerRides(S, St);
			TArray<FChoice> Choices;
			for (FHRHorse* H : Owned(S, St.Id))
			{
				// The horses an owner keeps resting sit this race day out.
				if (Owner && Owner->Resting.Contains(H->Id)) continue;
				FChoice C;
				if (BestChoice(*H, E, Distance, S.T, C)) Choices.Add(C);
			}
			Choices.Sort([](const FChoice& A, const FChoice& B)
			{
				if (A.bGreen != B.bGreen) return A.bGreen;
				if (A.Time != B.Time) return A.Time < B.Time;
				if (A.Horse->Condition != B.Horse->Condition) return A.Horse->Condition > B.Horse->Condition;
				return A.Horse->Id < B.Horse->Id;
			});
			for (int32 I = 0; I < FMath::Min(HRRules::EntriesPerStable, Choices.Num()); ++I)
			{
				FHRRunner R;
				R.HorseId = Choices[I].Horse->Id;
				R.StableId = St.Id;
				R.Preparation = Choices[I].Preparation;
				// The owner rides by choice, or because the stable has no rider on the books.
				if (bOwnerRides) R.RiderPlayerId = St.OwnerPlayerId;
				Entries.Add(R);
			}
		}
		if (Entries.Num() == 0) return;
		// Riders are put on the horses before the fields are dealt (the public odds include them).
		HRRules::AssignRiders(S, Entries);
		ON_SCOPE_EXIT { OnePlayerHorsePerRace(S); };
		if (E.bGrandPrix && E.bSprintQualifiers)
		{
			// A sprint tournament: every contender runs a timed sprint, six at most per run.
			DealIntoRaces(S, Entries, FMath::DivideAndRoundUp(Entries.Num(), HRRules::MaxRunners), TEXT("qualif"), E);
		}
		else if (E.bGrandPrix)
		{
			// Four heats when the field allows it, then a final of the heat winners.
			const int32 Heats = Entries.Num() >= 8 ? 4 : Entries.Num() >= 4 ? 2 : 1;
			DealIntoRaces(S, Entries, Heats, TEXT("semi"), E);
		}
		else
		{
			DealIntoRaces(S, Entries, FMath::DivideAndRoundUp(Entries.Num(), HRRules::MaxRunners), TEXT("village"), E);
		}
	}

	void DeclareFinal(FHRWorldState& S, const HRContent::FEvent& E, const TArray<FHRRunner>& Finalists)
	{
		FHRRace Final;
		Final.Key = TEXT("final:0");
		Final.Round = TEXT("final");
		Final.Group = 0;
		Final.EventId = E.Id;
		Final.Distance = HRRules::RaceDistance(E, TEXT("final"));
		Final.Status = TEXT("declared");
		Final.Entries = Finalists;
		// One horse per player's stable, the first qualifier listed (the fastest in a tournament, the first heat's winner
		// otherwise); an owner who rides rides the final too.
		TSet<FString> Mine;
		Final.Entries.RemoveAll([&S, &Mine](const FHRRunner& R)
		{
			if (!IsPlayerRunner(S, R)) return false;
			bool bExtra = false;
			Mine.Add(R.StableId, &bExtra);
			return bExtra;
		});
		for (FHRRunner& R : Final.Entries)
		{
			const FHRStable* St = HRRules::FindStable(S, R.StableId);
			R.RiderPlayerId = St && St->IsPlayerOwned() && OwnerRides(S, *St) ? St->OwnerPlayerId : FString();
		}
		Final.PublicOrders = HRRules::PublicOrders(S, Final);
		S.Meeting.Races.Add(Final);
	}

	/**
	 * Sprint tournament: the best official times (1/100 s) of all the sprint qualifiers go to the final. A horse too tired
	 * to run again withdraws and the next time takes its place. When horses tie at the cut, they run a new sprint
	 * (a barrage) between them; its times decide, and a new tie means a new barrage (at most three).
	 */
	void DeclareSprintFinal(FHRWorldState& S, const HRContent::FEvent& E)
	{
		constexpr int32 Slots = HRContent::SprintFinalists;
		struct FCand { FString HorseId; int64 Time = 0; int32 Preparation = 0; };
		TArray<FCand> Fit;
		for (const FHRRace& R : S.Meeting.Races)
		{
			if (R.Round != TEXT("qualif")) continue;
			for (const FHRFinish& F : R.Finishes)
			{
				FHRHorse& H = S.Horses.FindChecked(F.HorseId);
				// A horse in a barrage is a contender by right: the barrage's own effort never rules it out.
				const FHRRunner* InBarrage = nullptr;
				for (const FHRRace& X : S.Meeting.Races)
					if (X.Round == TEXT("barrage"))
						if (const FHRRunner* Y = X.Entries.FindByPredicate([&F](const FHRRunner& Z) { return Z.HorseId == F.HorseId; })) InBarrage = Y;
				FChoice C;
				const bool bFit = BestChoice(H, E, HRRules::RaceDistance(E, TEXT("final")), S.T, C);
				if (!bFit && !InBarrage)
				{
					if (!HRRules::FindRace(S, TEXT("barrage:0")))  // said once, when the sprints end
						HRRules::AddNews(S, TEXT("result"), FString::Printf(TEXT("%s, too tired after its sprint, withdraws from the %s final."), *H.Name, E.Name),
							{H.Id}, {H.OwnerId});
					continue;
				}
				Fit.Add({F.HorseId, HRRules::Hundredths(F.TimeUs), bFit ? C.Preparation : InBarrage->Preparation});
			}
		}
		Fit.Sort([](const FCand& A, const FCand& B) { return A.Time != B.Time ? A.Time < B.Time : A.HorseId < B.HorseId; });
		TArray<FCand> Qualified;
		TArray<FCand> Group;
		if (Fit.Num() <= Slots || Fit[Slots - 1].Time != Fit[Slots].Time)
		{
			for (int32 I = 0; I < FMath::Min(Slots, Fit.Num()); ++I) Qualified.Add(Fit[I]);
		}
		else
		{
			const int64 Cut = Fit[Slots - 1].Time;
			for (const FCand& C : Fit)
			{
				if (C.Time < Cut) Qualified.Add(C);
				else if (C.Time == Cut) Group.Add(C);
			}
		}
		// Barrages, in order, until the tied group is settled.
		for (int32 K = 0; Group.Num() > 0; ++K)
		{
			const int32 Left = Slots - Qualified.Num();
			const FString Key = FString::Printf(TEXT("barrage:%d"), K);
			const FHRRace* B = HRRules::FindRace(S, Key);
			if (!B)
			{
				FHRRace Barrage;
				Barrage.Key = Key;
				Barrage.Round = TEXT("barrage");
				Barrage.Group = K;
				Barrage.EventId = E.Id;
				Barrage.Distance = HRRules::RaceDistance(E, TEXT("barrage"));
				Barrage.Status = TEXT("declared");
				TArray<FString> Names;
				for (const FCand& C : Group)
				{
					const FHRHorse& H = S.Horses.FindChecked(C.HorseId);
					FHRRunner Runner;
					Runner.HorseId = C.HorseId;
					Runner.StableId = H.OwnerId;
					Runner.Preparation = C.Preparation;
					Barrage.Entries.Add(Runner);
					Names.Add(H.Name);
				}
				Barrage.PublicOrders = HRRules::PublicOrders(S, Barrage);
				S.Meeting.Races.Add(Barrage);
				HRRules::AddNews(S, TEXT("result"), FString::Printf(TEXT("%s: a dead heat to the hundredth between %s, %s for %d place%s in the final."), E.Name,
					*FString::Join(Names, TEXT(", ")), K == 0 ? TEXT("a barrage") : TEXT("a new barrage"), Left, Left > 1 ? TEXT("s") : TEXT("")));
				return;
			}
			if (!B->IsRun()) return;
			TArray<FCand> Order;
			for (const FHRFinish& F : B->Finishes)
			{
				const FCand* C = Group.FindByPredicate([&F](const FCand& X) { return X.HorseId == F.HorseId; });
				if (C) Order.Add({C->HorseId, HRRules::Hundredths(F.TimeUs), C->Preparation});
			}
			if (Order.Num() <= Left || K >= 2 || Order[Left - 1].Time != Order[Left].Time)
			{
				// Settled (after three barrages the finishing order decides).
				for (int32 I = 0; I < FMath::Min(Left, Order.Num()); ++I) Qualified.Add(Order[I]);
				Group.Reset();
			}
			else
			{
				const int64 Cut = Order[Left - 1].Time;
				TArray<FCand> Still;
				for (const FCand& C : Order)
				{
					if (C.Time < Cut) Qualified.Add(C);
					else if (C.Time == Cut) Still.Add(C);
				}
				Group = Still;
			}
		}
		TArray<FHRRunner> Finalists;
		for (const FCand& C : Qualified)
		{
			FHRRunner Runner;
			Runner.HorseId = C.HorseId;
			Runner.StableId = S.Horses.FindChecked(C.HorseId).OwnerId;
			Runner.Preparation = C.Preparation;
			Finalists.Add(Runner);
		}
		DeclareFinal(S, E, Finalists);
	}

	void DeclareFinalIfReadyImpl(FHRWorldState& S)
	{
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		if (!E.bGrandPrix || HRRules::FindRace(S, TEXT("final:0"))) return;
		if (E.bSprintQualifiers)
		{
			for (const FHRRace& R : S.Meeting.Races)
				if ((R.Round == TEXT("qualif") || R.Round == TEXT("barrage")) && !R.IsRun()) return;
			DeclareSprintFinal(S, E);
			return;
		}
		TArray<FHRRunner> Finalists;
		int32 Heats = 0;
		for (const FHRRace& R : S.Meeting.Races)
		{
			if (R.Round != TEXT("semi")) continue;
			if (!R.IsRun()) return;
			Heats++;
		}
		// Four finalists: the heat winners, or the top two of each heat on a two-heat day. A qualifier too
		// tired to run again withdraws and the next horse of the same heat takes the place.
		const int32 PerHeat = Heats <= 2 ? 2 : 1;
		for (const FHRRace& R : S.Meeting.Races)
		{
			if (R.Round != TEXT("semi")) continue;
			TArray<FString> Order;
			for (const FHRFinish& F : R.Finishes) Order.Add(F.HorseId);
			if (Order.Num() == 0 && R.Entries.Num() == 1) Order.Add(R.Entries[0].HorseId);
			int32 Taken = 0;
			FString Withdrawn;
			for (int32 I = 0; I < Order.Num() && Taken < PerHeat; ++I)
			{
				FHRHorse& H = S.Horses.FindChecked(Order[I]);
				FChoice C;
				if (!BestChoice(H, E, HRRules::RaceDistance(E, TEXT("final")), S.T, C))
				{
					if (I < PerHeat && Withdrawn.IsEmpty()) Withdrawn = H.Name;
					continue;
				}
				FHRRunner Runner;
				Runner.HorseId = H.Id;
				Runner.StableId = H.OwnerId;
				Runner.Preparation = C.Preparation;
				Finalists.Add(Runner);
				Taken++;
				if (!Withdrawn.IsEmpty() && I >= PerHeat)
				{
					HRRules::AddNews(S, TEXT("result"),
						FString::Printf(TEXT("%s, too tired after %s, withdraws from the final; %s takes its place."),
							*Withdrawn, *HRContent::RoundName(R.Round, R.Group), *H.Name), {H.Id}, {H.OwnerId});
					Withdrawn.Reset();
				}
			}
		}
		DeclareFinal(S, E, Finalists);
	}

	// ------------------------------------------------------------------ stables' decisions
	void CareAndPlaces(FHRWorldState& S, FHRStable& St)
	{
		TArray<FHRHorse*> LiveHorses = Live(S, St.Id);
		TMap<const FHRHorse*, bool> Safe;
		for (FHRHorse* H : LiveHorses) Safe.Add(H, IsSafe(S, *H));
		// Safe adults first, then injured animals (still in active care), then the nursery.
		LiveHorses.Sort([&Safe](const FHRHorse& A, const FHRHorse& B)
		{
			if (Safe[&A] != Safe[&B]) return Safe[&A];
			if (A.Injury.bActive != B.Injury.bActive) return A.Injury.bActive;
			if (A.ReadyT != B.ReadyT) return A.ReadyT < B.ReadyT;
			return A.Id < B.Id;
		});
		for (int32 I = 0; I < LiveHorses.Num(); ++I)
		{
			FHRHorse* H = LiveHorses[I];
			H->Placement = I < Capacity(St) ? TEXT("active") : TEXT("pasture");
			if (H->Injury.bActive && H->Injury.Plan.IsEmpty()) H->Injury.Plan = TEXT("progressive");
			if (H->Xp >= 100 && H->Mastery == 0) H->Mastery = 1;
		}
	}

	/** The breeding itself: costs are paid now, the mare is in foal and gives birth GestationDays later. */
	bool Conceive(FHRWorldState& S, FHRStable& St, FHRHorse& Mare, FHRHorse& Stallion, int32 Fee)
	{
		if (HRRules::FindPregnancy(S, Mare.Id)) return false;
		St.Coins -= HRRules::BreedingServiceCost + Fee;
		const FHRHorse* External = Mare.OwnerId != St.Id ? &Mare : Stallion.OwnerId != St.Id ? &Stallion : nullptr;
		const FString ExternalOwner = External ? External->OwnerId : FString();
		if (FHRStable* Owner = External ? HRRules::FindStable(S, ExternalOwner) : nullptr) Owner->Coins = HRRules::Credit(Owner->Coins, Fee);
		FHRPregnancy P;
		P.MareId = Mare.Id;
		P.SireId = Stallion.Id;
		P.BreederId = St.Id;
		P.ConceivedT = S.T;
		P.DueT = S.T + HRRules::GestationDays;
		S.Pregnancies.Add(P);
		// Individual cooldowns: one race day for the stallion; the mare is unavailable until she foals.
		Stallion.NextBreedingT = S.T + 1;
		Mare.NextBreedingT = FMath::Max(S.T + 2, P.DueT);
		St.AcquisitionT = S.T;
		const FString Due = HRContent::FormatDay(P.DueT);
		if (!ExternalOwner.IsEmpty())
		{
			HRRules::AddNews(S, TEXT("breeding"),
				FString::Printf(TEXT("%s buys a covering from %s: %s x %s, %d coins in breeding fees. Foal due on %s."),
					*St.Name, *StableName(S, ExternalOwner), *Mare.Name, *Stallion.Name, Fee, *Due),
				{Mare.Id, Stallion.Id}, {St.Id, ExternalOwner});
		}
		else
		{
			HRRules::AddNews(S, TEXT("breeding"),
				FString::Printf(TEXT("%s: %s is in foal to %s. Foal due on %s."), *St.Name, *Mare.Name, *Stallion.Name, *Due),
				{Mare.Id, Stallion.Id}, {St.Id});
		}
		return true;
	}

	/** Foals due today are born, in a fixed order, for the stable that arranged each breeding. */
	void DeliverFoals(FHRWorldState& S)
	{
		TArray<FHRPregnancy> Due = S.Pregnancies.FilterByPredicate([&S](const FHRPregnancy& P) { return P.DueT <= S.T; });
		S.Pregnancies.RemoveAll([&S](const FHRPregnancy& P) { return P.DueT <= S.T; });
		Due.Sort([](const FHRPregnancy& A, const FHRPregnancy& B) { return A.MareId < B.MareId; });
		for (const FHRPregnancy& P : Due)
		{
			FHRStable* St = HRRules::FindStable(S, P.BreederId);
			const FHRHorse* MareP = S.Horses.Find(P.MareId);
			const FHRHorse* SireP = S.Horses.Find(P.SireId);
			if (!St || !MareP || !SireP) continue;
			// AddHorse may reallocate the horse map: work on copies of the parents.
			const FHRHorse Mare = *MareP, Sire = *SireP;
			const FString Id = FString::Printf(TEXT("%s:foal:%d"), *St->Id, P.DueT);
			if (S.Horses.Contains(Id)) continue;
			HRRules::FGenerationOptions O;
			O.Id = Id;
			O.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *Id);
			O.OwnerId = St->Id;
			O.T = S.T;
			O.Origin = TEXT("foal");
			O.Mother = &Mare;
			O.Father = &Sire;
			FHRHorse Foal = HRRules::GenerateHorse(O);
			const FString Chosen = P.FoalName.TrimStartAndEnd().Left(22);
			if (!Chosen.IsEmpty()) Foal.Name = Chosen;  // a name already taken is drawn again by AddHorse
			FHRHorse& Added = HRRules::AddHorse(S, MoveTemp(Foal));
			// A birth is not the stable's decision of the day: keep its acquisition slot.
			const int32 Slot = St->AcquisitionT;
			Acquire(S, Added, *St);
			St->AcquisitionT = Slot;
			St->Births++;
			HRRules::AddNews(S, TEXT("birth"),
				FString::Printf(TEXT("A birth at %s: %s, a %s out of %s by %s."), *St->Name, *Added.Name,
					Added.bMare ? TEXT("filly") : TEXT("colt"), *Mare.Name, *Sire.Name),
				{Added.Id, Mare.Id, Sire.Id}, {St->Id});
		}
	}

	/** Picks the best affordable partner, in the stable or at another stable (for a fee). */
	bool TryBreed(FHRWorldState& S, FHRStable& St)
	{
		const int32 Budget = St.Coins - 30; // a small reserve: running costs keep stables lean
		TArray<FHRHorse*> Own;
		for (FHRHorse* H : Owned(S, St.Id))
			if (HRRules::CanBreed(S, *H)) Own.Add(H);
		if (Own.Num() == 0) return false;
		TArray<FHRHorse*> Pool;
		for (TPair<FString, FHRHorse>& It : S.Horses)
		{
			FHRHorse& H = It.Value;
			const FHRStable* Owner = HRRules::FindStable(S, H.OwnerId);
			if (Owner && Owner->IsComputer() && HRRules::CanBreed(S, H)) Pool.Add(&H);
		}
		Pool.Sort([](const FHRHorse& A, const FHRHorse& B) { return A.Id < B.Id; });
		FHRHorse* BestA = nullptr;
		FHRHorse* BestB = nullptr;
		int32 BestValue = MIN_int32, BestFee = 0;
		for (FHRHorse* A : Own)
		{
			for (FHRHorse* B : Pool)
			{
				if (A == B || A->bMare == B->bMare || HRRules::Related(S, *A, *B)) continue;
				const bool bExternal = B->OwnerId != St.Id;
				const int32 Fee = bExternal ? HRRules::BreedingFee(*B) : 0;
				if (Budget < HRRules::BreedingServiceCost + Fee) continue;
				// Public level and record of both parents; an outside fee must be worth it.
				const int32 Value = HRRules::CardScore(*A) + HRRules::CardScore(*B) + 4 * B->Wins + 15 * B->GpWins - Fee / 8;
				if (Value > BestValue)
				{
					BestValue = Value;
					BestA = A;
					BestB = B;
					BestFee = Fee;
				}
			}
		}
		if (!BestA) return false;
		FHRHorse& Mare = BestA->bMare ? *BestA : *BestB;
		FHRHorse& Stallion = BestA->bMare ? *BestB : *BestA;
		return Conceive(S, St, Mare, Stallion, BestFee);
	}

	void UpdateListings(FHRWorldState& S)
	{
		// Drop listings that no longer make sense, and age the price of the others.
		S.Listings.RemoveAll([&S](const FHRSaleListing& L)
		{
			const FHRHorse* H = S.Horses.Find(L.HorseId);
			const bool bDrop = !H || H->OwnerId != L.SellerId || H->IsRetired() || H->Injury.bActive || S.T - L.SinceT >= 4;
			return bDrop;
		});
		for (FHRSaleListing& L : S.Listings)
		{
			const FHRHorse& H = S.Horses.FindChecked(L.HorseId);
			L.Price = FMath::Max(30, HRRules::SaleValue(S, H) * (100 - 10 * (S.T - L.SinceT)) / 100);
		}
		for (FHRStable& St : S.Stables)
		{
			if (!St.IsComputer()) continue;
			TArray<FHRHorse*> LiveHorses = Live(S, St.Id);
			TArray<FHRHorse*> Ready = LiveHorses.FilterByPredicate([&S](const FHRHorse* H) { return H->ReadyT <= S.T && !H->Injury.bActive; });
			const bool bSurplus = LiveHorses.Num() >= 6;
			// A stable short of cash, or in debt for its running costs, sells a horse.
			const bool bCash = (St.Coins < 40 || St.Debt > 0) && Ready.Num() >= 3;
			if (!bSurplus && !bCash) continue;
			if (S.Listings.ContainsByPredicate([&St](const FHRSaleListing& L) { return L.SellerId == St.Id; })) continue;
			Ready.Sort([](const FHRHorse& A, const FHRHorse& B)
			{
				const int32 SA = HRRules::CardScore(A), SB = HRRules::CardScore(B);
				return SA != SB ? SA > SB : A.Id < B.Id;
			});
			// Keep the two best runners; offer the weakest of the rest.
			if (Ready.Num() <= 2) continue;
			FHRHorse* Offer = Ready.Last();
			FHRSaleListing L;
			L.HorseId = Offer->Id;
			L.SellerId = St.Id;
			L.SinceT = S.T;
			L.Price = HRRules::SaleValue(S, *Offer);
			S.Listings.Add(L);
			// A horse relisted after its listing expired is not announced again.
			const bool bAnnounced = S.News.ContainsByPredicate([Offer](const FHRNews& N) { return N.Kind == TEXT("listing") && N.HorseIds.Contains(Offer->Id); });
			if (!bAnnounced) HRRules::AddNews(S, TEXT("listing"),
				FString::Printf(TEXT("%s puts %s (%s, %s) up for sale for %d coins."), *St.Name, *Offer->Name,
					Offer->bMare ? TEXT("mare") : TEXT("stallion"), *HRContent::AgeLabel(S.T - Offer->BirthT), L.Price),
				{Offer->Id}, {St.Id});
		}
	}

	bool TryBuyListing(FHRWorldState& S, FHRStable& St, int32 Reserve)
	{
		int32 Best = INDEX_NONE;
		for (int32 I = 0; I < S.Listings.Num(); ++I)
		{
			const FHRSaleListing& L = S.Listings[I];
			if (L.SellerId == St.Id || St.Coins < L.Price + Reserve) continue;
			if (Best == INDEX_NONE || HRRules::CardScore(S.Horses[L.HorseId]) > HRRules::CardScore(S.Horses[S.Listings[Best].HorseId]))
				Best = I;
		}
		if (Best == INDEX_NONE) return false;
		const FHRSaleListing L = S.Listings[Best];
		S.Listings.RemoveAt(Best);
		FHRHorse& H = S.Horses.FindChecked(L.HorseId);
		FHRStable* Seller = HRRules::FindStable(S, L.SellerId);
		St.Coins -= L.Price;
		if (Seller) { Seller->Coins = HRRules::Credit(Seller->Coins, L.Price); Seller->Sales++; }
		St.Purchases++;
		Acquire(S, H, St);
		HRRules::AddNews(S, TEXT("sale"),
			FString::Printf(TEXT("Sale: %s leaves %s for %s, %d coins."), *H.Name, *StableName(S, L.SellerId), *St.Name, L.Price),
			{H.Id}, {L.SellerId, St.Id});
		return true;
	}

	bool TryUpgrade(FHRWorldState& S, FHRStable& St)
	{
		int32 Weakest = MAX_int32;
		for (FHRHorse* H : Live(S, St.Id))
			if (H->ReadyT <= S.T) Weakest = FMath::Min(Weakest, HRRules::CardScore(*H));
		if (Weakest == MAX_int32) return false;
		const bool bWorth = S.Listings.ContainsByPredicate([&](const FHRSaleListing& L)
		{
			return L.SellerId != St.Id && HRRules::CardScore(S.Horses[L.HorseId]) > Weakest + 5 && St.Coins >= L.Price + 150;
		});
		return bWorth && TryBuyListing(S, St, 150);
	}

	bool BuyFromMarket(FHRWorldState& S, FHRStable& St, int32 Slot, int32 Price, const TCHAR* Label)
	{
		const FString Id = FString::Printf(TEXT("%s:board:%d:%d"), *St.Id, S.T, Slot);
		HRRules::FGenerationOptions O;
		O.Id = Id;
		O.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *Id);
		O.OwnerId = TEXT("market");
		O.T = S.T;
		O.Origin = TEXT("recruit");
		O.Slot = Slot;
		FHRHorse& H = HRRules::AddHorse(S, HRRules::GenerateHorse(O));
		St.Coins -= Price;
		St.Purchases++;
		Acquire(S, H, St);
		HRRules::AddNews(S, TEXT("purchase"),
			FString::Printf(TEXT("%s buys %s (%s) at the market for %d coins."), *St.Name, *H.Name, Label, Price), {H.Id}, {St.Id});
		return true;
	}

	void RescuePurchase(FHRWorldState& S, FHRStable& St)
	{
		const FString Id = FString::Printf(TEXT("%s:recovery:%d"), *St.Id, S.T);
		HRRules::FGenerationOptions O;
		O.Id = Id;
		O.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *Id);
		O.OwnerId = TEXT("market");
		O.T = S.T;
		O.Origin = TEXT("recovery");
		const int32 Advance = St.bRescueUsed ? 0 : FMath::Max(0, 60 - St.Coins);
		St.Coins += Advance - 60;
		St.Debt += Advance;
		St.bRescueUsed = true;
		FHRHorse& H = HRRules::AddHorse(S, HRRules::GenerateHorse(O));
		Acquire(S, H, St);
		H.Placement = TEXT("active");
		HRRules::AddNews(S, TEXT("purchase"),
			FString::Printf(TEXT("%s, without a runner, buys %s for 60 coins%s."), *St.Name, *H.Name,
				Advance ? *FString::Printf(TEXT(" thanks to an advance of %d coins"), Advance) : TEXT("")),
			{H.Id}, {St.Id});
	}

	void ManageStables(FHRWorldState& S)
	{
		for (FHRStable& St : S.Stables)
			if (IsManaged(St)) CareAndPlaces(S, St);
		UpdateListings(S);
		TArray<FHRStable*> Order;
		for (FHRStable& St : S.Stables)
			if (St.IsComputer()) Order.Add(&St);
		Order.Sort([](const FHRStable& A, const FHRStable& B) { return A.Id < B.Id; });
		for (FHRStable* StPtr : Order)
		{
			FHRStable& St = *StPtr;
			if (St.AcquisitionT == S.T) continue;
			TArray<FHRHorse*> All = Owned(S, St.Id);
			const bool bAnySafe = All.ContainsByPredicate([&S](FHRHorse* H) { return !H->IsRetired() && IsSafe(S, *H); });
			if (!bAnySafe)
			{
				if (!St.bRescueUsed || St.Coins >= 60) RescuePurchase(S, St);
				continue;
			}
			TArray<FHRHorse*> LiveHorses = Live(S, St.Id);
			const int32 Ready = LiveHorses.FilterByPredicate([&S](const FHRHorse* H)
			{
				return H->ReadyT <= S.T && !H->Injury.bActive && H->ScheduledRetirementT - S.T > HRClock::LifeYear;
			}).Num();
			// Foals on the way count as young horses.
			const int32 Young = LiveHorses.FilterByPredicate([&S](const FHRHorse* H) { return H->ReadyT > S.T; }).Num() +
				S.Pregnancies.FilterByPredicate([&St](const FHRPregnancy& P) { return P.BreederId == St.Id; }).Num();
			// Stables enter up to three horses a day, so they keep a larger string.
			if (Ready >= 2 && Young < 2 && LiveHorses.Num() < 7 && TryBreed(S, St)) continue;
			const bool bNeedNow = Ready < 3;
			// A well-off stable also buys a listed horse that beats its weakest runner.
			if (St.Coins >= 250 && LiveHorses.Num() < 8 && TryUpgrade(S, St)) continue;
			if (LiveHorses.Num() >= 6) continue;
			if (bNeedNow && TryBuyListing(S, St, 40)) continue;
			if (!bNeedNow && LiveHorses.Num() < 5 && TryBuyListing(S, St, 100)) continue;
			if (LiveHorses.Num() >= 5) continue;
			// Market purchase only when it closes an actual gap; keep a 60-coin recovery reserve.
			if (St.Coins < (bNeedNow ? 80 : 125)) continue;
			if (bNeedNow) BuyFromMarket(S, St, 1, 80, TEXT("an all-round adult"));
			else BuyFromMarket(S, St, 0, 65, TEXT("a young prospect"));
		}
	}


	// ------------------------------------------------------------------ day close
	void CloseDay(FHRWorldState& S)
	{
		HRRules::StaffTraining(S);
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		TMap<FString, int32> BestXp;
		for (FHRStable& St : S.Stables)
		{
			int32 Gross = 0, Prestige = 0;
			bool bRaced = false, bBigRound = false;
			for (const FHRRace& R : S.Meeting.Races)
			{
				for (const FHRFinish& F : R.Finishes)
				{
					if (F.StableId != St.Id) continue;
					Gross += F.Gross;
					Prestige += F.Prestige;
					bRaced = true;
					bBigRound |= R.Round != TEXT("village");
					if (F.Place == 1 && !HRRules::IsHeatRound(R.Round))
					{
						St.EventWins++;
						if (R.Round == TEXT("final")) St.GpTitles.Add(FString::Printf(TEXT("%d:%s"), S.Edition, E.Id));
					}
				}
			}
			const int32 Repayment = FMath::Min(St.Debt, Gross / 4);
			St.Coins = HRRules::Credit(St.Coins, (int64)Gross - Repayment);
			St.Debt -= Repayment;
			// Running costs: what a computer stable cannot pay becomes debt, repaid from later winnings.
			if (St.IsComputer())
			{
				const int32 Upkeep = HRRules::DailyUpkeep(S, St);
				const int32 Paid = FMath::Min(FMath::Max(0, St.Coins), Upkeep);
				St.Coins -= Paid;
				St.UpkeepPaid = HRRules::Tally(St.UpkeepPaid, Paid);
				if (Paid < Upkeep)
				{
					const bool bNewDebt = St.Debt == 0;
					St.Debt = HRRules::Credit(St.Debt, (int64)Upkeep - Paid);
					if (bNewDebt)
					{
						HRRules::AddNews(S, TEXT("debt"),
							FString::Printf(TEXT("%s can no longer pay for its horses (%d coins a day) and falls into debt."), *St.Name, Upkeep), {}, {St.Id});
					}
				}
			}
			if (St.IsPlayerOwned()) HRRules::CloseOwnerDay(S, St, Gross);
			St.TotalEarnings = HRRules::Tally(St.TotalEarnings, Gross);
			St.Prestige += Prestige;
			if (bRaced) St.Renown += bBigRound ? 3 : 2;
			// A computer stable with no runner and no money does paid work elsewhere.
			if (St.IsComputer() && !bRaced && St.bRescueUsed && St.Coins < 60)
			{
				bool bAnySafe = false;
				for (FHRHorse* H : Owned(S, St.Id)) bAnySafe |= !H->IsRetired() && IsSafe(S, *H);
				if (!bAnySafe) St.Coins = HRRules::Credit(St.Coins, 20);
			}
		}
		for (const FHRRace& R : S.Meeting.Races)
			for (const FHRFinish& F : R.Finishes)
				BestXp.FindOrAdd(F.HorseId) = FMath::Max(BestXp.FindRef(F.HorseId), F.Xp);
		for (TPair<FString, FHRHorse>& It : S.Horses)
		{
			FHRHorse& H = It.Value;
			if (const int32* Xp = BestXp.Find(H.Id))
			{
				H.Xp += *Xp;
				for (int32 A = 0; A < 4; ++A) HRRules::ProgressAbility(H, A, 3, S.T);
				HRRules::RecoverTissueLoad(H);
			}
			else if (H.Placement != TEXT("offer"))
			{
				HRRules::Bench(H, S.T);
			}
			if (H.Placement == TEXT("active") || H.Placement == TEXT("pasture")) H.Condition = FMath::Min(3, H.Condition + 2);
		}
		// Tickets on a race that did not take place are refunded at the close.
		for (FHRTicket& T : S.Tickets)
		{
			if (T.T != S.T || T.Status != TEXT("open")) continue;
			T.Status = TEXT("refunded");
			T.Payout = T.Stake;
			if (FHRPlayer* P = HRRules::FindPlayer(S, T.PlayerId)) P->Coins = HRRules::Credit(P->Coins, T.Stake);
		}
		// Settled tickets are kept for one season, so the saved world does not grow without end.
		S.Tickets.RemoveAll([&S](const FHRTicket& T) { return T.T <= S.T - HRClock::DaysPerSeason; });

		HRRules::AdvanceRiders(S);
		for (TPair<FString, FHRPlayer>& It : S.Players)
		{
			It.Value.Coins = HRRules::Credit(It.Value.Coins, HRRules::PlayerDailyIncome);
			It.Value.TotalIncome = HRRules::Tally(It.Value.TotalIncome, HRRules::PlayerDailyIncome);
		}
		S.T++;
		for (TPair<FString, FHRHorse>& It : S.Horses)
		{
			FHRHorse& H = It.Value;
			const bool bWasRacing = !H.IsRetired();
			HRRules::AdvanceHorse(H, S.T);
			if (bWasRacing && H.IsRetired() && H.OwnerId != TEXT("market"))
			{
				HRRules::AddNews(S, TEXT("retire"),
					FString::Printf(TEXT("%s (%s) retires from racing after %d starts and %d wins."), *H.Name, *StableName(S, H.OwnerId), H.Starts, H.Wins),
					{H.Id}, {H.OwnerId});
			}
		}
		if (S.T % HRClock::DaysPerSeason == 0)
		{
			for (FHRStable& St : S.Stables)
			{
				const FString Prefix = FString::Printf(TEXT("%d:"), S.Edition);
				if (St.GpTitles.FilterByPredicate([&Prefix](const FString& X) { return X.StartsWith(Prefix); }).Num() == HRClock::GrandPrixPerSeason)
				{
					St.GrandSlams.Add(S.Edition);
					HRRules::AddNews(S, TEXT("title"), FString::Printf(TEXT("Grand slam! %s won all four Grands Prix of the season."), *St.Name), {}, {St.Id});
				}
				St.Prestige = 0;
				St.EventWins = 0;
			}
			S.Edition++;
			for (TPair<FString, FHRHorse>& It : S.Horses)
				if (It.Value.Placement == TEXT("active")) It.Value.Condition = 3;
		}
		DeliverFoals(S);
		ManageStables(S);
		HRRules::ManageRiders(S);
		HRRules::SweepOwnerCoins(S);  // a computer stable may have bought a player's listed horse or rider
	}

	/** First-round races of today: everything but the barrages and the final. */
	int32 FirstRoundRaces(const FHRWorldState& S)
	{
		int32 N = 0;
		for (const FHRRace& R : S.Meeting.Races) N += R.Round != TEXT("final") && R.Round != TEXT("barrage") ? 1 : 0;
		return N;
	}
}

namespace HRRules
{
	void DeclareFinalIfReady(FHRWorldState& S)
	{
		DeclareFinalIfReadyImpl(S);
	}

	FHRStable* FindStable(FHRWorldState& S, const FString& Id)
	{
		return S.Stables.FindByPredicate([&Id](const FHRStable& X) { return X.Id == Id; });
	}

	const FHRStable* FindStable(const FHRWorldState& S, const FString& Id)
	{
		return S.Stables.FindByPredicate([&Id](const FHRStable& X) { return X.Id == Id; });
	}

	FHRRace* FindRace(FHRWorldState& S, const FString& Key)
	{
		return S.Meeting.Races.FindByPredicate([&Key](const FHRRace& R) { return R.Key == Key; });
	}

	const FHRRace* FindRace(const FHRWorldState& S, const FString& Key)
	{
		return S.Meeting.Races.FindByPredicate([&Key](const FHRRace& R) { return R.Key == Key; });
	}

	FHRRace* NextRace(FHRWorldState& S)
	{
		return S.Meeting.Races.FindByPredicate([](const FHRRace& R) { return !R.IsRun(); });
	}

	FString RunNextRace(FHRWorldState& S)
	{
		FHRRace* Race = NextRace(S);
		if (!Race) return FString();
		ResolveRace(S, *Race);
		const FHRRace Copy = *Race;
		SettleRace(S, Copy);
		const HRContent::FEvent& E = HRContent::EventForT(S.T);
		if (Copy.Status == TEXT("run") && Copy.Finishes.Num())
		{
			// The result line; an upset when the winner was an outsider (odds above 10).
			const FHRFinish& Win = Copy.Finishes[0];
			const double WinRapport = Rapport(S, Copy, Win.HorseId);
			if (Copy.Round == TEXT("final"))
			{
				AddNews(S, TEXT("title"),
					FString::Printf(TEXT("%s wins the %s final (odds %.2f): a title for %s."), *Win.HorseName, E.Name, WinRapport, *Win.StableName),
					{Win.HorseId}, {Win.StableId});
			}
			else
			{
				AddNews(S, WinRapport > 10 ? TEXT("upset") : TEXT("result"),
					FString::Printf(TEXT("%s%s, %s: %s (%s) wins at odds of %.2f."), WinRapport > 10 ? TEXT("Upset! ") : TEXT(""), E.Name,
						*HRContent::RoundName(Copy.Round, Copy.Group), *Win.HorseName, *Win.StableName, WinRapport),
					{Win.HorseId}, {Win.StableId});
			}
		}
		for (const FHRFinish& F : Copy.Finishes)
		{
			if (!F.Injury.IsEmpty() && F.Injury != TEXT("soreness"))
			{
				AddNews(S, TEXT("injury"),
					FString::Printf(TEXT("%s (%s): %s injury during the %s."), *F.HorseName, *F.StableName, *F.Injury, E.Name),
					{F.HorseId}, {F.StableId});
			}
		}
		DeclareFinalIfReady(S);
		return Copy.Key;
	}

	bool DayComplete(const FHRWorldState& S)
	{
		return !S.Meeting.Races.ContainsByPredicate([](const FHRRace& R) { return !R.IsRun(); });
	}

	void AdvanceDay(FHRWorldState& S)
	{
		while (!RunNextRace(S).IsEmpty())
		{
		}
		CloseDay(S);
		OpenDay(S);
	}

	int32 DaySlotCount(const FHRWorldState& S)
	{
		return HRClock::SlotCount(FirstRoundRaces(S), HRContent::EventForT(S.T).bGrandPrix);
	}

	int32 RaceSlot(const FHRWorldState& S, const FHRRace& Race)
	{
		const int32 Count = DaySlotCount(S);
		if (Race.Round == TEXT("final")) return Count - 1;
		if (Race.Round == TEXT("barrage")) return Count - 2;
		int32 Index = 0;
		for (const FHRRace& R : S.Meeting.Races)
		{
			if (R.Key == Race.Key) return Index;
			if (R.Round != TEXT("final") && R.Round != TEXT("barrage")) ++Index;
		}
		return 0;
	}

	double RaceStartSeconds(const FHRWorldState& S, const FString& RaceKey)
	{
		const FHRRace* Race = FindRace(S, RaceKey);
		return Race ? HRClock::SlotStart(S.T, RaceSlot(S, *Race), DaySlotCount(S)) : -1.0;
	}

	HRClock::EHRRacePhase RacePhase(const FHRWorldState& S, const FString& RaceKey, double Now)
	{
		const FHRRace* Race = FindRace(S, RaceKey);
		if (!Race) return HRClock::EHRRacePhase::Upcoming;
		const HRClock::EHRRacePhase ByClock = HRClock::PhaseAt(RaceStartSeconds(S, RaceKey), Now);
		// The clock decides, but a race not yet run (the host has not advanced) is still upcoming.
		return Race->IsRun() ? ByClock : HRClock::EHRRacePhase::Upcoming;
	}

	void StartClock(FHRWorldState& S, int64 NowUnix)
	{
		S.EpochUnix = NowUnix - (int64)HRClock::DayStart(S.T);
	}

	double WorldSeconds(const FHRWorldState& S, double NowUnix)
	{
		return NowUnix - (double)S.EpochUnix;
	}

	int32 LimitCatchUp(FHRWorldState& S, double& Now, int32 MaxDays)
	{
		MaxDays = FMath::Clamp(MaxDays, 1, HRSave::MaxDay);
		// More than HRSave::MaxDay race days ahead is not a clock reading: keep the world (and its admissible epoch) as it is.
		if (!FMath::IsFinite(Now) || Now > HRClock::DayStart(S.T) + HRClock::DaySeconds * HRSave::MaxDay)
		{
			Now = HRClock::DayStart(S.T);
			return 0;
		}
		const double Behind = Now - HRClock::DayStart(S.T + MaxDays);
		if (Behind <= 0.) return 0;
		const int64 Skipped = (int64)FMath::CeilToDouble(Behind / HRClock::DaySeconds);
		S.EpochUnix += Skipped * (int64)HRClock::DaySeconds;
		Now -= (double)Skipped * HRClock::DaySeconds;
		return (int32)FMath::Min<int64>(Skipped, MAX_int32);
	}

	void AdvanceTo(FHRWorldState& S, double Now, int32 MaxDays)
	{
		LimitCatchUp(S, Now, MaxDays);
		for (;;)
		{
			// Races in running order: a Grand Prix final appears once its heats are run, in the last slot.
			while (FHRRace* Race = NextRace(S))
			{
				if (HRClock::SlotStart(S.T, RaceSlot(S, *Race), DaySlotCount(S)) > Now) break;
				RunNextRace(S);
			}
			if (Now < HRClock::DayStart(S.T + 1)) break;
			AdvanceDay(S);
		}
	}

	FHRWorldState CreateWorld(const FString& Seed)
	{
		FHRWorldState S;
		S.RulesVersion = RulesVersion;
		S.Seed = Seed;
		S.T = 0;
		const TArray<HRContent::FStableDef>& Defs = HRContent::StableDefs();
		TArray<FString> Profiles = {TEXT("established"), TEXT("rising"), TEXT("rising"), TEXT("rebuilding"), TEXT("rebuilding"), TEXT("struggling")};
		Profiles = HRRandom::Shuffled(Profiles, Seed, TEXT("world:initial-situations"));
		for (int32 I = 0; I < Defs.Num(); ++I)
		{
			FHRStable St;
			St.Id = Defs[I].Id;
			St.Name = Defs[I].Name;
			St.Color = Defs[I].Color;
			St.Emblem = Defs[I].Emblem;
			St.Motto = Defs[I].Motto;
			St.bForSale = I == 0;
			St.Profile = I == 0 ? ForSaleProfile : Profiles[(I - 1) % Profiles.Num()];
			S.Stables.Add(St);
		}

		for (FHRStable& St : S.Stables)
		{
			if (!St.IsComputer()) continue;
			const FString& P = St.Profile;
			St.Coins = (P == TEXT("established") ? 280 : P == TEXT("rising") ? 120 : P == TEXT("rebuilding") ? 70 : 0) +
				HRRandom::Draw(Seed, FString::Printf(TEXT("world:coins:%s"), *St.Id), P == TEXT("struggling") ? 21 : 81);
			if (P == TEXT("struggling"))
			{
				St.bRescueUsed = true;
				St.Debt = 30 + HRRandom::Draw(Seed, FString::Printf(TEXT("world:debt:%s"), *St.Id), 31);
			}
			// Founders' ages in horse months; stables enter up to three horses, so they start with four or five.
			const TArray<int32> Ages = P == TEXT("established") ? TArray<int32>{18, 24, 30, 40, 4}
				: P == TEXT("rising") ? TArray<int32>{12, 22, 30, 4}
				: P == TEXT("rebuilding") ? TArray<int32>{72, 8, 20, 2}
				: TArray<int32>{41, 14, 0};
			for (int32 Slot = 0; Slot < Ages.Num(); ++Slot)
			{
				FGenerationOptions O;
				O.Id = FString::Printf(TEXT("%s:founder:%d"), *St.Id, Slot);
				O.Seed = FString::Printf(TEXT("%s:%s"), *Seed, *O.Id);
				O.OwnerId = St.Id;
				O.T = 0;
				O.Origin = TEXT("rival");
				O.Slot = P == TEXT("established") ? 8 : P == TEXT("struggling") ? 0 : 4;
				O.AgeSteps = Ages[Slot] + HRRandom::Draw(Seed, FString::Printf(TEXT("world:age:%s"), *O.Id), 6);
				O.Prospect = (P == TEXT("established") && Slot < 3) ? TEXT("established") : P == TEXT("struggling") ? TEXT("modest") : TEXT("");
				FHRHorse H = GenerateHorse(O);
				if (P == TEXT("rebuilding") && Slot == 0)
				{
					// One seasoned founder reaches its genetic retirement during the earlier season.
					const int32 Shift = H.ScheduledRetirementT - 9;
					H.BirthT -= Shift;
					H.ReadyT -= Shift;
					H.ScheduledRetirementT -= Shift;
				}
				AddHorse(S, MoveTemp(H));
			}
		}
		CreateRiders(S);
		OpenDay(S);
		// One genuinely simulated earlier season, so the world has records and a history on arrival.
		for (int32 Day = 0; Day < HRClock::DaysPerSeason; ++Day)
		{
			AdvanceDay(S);
		}
		S.ArrivalT = S.T;
		AddNews(S, TEXT("arrival"), FString::Printf(TEXT("The racing world opens. %s is for sale; until then, bet on the races."), *S.Stables[0].Name));
		return S;
	}

	TArray<const FHRHorse*> StableHorses(const FHRWorldState& S, const FString& StableId, bool bIncludeArchive)
	{
		TArray<const FHRHorse*> Out;
		for (const TPair<FString, FHRHorse>& It : S.Horses)
		{
			const FHRHorse& H = It.Value;
			if (H.OwnerId != StableId || H.Placement == TEXT("offer")) continue;
			if (!bIncludeArchive && H.Placement == TEXT("archive")) continue;
			Out.Add(&H);
		}
		Out.Sort([&S](const FHRHorse& A, const FHRHorse& B)
		{
			const int32 GA = A.IsRetired() ? 2 : A.ReadyT > S.T ? 1 : 0, GB = B.IsRetired() ? 2 : B.ReadyT > S.T ? 1 : 0;
			if (GA != GB) return GA < GB;
			const int32 SA = CardScore(A), SB = CardScore(B);
			return SA != SB ? SA > SB : A.Id < B.Id;
		});
		return Out;
	}

	int32 DailyUpkeep(const FHRWorldState& S, const FHRStable& St)
	{
		if (St.bForSale) return 0;
		int64 Cost = UpkeepBase;
		for (const FHRHorse* H : StableHorses(S, St.Id))
		{
			if (H->Placement == TEXT("archive")) continue;
			Cost += H->IsRetired() ? UpkeepRetired : H->ReadyT > S.T ? UpkeepFoal : UpkeepRacing;
		}
		return (int32)FMath::Clamp<int64>(Cost + RiderWages(S, St.Id), 0, MaxCoins);
	}

	int32 BreedingFee(const FHRHorse& H)
	{
		// Public achievements only; abilities, genes and ceilings are never read. About half the reference fee, so lean
		// stables can afford outside sires and dams.
		return FMath::Min(200, 10 + 3 * H.Wins + 12 * H.GpWins + H.Podiums + H.Earnings / 200);
	}

	int32 CardScore(const FHRHorse& H)
	{
		return (int32)HRRandom::Round(H.AbilitySum() / 4.0 * 10);
	}

	int32 SaleValue(const FHRWorldState& S, const FHRHorse& H)
	{
		// Public level and record, discounted in the last two horse years of the career.
		int32 Value = 20 + (CardScore(H) - 30) * 4 + 6 * H.Wins + 25 * H.GpWins;
		if (H.ScheduledRetirementT - S.T < 2 * HRClock::LifeYear) Value = Value * 6 / 10;
		return FMath::Clamp(Value, 40, 400);
	}

	const FHRPregnancy* FindPregnancy(const FHRWorldState& S, const FString& MareId)
	{
		return S.Pregnancies.FindByPredicate([&MareId](const FHRPregnancy& P) { return P.MareId == MareId; });
	}

	void AddNews(FHRWorldState& S, const FString& Kind, const FString& Text, const TArray<FString>& Horses, const TArray<FString>& Stables)
	{
		FHRNews N;
		N.T = S.T;
		N.Kind = Kind;
		N.Text = Text;
		N.HorseIds = Horses;
		N.StableIds = Stables;
		S.News.Add(N);
		constexpr int32 Keep = 400;
		if (S.News.Num() > Keep) S.News.RemoveAt(0, S.News.Num() - Keep);
	}

	// ------------------------------------------------------------------ players' stables: training and breeding

	void StaffTraining(FHRWorldState& S)
	{
		for (FHRStable& St : S.Stables)
		{
			FHRPlayer* P = St.IsPlayerOwned() ? FindPlayer(S, St.OwnerPlayerId) : nullptr;
			if (!P) continue;
			// The sessions the owner left are done by the staff, an average session each, on the owner's coins.
			const TArray<FString> Skip = P->TrainedT == S.T ? P->Trained : TArray<FString>();
			St.Coins = P->Coins;
			P->Coins = 0;
			TrainStable(S, St, Skip);
			P->Coins = St.Coins;
			St.Coins = 0;
		}
	}

	FString BreedingAvailability(const FHRWorldState& S, const FHRHorse& H)
	{
		if (H.Placement == TEXT("archive") || H.OwnerId == TEXT("market")) return TEXT("Not available for breeding.");
		if (S.T - H.BirthT < 2 * HRClock::LifeYear) return TEXT("Too young: two horse years at least.");
		if (S.T < H.ReadyT) return TEXT("Not grown yet.");
		if (H.Injury.bActive) return TEXT("Injured: in care.");
		if (FindPregnancy(S, H.Id)) return TEXT("Already in foal.");
		if (S.T < H.NextBreedingT) return FString::Printf(TEXT("Resting until %s."), *HRContent::FormatDay(H.NextBreedingT));
		if (H.BreedingUntilT >= 0 && S.T >= H.BreedingUntilT) return TEXT("Its breeding career is over.");
		if (!CanBreed(S, H)) return TEXT("Not available for breeding.");
		return FString();
	}

	int32 BreedingCost(const FHRWorldState& S, const FString& PlayerId, const FHRHorse& Partner)
	{
		const FHRStable* St = PlayerStable(S, PlayerId);
		return BreedingServiceCost + (St && Partner.OwnerId == St->Id ? 0 : BreedingFee(Partner));
	}

	FString BreedingRefusal(const FHRWorldState& S, const FString& PlayerId, const FHRHorse& Mine, const FHRHorse& Partner)
	{
		const FHRStable* St = PlayerStable(S, PlayerId);
		const FHRPlayer* P = FindPlayer(S, PlayerId);
		if (!St || !P || Mine.OwnerId != St->Id) return TEXT("Choose one of your horses first.");
		if (Mine.Id == Partner.Id || Mine.bMare == Partner.bMare) return TEXT("It takes a mare and a stallion.");
		const FHRStable* Owner = FindStable(S, Partner.OwnerId);
		if (!Owner || Owner->bForSale) return FString::Printf(TEXT("%s is not offered for breeding."), *Partner.Name);
		FString Why = BreedingAvailability(S, Mine);
		if (!Why.IsEmpty()) return Mine.Name + TEXT(": ") + Why;
		Why = BreedingAvailability(S, Partner);
		if (!Why.IsEmpty()) return Partner.Name + TEXT(": ") + Why;
		if (Related(S, Mine, Partner)) return TEXT("These two horses are too closely related.");
		// One breeding a day (it also keeps the foals' ids unique).
		if (S.Pregnancies.ContainsByPredicate([&S, St](const FHRPregnancy& X) { return X.BreederId == St->Id && X.ConceivedT == S.T; }))
			return TEXT("One covering a day: the next one tomorrow.");
		const int32 Cost = BreedingCost(S, PlayerId, Partner);
		if (P->Coins < Cost) return FString::Printf(TEXT("%d coins are missing."), Cost - P->Coins);
		return FString();
	}

	FString BreedPlayer(FHRWorldState& S, const FString& PlayerId, const FString& MineId, const FString& PartnerId, const FString& FoalName)
	{
		FHRHorse* Mine = S.Horses.Find(MineId);
		FHRHorse* Partner = S.Horses.Find(PartnerId);
		if (!Mine || !Partner) return TEXT("Horse not found.");
		const FString Why = BreedingRefusal(S, PlayerId, *Mine, *Partner);
		if (!Why.IsEmpty()) return Why;
		FHRStable& St = *PlayerStable(S, PlayerId);
		FHRPlayer& P = *FindPlayer(S, PlayerId);
		const int32 Fee = Partner->OwnerId == St.Id ? 0 : BreedingFee(*Partner);
		St.Coins = P.Coins;
		P.Coins = 0;
		FHRHorse& Mare = Mine->bMare ? *Mine : *Partner;
		FHRHorse& Stallion = Mine->bMare ? *Partner : *Mine;
		const bool bDone = Conceive(S, St, Mare, Stallion, Fee);
		P.Coins = St.Coins;
		St.Coins = 0;
		SweepOwnerCoins(S);  // the fee may have gone to another player's stable
		if (!bDone) return TEXT("The covering could not take place.");
		if (FHRPregnancy* Pregnancy = S.Pregnancies.FindByPredicate([&Mare](const FHRPregnancy& X) { return X.MareId == Mare.Id; }))
			Pregnancy->FoalName = FoalName.TrimStartAndEnd().Left(22);
		return FString();
	}

	FFoalOutlook FoalOutlook(const FHRWorldState& S, const FHRHorse& Mare, const FHRHorse& Sire, int32 Samples)
	{
		FFoalOutlook Out;
		TArray<int32> Values[4];
		for (int32 I = 0; I < FMath::Max(1, Samples); ++I)
		{
			FGenerationOptions O;
			O.Id = FString::Printf(TEXT("outlook:%s:%s:%d"), *Mare.Id, *Sire.Id, I);
			O.Seed = FString::Printf(TEXT("%s:%s"), *S.Seed, *O.Id);
			O.OwnerId = TEXT("outlook");
			O.T = S.T;
			O.Origin = TEXT("foal");
			O.Mother = &Mare;
			O.Father = &Sire;
			const FHRHorse Foal = GenerateHorse(O);
			for (int32 A = 0; A < 4; ++A) Values[A].Add(Foal.Ceilings.IsValidIndex(A) ? Foal.Ceilings[A] : 0);
		}
		for (int32 A = 0; A < 4; ++A)
		{
			Values[A].Sort();
			const int32 N = Values[A].Num();
			Out.Low[A] = Values[A][N / 10];
			Out.Mid[A] = Values[A][N / 2];
			Out.High[A] = Values[A][FMath::Min(N - 1, N * 9 / 10)];
		}
		return Out;
	}
}
