#pragma once

#include "CoreMinimal.h"
#include "HRTypes.h"

/**
 * The whole racing world as JSON: what a host saves to disk. The round trip
 * is lossless, so a reloaded world plays on exactly as the original would.
 *
 * Loading admits a world before it replaces anything: the schema and rules versions, the required fields, unique ids
 * (no repeated JSON key, unique stables, races and tickets), every reference (owners, parents, riders, entrants, bets),
 * numeric ranges and collection sizes. Malformed text is refused with a reason and the destination is left untouched.
 */
namespace HRSave
{
	inline constexpr int32 SchemaVersion = 1;

	/** Admission bounds: far above any world the rules make, low enough that indexing and arithmetic stay safe. */
	inline constexpr int32 MaxJsonChars = 64 * 1024 * 1024;
	inline constexpr int32 MaxDay = 1000000;
	inline constexpr int32 MaxStables = 256;
	inline constexpr int32 MaxHorses = 200000;
	inline constexpr int32 MaxRiders = 200000;
	inline constexpr int32 MaxPlayers = 10000;
	inline constexpr int32 MaxRaces = 64;
	inline constexpr int32 MaxEntries = 64;
	inline constexpr int32 MaxTickets = 500000;
	inline constexpr int32 MaxListings = 10000;
	inline constexpr int32 MaxPregnancies = 10000;
	inline constexpr int32 MaxNews = 1000;
	inline constexpr int32 MaxCareer = 10000;
	inline constexpr int32 MaxGenes = 256;
	inline constexpr int32 MaxList = 1024;
	inline constexpr int32 MaxIdChars = 256;
	inline constexpr int32 MaxTextChars = 4096;
	inline constexpr int32 MaxAbility = 100;
	inline constexpr int32 MaxSkill = 2000;

	/** Compact JSON of the world (one line). */
	ATELIERHORSERACING_API FString ToJson(const FHRWorldState& S);
	/** Parses and admits a world written by ToJson. False (Out untouched, Error the reason) when the text is not an
	 * admissible world of these rules. */
	ATELIERHORSERACING_API bool FromJson(const FString& Json, FHRWorldState& Out, FString& Error);
	ATELIERHORSERACING_API bool FromJson(const FString& Json, FHRWorldState& Out);
	/** Why a parsed world is not admissible ("" when it is): versions, ids, references, ranges and sizes. */
	ATELIERHORSERACING_API FString Validate(const FHRWorldState& S);
}
