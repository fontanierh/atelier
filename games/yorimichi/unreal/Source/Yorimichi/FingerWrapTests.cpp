#include "FingerWrapNode.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

namespace
{
    // A round handle along Z through the origin, its radius grown by the skin (cm); with Contact .05 a segment's gap is
    // its distance from the axis less 2.55 (jim-playtest's capsule examples, #8034)
    constexpr double Grown = 2.5, Contact = .05;
    const float Min[3] = { -39.f, -180.f, -180.f }, Max[3] = { 95.f, 110.f, 90.f };

    double Clearance(const FVector& P, const FVector& Q) { return FMath::PointDistToSegment(FVector::ZeroVector, P, Q) - Grown; }
    double Outside(const FVector& P) { return P.Size2D() - Grown; }

    double Gap(const FVector (&J)[4], int32 K) { return Clearance(J[K], J[K + 1]) - Contact; }

    bool Wrap(FVector (&J)[4], FQuat (&Turns)[3], double Weight = 1.)
    {
        // the wrist on the base bone's line, so the knuckle's flexion is 0 and it opens 39 degrees at most
        const FVector Wrist = J[0] - (J[1] - J[0]);
        return FFingerWrapNode::WrapDigit(J, Turns, Wrist, 0, 0, Min, Max, Contact, .15, 80., 45., Weight, .01,
            [](const FVector& P, const FVector& Q) { return Clearance(P, Q); }, [](const FVector& P) { return Outside(P); });
    }

    // the two fingers of #8034: a clear knuckle with the end joint in the wood, and a floating finger whose base would
    // reach the handle at 36.75 degrees with the next bone 1.64 cm inside it
    const FVector Buried[4] = { FVector(4., 0., 0.), FVector(2.6, 0., 0.), FVector(2.35, .4, 0.), FVector(2.8, .7, 0.) };
    const FVector Floating[4] = { FVector(3.5, 0., 0.), FVector(3., 1., 0.), FVector(1.6, 2.2, 0.), FVector(1.6, 2.6, 0.) };
    // the clips' clenched fist round the handle (bones 2, 1.3 and 1 cm, bent 70 and 60 degrees; worst .77 cm deep), and a
    // half fist (bent 50 and 40; .48 cm) that no pass opens without sinking a bone (#8081)
    const FVector Fist[4] = { FVector(3.4, 1.8, 0.), FVector(1.6679, .8, 0.), FVector(1.8937, -.4803, 0.), FVector(2.8334, -.8223, 0.) };
    const FVector HalfFist[4] = { FVector(3.6, 1.4, 0.), FVector(2.0679, .1144, 0.), FVector(2.0679, -1.1856, 0.), FVector(2.7107, -1.9516, 0.) };

    // a finger with its middle bone just clear and its end bone .74 cm in: the plain pass takes the worst to .13 cm by
    // sinking the middle bone .13 cm, which a choice by the worst alone would keep (#8091)
    const FVector Trap[4] = { FVector(1.2814, 3.9967, 0.), FVector(-.6708, 3.5622, 0.), FVector(-1.1903, 2.3705, 0.), FVector(-1.1827, 1.3705, 0.) };

    double Depth(const FVector (&J)[4]) { double D = 0.; for (int32 K = 0; K < 3; ++K) D = FMath::Max(D, -Gap(J, K)); return D; }

    // No segment's gap ends below its own or contact, whichever is less
    void NotBuried(FAutomationTestBase& Test, const TCHAR* Case, const FVector (&Start)[4], const FVector (&J)[4])
    {
        for (int32 K = 0; K < 3; ++K)
            Test.TestTrue(FString::Printf(TEXT("%s: segment %d not buried (gap %.4f, was %.4f)"), Case, K, Gap(J, K), Gap(Start, K)),
                Gap(J, K) >= FMath::Min(0., Gap(Start, K)));
    }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFingerWrapLiftTest, "Yorimichi.Grip.LiftBuriedJoint",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// No turn about the buried end joint clears its bones, so the knuckle opens, carrying the chain, until every segment is
// clear (about 37.9 degrees, within its 39)
bool FFingerWrapLiftTest::RunTest(const FString&)
{
    FVector J[4] = { Buried[0], Buried[1], Buried[2], Buried[3] };
    FQuat Turns[3];
    TestTrue(TEXT("a bent finger"), Wrap(J, Turns));
    const FVector Base = (Buried[1] - Buried[0]).GetSafeNormal();
    const double Opened = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Base | (J[1] - J[0]).GetSafeNormal(), -1., 1.)));
    TestTrue(FString::Printf(TEXT("the knuckle opens about 37.9 degrees (%.2f)"), Opened), FMath::Abs(Opened - 37.92) < .2);
    for (int32 K = 0; K < 3; ++K) TestTrue(FString::Printf(TEXT("segment %d clear (gap %.4f)"), K, Gap(J, K)), Gap(J, K) >= 0.);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFingerWrapCloseTest, "Yorimichi.Grip.CloseKeepsLaterSegments",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// The floating finger closes nearer the handle, burying no bone (its base reaching the grip with the next bone 1.6 cm
// inside it is refused)
bool FFingerWrapCloseTest::RunTest(const FString&)
{
    FVector J[4] = { Floating[0], Floating[1], Floating[2], Floating[3] };
    FQuat Turns[3];
    TestTrue(TEXT("a bent finger"), Wrap(J, Turns));
    NotBuried(*this, TEXT("closing"), Floating, J);
    double Was = 0., Is = 0.;
    for (int32 K = 0; K < 3; ++K) { Was += Gap(Floating, K); Is += Gap(J, K); }
    TestTrue(FString::Printf(TEXT("nearer the handle (gaps %.3f, were %.3f)"), Is, Was), Is < Was - .1);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFingerWrapWeightTest, "Yorimichi.Grip.PartialWeight",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// Blending in, at half and seven-tenths weight: the part of the lift sinks the buried bones further before the whole of it
// clears them, so the finger keeps its incoming pose; the floating finger closes part way, burying nothing (#8044)
bool FFingerWrapWeightTest::RunTest(const FString&)
{
    for (const double Weight : { .5, .7 })
    {
        FVector J[4] = { Buried[0], Buried[1], Buried[2], Buried[3] };
        FQuat Turns[3];
        TestTrue(TEXT("a bent finger"), Wrap(J, Turns, Weight));
        const FString Lift = FString::Printf(TEXT("lift at %.1f"), Weight);
        TestTrue(Lift + TEXT(": the knuckle keeps its pose"), Turns[0].Equals(FQuat::Identity, 0.f) && J[1].Equals(Buried[1], 1e-9));
        NotBuried(*this, *Lift, Buried, J);
        FVector C[4] = { Floating[0], Floating[1], Floating[2], Floating[3] };
        TestTrue(TEXT("a bent finger"), Wrap(C, Turns, Weight));
        NotBuried(*this, *FString::Printf(TEXT("closing at %.1f"), Weight), Floating, C);
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFingerWrapFistTest, "Yorimichi.Grip.OpenFist",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// At full weight the clenched fist opens bend by bend, each sinking a later bone for the next to lift, to under .1 cm
// deep; at part weight that pass ends deeper, and the half fist at any weight, so each keeps its incoming pose (#8081)
bool FFingerWrapFistTest::RunTest(const FString&)
{
    for (const double Weight : { 1., .7, .5 })
    {
        FVector J[4] = { Fist[0], Fist[1], Fist[2], Fist[3] };
        FQuat Turns[3];
        TestTrue(TEXT("a bent finger"), Wrap(J, Turns, Weight));
        const FString Case = FString::Printf(TEXT("fist at %.1f"), Weight);
        NotBuried(*this, *Case, Fist, J);
        if (Weight == 1.) TestTrue(FString::Printf(TEXT("%s: opened to under .1 cm deep (%.3f)"), *Case, Depth(J)), Depth(J) < .1);
        else TestTrue(Case + TEXT(": keeps its pose"), J[1].Equals(Fist[1], 1e-9) && J[2].Equals(Fist[2], 1e-9) && J[3].Equals(Fist[3], 1e-9));
        FVector H[4] = { HalfFist[0], HalfFist[1], HalfFist[2], HalfFist[3] };
        TestTrue(TEXT("a bent finger"), Wrap(H, Turns, Weight));
        const FString Half = FString::Printf(TEXT("half fist at %.1f"), Weight);
        NotBuried(*this, *Half, HalfFist, H);
        TestTrue(Half + TEXT(": keeps its pose"), H[1].Equals(HalfFist[1], 1e-9) && H[2].Equals(HalfFist[2], 1e-9) && H[3].Equals(HalfFist[3], 1e-9));
    }
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFingerWrapClearTest, "Yorimichi.Grip.KeepsClearSegment",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

// A pass that improves the worst depth by burying a clear bone is not taken: the plain pass does exactly that here, and
// the guarded pass lifts the end bone out with the middle one still clear
bool FFingerWrapClearTest::RunTest(const FString&)
{
    const FVector Wrist = Trap[0] - (Trap[1] - Trap[0]);
    const FVector Bend = ((Trap[1] - Trap[0]) ^ (Trap[2] - Trap[1])).GetSafeNormal();
    FVector P[4] = { Trap[0], Trap[1], Trap[2], Trap[3] };
    FQuat Turns[3];
    FFingerWrapNode::Bends(P, Turns, Bend, Wrist, 0, 0, Min, Max, Contact, .15, 80., 45., 1., .01, false,
        [](const FVector& A, const FVector& B) { return Clearance(A, B); }, [](const FVector& A) { return Outside(A); });
    TestTrue(FString::Printf(TEXT("the plain pass: shallower at its worst (%.3f, was %.3f) with the clear middle bone sunk (%.3f, was %.3f)"),
        Depth(P), Depth(Trap), Gap(P, 1), Gap(Trap, 1)), Depth(P) < Depth(Trap) - .5 && Gap(Trap, 1) > 0. && Gap(P, 1) < -.1);
    FVector J[4] = { Trap[0], Trap[1], Trap[2], Trap[3] };
    TestTrue(TEXT("a bent finger"), Wrap(J, Turns));
    NotBuried(*this, TEXT("chosen"), Trap, J);
    TestTrue(FString::Printf(TEXT("chosen: clear (%.4f)"), Depth(J)), Depth(J) <= 1e-3);
    return true;
}
#endif
