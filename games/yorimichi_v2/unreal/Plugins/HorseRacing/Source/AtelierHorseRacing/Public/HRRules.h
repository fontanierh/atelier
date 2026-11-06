#pragma once

#include "CoreMinimal.h"
#include "HRClock.h"
#include "HRContent.h"
#include "HRTypes.h"

/**
 * The rules of a living horse racing world, as pure functions over FHRWorldState: computer stables race, train, breed,
 * trade horses and riders; players (opaque ids) bet, and may own stables. No engine world, actor or UI is involved, and
 * every draw comes from the world's seed, so any machine given the same state and the same calls reaches the same state.
 *
 * Refusal functions return an empty string when the action is allowed, otherwise the reason (English).
 */
namespace HRRules
{
	inline constexpr const TCHAR* RulesVersion = TEXT("atelier-horse-racing-1");

	// ---------------------------------------------------------------- money
	/** Every balance (a player's or a stable's coins, a debt, a price) stays within 0..MaxCoins: credits saturate there and
	 * sums are taken in int64, so no prize, payout, refund or sale can overflow. */
	inline constexpr int32 MaxCoins = 1000000000;
	/** A balance plus a credit (never negative), saturated at MaxCoins. */
	inline int32 Credit(int32 Balance, int64 Amount)
	{
		return (int32)FMath::Clamp<int64>((int64)Balance + FMath::Max<int64>(Amount, 0), 0, MaxCoins);
	}
	/** A running total (earnings, winnings, upkeep paid) plus an amount, saturated within 0..MAX_int32. */
	inline int32 Tally(int32 Total, int64 Amount)
	{
		return (int32)FMath::Clamp<int64>((int64)Total + Amount, 0, MAX_int32);
	}

	// ---------------------------------------------------------------- generation
	struct FGenerationOptions
	{
		FString Id;
		FString Seed;
		FString OwnerId;
		/** The race day the horse is generated on. */
		int32 T = 0;
		/** "rival", "recruit", "starter", "foal" or "recovery". */
		FString Origin;
		int32 Slot = 0;
		const FHRHorse* Mother = nullptr;
		const FHRHorse* Father = nullptr;
		/** Initial-world founders only: exact age in horse months. */
		int32 AgeSteps = -1;
		/** "", "modest" or "established". */
		FString Prospect;
	};
	ATELIERHORSERACING_API FHRHorse GenerateHorse(const FGenerationOptions& O);
	/** Adds the horse with a unique name. */
	ATELIERHORSERACING_API FHRHorse& AddHorse(FHRWorldState& S, FHRHorse&& H);
	/** Age of a horse in horse months on day T. */
	inline int32 HorseAgeMonths(const FHRHorse& H, int32 T) { return HRClock::LifeMonths(H.BirthT, T); }

	// ---------------------------------------------------------------- biology
	struct FForecast
	{
		/** "green", "amber", "red" or "critical". */
		FString Band;
		bool bAllowed = false;
		FString Reason;
		TArray<int32> Incoming;
		bool bPermanentRisk = false;
	};
	ATELIERHORSERACING_API bool Runnable(const FHRHorse& H, int32 T);
	ATELIERHORSERACING_API FForecast Forecast(const FHRHorse& H, const HRContent::FEvent& E, int32 Distance, int32 Preparation, int32 T);
	ATELIERHORSERACING_API FString Exert(FHRHorse& H, const FForecast& F, int32 T, bool bRace);
	/** Ends the racing career; the horse may still breed until it goes to the archives HRClock::ArchiveDays later. */
	ATELIERHORSERACING_API void Retire(FHRHorse& H, int32 T);
	ATELIERHORSERACING_API void RecoverTissueLoad(FHRHorse& H);
	ATELIERHORSERACING_API void Bench(FHRHorse& H, int32 T);
	/** Start of day T: scheduled retirement, archiving, injury recovery. */
	ATELIERHORSERACING_API void AdvanceHorse(FHRHorse& H, int32 T);
	ATELIERHORSERACING_API int32 ProgressAbility(FHRHorse& H, int32 Ability, int32 Base, int32 T);
	ATELIERHORSERACING_API bool CanBreed(const FHRWorldState& S, const FHRHorse& H);
	ATELIERHORSERACING_API bool Related(const FHRWorldState& S, const FHRHorse& A, const FHRHorse& B);

	// ---------------------------------------------------------------- races
	ATELIERHORSERACING_API int32 RaceDistance(const HRContent::FEvent& E, const FString& Round);
	/** Public neutral-form estimate (microseconds), used by the stables to choose runners. */
	ATELIERHORSERACING_API int64 PlanningTime(const FHRHorse& H, int32 Preparation, const HRContent::FEvent& E, int32 Distance);
	/** Runs one race: day form, stage swings and incidents from the seed. Updates the horses (records, exertion). */
	ATELIERHORSERACING_API void ResolveRace(FHRWorldState& S, FHRRace& Race);
	/** Top-three orders over Runs replays with fresh public form draws: the crowd's view, frozen at declaration. */
	ATELIERHORSERACING_API TArray<FHROrderCount> PublicOrders(const FHRWorldState& S, const FHRRace& Race, int32 Runs = 200);
	/** Grand Prix rounds before the final: "semi" heats, "qualif" sprints and "barrage" re-runs. */
	ATELIERHORSERACING_API bool IsHeatRound(const FString& Round);
	/** Official timing (1/100 s) of a finish: sprint-tournament ties are decided at this precision. */
	inline int64 Hundredths(int64 TimeUs) { return (TimeUs + 5000) / 10000; }

	inline constexpr int32 EntriesPerStable = 3;
	inline constexpr int32 MaxRunners = 6;

	// ---------------------------------------------------------------- world and clock
	/** A new world: the default stables (the first one for sale), their horses and riders, and one simulated season so
	 * the world has records on arrival. No player yet. */
	ATELIERHORSERACING_API FHRWorldState CreateWorld(const FString& Seed);
	/** Anchors the clock: world second DayStart(S.T) is NowUnix. */
	ATELIERHORSERACING_API void StartClock(FHRWorldState& S, int64 NowUnix);
	/** World seconds at a Unix time, from the anchor StartClock set. */
	ATELIERHORSERACING_API double WorldSeconds(const FHRWorldState& S, double NowUnix);
	/** The most race days one catch-up simulates: one real week (84 days). A world left longer resumes as if paused. */
	inline constexpr int32 MaxCatchUpDays = 7 * HRClock::DaysPerSeason;
	/**
	 * Bounds a catch-up: when WorldSeconds is more than MaxDays race days ahead of the world, the excess whole days are
	 * skipped (the clock anchor moves forward by them and WorldSeconds back), so at most MaxDays days remain to simulate.
	 * A non-finite or absurd time is refused (WorldSeconds becomes the world's present). Returns the days skipped.
	 * Deterministic: the same world and time give the same result.
	 */
	ATELIERHORSERACING_API int32 LimitCatchUp(FHRWorldState& S, double& WorldSeconds, int32 MaxDays = MaxCatchUpDays);
	/**
	 * Brings the world to a world second: every race whose slot has started is run (its result is decided at its start),
	 * every finished day is closed and the next one opened. Idempotent, and catching up hours at once gives the same
	 * world as stepping through them. At most MaxDays days are simulated (LimitCatchUp).
	 */
	ATELIERHORSERACING_API void AdvanceTo(FHRWorldState& S, double WorldSeconds, int32 MaxDays = MaxCatchUpDays);
	/** Runs any race left, closes the day (payouts, ageing, stables' decisions) and opens the next. */
	ATELIERHORSERACING_API void AdvanceDay(FHRWorldState& S);
	/** Runs the next race of the day; returns its key (empty when none is left). */
	ATELIERHORSERACING_API FString RunNextRace(FHRWorldState& S);
	ATELIERHORSERACING_API bool DayComplete(const FHRWorldState& S);
	/** Declares the Grand Prix final once its heats (and any barrage) are run; may declare a barrage instead. */
	ATELIERHORSERACING_API void DeclareFinalIfReady(FHRWorldState& S);

	/** The race's slot in today's schedule: first-round races in order, barrages in the second last slot, the final in
	 * the last one. */
	ATELIERHORSERACING_API int32 RaceSlot(const FHRWorldState& S, const FHRRace& Race);
	ATELIERHORSERACING_API int32 DaySlotCount(const FHRWorldState& S);
	/** World second at which a race of today starts (-1 if unknown). */
	ATELIERHORSERACING_API double RaceStartSeconds(const FHRWorldState& S, const FString& RaceKey);
	ATELIERHORSERACING_API HRClock::EHRRacePhase RacePhase(const FHRWorldState& S, const FString& RaceKey, double WorldSeconds);

	ATELIERHORSERACING_API FHRRace* FindRace(FHRWorldState& S, const FString& Key);
	ATELIERHORSERACING_API const FHRRace* FindRace(const FHRWorldState& S, const FString& Key);
	/** Next race of the day still to run, or nullptr when the race day is over. */
	ATELIERHORSERACING_API FHRRace* NextRace(FHRWorldState& S);
	ATELIERHORSERACING_API FHRStable* FindStable(FHRWorldState& S, const FString& Id);
	ATELIERHORSERACING_API const FHRStable* FindStable(const FHRWorldState& S, const FString& Id);
	ATELIERHORSERACING_API TArray<const FHRHorse*> StableHorses(const FHRWorldState& S, const FString& StableId, bool bIncludeArchive = false);
	ATELIERHORSERACING_API int32 BreedingFee(const FHRHorse& H);
	ATELIERHORSERACING_API int32 SaleValue(const FHRWorldState& S, const FHRHorse& H);
	ATELIERHORSERACING_API int32 CardScore(const FHRHorse& H);
	ATELIERHORSERACING_API void AddNews(FHRWorldState& S, const FString& Kind, const FString& Text, const TArray<FString>& Horses = {}, const TArray<FString>& Stables = {});

	inline constexpr int32 BreedingServiceCost = 70;
	/** Gestation: three horse months (21 race days, 42 real hours), the horse clock's pace rather than eleven months. */
	inline constexpr int32 GestationDays = 3 * HRClock::LifeMonth;
	ATELIERHORSERACING_API const FHRPregnancy* FindPregnancy(const FHRWorldState& S, const FString& MareId);
	/** Running costs, charged at each day's close: base fee plus feed and care of every horse a stable keeps. */
	inline constexpr int32 UpkeepBase = 5;
	inline constexpr int32 UpkeepRacing = 6;
	inline constexpr int32 UpkeepFoal = 3;
	inline constexpr int32 UpkeepRetired = 2;
	/** A day's running costs of a stable, its riders' wages included. */
	ATELIERHORSERACING_API int32 DailyUpkeep(const FHRWorldState& S, const FHRStable& St);
	inline constexpr int32 TrainingCost = 2;
	inline constexpr int32 TrainingSlots = 3;

	// ---------------------------------------------------------------- riders (HRRiders.cpp)
	/** Every stable keeps three jockeys on fixed salaries. */
	inline constexpr int32 RidersPerStable = 3;
	/** Displayed stat 1..10 of a skill in hundredths. */
	inline int32 RiderStat(int32 Skill) { return FMath::Clamp((Skill + 50) / 100, 1, 10); }
	inline constexpr int32 RiderLegendPerMille = 15;
	/** The for-sale stable's roster is drawn with a better chance: about one world in three gets a legend there. */
	inline constexpr int32 ForSaleLegendPerMille = 125;
	/** Race days before a retired legend may appear again: one season. */
	inline constexpr int32 LegendCooldownDays = HRClock::DaysPerSeason;
	/** Race days a free agent waits for a contract before retiring: one season. */
	inline constexpr int32 FreeAgentDays = HRClock::DaysPerSeason;
	ATELIERHORSERACING_API int32 RiderAgeMonths(const FHRRider& R, int32 T);
	ATELIERHORSERACING_API int32 RiderOverall(const FHRRider& R);
	ATELIERHORSERACING_API int32 RiderValue(const FHRRider& R, int32 T);
	/** One rider month of the career curve at that age (months): growth, plateau, then an accelerating decline. */
	ATELIERHORSERACING_API void StepRiderCurve(FHRRider& R, int32 AgeMonths, int32 Rides);
	ATELIERHORSERACING_API TArray<const FHRRider*> StableRiders(const FHRWorldState& S, const FString& StableId);
	/** The rider of a horse on this race day, or nullptr (a hired jockey). */
	ATELIERHORSERACING_API const FHRRider* RiderOf(const FHRWorldState& S, const FString& HorseId);
	/** Stage bonus (stage 0..3) a rider gives on this race: the stat bonus within -2..+2 plus any legend specialty. */
	ATELIERHORSERACING_API int32 RiderBonus(const FHRRider& R, int32 Stage, int32 Distance, int32 T);
	/** English title of a legend ("" for an ordinary rider). */
	ATELIERHORSERACING_API FString LegendTitle(const FString& Legend);
	/** The riders of a new world: three per stable. */
	ATELIERHORSERACING_API void CreateRiders(FHRWorldState& S);
	/** Signs academy riders (17 to 19 years old) until the stable has RidersPerStable; returns how many. */
	ATELIERHORSERACING_API int32 SignAcademyRiders(FHRWorldState& S, const FString& StableId, int32 LegendPerMille = RiderLegendPerMille);
	/** Race day: each stable puts its best riders on its best entries (an owner who rides takes none). */
	ATELIERHORSERACING_API void AssignRiders(FHRWorldState& S, const TArray<FHRRunner>& Entries);
	/** Day close: rides and wins, career curves (once per rider month), retirements, legend cooldowns. */
	ATELIERHORSERACING_API void AdvanceRiders(FHRWorldState& S);
	/** Computer stables' rider decisions: signings, academy promotions, the transfer list and transfers. */
	ATELIERHORSERACING_API void ManageRiders(FHRWorldState& S);
	ATELIERHORSERACING_API int32 RiderWages(const FHRWorldState& S, const FString& StableId);

	// ---------------------------------------------------------------- players and their stables (HROwner.cpp)
	/** Coins a player receives at each day's close. */
	inline constexpr int32 PlayerDailyIncome = 5;
	inline constexpr int32 StablePrice = 300;
	/** Market recruits offered to each owner every day: a young prospect and an all-round adult. */
	inline constexpr int32 ProspectPrice = 65;
	inline constexpr int32 AdultPrice = 80;
	/** Adds a player (or returns the existing one). Players start with FHRPlayer's default coins. */
	ATELIERHORSERACING_API FHRPlayer& AddPlayer(FHRWorldState& S, const FString& PlayerId, const FString& Name);
	ATELIERHORSERACING_API FHRPlayer* FindPlayer(FHRWorldState& S, const FString& PlayerId);
	ATELIERHORSERACING_API const FHRPlayer* FindPlayer(const FHRWorldState& S, const FString& PlayerId);
	/** The stable a player owns, or nullptr. */
	ATELIERHORSERACING_API FHRStable* PlayerStable(FHRWorldState& S, const FString& PlayerId);
	ATELIERHORSERACING_API const FHRStable* PlayerStable(const FHRWorldState& S, const FString& PlayerId);
	/** Buys a stable listed for sale (StablePrice), with its riders or without (they become free agents), plus one
	 * starter horse. One stable per player. */
	ATELIERHORSERACING_API FString BuyStable(FHRWorldState& S, const FString& PlayerId, const FString& StableId, bool bKeepRiders);
	/** Founds a new stable (StablePrice) with three academy riders and one starter horse, so any number of players can
	 * own one. Its id is "player:<player id>". */
	ATELIERHORSERACING_API FString FoundStable(FHRWorldState& S, const FString& PlayerId, const FString& Name, const FString& Color);
	/** A listed horse (another stable's) or a market recruit ("market:prospect" / "market:adult"). */
	ATELIERHORSERACING_API FString BuyHorse(FHRWorldState& S, const FString& PlayerId, const FString& Key);
	/** The day's market recruits for this player (generated from the seed, not stored until bought). */
	ATELIERHORSERACING_API TArray<FHRHorse> MarketRecruits(const FHRWorldState& S, const FString& PlayerId);
	/** Puts one of the player's horses up for sale at its value (any stable may buy it), or withdraws it. */
	ATELIERHORSERACING_API FString ListHorse(FHRWorldState& S, const FString& PlayerId, const FString& HorseId, bool bList);
	ATELIERHORSERACING_API void SetResting(FHRWorldState& S, const FString& PlayerId, const FString& HorseId, bool bResting);
	/** Signs a free agent (no fee) or buys a listed rider (its price to the seller). At most RidersPerStable. */
	ATELIERHORSERACING_API FString HireRider(FHRWorldState& S, const FString& PlayerId, const FString& RiderId);
	/** Releases a rider (no fee): a free agent. */
	ATELIERHORSERACING_API FString ReleaseRider(FHRWorldState& S, const FString& PlayerId, const FString& RiderId);
	/** Puts one of the player's riders on the transfer list (Price 0: its value), or takes it off (bList false). */
	ATELIERHORSERACING_API FString ListRider(FHRWorldState& S, const FString& PlayerId, const FString& RiderId, bool bList, int32 Price = 0);
	ATELIERHORSERACING_API void SetPlayerRides(FHRWorldState& S, const FString& PlayerId, bool bRides);
	/** The runner this player rides in a race, nullptr if none. */
	ATELIERHORSERACING_API const FHRRunner* PlayerRunner(const FHRRace& Race, const FString& PlayerId);
	/** Day close for a player's stable: winnings in, running costs and wages out; riders who cannot be paid leave (no
	 * debt). */
	ATELIERHORSERACING_API void CloseOwnerDay(FHRWorldState& S, FHRStable& St, int32 Gross);
	/** Money a sale or a prize put on a player's stable goes to the player's coins. */
	ATELIERHORSERACING_API void SweepOwnerCoins(FHRWorldState& S);

	// The player as a rider. A beginner rides at 450 on every stage (an average ride, bonus 0).
	inline constexpr int32 PlayerStartSkill = 450;
	inline constexpr int32 PlayerMaxSkill = 900;
	inline constexpr int32 PlayerRaceXp = 6;
	ATELIERHORSERACING_API int32 PlayerRiderSkill(const FHRWorldState& S, const FString& PlayerId, int32 Stage);
	/** The stage bonus of the player's ride (-2..+2), from their skill like any rider's. */
	ATELIERHORSERACING_API int32 PlayerRiderBonus(const FHRWorldState& S, const FString& PlayerId, int32 Stage);
	/** Stage bonus of whoever rides this runner (a player, the stable's rider or a hired jockey: 0). */
	ATELIERHORSERACING_API int32 RunnerRiderBonus(const FHRWorldState& S, const FHRRunner& R, int32 Stage, int32 Distance);
	/** After a race the player rode: a little experience on every stage. */
	ATELIERHORSERACING_API void PlayerRode(FHRWorldState& S, const FString& PlayerId);

	// Training sessions. Each horse may train once a day, TrainingSlots sessions a day in all, TrainingCost coins each.
	// The exercise (a short mini-game in the game) gives a grade -2..+2 that sets the gain; sessions an owner does not
	// play are done by the staff at the day's close with an average grade.
	ATELIERHORSERACING_API int32 TrainingGain(int32 Grade);
	ATELIERHORSERACING_API FString TrainingRefusal(const FHRWorldState& S, const FString& PlayerId, const FString& HorseId, int32 Ability);
	ATELIERHORSERACING_API int32 TrainingSessionsLeft(const FHRWorldState& S, const FString& PlayerId);
	/** Plays a session: the horse's ability progresses by TrainingGain(Grade); the player, riding it, gains rider skill
	 * on the matching race stage. Out: the progress gained (hundredths of a point). */
	ATELIERHORSERACING_API FString TrainHorse(FHRWorldState& S, const FString& PlayerId, const FString& HorseId, int32 Ability, int32 Grade, int32* OutGain = nullptr);
	/** Day close: the staff plays the sessions every owner left (grade 0). */
	ATELIERHORSERACING_API void StaffTraining(FHRWorldState& S);

	// Breeding for a player: one parent from the player's stable, the other theirs or another stable's (its breeding fee
	// goes to its owner). BreedingServiceCost plus the fee; the foal is born GestationDays later.
	ATELIERHORSERACING_API FString BreedingRefusal(const FHRWorldState& S, const FString& PlayerId, const FHRHorse& Mine, const FHRHorse& Partner);
	ATELIERHORSERACING_API int32 BreedingCost(const FHRWorldState& S, const FString& PlayerId, const FHRHorse& Partner);
	ATELIERHORSERACING_API FString BreedPlayer(FHRWorldState& S, const FString& PlayerId, const FString& MineId, const FString& PartnerId, const FString& FoalName);
	/** Why a horse cannot breed now ("" if it can). */
	ATELIERHORSERACING_API FString BreedingAvailability(const FHRWorldState& S, const FHRHorse& H);
	struct FFoalOutlook
	{
		/** Per ability: the likely ceiling range of the foal (10th, 50th and 90th percentile of sampled foals). */
		int32 Low[4] = {0, 0, 0, 0};
		int32 Mid[4] = {0, 0, 0, 0};
		int32 High[4] = {0, 0, 0, 0};
	};
	/** An estimate of the foal's potential from the parents' genes (sampled; nothing is drawn for real). */
	ATELIERHORSERACING_API FFoalOutlook FoalOutlook(const FHRWorldState& S, const FHRHorse& Mare, const FHRHorse& Sire, int32 Samples = 32);

	// ---------------------------------------------------------------- betting (HRBetting.cpp): win bets only
	struct FBetLimits
	{
		static constexpr int32 MinStake = 1;
		static constexpr int32 MaxStake = 10;
		static constexpr int32 PerDay = 30;
		static constexpr int32 TicketsPerRace = 3;
	};
	/** The pool's take, the lowest odds paid, and the share of the crowd betting at random (it keeps long shots finite). */
	inline constexpr double Take = 0.15;
	inline constexpr double MinRapport = 1.05;
	inline constexpr double Longshot = 0.10;
	/** The crowd's chance that this horse wins, from the frozen public replays. */
	ATELIERHORSERACING_API double WinChance(const FHRRace& Race, const FString& HorseId);
	/** Odds for one coin: the crowd's pool and every player's ticket on this race (plus ExtraStake on this horse). */
	ATELIERHORSERACING_API double Rapport(const FHRWorldState& S, const FHRRace& Race, const FString& HorseId, int32 ExtraStake = 0);
	/** Coins a player has staked today. */
	ATELIERHORSERACING_API int32 DayStake(const FHRWorldState& S, const FString& PlayerId);
	ATELIERHORSERACING_API FString BetRefusal(const FHRWorldState& S, const FString& PlayerId, const FHRRace& Race, const FString& HorseId, int32 Stake);
	ATELIERHORSERACING_API FString PlaceBet(FHRWorldState& S, const FString& PlayerId, const FString& RaceKey, const FString& HorseId, int32 Stake);
	/** Pays or refunds every open ticket on a race that has been run (or not run). */
	ATELIERHORSERACING_API void SettleRace(FHRWorldState& S, const FHRRace& Race);
}
