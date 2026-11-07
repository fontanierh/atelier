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
    TestTrue(TEXT("The wait covers one-way transit plus measured arrival spread and margin"), FMath::IsNearlyEqual(Clock.Wait, .09, .00001));
    TestTrue(TEXT("Packet jitter is not added to the original press time"), Clock.MapAccepted(1.03, 10.12, .12, .015, Mapped));
    TestTrue(TEXT("Original input spacing survives a jittered arrival"), FMath::IsNearlyEqual(Mapped, 10.03, .00001));
    TestFalse(TEXT("Duplicate accepted timestamps cannot remap defence history"), Clock.MapAccepted(1.03, 10.13, .12, .015, Mapped));
    Clock.Reset();
    TestTrue(TEXT("Excessive measured ping still has a bounded result wait"), Clock.MapAccepted(1., 20., 1., .3, Mapped));
    TestTrue(TEXT("A bad connection cannot delay contacts indefinitely"), Clock.Wait <= .2 && Clock.OneWay <= .15);
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
        Clock.Reset(); Clock.MapAccepted(1., 10., .12, .05, Mapped, .03334, HostDt);
        const double Expected = FMath::Min(.2, .12334 + FMath::Max(0., FMath::Min(HostDt, .1) - 1. / 60.));
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
    Clock.Reset(); Clock.MapAccepted(1., 10., .12, 0., Mapped, .033333, 1. / 60.);
    Clock.MapAccepted(1.03, 10.08, .12, 0., Mapped, .033333, 1. / 60.);
    TestTrue(TEXT("A single warmup bucket cannot buy jitter allowance"), Clock.Samples.Num() == 1 && Clock.ArrivalSpread == 0.);
    for (double HostDt : {1. / 60., .05, .1, 2.})
    {
        Clock.Reset();
        for (int32 I = 0; I < 20; ++I)
        {
            const double Ts = 1. + I * .2;
            Clock.MapAccepted(Ts, Ts + 10. + (I % 2 ? .06 : 0.), .3, .05, Mapped, .033333, HostDt);
        }
        TestTrue(TEXT("Sustained tail and high RTT saturate the total 200 ms ceiling at every host rate"),
            Clock.ArrivalSpread == .05 && Clock.MaximumRewind == .2 && Clock.Wait == .2);
    }
    // Reproduce the fast-host guard's measured floor, 39.6 ms arrival tail,
    // and 33 ms input age. The prior smoothed-jitter bound left only 4.8 ms.
    Clock.Reset();
    Clock.MapAccepted(.033348, 19.959806, .199148, .02915, Mapped, .033348, .016676);
    Clock.MapAccepted(.066693, 19.993155, .132289, .027391, Mapped, .033345, .016667);
    for (int32 I = 1; I <= 60; ++I)
    {
        const double Ts = .1 + I * .11;
        Clock.MapAccepted(Ts, Ts + 19.926458 + (I % 2 ? .038 : .004), .15, .014, Mapped, .033343, 1. / 60.);
    }
    Clock.MapAccepted(7.035473, 27.001529, .149738, .013999, Mapped, .033343, .016701);
    TestTrue(TEXT("Recorded fast-host guard keeps ten milliseconds inside the measured tail"),
        Clock.OriginalPress(33, 27.001529, Press) && Press - (27.001529 - Clock.MaximumRewind) >= .01);
    TestTrue(TEXT("Arrival spread is bounded and separate from mean ACK jitter"),
        Clock.ArrivalSpread >= .037 && Clock.ArrivalSpread <= .05 && Clock.Wait <= .2);
    Normal = Clock; Spike = Clock;
    Normal.MapAccepted(7.2, 27.164458, .15, .014, NormalTime, .033343, 1. / 60.);
    Spike.MapAccepted(7.2, 27.214458, .15, .014, SpikeTime, .033343, 1. / 60.);
    TestTrue(TEXT("One deliberately held packet cannot widen the arrival-tail allowance"),
        Normal.MaximumRewind == Spike.MaximumRewind);
    Clock.Reset();
    for (int32 I = 0; I < 50; ++I)
    {
        const double Ts = 1. + I * .12;
        Clock.MapAccepted(Ts, Ts + 10. + (I % 2 ? .0467 : 0.), .132, .001, Mapped, .033333, 1. / 60.);
    }
    const double TailNow = 7. + 10. + .0467;
    Clock.MapAccepted(7., TailNow, .132, .001, Mapped, .033333, 1. / 60.);
    TestTrue(TEXT("A sustained 60/15 tail plus host quantization keeps honest input inside"),
        Clock.OriginalPress(33, TailNow, Press) && Press - (TailNow - Clock.Wait) >= .01);
    const uint16 Beyond = uint16(FMath::CeilToInt((Clock.Wait - (TailNow - Mapped)) * 1000.) + 1);
    TestFalse(TEXT("A claimed press beyond the measured tail plus one millisecond is rejected"),
        Clock.OriginalPress(Beyond, TailNow, Press));


    // The host may process an input 150 ms after its original movement step.
    // Eligibility uses that step's origin, not the time its packet was received.
    FJapanDefenceTimeline MappedHistory, ArrivalHistory;
    FJapanDefenceSample Eligible;
    Eligible.Time = 9.98; ArrivalHistory.Record(Eligible);
    MappedHistory.RecordMapped(Eligible, 9.966667, 0.);
    Eligible.bGround = Eligible.bArmed = Eligible.bCanParry = true;
    Eligible.Time = 10.15; ArrivalHistory.Record(Eligible);
    MappedHistory.RecordMapped(Eligible, 10., 0.);
    // The next move covers [10, 10.033333]. A press halfway through it sees
    // eligible pre-state, even when the action locks after this move advances.
    MappedHistory.RecordMapped(Eligible, 10.033333, .033333);
    constexpr double MidPress = 10.016;
    MappedHistory.Hold(1, MidPress, true); ArrivalHistory.Hold(1, MidPress, true);
    TestTrue(TEXT("Mapped pre-step eligibility admits a delayed mid-step press"),
        MappedHistory.Add(2, MidPress, EJapanDefence::Parry, .02, .2));
    TestFalse(TEXT("Arrival-stamped history reproduces the stale eligibility rejection"),
        ArrivalHistory.Add(2, MidPress, EJapanDefence::Parry, .02, .2));
    MappedHistory.BindAction(2, 42, 10.2);
    Eligible.bCanParry = false; Eligible.ThroughEdge = 2;
    MappedHistory.RecordMapped(Eligible, 10.033333, 0.);
    const auto* MidState = MappedHistory.At(MidPress);
    TestTrue(TEXT("Post-step state does not rewrite eligibility inside its own step"), MidState && MidState->bCanParry);
    uint16 MappedEdge = 0;
    TestEqual(TEXT("Delayed parry resolves its original contact with mapped history"),
        MappedHistory.Resolve(10.058, FVector(100, 0, 0), .5f, MappedEdge), EJapanDefence::Parry);
    TestEqual(TEXT("The mapped result keeps the original edge"), MappedEdge, uint16(2));
    TestEqual(TEXT("The mapped result is bound to its real live action"), MappedHistory.AuthoredFallbacks, uint32(0));
    // No accepted move means no new remote sample: forced host ticks cannot
    // fill a starvation gap with state stamped using a stale input clock.
    MappedHistory.Reset(); Eligible.bCanParry = true; Eligible.ThroughEdge = 0;
    MappedHistory.RecordMapped(Eligible, 20., 0.);
    MappedHistory.RecordMapped(Eligible, 20.533333, .033333);
    MappedHistory.RecordMapped(Eligible, 20.533333, 0.);
    TestTrue(TEXT("Input starvation over 150 ms intentionally leaves no eligibility"), MappedHistory.At(20.2) == nullptr);
    MappedHistory.Hold(3, 20.2, true);
    TestFalse(TEXT("A press inside an unsampled starvation gap fails conservatively"),
        MappedHistory.Add(4, 20.2, EJapanDefence::Parry, .02, .2));
    const double LastSample = MappedHistory.LatestTime();
    MappedHistory.RecordMapped(Eligible, 20.50, .033333);
    Eligible.bCanParry = false;
    MappedHistory.RecordMapped(Eligible, 20.50, 0.);
    TestTrue(TEXT("Both mapped pre and post stamps remain monotonic during an offset plateau"),
        MappedHistory.LatestTime() == LastSample);
    const auto* PlateauState = MappedHistory.At(LastSample);
    TestTrue(TEXT("A plateau post cannot replace its own eligible pre-state"), PlateauState && PlateauState->bCanParry);
    MappedHistory.Reset(); Eligible.bGuardHeld = true;
    MappedHistory.RecordMapped(Eligible, 30., 0.);
    uint16 StarvedEdge = 0;
    TestEqual(TEXT("A bounded contact with history over 50 ms behind cannot invent a held guard"),
        MappedHistory.Resolve(30.08, FVector(100, 0, 0), .5f, StarvedEdge), EJapanDefence::None);
    TestEqual(TEXT("Starved held-guard resolution records its loss of compensation"),
        MappedHistory.MissingSamples, uint32(1));

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
