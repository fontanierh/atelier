#include "HRSave.h"

#include "HRBreeds.h"
#include "HRClock.h"
#include "HRContent.h"
#include "HRRules.h"
#include "HRVisualGenome.h"
#include "JsonObjectConverter.h"
#include "Dom/JsonObject.h"
#include "UObject/UnrealType.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	/** Token-stream pre-pass before building a DOM: rejects repeated object keys (case-insensitively, as TMap<FString,...>
	 * compares), any single array or object exceeding MaxTickets entries, and any document exceeding MaxTotalNodes total tokens
	 * so a crafted input cannot allocate an unbounded DOM. */
	bool ScanJsonTokens(const FString& Json, FString& Error)
	{
		constexpr int32 MaxTotalNodes = 20000000;
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
		TArray<TSet<FString>> Keys;
		TArray<bool> IsObject;
		TArray<int32> Counts;
		int32 TotalNodes = 0;
		EJsonNotation Notation;
		while (Reader->ReadNext(Notation))
		{
			if (Notation == EJsonNotation::ObjectEnd || Notation == EJsonNotation::ArrayEnd)
			{
				if (Keys.Num()) { Keys.Pop(EAllowShrinking::No); IsObject.Pop(EAllowShrinking::No); Counts.Pop(EAllowShrinking::No); }
				continue;
			}
			if (Notation == EJsonNotation::Error) return true;  // the parser reports it
			if (++TotalNodes > MaxTotalNodes)
			{
				Error = FString::Printf(TEXT("the save has more than %d JSON values"), MaxTotalNodes);
				return false;
			}
			if (Counts.Num() && ++Counts.Last() > HRSave::MaxTickets)
			{
				Error = FString::Printf(TEXT("an array or object has more than %d entries"), HRSave::MaxTickets);
				return false;
			}
			if (IsObject.Num() && IsObject.Last())
			{
				bool bSeen = false;
				Keys.Last().Add(Reader->GetIdentifier(), &bSeen);
				if (bSeen)
				{
					Error = FString::Printf(TEXT("the key \"%s\" appears twice in one object"), *Reader->GetIdentifier().Left(64));
					return false;
				}
			}
			if (Notation == EJsonNotation::ObjectStart || Notation == EJsonNotation::ArrayStart)
			{
				Keys.AddDefaulted();
				IsObject.Add(Notation == EJsonNotation::ObjectStart);
				Counts.Add(0);
			}
		}
		return true;
	}

	/** Collects the first failure; every check is a no-op once one has failed. */
	struct FAdmission
	{
		FString Error;
		bool Ok() const { return Error.IsEmpty(); }
		void Fail(const FString& Why) { if (Error.IsEmpty()) Error = Why; }
		void Check(bool bCondition, const FString& Why) { if (!bCondition) Fail(Why); }
		void Range(int64 Value, int64 Low, int64 High, const FString& What)
		{
			if (Ok() && (Value < Low || Value > High))
				Fail(FString::Printf(TEXT("%s is %lld, outside %lld..%lld"), *What, Value, Low, High));
		}
		void Size(int32 Num, int32 Max, const FString& What)
		{
			if (Ok() && Num > Max) Fail(FString::Printf(TEXT("%s has %d entries, more than %d"), *What, Num, Max));
		}
		void Id(const FString& Value, const FString& What)
		{
			if (!Ok()) return;
			if (Value.IsEmpty()) Fail(What + TEXT(" is missing"));
			else if (Value.Len() > HRSave::MaxIdChars) Fail(What + TEXT(" is too long"));
		}
		void Text(const FString& Value, const FString& What)
		{
			if (Ok() && Value.Len() > HRSave::MaxTextChars) Fail(What + TEXT(" is too long"));
		}
		void Stats(const TArray<int32>& Values, int32 Exact, int32 Low, int32 High, const FString& What)
		{
			if (!Ok()) return;
			if (Exact >= 0 ? Values.Num() != Exact : Values.Num() > -Exact)
			{
				Fail(FString::Printf(TEXT("%s has %d values"), *What, Values.Num()));
				return;
			}
			for (int32 I = 0; I < Values.Num(); ++I) Range(Values[I], Low, High, FString::Printf(TEXT("%s[%d]"), *What, I));
		}
	};

	/** The highest allele a gene may carry: 0..4 unless the gene says otherwise (HRTypes.h, HRBreeds.h, HRVisualGenome.h).
	 * Alleles index tables when a foal inherits them, so an out-of-range one is refused rather than clamped. */
	int32 GeneMax(const FString& Key)
	{
		if (Key == HRBreeds::Gene) return HRBreeds::AlleleCount - 1;
		if (Key == TEXT("signature")) return HRContent::Traits().Num() - 1;
		if (Key == TEXT("surface")) return 2;
		if (Key == TEXT("surfaceFlex") || Key == TEXT("stifleRisk")) return 1;
		const int32 Visual = HRVisual::AlleleCount(Key);
		return Visual > 0 ? Visual - 1 : 4;
	}

	bool OneOf(const FString& Value, std::initializer_list<const TCHAR*> Allowed)
	{
		for (const TCHAR* A : Allowed) if (Value == A) return true;
		return false;
	}

	bool StrictJsonValue(const FProperty* Prop, const TSharedPtr<FJsonValue>& Val, const FString& Path, FString& Error);
	/** Validates known UStruct properties before JsonObjectToUStruct coerces them; unknown JSON keys are ignored for forward compatibility. */
	bool StrictJsonStruct(const UStruct* Struct, const TSharedPtr<FJsonObject>& Obj, const FString& Path, FString& Error)
	{
		if (!Struct || !Obj.IsValid()) { Error = Path + TEXT(" is not a JSON object"); return false; }
		for (TFieldIterator<FProperty> It(Struct); It; ++It)
		{
			const FProperty* Prop = *It;
			for (const auto& Entry : Obj->Values)
			{
				const FString Key(Entry.Key);
				if (!Key.Equals(Prop->GetName(), ESearchCase::IgnoreCase)) continue;
				if (!StrictJsonValue(Prop, Entry.Value, Path.IsEmpty() ? Key : Path + TEXT(".") + Key, Error)) return false;
			}
		}
		return true;
	}

	bool StrictJsonValue(const FProperty* Prop, const TSharedPtr<FJsonValue>& Val, const FString& Path, FString& Error)
	{
		if (!Prop || !Val.IsValid() || Val->Type == EJson::Null) { Error = Path + TEXT(" is null or missing"); return false; }
		if (CastField<FBoolProperty>(Prop))
		{
			if (Val->Type != EJson::Boolean) { Error = Path + TEXT(" must be a boolean"); return false; }
			return true;
		}
		if (CastField<FStrProperty>(Prop) || CastField<FNameProperty>(Prop))
		{
			if (Val->Type != EJson::String) { Error = Path + TEXT(" must be a string"); return false; }
			return true;
		}
		if (const FNumericProperty* Num = CastField<FNumericProperty>(Prop))
		{
			if (Val->Type != EJson::Number) { Error = Path + TEXT(" must be a number"); return false; }
			const double D = Val->AsNumber();
			if (!FMath::IsFinite(D)) { Error = Path + TEXT(" is not finite"); return false; }
			if (Num->IsInteger())
			{
				if (FMath::FloorToDouble(D) != D) { Error = Path + TEXT(" must be an integer"); return false; }
				if (CastField<FIntProperty>(Prop) && (D < double(MIN_int32) || D > double(MAX_int32)))
				{ Error = Path + TEXT(" is outside int32"); return false; }
				if (CastField<FInt64Property>(Prop) && (D < -9007199254740992.0 || D > 9007199254740992.0))
				{ Error = Path + TEXT(" is outside safe int64"); return false; }
			}
			return true;
		}
		if (const FStructProperty* St = CastField<FStructProperty>(Prop))
		{
			const TSharedPtr<FJsonObject>* Child = nullptr;
			if (!Val->TryGetObject(Child) || !Child) { Error = Path + TEXT(" must be an object"); return false; }
			return StrictJsonStruct(St->Struct, *Child, Path, Error);
		}
		if (const FArrayProperty* Arr = CastField<FArrayProperty>(Prop))
		{
			const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
			if (!Val->TryGetArray(List) || !List) { Error = Path + TEXT(" must be an array"); return false; }
			for (int32 I = 0; I < List->Num(); ++I)
				if (!StrictJsonValue(Arr->Inner, (*List)[I], FString::Printf(TEXT("%s[%d]"), *Path, I), Error)) return false;
			return true;
		}
		if (const FMapProperty* Map = CastField<FMapProperty>(Prop))
		{
			const TSharedPtr<FJsonObject>* Child = nullptr;
			if (!Val->TryGetObject(Child) || !Child) { Error = Path + TEXT(" must be an object"); return false; }
			for (const auto& Entry : (*Child)->Values)
			{
				const FString Key(Entry.Key);
				if (!StrictJsonValue(Map->ValueProp, Entry.Value, Path + TEXT(".") + Key, Error)) return false;
			}
			return true;
		}
		return true;
	}
}

namespace HRSave
{
	FString ToJson(const FHRWorldState& S)
	{
		FString Json;
		FJsonObjectConverter::UStructToJsonObjectString(S, Json, 0, 0, 0, nullptr, false);
		return Json;
	}

	FString Validate(const FHRWorldState& S)
	{
		FAdmission A;
		constexpr int64 MaxInt = MAX_int32;
		const int64 MaxCoins = HRRules::MaxCoins;
		A.Check(S.SchemaVersion == SchemaVersion, FString::Printf(TEXT("schema version %d, expected %d"), S.SchemaVersion, SchemaVersion));
		A.Check(S.RulesVersion == HRRules::RulesVersion, FString::Printf(TEXT("rules version \"%s\", expected \"%s\""), *S.RulesVersion.Left(64), HRRules::RulesVersion));
		A.Id(S.Seed, TEXT("seed"));
		A.Range(S.T, 0, MaxDay, TEXT("day"));
		A.Range(S.Edition, 1, MaxDay, TEXT("season"));
		A.Range(S.ArrivalT, 0, S.T, TEXT("arrival day"));
		A.Range(S.EpochUnix, -100000000000LL, 100000000000LL, TEXT("clock epoch"));
		A.Range(S.Serial, 0, MaxInt, TEXT("serial"));
		A.Range(S.RiderSerial, 0, MaxInt, TEXT("rider serial"));
		A.Size(S.Stables.Num(), MaxStables, TEXT("stables"));
		A.Size(S.Horses.Num(), MaxHorses, TEXT("horses"));
		A.Size(S.Riders.Num(), MaxRiders, TEXT("riders"));
		A.Size(S.Players.Num(), MaxPlayers, TEXT("players"));
		A.Size(S.Meeting.Races.Num(), MaxRaces, TEXT("races"));
		A.Size(S.Tickets.Num(), MaxTickets, TEXT("tickets"));
		A.Size(S.Listings.Num(), MaxListings, TEXT("listings"));
		A.Size(S.Pregnancies.Num(), MaxPregnancies, TEXT("pregnancies"));
		A.Size(S.News.Num(), MaxNews, TEXT("news"));
		A.Size(S.LegendCooldownUntil.Num(), MaxList, TEXT("legend cooldowns"));
		A.Size(S.Meeting.Riders.Num(), MaxList, TEXT("race day riders"));
		if (!A.Ok()) return A.Error;

		// Identities first, so references can be checked against them.
		TSet<FString> StableIds;
		for (const FHRStable& St : S.Stables)
		{
			A.Id(St.Id, TEXT("a stable's id"));
			bool bSeen = false;
			StableIds.Add(St.Id, &bSeen);
			A.Check(!bSeen, FString::Printf(TEXT("stable %s appears twice"), *St.Id.Left(64)));
		}
		auto IsStable = [&StableIds](const FString& Id) { return StableIds.Contains(Id); };
		auto IsHorse = [&S](const FString& Id) { return S.Horses.Contains(Id); };
		auto IsPlayer = [&S](const FString& Id) { return S.Players.Contains(Id); };
		auto IsRider = [&S](const FString& Id) { return S.Riders.Contains(Id); };
		for (const TPair<FString, FHRHorse>& It : S.Horses)
			A.Check(It.Key == It.Value.Id && !It.Key.IsEmpty(), FString::Printf(TEXT("horse key %s does not match its id"), *It.Key.Left(64)));
		for (const TPair<FString, FHRRider>& It : S.Riders)
			A.Check(It.Key == It.Value.Id && !It.Key.IsEmpty(), FString::Printf(TEXT("rider key %s does not match its id"), *It.Key.Left(64)));
		for (const TPair<FString, FHRPlayer>& It : S.Players)
			A.Check(It.Key == It.Value.Id && !It.Key.IsEmpty(), FString::Printf(TEXT("player key %s does not match its id"), *It.Key.Left(64)));
		if (!A.Ok()) return A.Error;

		TSet<FString> OwnerPlayers;
		for (const FHRStable& St : S.Stables)
		{
			const FString W = TEXT("stable ") + St.Id.Left(64);
			A.Text(St.Name, W + TEXT(" name"));
			A.Text(St.Motto, W + TEXT(" motto"));
			A.Check(St.OwnerPlayerId.IsEmpty() || IsPlayer(St.OwnerPlayerId), W + TEXT(" is owned by an unknown player"));
			if (!St.OwnerPlayerId.IsEmpty())
			{
				bool bOwned = false;
				OwnerPlayers.Add(St.OwnerPlayerId, &bOwned);
				A.Check(!bOwned, W + TEXT(" shares its owner player with another stable"));
			}
			A.Range(St.Coins, 0, MaxCoins, W + TEXT(" coins"));
			A.Range(St.Debt, 0, MaxCoins, W + TEXT(" debt"));
			A.Range(St.Emblem, 0, MaxInt, W + TEXT(" emblem"));
			A.Range(St.TotalEarnings, 0, MaxInt, W + TEXT(" earnings"));
			A.Range(St.UpkeepPaid, 0, MaxInt, W + TEXT(" upkeep paid"));
			A.Range(St.TrainingUsed, 0, HRRules::TrainingSlots, W + TEXT(" training sessions"));
			A.Size(St.GpTitles.Num(), MaxList, W + TEXT(" titles"));
			A.Size(St.GrandSlams.Num(), MaxList, W + TEXT(" grand slams"));
		}
		for (const TPair<FString, FHRHorse>& It : S.Horses)
		{
			if (!A.Ok()) break;
			const FHRHorse& H = It.Value;
			const FString W = TEXT("horse ") + H.Id.Left(64);
			A.Id(H.Id, W + TEXT(" id"));
			A.Id(H.Seed, W + TEXT(" seed"));
			A.Text(H.Name, W + TEXT(" name"));
			A.Check(H.OwnerId == TEXT("market") || IsStable(H.OwnerId), W + TEXT(" has an unknown owner"));
			A.Check(H.Parents.Num() == 0 || H.Parents.Num() == 2, W + TEXT(" must have no parents or two"));
			for (const FString& P : H.Parents)
			{
				A.Check(P != H.Id && IsHorse(P), W + TEXT(" has an unknown parent"));
				if (const FHRHorse* Parent = S.Horses.Find(P))
					A.Check(Parent->BirthT < H.BirthT, W + TEXT(" has a parent born no earlier than itself"));
			}
			A.Size(H.Owners.Num(), MaxList, W + TEXT(" owners"));
			for (const FString& O : H.Owners) A.Check(O == TEXT("market") || IsStable(O), W + TEXT(" lists an unknown former owner"));
			A.Size(H.Career.Num(), MaxCareer, W + TEXT(" career"));
			A.Size(H.Genome.Num(), MaxGenes, W + TEXT(" genome"));
			for (const TPair<FString, FHRGenePair>& G : H.Genome)
			{
				A.Range(G.Value.A, 0, GeneMax(G.Key), W + TEXT(" gene ") + G.Key.Left(32));
				A.Range(G.Value.B, 0, GeneMax(G.Key), W + TEXT(" gene ") + G.Key.Left(32));
			}
			A.Stats(H.Abilities, HRAbility::Count, 0, MaxAbility, W + TEXT(" abilities"));
			A.Stats(H.Ceilings, HRAbility::Count, 0, MaxAbility, W + TEXT(" ceilings"));
			A.Stats(H.Response, HRAbility::Count, 0, 1000, W + TEXT(" response"));
			A.Stats(H.Progress, HRAbility::Count, 0, 1000000, W + TEXT(" progress"));
			A.Check(H.Zones.Num() == 4, W + TEXT(" must have four tissue zones"));
			for (int32 Z = 0; Z < H.Zones.Num(); ++Z)
			{
				const FHRZone& Zone = H.Zones[Z];
				const FString ZW = FString::Printf(TEXT("%s zone[%d]"), *W, Z);
				A.Range(Zone.Structure, 0, 10000000, ZW + TEXT(" structure"));
				A.Range(Zone.Acute, 0, 10000000, ZW + TEXT(" acute"));
				A.Range(Zone.Recovery, 0, 10000000, ZW + TEXT(" recovery"));
				A.Range(Zone.Adaptation, 0, 10000000, ZW + TEXT(" adaptation"));
				A.Range(Zone.InflammationGene, 0, 10000000, ZW + TEXT(" inflammation gene"));
				A.Range(Zone.Load, 0, 10000000, ZW + TEXT(" load"));
				A.Range(Zone.Tolerance, 0, 10000000, ZW + TEXT(" tolerance"));
				A.Range(Zone.Inflammation, 0, 10000000, ZW + TEXT(" inflammation"));
				A.Range(Zone.Scars, 0, 100, ZW + TEXT(" scars"));
			}
			A.Range(H.Condition, 0, 3, W + TEXT(" condition"));
			A.Range(H.Mastery, 0, 2, W + TEXT(" mastery"));
			A.Range(H.Favorite, 0, 2, W + TEXT(" favourite surface"));
			A.Range(H.Difficult, 0, 2, W + TEXT(" difficult surface"));
			A.Range(H.ReadyT, -MaxDay, MaxDay * 2, W + TEXT(" ready day"));
			A.Range(H.ScheduledRetirementT, -MaxDay, MaxDay * 2, W + TEXT(" retirement day"));
			A.Range(H.RetiredT, -1, S.T + 1, W + TEXT(" retired day"));
			A.Range(H.BreedingUntilT, -1, MaxDay * 2, W + TEXT(" breeding until day"));
			A.Range(H.NextBreedingT, -MaxDay, MaxDay * 2, W + TEXT(" next breeding day"));
			A.Range(H.Injury.Benches, 0, MaxDay, W + TEXT(" injury benches"));
			A.Range(H.Injury.Minimum, 0, MaxDay, W + TEXT(" injury minimum"));
			A.Range(H.Injury.SinceT, -1, S.T + 1, W + TEXT(" injury day"));
			A.Range(H.Stress, 0, MaxInt, W + TEXT(" stress"));
			A.Range(H.Xp, 0, MaxInt, W + TEXT(" experience"));
			A.Range(H.BirthT, -MaxDay, S.T + 1, W + TEXT(" birth day"));
			A.Range(H.Starts, 0, MaxInt, W + TEXT(" starts"));
			A.Range(H.Wins, 0, H.Starts, W + TEXT(" wins"));
			A.Range(H.Earnings, 0, MaxInt, W + TEXT(" earnings"));
			A.Range(H.Generation, 0, MaxDay, W + TEXT(" generation"));
		}
		for (const TPair<FString, FHRRider>& It : S.Riders)
		{
			if (!A.Ok()) break;
			const FHRRider& R = It.Value;
			const FString W = TEXT("rider ") + R.Id.Left(64);
			FString Suffix;
			if (R.Id.Split(TEXT("rider:"), nullptr, &Suffix) && Suffix.IsNumeric())
				A.Check(FCString::Atoi64(*Suffix) <= S.RiderSerial, W + TEXT(" exceeds rider serial"));
			A.Text(R.FirstName + R.LastName, W + TEXT(" name"));
			A.Check(R.OwnerId.IsEmpty() || IsStable(R.OwnerId), W + TEXT(" rides for an unknown stable"));
			A.Size(R.Stables.Num(), MaxList, W + TEXT(" stables"));
			for (const FString& St : R.Stables) A.Check(IsStable(St), W + TEXT(" lists an unknown stable"));
			A.Stats(R.Skill, 4, 0, MaxSkill, W + TEXT(" skills"));
			A.Stats(R.SeasonSkill, 4, 0, MaxSkill, W + TEXT(" season skills"));
			A.Stats(R.Potential, 4, 0, MaxSkill, W + TEXT(" potential"));
			A.Range(R.Growth, 0, 1000, W + TEXT(" growth"));
			A.Range(R.Decline, 0, 1000, W + TEXT(" decline"));
			A.Range(R.PeakAge, 0, 12000, W + TEXT(" peak age"));
			A.Range(R.PeakMonths, 0, 12000, W + TEXT(" peak months"));
			A.Range(R.RetireAge, 0, 12000, W + TEXT(" retire age"));
			A.Range(R.BirthT, -MaxDay, S.T + 1, W + TEXT(" birth day"));
			A.Range(R.DebutT, -MaxDay, S.T + 1, W + TEXT(" debut day"));
			A.Range(R.CurveRides, 0, MaxInt, W + TEXT(" curve rides"));
			A.Range(R.Wage, 0, MaxCoins, W + TEXT(" wage"));
			A.Range(R.ListedPrice, 0, MaxCoins, W + TEXT(" transfer price"));
			A.Range(R.Rides, 0, MaxInt, W + TEXT(" rides"));
			A.Range(R.Wins, 0, MaxInt, W + TEXT(" wins"));
		}
		for (const TPair<FString, FHRPlayer>& It : S.Players)
		{
			if (!A.Ok()) break;
			const FHRPlayer& P = It.Value;
			const FString W = TEXT("player ") + P.Id.Left(64);
			A.Id(P.Id, W + TEXT(" id"));
			A.Text(P.Name, W + TEXT(" name"));
			A.Range(P.Coins, 0, MaxCoins, W + TEXT(" coins"));
			A.Range(P.TotalStaked, 0, MaxInt, W + TEXT(" total staked"));
			A.Range(P.TotalWon, 0, MaxInt, W + TEXT(" total won"));
			A.Range(P.TotalIncome, 0, MaxInt, W + TEXT(" total income"));
			A.Range(P.TicketsWon, 0, MaxInt, W + TEXT(" tickets won"));
			A.Range(P.Rides, 0, MaxInt, W + TEXT(" rides"));
			A.Stats(P.RiderSkill, -4, 0, MaxSkill, W + TEXT(" rider skill"));
			A.Size(P.Resting.Num(), MaxList, W + TEXT(" resting horses"));
			A.Size(P.Trained.Num(), MaxList, W + TEXT(" trained horses"));
			for (const FString& H : P.Resting) A.Check(IsHorse(H), W + TEXT(" rests an unknown horse"));
			for (const FString& H : P.Trained) A.Check(IsHorse(H), W + TEXT(" trained an unknown horse"));
		}
		if (!A.Ok()) return A.Error;

		// The race day.
		A.Check(S.Meeting.T == S.T, TEXT("the race day is not today"));
		A.Check(S.Meeting.EventIndex == HRClock::DayOfSeason(S.T), TEXT("the race day's event does not match the day"));
		TSet<FString> RaceKeys;
		for (const FHRRace& R : S.Meeting.Races)
		{
			const FString W = TEXT("race ") + R.Key.Left(64);
			A.Id(R.Key, TEXT("a race's key"));
			bool bSeen = false;
			RaceKeys.Add(R.Key, &bSeen);
			A.Check(!bSeen, W + TEXT(" appears twice"));
			A.Check(OneOf(R.Status, {TEXT("declared"), TEXT("run"), TEXT("uncontested"), TEXT("bye")}), W + TEXT(" has an unknown status"));
			A.Range(R.Distance, 0, 100000, W + TEXT(" distance"));
			A.Size(R.Entries.Num(), MaxEntries, W + TEXT(" entries"));
			A.Size(R.Finishes.Num(), R.Entries.Num(), W + TEXT(" finishes"));
			A.Size(R.Runs.Num(), 2, W + TEXT(" runs"));
			A.Size(R.Incidents.Num(), MaxList, W + TEXT(" incidents"));
			A.Size(R.PublicOrders.Num(), MaxList, W + TEXT(" public orders"));
			TSet<FString> Entrants;
			for (const FHRRunner& E : R.Entries)
			{
				A.Check(IsHorse(E.HorseId), W + TEXT(" has an unknown entrant"));
				A.Check(IsStable(E.StableId), W + TEXT(" has an entrant of an unknown stable"));
				A.Check(E.RiderPlayerId.IsEmpty() || IsPlayer(E.RiderPlayerId), W + TEXT(" has an unknown player riding"));
				A.Range(E.Preparation, 0, 2, W + TEXT(" preparation"));
				bool bTwice = false;
				Entrants.Add(E.HorseId, &bTwice);
				A.Check(!bTwice, W + TEXT(" has a horse entered twice"));
			}
			auto Finishes = [&](const TArray<FHRFinish>& List)
			{
				for (const FHRFinish& F : List)
				{
					A.Check(Entrants.Contains(F.HorseId), W + TEXT(" has a finisher that was not entered"));
					A.Range(F.Place, 0, MaxEntries, W + TEXT(" place"));
					A.Range(F.Gross, 0, MaxCoins, W + TEXT(" prize"));
					A.Range(F.TimeUs, 0, 3600000000LL, W + TEXT(" finish time"));
					A.Size(F.Segments.Num(), 16, W + TEXT(" segments"));
					for (const FHRSegment& Seg : F.Segments)
					{
						A.Range(Seg.DurationUs, 0, 3600000000LL, W + TEXT(" segment time"));
						A.Range(Seg.CumulativeUs, 0, 3600000000LL, W + TEXT(" cumulative time"));
					}
					A.Size(F.RunTimesUs.Num(), 2, W + TEXT(" run times"));
					for (int64 RunUs : F.RunTimesUs) A.Range(RunUs, 0, 3600000000LL, W + TEXT(" run time"));
				}
			};
			Finishes(R.Finishes);
			for (const FHRRaceRun& Run : R.Runs) Finishes(Run.Finishes);
			for (const FHROrderCount& O : R.PublicOrders) A.Range(O.Count, 0, MaxInt, W + TEXT(" public order count"));
		}
		for (const TPair<FString, FString>& It : S.Meeting.Riders)
			A.Check(IsHorse(It.Key) && IsRider(It.Value), TEXT("a race day rider refers to an unknown horse or rider"));

		// Markets, breeding and bets.
		TSet<FString> Listed, Mares, Tickets;
		for (const FHRSaleListing& L : S.Listings)
		{
			A.Check(IsHorse(L.HorseId), TEXT("a listing offers an unknown horse"));
			A.Check(IsStable(L.SellerId), TEXT("a listing has an unknown seller"));
			if (const FHRHorse* H = S.Horses.Find(L.HorseId))
				A.Check(H->OwnerId == L.SellerId, TEXT("a listing's seller does not own the horse"));
			A.Range(L.Price, 0, MaxCoins, TEXT("a listing's price"));
			bool bSeen = false;
			Listed.Add(L.HorseId, &bSeen);
			A.Check(!bSeen, TEXT("a horse is listed twice"));
		}
		for (const FHRPregnancy& P : S.Pregnancies)
		{
			A.Check(IsHorse(P.MareId) && IsHorse(P.SireId), TEXT("a pregnancy refers to an unknown horse"));
			if (const FHRHorse* Mare = S.Horses.Find(P.MareId))
				if (const FHRHorse* Sire = S.Horses.Find(P.SireId))
					A.Check(P.MareId != P.SireId && Mare->bMare && !Sire->bMare, TEXT("a pregnancy requires a mare and a sire"));
			A.Check(IsStable(P.BreederId), TEXT("a pregnancy has an unknown breeder"));
			A.Range(P.DueT, 0, MaxDay, TEXT("a pregnancy's due day"));
			bool bSeen = false;
			Mares.Add(P.MareId, &bSeen);
			A.Check(!bSeen, TEXT("a mare is in foal twice"));
		}
		for (const FHRTicket& T : S.Tickets)
		{
			const FString W = TEXT("ticket ") + T.Id.Left(64);
			A.Id(T.Id, TEXT("a ticket's id"));
			bool bSeen = false;
			Tickets.Add(T.Id, &bSeen);
			A.Check(!bSeen, W + TEXT(" appears twice"));
			const FString Prefix = FString::Printf(TEXT("bet:%d:"), S.T);
			if (T.Id.StartsWith(Prefix, ESearchCase::CaseSensitive))
			{
				const FString Rest = T.Id.Mid(Prefix.Len());
				if (Rest.IsNumeric()) A.Check(FCString::Atoi64(*Rest) < S.Serial, W + TEXT(" reaches or exceeds serial"));
			}
			A.Check(IsPlayer(T.PlayerId), W + TEXT(" belongs to an unknown player"));
			A.Check(IsHorse(T.HorseId), W + TEXT(" backs an unknown horse"));
			A.Check(OneOf(T.Status, {TEXT("open"), TEXT("won"), TEXT("lost"), TEXT("refunded")}), W + TEXT(" has an unknown status"));
			A.Check(T.Status != TEXT("open") || (T.T == S.T && RaceKeys.Contains(T.RaceKey)), W + TEXT(" is open on a race not run today"));
			A.Range(T.T, 0, S.T, W + TEXT(" day"));
			A.Range(T.Stake, HRRules::FBetLimits::MinStake, HRRules::FBetLimits::MaxStake, W + TEXT(" stake"));
			A.Range(T.Payout, 0, MaxCoins, W + TEXT(" payout"));
			A.Check(FMath::IsFinite(T.Rapport) && T.Rapport >= 0. && T.Rapport < 1e6, W + TEXT(" has invalid odds"));
		}
		for (const FHRNews& N : S.News)
		{
			A.Text(N.Text, TEXT("a news item"));
			A.Size(N.HorseIds.Num() + N.StableIds.Num(), MaxList, TEXT("a news item's references"));
		}
		return A.Error;
	}

	bool FromJson(const FString& Json, FHRWorldState& Out, FString& Error)
	{
		if (Json.Len() > MaxJsonChars)
		{
			Error = FString::Printf(TEXT("the save is %d characters, more than %d"), Json.Len(), MaxJsonChars);
			return false;
		}
		if (!ScanJsonTokens(Json, Error)) return false;
		TSharedPtr<FJsonObject> Root;
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root.IsValid())
		{
			Error = TEXT("not a JSON object");
			return false;
		}
		// Fields a world of these rules always has (JSON keys compare case-insensitively).
		for (const TCHAR* Field : {TEXT("schemaVersion"), TEXT("rulesVersion"), TEXT("seed"), TEXT("t"), TEXT("edition"), TEXT("stables"),
			TEXT("horses"), TEXT("meeting"), TEXT("players"), TEXT("riders"), TEXT("tickets")})
		{
			if (!Root->HasField(Field))
			{
				Error = FString::Printf(TEXT("the required field \"%s\" is missing"), Field);
				return false;
			}
		}
		if (!StrictJsonStruct(FHRWorldState::StaticStruct(), Root, FString(), Error)) return false;
		FHRWorldState Parsed;
		if (!FJsonObjectConverter::JsonObjectToUStruct(Root.ToSharedRef(), &Parsed, 0, 0))
		{
			Error = TEXT("the JSON does not match the world's fields");
			return false;
		}
		Error = Validate(Parsed);
		if (!Error.IsEmpty()) return false;
		HRVisual::FillMissingLoci(Parsed);
		HRBreeds::FillMissing(Parsed);
		Error = Validate(Parsed);
		if (!Error.IsEmpty()) return false;
		Out = MoveTemp(Parsed);
		return true;
	}

	bool FromJson(const FString& Json, FHRWorldState& Out)
	{
		FString Error;
		return FromJson(Json, Out, Error);
	}
}
