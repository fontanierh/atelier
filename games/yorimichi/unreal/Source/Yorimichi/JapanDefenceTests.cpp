#include "JapanDefenceTimeline.h"
#include "JapanDefenceClock.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanDefenceTimelineTest, "Yorimichi.Network.DefenceTimeline",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FJapanDefenceTimelineTest::RunTest(const FString&)
{
    FJapanDefenceClock Clock;
    double Mapped = 0.;
    TestTrue(TEXT("Accepted CMC time maps using a host-only transit estimate"), Clock.MapAccepted(1., 10.06, .12, .015, Mapped));
    TestTrue(TEXT("Combat mapping removes, rather than adds, inbound transit"), FMath::IsNearlyEqual(Mapped, 10., .00001));
    TestTrue(TEXT("The wait covers one-way transit plus measured jitter and margin"), FMath::IsNearlyEqual(Clock.Wait, .105, .00001));
    TestTrue(TEXT("Packet jitter is not added to the original press time"), Clock.MapAccepted(1.03, 10.12, .12, .015, Mapped));
    TestTrue(TEXT("Original input spacing survives a jittered arrival"), FMath::IsNearlyEqual(Mapped, 10.03, .00001));
    TestFalse(TEXT("Duplicate accepted timestamps cannot remap defence history"), Clock.MapAccepted(1.03, 10.13, .12, .015, Mapped));
    Clock.Reset();
    TestTrue(TEXT("Excessive measured ping still has a bounded result wait"), Clock.MapAccepted(1., 20., 1., .3, Mapped));
    TestTrue(TEXT("A bad connection cannot delay contacts indefinitely"), Clock.Wait <= .15 && Clock.OneWay <= .15);
    double Press = 0.;
    Clock.Reset(); Clock.MapAccepted(1., 10.06, .12, .015, Mapped);
    TestTrue(TEXT("A recent journal edge fits the measured transit allowance"), Clock.OriginalPress(10, 10.06, Press));
    TestFalse(TEXT("A hindsight press cannot borrow the full journal history"), Clock.OriginalPress(200, 10.06, Press));
    TestFalse(TEXT("An expired wire marker can never create defence"), Clock.OriginalPress(511, 10.06, Press));
    for (uint16 StepMs : {uint16(33), uint16(50), uint16(67)})
    {
        Clock.Reset();
        TestTrue(TEXT("Accepted movement step maps at low frame rates"),
            Clock.MapAccepted(1., 10.001, .002, .002, Mapped, StepMs * .001));
        TestTrue(TEXT("Original press includes its accepted movement step on a LAN"),
            Clock.OriginalPress(StepMs, 10.001, Press));
        TestFalse(TEXT("An old press cannot exceed the step plus transport allowance"),
            Clock.OriginalPress(StepMs + 40, 10.001, Press));
        TestTrue(TEXT("The wait still matches the entire accepted rewind"), Clock.Wait == Clock.MaximumRewind && Clock.Wait <= .15);
    }
    // Recorded 20 Hz host / 30 Hz guest, 60 ms delay, 15 ms variance, 2% loss.
    // The fastest ACK was over eight seconds before the press: a two-second
    // minimum misses it and leaves the jump less than 1 ms inside the new bound.
    Clock.Reset();
    Clock.MapAccepted(.966895, 15.135253, .148917, .023806, Mapped, .033339, .05);
    Clock.MapAccepted(7.536004, 21.686925, .199059, .025808, Mapped, .033340, .05);
    const double Recorded[][4] = {
        {9.203249, 23.387701, .249000, .022729},
        {9.236588, 23.437701, .249043, .022246},
    };
    for (const auto& R : Recorded)
    {
        TestTrue(TEXT("Recorded delayed-ACK movement maps"), Clock.MapAccepted(R[0], R[1], R[2], R[3], Mapped, .03334, .05));
        TestTrue(TEXT("Recorded guard and jump keep the measured transit floor"), FMath::IsNearlyEqual(Clock.OneWay, .0744585, .000001));
        TestTrue(TEXT("Both recorded honest presses are accepted"), Clock.OriginalPress(33, R[1], Press));
        TestTrue(TEXT("Recorded presses have at least 10 ms timing margin"), Press - (R[1] - Clock.MaximumRewind) >= .01);
        const uint16 TooOld = uint16(FMath::CeilToInt((Clock.MaximumRewind - (R[1] - Mapped)) * 1000.) + 1);
        TestFalse(TEXT("An edge beyond the measured allowance plus 1 ms is rejected"), Clock.OriginalPress(TooOld, R[1], Press));
    }
    const double WorstArrival = 9.269922 + 14.150921 + .0674;
    Clock.MapAccepted(9.269922, WorstArrival, .249043, .023, Mapped, .03334, .05);
    TestTrue(TEXT("The observed worst 67.4 ms arrival spread plus a guest step fits"), Clock.OriginalPress(33, WorstArrival, Press));

    FJapanDefenceClock Normal = Clock, Spike = Clock;
    double NormalTime = 0., SpikeTime = 0.;
    Normal.MapAccepted(9.31, 23.52, .199, .023, NormalTime, .03334, .05);
    Spike.MapAccepted(9.31, 23.52, .9, .023, SpikeTime, .03334, .05);
    TestTrue(TEXT("One delayed ACK cannot backdate the mapped movement"), NormalTime == SpikeTime);
    TestTrue(TEXT("One delayed ACK cannot widen contact waiting"), Normal.MaximumRewind == Spike.MaximumRewind);
    for (double HostDt : {1. / 60., .05, .1, 2.})
    {
        Clock.Reset(); Clock.MapAccepted(1., 10., .3, .05, Mapped, .03334, HostDt);
        const double Expected = FMath::Min(.2, .15 + FMath::Max(0., FMath::Min(HostDt, .1) - 1. / 60.));
        TestTrue(TEXT("Only host frame time beyond 60 Hz increases the old bound"), FMath::IsNearlyEqual(Clock.MaximumRewind, Expected, .000001));
        TestTrue(TEXT("Every allowed rewind has an equal bounded contact wait"), Clock.Wait == Clock.MaximumRewind && Clock.Wait <= .2);
    }
    Clock.Reset(); Clock.MapAccepted(1., 10., .12, 0., Mapped);
    Clock.MapAccepted(12., 21.5, .4, 0., Mapped);
    TestTrue(TEXT("An expired transit minimum cannot survive a route change"), Clock.Samples.Num() == 1 && Clock.OneWay == .15);
    Clock.MapAccepted(.1, 21.6, .02, 0., Mapped);
    TestTrue(TEXT("A validated CMC timestamp generation resets both minima"), Clock.Generation == 1 && Clock.Samples.Num() == 1 && Clock.OneWay == .01);
    TestTrue(TEXT("A clock generation never moves mapped history backwards"), Mapped >= 21.35);
    Clock.Reset(); Clock.MapAccepted(1., 10., 0., 0., Mapped);
    Clock.MapAccepted(1.03, 10.03, .12, 0., Mapped);
    TestTrue(TEXT("An initial unknown RTT does not pin the minimum to zero"), Clock.OneWay == .06);
    for (int32 I = 1; I <= 700; ++I) Clock.MapAccepted(2. + I / 60., 11. + I / 60., .12, 0., Mapped);
    TestTrue(TEXT("The ten-second window has bounded bucket storage"), Clock.Samples.Num() <= 102);

    FJapanDefenceTimeline History;
    FJapanDefenceSample Sample;
    Sample.Time = 1.; Sample.bCanParry = Sample.bCanDodge = Sample.bArmed = Sample.bGround = true;
    History.Record(Sample);
    History.Hold(1, 1., true);
    TestTrue(TEXT("Guard and parry in the same original move preserve edge order"),
        History.Add(2, 1., EJapanDefence::Parry, .02, .12));
    Sample.Time = 1.10; History.Record(Sample);
    uint16 Edge = 0;
    TestEqual(TEXT("Late arrival does not change the original authored window"),
        History.Resolve(1.10, FVector(100, 0, 0), .5f, Edge), EJapanDefence::Parry);
    TestEqual(TEXT("Parry identifies its original edge"), Edge, uint16(2));
    TestEqual(TEXT("A parry cannot resolve two contacts"),
        History.Resolve(1.11, FVector(100, 0, 0), .5f, Edge), EJapanDefence::Guard);
    TestFalse(TEXT("Resending a consumed edge cannot recreate its window"),
        History.Add(2, 1., EJapanDefence::Parry, .02, .12));
    Sample.Time = 1.18; History.Record(Sample);
    TestEqual(TEXT("Late press does not widen window to late live animation"),
        History.Resolve(1.18, FVector(-100, 0, 0), .5f, Edge), EJapanDefence::None);
    TestEqual(TEXT("A future sample cannot defend a past strike"),
        History.Resolve(.99, FVector(100, 0, 0), .5f, Edge), EJapanDefence::None);
    TestEqual(TEXT("Stalled history cannot hold protection indefinitely"),
        History.Resolve(1.24, FVector(100, 0, 0), .5f, Edge), EJapanDefence::None);
    History.Reset();
    Sample.Time = 2.; Sample.bCanParry = Sample.bCanDodge = false; History.Record(Sample);
    History.Hold(1, 2., true);
    TestFalse(TEXT("Later eligibility cannot authorize an ineligible original press"),
        History.Add(2, 2., EJapanDefence::Parry, .01, .1));
    TestFalse(TEXT("A historically ineligible dodge cannot create invulnerability"),
        History.Add(3, 2., EJapanDefence::Dodge, 0., .4, .25));
    History.Reset();
    Sample = FJapanDefenceSample();
    Sample.Time = 3.; Sample.bCanDodge = true; History.Record(Sample);
    TestTrue(TEXT("An eligible late hop gets its original authored interval"),
        History.Add(1, 3., EJapanDefence::Dodge, 0., .6, .25));
    History.BindAction(1, 10, 3.1);
    History.SelfCutoff(10, 3.3); // early landing after .2 live seconds, projected to 3.2
    Sample.Time = 3.19; History.Record(Sample);
    TestEqual(TEXT("A hop before its projected landing can perfect-dodge"),
        History.Resolve(3.19, FVector(100, 0, 0), .5f, Edge), EJapanDefence::PerfectDodge);
    Sample.Time = 3.21; History.Record(Sample);
    TestEqual(TEXT("An early landing leaves recovery but cannot award a flurry"),
        History.Resolve(3.21, FVector(100, 0, 0), .5f, Edge), EJapanDefence::Recovering);
    Sample.Time = 3.61; History.Record(Sample);
    TestEqual(TEXT("Landing never extends the original invulnerability deadline"),
        History.Resolve(3.61, FVector(100, 0, 0), .5f, Edge), EJapanDefence::None);
    History.Reset();
    Sample.Time = 4.; Sample.bCanParry = Sample.bArmed = Sample.bGround = Sample.bGuardHeld = true;
    History.Record(Sample);
    History.Add(1, 4., EJapanDefence::Parry, 0., .4);
    History.BindAction(1, 20, 4.1);
    History.CancelByInput(20, 4.15);
    History.SelfCutoff(21, 4.11); // a different action cannot shorten this one
    Sample.Time = 4.16; Sample.bGuardHeld = false; History.Record(Sample);
    TestEqual(TEXT("A later original input cancels the parry at its original time"),
        History.Resolve(4.16, FVector(100, 0, 0), .5f, Edge), EJapanDefence::None);
    History.Reset();
    Sample.Time = 5.; History.Record(Sample);
    History.Add(1, 5., EJapanDefence::Dodge, 0., .4, .25);
    Sample.Time = 5.1; History.Record(Sample);
    History.Resolve(5.1, FVector(100, 0, 0), .5f, Edge);
    TestEqual(TEXT("Historically eligible actions with no live instance are observable fallbacks"), History.AuthoredFallbacks, uint32(1));
    Sample.Time = 5.5; Sample.bGuardHeld = true; Sample.bGuardBroken = true; History.Record(Sample);
    TestEqual(TEXT("A broken guard cannot absorb another queued contact"),
        History.Resolve(5.5, FVector(100, 0, 0), .5f, Edge), EJapanDefence::None);
    History.Reset();
    Sample = FJapanDefenceSample(); Sample.Time = 6.; Sample.bCanDodge = true;
    History.Record(Sample); History.Add(1, 6., EJapanDefence::Dodge, 0., .4, .25);
    TestEqual(TEXT("An established authored window survives a missing contact sample"),
        History.Resolve(6.1, FVector(100, 0, 0), .5f, Edge), EJapanDefence::PerfectDodge);
    History.Reset();
    Sample.Time = 7.; Sample.bGround = Sample.bArmed = Sample.bGuardHeld = true; History.Record(Sample);
    Sample.Time = 7.1; Sample.bGuardHeld = false; History.Record(Sample);
    TestEqual(TEXT("Bracketed history carries guard through one dropped movement packet"),
        History.Resolve(7.08, FVector(100, 0, 0), .5f, Edge), EJapanDefence::Guard);
    History.Reset();
    Sample.Time = 8.; History.Record(Sample); History.Add(1, 8., EJapanDefence::Dodge, 0., .2, .1);
    History.RetainThrough(8.1);
    Sample.Time = 8.8; History.Record(Sample);
    TestEqual(TEXT("A pending contact pins its defence window against later sample bursts"),
        History.Resolve(8.1, FVector(100, 0, 0), .5f, Edge), EJapanDefence::PerfectDodge);
    return true;
}
#endif
