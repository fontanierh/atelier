#pragma once
#include "CoreMinimal.h"

/** Server-only mapping for already accepted CMC moves. Unlike the skate presentation
 * clock, this subtracts the host-measured one-way transit estimate. The client never
 * supplies a world-clock delta, ping, jitter or an adjudication wait. */
struct FJapanDefenceClock
{
    static constexpr double MaximumCompensation = .2;
    static constexpr double SampleWindow = 10.;
    struct FSample { double Arrival = 0., Offset = 0., RTT = 0.; };
    TArray<FSample, TInlineAllocator<104>> Samples;
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
    bool MapAccepted(double Timestamp, double Now, double HostRTT, double HostJitter, double& Mapped,
        double AcceptedDt = 0., double HostDt = 0.)
    {
        if (!FMath::IsFinite(Timestamp) || !FMath::IsFinite(Now) || !FMath::IsFinite(HostRTT) ||
            !FMath::IsFinite(HostJitter) || !FMath::IsFinite(AcceptedDt) || !FMath::IsFinite(HostDt) ||
            AcceptedDt < 0. || HostDt < 0. || Timestamp < 0. || Now < 0. || HostRTT < 0. || HostJitter < 0.) return false;
        // UE has already validated its periodic CMC timestamp reset before this call.
        // Existing contacts/history use host time and survive this clock generation.
        if (LastTimestamp >= 0. && Timestamp < LastTimestamp - 1.) { Samples.Reset(); ++Generation; }
        else if (Timestamp <= LastTimestamp) return false;
        while (!Samples.IsEmpty() && Now - Samples[0].Arrival > SampleWindow) Samples.RemoveAt(0, 1, EAllowShrinking::No);
        const double Delta = Now - Timestamp;
        if (!Samples.IsEmpty() && Now - Samples.Last().Arrival < .1)
        {
            Samples.Last().Offset = FMath::Min(Samples.Last().Offset, Delta);
            if (HostRTT > 0.) Samples.Last().RTT = Samples.Last().RTT > 0. ? FMath::Min(Samples.Last().RTT, HostRTT) : HostRTT;
        }
        else Samples.Add({Now, Delta, HostRTT});
        double Offset = Delta, MinimumRTT = TNumericLimits<double>::Max();
        for (const auto& Sample : Samples)
        {
            Offset = FMath::Min(Offset, Sample.Offset);
            if (Sample.RTT > 0.) MinimumRTT = FMath::Min(MinimumRTT, Sample.RTT);
        }
        // RawPing is the maximum ACK RTT in a frame. A single delayed ACK must
        // not backdate every defensive press. Retain the fastest measured path
        // over the SAME bounded window as the arrival offset; zero is unknown.
        OneWay = MinimumRTT == TNumericLimits<double>::Max() ? 0. : FMath::Clamp(MinimumRTT * .5, 0., .15);
        // Edges include their first accepted movement step. The original budget
        // covers a 60 Hz host; only its additional measured frame time is new
        // allowance. The same estimate dates input and bounds contact waiting.
        const double Step = FMath::Clamp(AcceptedDt, 0., .1);
        const double SlowHost = FMath::Max(0., FMath::Min(HostDt, .1) - 1. / 60.);
        const double Base = FMath::Clamp(OneWay + FMath::Min(HostJitter, .05) + .03 + Step, .03, .15);
        MaximumRewind = FMath::Min(MaximumCompensation, Base + SlowHost);
        Wait = MaximumRewind;
        Mapped = FMath::Clamp(Timestamp + Offset - OneWay, FMath::Max(0., Now - .5), Now);
        // Updated RTT/minimum samples cannot move accepted history backwards. Short
        // plateaus replace an equal-time sample; no new future interval is invented.
        if (LastMapped >= 0.) Mapped = FMath::Max(LastMapped, Mapped);
        if (Mapped > Now) return false;
        LastTimestamp = Timestamp; LastMapped = Mapped;
        return true;
    }
};
