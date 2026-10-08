#pragma once
#include "CoreMinimal.h"

/** Maps capture spacing to the host's fastest recent arrival, for presentation only.
 *  This intentionally includes transit time; it must never adjudicate combat input. */
struct FJapanSkateClock
{
    struct FSample { double At, Offset; };
    TArray<FSample, TInlineAllocator<24>> Samples;
    double SmoothedOffset = 0., LastArrival = -1., LastSender = -1.;
    double Map(double SenderTime, double Now)
    {
        while (!Samples.IsEmpty() && Now - Samples[0].At > 2.) Samples.RemoveAt(0, 1, EAllowShrinking::No);
        const double Delta = Now - SenderTime;
        if (!Samples.IsEmpty() && Now - Samples.Last().At < .1)
            Samples.Last().Offset = FMath::Min(Samples.Last().Offset, Delta);
        else Samples.Add({Now, Delta});
        double Offset = Delta;
        for (const auto& Sample : Samples) Offset = FMath::Min(Offset, Sample.Offset);
        // Changing routes or expiring a minimum cannot jump one new frame across
        // already buffered frames. Sender clocks are monotonic local world time.
        if (LastArrival < 0.) SmoothedOffset = Offset;
        else
        {
            const double Elapsed = FMath::Min(FMath::Max(0., Now - LastArrival), FMath::Max(0., SenderTime - LastSender));
            SmoothedOffset += FMath::Clamp(Offset - SmoothedOffset, -.25 * Elapsed, .25 * Elapsed);
        }
        LastArrival = Now; LastSender = FMath::Max(LastSender, SenderTime);
        // During a route improvement the slewed capture clock can briefly lead
        // arrival. Clamping to this tick would merge every packet in a burst.
        // Playback clamps to its buffer; this clock never adjudicates gameplay.
        return FMath::Max(0., SenderTime + SmoothedOffset);
    }
};

/** The actual observer delay and interpolation selector, shared by every visual
 * stream. No GameState clock enters this path. Each buffer clamps independently. */
struct FJapanSkatePlayout
{
    FJapanSkateClock Clock;
    double Interval = 1./30., Delay = .1, Jitter = 0.;
    double LastPose = -1., LastDecay = -1., LastRender = -1., Requested = -1.;
    struct FSample
    {
        int32 A = 0, B = 0;
        double Time = 0.;
        float Alpha = 1.f;
        bool bBefore = false, bAfter = false;
    };
    static bool CanApplyBodies(const FSample& Sample, double RequestedTime, double A, double B)
    {
        // Never pull the first bail anchors into an earlier rider pose, or blend
        // two separate bails across the gap between their streams.
        return !Sample.bBefore && B - A <= .1 && RequestedTime - B <= .1;
    }
    double Map(double Stamp, double Arrival) { return Clock.Map(Stamp, Arrival); }
    void Decay(double Now)
    {
        if (LastDecay >= 0.) Jitter *= FMath::Exp(-FMath::Max(0., Now - LastDecay));
        LastDecay = Now;
    }
    void ReceivePose(double Stamp, double Arrival, double OfferedInterval)
    {
        Decay(Arrival);
        const double Spacing = LastPose < 0. ? OfferedInterval : FMath::Clamp(Arrival - LastPose, 1./120., 30.);
        Interval = FMath::Max(OfferedInterval, FMath::Lerp(Interval, Spacing, .2));
        Jitter = FMath::Max(Jitter, FMath::Clamp(Arrival - Stamp, 0., .5));
        LastPose = Arrival;
    }
    double Advance(double LocalNow)
    {
        Decay(LocalNow);
        const double Dt = LastRender < 0. ? 0. : FMath::Max(0., LocalNow - LastRender);
        const double Target = FMath::Clamp(Jitter + 1.5 * Interval + .05, .1, 30.);
        Delay += FMath::Clamp(Target - Delay, -.25 * Dt, .25 * Dt);
        LastRender = LocalNow;
        Requested = FMath::Max(Requested, LocalNow - Delay);
        return Requested;
    }
    template<typename T, typename F> static FSample Sample(const TArray<T>& Frames, double RequestedTime, F Stamp)
    {
        check(!Frames.IsEmpty());
        FSample Out;
        Out.bBefore = RequestedTime < Stamp(Frames[0]); Out.bAfter = RequestedTime > Stamp(Frames.Last());
        Out.Time = FMath::Clamp(RequestedTime, double(Stamp(Frames[0])), double(Stamp(Frames.Last())));
        while (Out.A + 2 < Frames.Num() && Stamp(Frames[Out.A + 1]) <= Out.Time) ++Out.A;
        Out.B = FMath::Min(Out.A + 1, Frames.Num() - 1);
        const double A = Stamp(Frames[Out.A]), B = Stamp(Frames[Out.B]);
        Out.Alpha = B > A ? FMath::Clamp(float((Out.Time - A) / (B - A)), 0.f, 1.f) : 1.f;
        return Out;
    }
};
