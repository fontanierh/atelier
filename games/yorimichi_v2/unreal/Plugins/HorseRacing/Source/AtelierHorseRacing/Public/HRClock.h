#pragma once

#include "CoreMinimal.h"

/**
 * The racing world's continuous clock. World seconds are real seconds since the world's day 0 (the host maps them to
 * Unix time with FHRWorldState::EpochUnix). Race day T runs from DayStart(T) for DaySeconds: two real hours. Twelve
 * race days (eight ordinary, four Grand Prix) make a season, one in-game year: 24 real hours. A day's races start in
 * slots spread over its two hours and each is shown running for RaceSeconds after its start.
 *
 * Horses and riders age on a slower clock: one horse year is one real week (LifeYear race days), so a foal is an adult
 * after a week and a career of six to nine horse years lasts six to nine weeks.
 */
namespace HRClock
{
    inline constexpr double DaySeconds = 2.0 * 3600.0;
    inline constexpr int32 DaysPerSeason = 12;
    inline constexpr int32 GrandPrixPerSeason = 4;
    /** Race days per horse (and rider) month: 14 real hours. */
    inline constexpr int32 LifeMonth = 7;
    /** Race days per horse year: 84, one real week. */
    inline constexpr int32 LifeYear = 12 * LifeMonth;
    /** A retired horse goes to the archives two in-game years (48 real hours) after its retirement. */
    inline constexpr int32 ArchiveDays = 2 * DaysPerSeason;

    /** The day's race slots: the first starts FirstRaceSecond into the day, the others are spread over RaceSpan. A day
     * with more races than RaceSlots packs them closer. The last race ends well before the next day. */
    inline constexpr int32 RaceSlots = 6;
    inline constexpr double FirstRaceSecond = 600.0;
    inline constexpr double RaceSpan = 6300.0;
    /** How long a race is shown running after its start (its result is decided at the start). */
    inline constexpr double RaceSeconds = 180.0;

    enum class EHRRacePhase : uint8
    {
        Upcoming,
        Running,
        Finished,
    };

    /** The race day at a world second. */
    ATELIERHORSERACING_API int32 DayAt(double WorldSeconds);
    inline double DayStart(int32 T) { return T * DaySeconds; }
    /** Season number of a day (0-based) and the day's index in its season (0..11). */
    inline int32 SeasonOf(int32 T) { return FMath::FloorToInt(T / (double)DaysPerSeason); }
    inline int32 DayOfSeason(int32 T) { return ((T % DaysPerSeason) + DaysPerSeason) % DaysPerSeason; }
    ATELIERHORSERACING_API bool IsGrandPrixDay(int32 T);

    /** Whole horse (or rider) months from day FromT to day ToT, rounded down. */
    inline int32 LifeMonths(int32 FromT, int32 ToT) { return FMath::FloorToInt((int64(ToT) - int64(FromT)) / double(LifeMonth)); }

    /** Slots of a day whose first round has FirstRoundRaces races: a Grand Prix keeps two more for its barrages and its
     * final. At least RaceSlots. */
    ATELIERHORSERACING_API int32 SlotCount(int32 FirstRoundRaces, bool bGrandPrix);
    /** World second at which slot Slot of day T starts, for a day of Count slots. */
    ATELIERHORSERACING_API double SlotStart(int32 T, int32 Slot, int32 Count = RaceSlots);
    ATELIERHORSERACING_API EHRRacePhase PhaseAt(double StartSeconds, double WorldSeconds);

    /** What the schedule says at one world second. */
    struct FSlot
    {
        int32 T = 0;
        int32 Season = 0;
        int32 DayOfSeason = 0;
        bool bGrandPrix = false;
        /** The race slot in focus: the last one started (running or finished), or the first one before it starts. */
        int32 Slot = 0;
        int32 SlotCount = RaceSlots;
        double Start = 0;
        double End = 0;
        EHRRacePhase Phase = EHRRacePhase::Upcoming;
    };
    /** Nonfatal admission for external time/count values; failure leaves Out unchanged. */
    ATELIERHORSERACING_API bool TryScheduleAt(double WorldSeconds, int32 Count, FSlot& Out);
    /** Internal convenience for validated finite world seconds and nonnegative counts. */
    ATELIERHORSERACING_API FSlot ScheduleAt(double WorldSeconds, int32 Count = RaceSlots);
}
