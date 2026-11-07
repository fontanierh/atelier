#include "HRClock.h"

namespace HRClockPrivate
{
    bool ValidTime(double Seconds)
    {
        return FMath::IsFinite(Seconds) && FMath::FloorToDouble(Seconds / HRClock::DaySeconds) >= double(MIN_int32)
            && FMath::FloorToDouble(Seconds / HRClock::DaySeconds) <= double(MAX_int32);
    }
}

int32 HRClock::DayAt(double WorldSeconds)
{
    if (!HRClockPrivate::ValidTime(WorldSeconds))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing clock requires finite world seconds with an int32 day"));
    return FMath::FloorToInt(WorldSeconds / DaySeconds);
}

bool HRClock::IsGrandPrixDay(int32 T)
{
    // The calendar owns this rule; authored event names/content do not own the clock.
    return DayOfSeason(T) % 3 == 2;
}

int32 HRClock::SlotCount(int32 FirstRoundRaces, bool bGrandPrix)
{
    if (FirstRoundRaces < 0 || FirstRoundRaces > MAX_int32 - (bGrandPrix ? 2 : 0))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing first-round count is out of range"));
    return FMath::Max(RaceSlots, FirstRoundRaces + (bGrandPrix ? 2 : 0));
}

double HRClock::SlotStart(int32 T, int32 Slot, int32 Count)
{
    if (Count < 0 || Slot < 0 || Slot >= FMath::Max(RaceSlots, Count))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing slot is outside its schedule"));
    return DayStart(T) + FirstRaceSecond + double(Slot) * RaceSpan / FMath::Max(RaceSlots, Count);
}

HRClock::EHRRacePhase HRClock::PhaseAt(double StartSeconds, double WorldSeconds)
{
    if (!FMath::IsFinite(StartSeconds) || !FMath::IsFinite(WorldSeconds))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing race phase requires finite times"));
    if (WorldSeconds < StartSeconds) return EHRRacePhase::Upcoming;
    return WorldSeconds < StartSeconds + RaceSeconds ? EHRRacePhase::Running : EHRRacePhase::Finished;
}

bool HRClock::TryScheduleAt(double WorldSeconds, int32 Count, FSlot& Out)
{
    if (!HRClockPrivate::ValidTime(WorldSeconds) || Count < 0) return false;
    FSlot At;
    At.T = DayAt(WorldSeconds);
    At.Season = SeasonOf(At.T);
    At.DayOfSeason = DayOfSeason(At.T);
    At.bGrandPrix = IsGrandPrixDay(At.T);
    At.SlotCount = FMath::Max(RaceSlots, Count);
    // Upper bound by the actual computed slot times, not a rounded division.
    // At most 31 iterations even for an int32-sized schedule.
    int32 Low = 0, High = At.SlotCount;
    while (Low < High)
    {
        const int32 Middle = Low + (High - Low) / 2;
        if (SlotStart(At.T, Middle, At.SlotCount) <= WorldSeconds) Low = Middle + 1;
        else High = Middle;
    }
    At.Slot = FMath::Max(0, Low - 1);
    At.Start = SlotStart(At.T, At.Slot, At.SlotCount);
    At.End = At.Start + RaceSeconds;
    At.Phase = PhaseAt(At.Start, WorldSeconds);
    Out = At;
    return true;
}

HRClock::FSlot HRClock::ScheduleAt(double WorldSeconds, int32 Count)
{
    FSlot At;
    if (!TryScheduleAt(WorldSeconds, Count, At))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing schedule requires valid time/count; admit external values with TryScheduleAt"));
    return At;
}
