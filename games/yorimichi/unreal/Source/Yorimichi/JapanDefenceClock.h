#pragma once
#include "CoreMinimal.h"

/** Server-only mapping for already accepted CMC moves. Unlike the skate presentation
 * clock, this subtracts the host-measured one-way transit estimate. The client never
 * supplies a world-clock delta, ping, jitter or an adjudication wait. */
struct FJapanDefenceClock
{
    struct FSample { double Arrival = 0., Offset = 0.; };
    TArray<FSample, TInlineAllocator<24>> Samples;
    double LastTimestamp = -1., LastMapped = -1.;
    double OneWay = 0., Wait = .03, MaximumRewind = .03;
    uint32 Generation = 0;

    bool OriginalPress(uint16 AgeMilliseconds, double Arrival, double& Press) const
    {
        if (AgeMilliseconds > 500 || LastMapped < 0. || !FMath::IsFinite(Arrival)) return false;
        Press = LastMapped - AgeMilliseconds * .001;
        // The 500 ms journal wire range permits retransmitted live input. It is NOT
        // permission to defend that far in the past. Only measured host transit is.
        return Press >= Arrival - MaximumRewind && Press <= Arrival;
    }

    void Reset() { *this = FJapanDefenceClock(); }
    bool MapAccepted(double Timestamp, double Now, double HostRTT, double HostJitter, double& Mapped, double AcceptedDt = 0.)
    {
        if (!FMath::IsFinite(Timestamp) || !FMath::IsFinite(Now) || !FMath::IsFinite(HostRTT) ||
            !FMath::IsFinite(HostJitter) || !FMath::IsFinite(AcceptedDt) || AcceptedDt < 0. || Timestamp < 0. || Now < 0. || HostRTT < 0. || HostJitter < 0.) return false;
        // UE has already validated its periodic CMC timestamp reset before this call.
        // Existing contacts/history use host time and survive this clock generation.
        if (LastTimestamp >= 0. && Timestamp < LastTimestamp - 1.) { Samples.Reset(); ++Generation; }
        else if (Timestamp <= LastTimestamp) return false;
        OneWay = FMath::Clamp(HostRTT * .5, 0., .15);
        // Edges are sampled at the start of the accepted movement step. Their
        // wire age includes that step, independently of transport delay/jitter.
        const double Step = FMath::Clamp(AcceptedDt, 0., .1);
        MaximumRewind = FMath::Clamp(OneWay + FMath::Min(HostJitter, .05) + .03 + Step, .03, .15);
        Wait = MaximumRewind;
        while (!Samples.IsEmpty() && Now - Samples[0].Arrival > 2.) Samples.RemoveAt(0, 1, EAllowShrinking::No);
        const double Delta = Now - Timestamp;
        if (!Samples.IsEmpty() && Now - Samples.Last().Arrival < .1)
            Samples.Last().Offset = FMath::Min(Samples.Last().Offset, Delta);
        else Samples.Add({Now, Delta});
        double Offset = Delta;
        for (const auto& Sample : Samples) Offset = FMath::Min(Offset, Sample.Offset);
        Mapped = FMath::Clamp(Timestamp + Offset - OneWay, FMath::Max(0., Now - .5), Now);
        // Updated RTT/minimum samples cannot move accepted history backwards. Short
        // plateaus replace an equal-time sample; no new future interval is invented.
        if (LastMapped >= 0.) Mapped = FMath::Max(LastMapped, Mapped);
        if (Mapped > Now) return false;
        LastTimestamp = Timestamp; LastMapped = Mapped;
        return true;
    }
};
