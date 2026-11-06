#pragma once

#include "CoreMinimal.h"

/** Fixed content shared by the rules: the season's race days, traits, the default stables and the name vocabulary. */
namespace HRContent
{
	struct FEvent
	{
		const TCHAR* Id;
		const TCHAR* Name;
		int32 Distance;
		/** 0 firm, 1 soft, 2 sand. */
		int32 Surface;
		/** 0 straight, 1 broad, 2 technical. */
		int32 Shape;
		/** Where it is run; the game maps the id to a racecourse. */
		const TCHAR* Venue;
		bool bGrandPrix;
		/** Grand Prix only: heat and final distances, obstacles. */
		int32 EliminatoryDistance;
		int32 FinalDistance;
		bool bObstacles;
		/** Runs per race: 2 means every horse runs twice and its best time counts. */
		int32 Runs;
		/** Laps of the course (presentation only: the distance is the whole race). */
		int32 Laps;
		/** Every contender runs a timed sprint ("qualif"); the best SprintFinalists times go to the final; a tie at the
		 * cut is settled by "barrage" sprints between the tied horses. */
		bool bSprintQualifiers;
	};

	inline constexpr int32 SprintFinalists = 4;

	/** The twelve race days of a season; every third one is a Grand Prix. */
	ATELIERHORSERACING_API const TArray<FEvent>& Events();
	ATELIERHORSERACING_API const FEvent& EventForT(int32 T);
	ATELIERHORSERACING_API const FEvent* FindEvent(const FString& Id);

	/** Signature traits: "solar", "breath", "gate", "quiet", "clear", "wise" (HRRace.cpp says what each one does). */
	ATELIERHORSERACING_API const TArray<FString>& Traits();

	/** A race's name in news lines ("heat 2", "final", "race 1"). */
	ATELIERHORSERACING_API FString RoundName(const FString& Round, int32 Group);
	/** "season 3, day 5". */
	ATELIERHORSERACING_API FString FormatDay(int32 T);
	/** A horse's age in horse years and months ("3 years 2 months"), from a number of race days. */
	ATELIERHORSERACING_API FString AgeLabel(int32 Days);

	/** The default stables of a new world (slot 0 starts for sale). */
	struct FStableDef
	{
		const TCHAR* Id;
		const TCHAR* Name;
		const TCHAR* Color;
		int32 Emblem;
		const TCHAR* Motto;
	};
	ATELIERHORSERACING_API const TArray<FStableDef>& StableDefs();

	/** Unique, deterministic horse names (the reference vocabulary). */
	ATELIERHORSERACING_API const TArray<FString>& HorseNamePool();
	ATELIERHORSERACING_API FString GeneratedHorseName(const FString& Seed);
	/** Accent-folded lower case: two names that normalise alike are the same name. */
	ATELIERHORSERACING_API FString NormalizeName(const FString& Name);
}
