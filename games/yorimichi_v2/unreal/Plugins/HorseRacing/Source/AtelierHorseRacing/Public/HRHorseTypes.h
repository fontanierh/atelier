#pragma once

#include "CoreMinimal.h"
#include "HRHorseTypes.generated.h"

/**
 * Horse data for the racing rules. These reflected structures are plain values, not admitted saves or network requests.
 * Persistence and gameplay admission must validate their identities, ranges and collection shapes before rule operations.
 *
 * Time: T counts race days since the world's day 0. A race day lasts two real hours and a season of twelve race days is
 * one in-game year (24 real hours). Horses and riders age on a slower clock: one horse year is 84 race days, one real
 * week (HRClock.h). Fields named ...T are race days.
 */

/** Ability order everywhere: 0 start (acceleration), 1 speed, 2 endurance, 3 composure. */
namespace HRAbility
{
    constexpr int32 Acceleration = 0;
    constexpr int32 Speed = 1;
    constexpr int32 Endurance = 2;
    constexpr int32 Composure = 3;
    constexpr int32 Count = 4;
}

/** One gene: the allele from the mother and the one from the father (each 0..4 unless stated). */
USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRGenePair
{
    GENERATED_BODY()

    UPROPERTY() int32 A = 0;
    UPROPERTY() int32 B = 0;

    FHRGenePair() = default;
    FHRGenePair(int32 InA, int32 InB) : A(InA), B(InB) {}
    int64 Sum() const { return int64(A) + int64(B); }
    int32 operator[](int32 I) const
    {
        if (I != 0 && I != 1) UE_LOG(LogTemp, Fatal, TEXT("HorseRacing gene pair index must be 0 or 1"));
        return I == 0 ? A : B;
    }
};

/** Tissue zone: 0 front tendons, 1 stifles, 2 back, 3 hind tendons. Fixed point values (x10000). */
USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRZone
{
    GENERATED_BODY()

    UPROPERTY() int32 Structure = 0;
    UPROPERTY() int32 Acute = 0;
    UPROPERTY() int32 Recovery = 0;
    UPROPERTY() int32 Adaptation = 0;
    UPROPERTY() int32 InflammationGene = 0;
    UPROPERTY() int32 Load = 0;
    UPROPERTY() int32 Tolerance = 0;
    UPROPERTY() int32 Inflammation = 0;
    UPROPERTY() int32 Scars = 0;
};

USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRInjury
{
    GENERATED_BODY()

    UPROPERTY() bool bActive = false;
    /** "soreness", "light", "moderate", "serious" or "career-ending". */
    UPROPERTY() FString Severity;
    /** "progressive", "extended" or empty (no plan yet). */
    UPROPERTY() FString Plan;
    /** Race days rested since the injury. */
    UPROPERTY() int32 Benches = 0;
    UPROPERTY() int32 Minimum = 0;
    UPROPERTY() int32 SinceT = 0;
};

/** Visible features decoded from the eight simple visual genes (a card silhouette); the 3D look is HRVisualGenome.h. */
USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRAppearance
{
    GENERATED_BODY()

    UPROPERTY() int32 Family = 0;
    UPROPERTY() FString Coat;
    UPROPERTY() FString Mane;
    UPROPERTY() int32 Marking = 0;
    UPROPERTY() float Height = 0.5f;
    UPROPERTY() float Bulk = 0.5f;
    UPROPERTY() float LegLength = 0.5f;
    UPROPERTY() float Head = 0.5f;
    UPROPERTY() float Hair = 0.5f;
};

/** One line of a horse's record. */
USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRCareerLine
{
    GENERATED_BODY()

    UPROPERTY() int32 T = 0;
    UPROPERTY() FString EventName;
    /** "village", "semi", "qualif", "barrage" or "final". */
    UPROPERTY() FString Round;
    UPROPERTY() int32 Place = 0;
    UPROPERTY() int32 Runners = 0;
    UPROPERTY() int32 Gross = 0;
    UPROPERTY() FString StableId;
    /** The race of that day ("village:1"): identifies head-to-heads. */
    UPROPERTY() FString RaceKey;
};

USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRHorse
{
    GENERATED_BODY()

    UPROPERTY() FString Id;
    UPROPERTY() FString Name;
    UPROPERTY() FString Seed;
    /** Stable id, or "market" for a horse on offer. */
    UPROPERTY() FString OwnerId;
    UPROPERTY() bool bMare = false;
    UPROPERTY() int32 BirthT = 0;
    /** First race day it may race: one horse year after its birth. */
    UPROPERTY() int32 ReadyT = 0;
    UPROPERTY() int32 ScheduledRetirementT = 0;
    /** -1 while racing. */
    UPROPERTY() int32 RetiredT = -1;
    /** -1 until retirement; the day it goes to the archives (HRClock::ArchiveDays after retiring). */
    UPROPERTY() int32 BreedingUntilT = -1;
    UPROPERTY() int32 NextBreedingT = 0;
    /** "active", "pasture", "retired", "archive" or "offer" (market horse not yet bought). */
    UPROPERTY() FString Placement;
    /** "rival", "recruit", "starter", "foal" or "recovery". */
    UPROPERTY() FString Origin;
    UPROPERTY() TArray<FString> Parents;
    UPROPERTY() TMap<FString, FHRGenePair> Genome;
    UPROPERTY() TArray<int32> Abilities;
    UPROPERTY() TArray<int32> Ceilings;
    /** Learning response in percent: 70, 100 or 135. */
    UPROPERTY() TArray<int32> Response;
    UPROPERTY() TArray<int32> Progress;
    /** 0 exhausted .. 3 fresh. */
    UPROPERTY() int32 Condition = 3;
    UPROPERTY() TArray<FHRZone> Zones;
    UPROPERTY() int32 Stress = 0;
    UPROPERTY() FString Trait;
    /** 0 none, 1 or 2 chosen mastery. */
    UPROPERTY() int32 Mastery = 0;
    UPROPERTY() int32 Xp = 0;
    /** 0 firm, 1 soft, 2 sand. */
    UPROPERTY() int32 Favorite = 0;
    UPROPERTY() int32 Difficult = 0;
    UPROPERTY() FHRInjury Injury;
    UPROPERTY() int32 Starts = 0;
    UPROPERTY() int32 Wins = 0;
    UPROPERTY() int32 GpWins = 0;
    UPROPERTY() int32 Podiums = 0;
    UPROPERTY() int32 Earnings = 0;
    UPROPERTY() int32 Generation = 0;
    UPROPERTY() FHRAppearance Appearance;
    UPROPERTY() TArray<FHRCareerLine> Career;
    /** Stables that owned this horse, in order (first = breeder). */
    UPROPERTY() TArray<FString> Owners;

    bool IsRetired() const { return RetiredT >= 0; }
    int64 AbilitySum() const { int64 S = 0; for (int32 V : Abilities) S += V; return S; }
};
