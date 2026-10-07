#pragma once
#include "CoreMinimal.h"

/** Maps capture spacing to the host's fastest recent arrival, for presentation only.
 *  This intentionally includes transit time; it must never adjudicate combat input. */
struct FJapanSkateClock
{
    struct FSample { double At, Offset; };
    TArray<FSample, TInlineAllocator<24>> Samples;
    double Map(double SenderTime, double Now)
    {
        while (!Samples.IsEmpty() && Now - Samples[0].At > 2.) Samples.RemoveAt(0, 1, EAllowShrinking::No);
        const double Delta = Now - SenderTime;
        if (!Samples.IsEmpty() && Now - Samples.Last().At < .1)
            Samples.Last().Offset = FMath::Min(Samples.Last().Offset, Delta);
        else Samples.Add({Now, Delta});
        double Offset = Delta;
        for (const auto& Sample : Samples) Offset = FMath::Min(Offset, Sample.Offset);
        return FMath::Clamp(SenderTime + Offset, FMath::Max(0., Now - .5), Now);
    }
};
