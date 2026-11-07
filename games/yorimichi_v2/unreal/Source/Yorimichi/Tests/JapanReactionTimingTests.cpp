#include "JapanReactionTiming.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "GameFramework/GameNetworkManager.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "HAL/IConsoleManager.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanReactionTimingTest, "Yorimichi.Network.ReactionTiming",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanReactionTimingTest::RunTest(const FString&)
{
    using JapanReactionTiming::EResult;
    const auto* Scalar = IConsoleManager::Get().FindConsoleVariable(TEXT("p.NetServerMaxMoveDeltaTimeScalar"));
    if (!TestNotNull(TEXT("Effective server move cap is available"), Scalar)) return false;
    const float Cap = GetDefault<AGameNetworkManager>()->MaxMoveDeltaTime * Scalar->GetFloat();
    const float Step = 1.f / 30.f;
    const float ResetPeriod = GetDefault<UCharacterMovementComponent>()->MinTimeBetweenTimeStampResets;
    const FJapanReactionOrigin Origin{{0, Step}, {0, 2.f * Step}, Step};
    const float AcceptedTwo = 3.f * Step - Step; // CMC derives Dt from end stamps.
    auto Split = JapanReactionTiming::Plan({0, Step}, {0, Step}, {0, 3.f * Step},
        AcceptedTwo, Cap, ResetPeriod, Origin, true);
    TestTrue(TEXT("Lost first marked move retains its original timing"), Split.Result == EResult::Exact);
    TestTrue(TEXT("No invented prefix when only the marked move was lost"), Split.Before == 0.f);
    TestTrue(TEXT("Original reaction move keeps its saved Dt"), Split.Reaction == Step);
    TestTrue(TEXT("Later accepted move remains a separate tail"), FMath::IsNearlyEqual(Split.After, Step, 1.e-7f));
    Split = JapanReactionTiming::Plan({0, 0.f}, {0, 0.f}, {0, 3.f * Step},
        3.f * Step, Cap, ResetPeriod, Origin, true);
    TestTrue(TEXT("Lost preceding and marked moves split before the reaction"), Split.Result == EResult::Exact);
    TestTrue(TEXT("Lost preceding move runs before the reaction"), FMath::IsNearlyEqual(Split.Before, Step, 1.e-7f));
    const float Predicted = 99.9f * Step - 46.9f * (2.f * Step);
    const float Reconstructed = 99.9f * Split.Before - 46.9f * (Split.Reaction + Split.After);
    TestTrue(TEXT("Merged loss preserves the original reaction position"), FMath::Abs(Predicted - Reconstructed) < .001f);
    TestTrue(TEXT("Applying at merged move start reproduces a real correction"),
        FMath::Abs(Predicted - (-46.9f * 3.f * Step)) > 1.f);
    TestTrue(TEXT("Slices never invent accepted simulation time"),
        FMath::IsNearlyEqual(Split.Before + Split.Reaction + Split.After, 3.f * Step, 1.e-7f));
    const auto LateOld = JapanReactionTiming::Plan({0, 3.f * Step}, {0, 0.f}, Origin.End,
        Step, Cap, ResetPeriod, Origin, true);
    TestTrue(TEXT("Late old move cannot be re-admitted by reaction timing"), LateOld.Result == EResult::InvalidMove);
    auto ForgedOrigin = Origin; ForgedOrigin.End.Time = 1.f;
    TestTrue(TEXT("Forged future origin requests counted clamp"),
        JapanReactionTiming::Plan({0, 0.f}, {0, 0.f}, {0, .1f}, .1f, Cap, ResetPeriod, ForgedOrigin, true).Result == EResult::Clamped);
    ForgedOrigin = Origin; ForgedOrigin.DeltaTime = Cap + .001f;
    TestTrue(TEXT("Owner Dt beyond the effective CMC cap requests counted clamp"),
        JapanReactionTiming::Plan({0, 0.f}, {0, 0.f}, {0, .1f}, .1f, Cap, ResetPeriod, ForgedOrigin, true).Result == EResult::Clamped);
    ForgedOrigin.DeltaTime = 0.f;
    TestTrue(TEXT("Zero owner Dt cannot split an accepted move"),
        JapanReactionTiming::Plan({0, 0.f}, {0, 0.f}, {0, .1f}, .1f, Cap, ResetPeriod, ForgedOrigin, true).Result == EResult::Clamped);
    // The origin crosses UE's periodic reset; the generation comes from the
    // accepted movement clock. Numeric float times alone would reverse order.
    const FJapanReactionOrigin Wrapped{{0, ResetPeriod}, {1, Step}, Step};
    const auto AcrossReset = JapanReactionTiming::Plan({0, ResetPeriod}, {0, ResetPeriod}, {1, 2.f * Step},
        2.f * Step, Cap, ResetPeriod, Wrapped, true);
    TestTrue(TEXT("Pending reaction survives a legitimate timestamp wrap"), AcrossReset.Result == EResult::Exact);
    TestTrue(TEXT("Wrapped first move starts at the original boundary"), AcrossReset.Before == 0.f);
    TestTrue(TEXT("Wrapped first move retains saved Dt"), AcrossReset.Reaction == Step);
    const FJapanReactionOrigin Capped{{0, 1.f}, {0, 1.4f}, Cap};
    const auto CappedPlan = JapanReactionTiming::Plan({0, 1.f}, {0, 1.f}, {0, 1.4f}, Cap, Cap, ResetPeriod, Capped, true);
    TestTrue(TEXT("Capped timestamp gap does not invent owner simulation"), CappedPlan.Result == EResult::Exact);
    TestTrue(TEXT("Capped origin uses only its actual saved duration"), CappedPlan.Reaction == Cap);
    for (float Base : {0.f, ResetPeriod - .1f})
    {
        const float Prior = Base + Step, Marked = Prior + Step, Latest = Marked + Step;
        const float MarkedDt = Marked - Prior, TailDt = Latest - Marked;
        const FJapanReactionOrigin AtScale{{0, Prior}, {0, Marked}, MarkedDt};
        const auto OneLost = JapanReactionTiming::Plan({0, Prior}, {0, Prior}, {0, Latest},
            Latest - Prior, Cap, ResetPeriod, AtScale, true);
        TestTrue(TEXT("Lost marked move is Exact near the reset boundary"), OneLost.Result == EResult::Exact);
        TestTrue(TEXT("High-stamp matching Previous/Current keeps an exact zero prefix"), OneLost.Before == 0.f);
        TestTrue(TEXT("High-stamp reaction keeps its actual saved duration"), OneLost.Reaction == MarkedDt);
        TestTrue(TEXT("High-stamp tail retains the next move"), FMath::IsNearlyEqual(OneLost.After, TailDt, 1.e-6f));
        const auto TwoLost = JapanReactionTiming::Plan({0, Base}, {0, Base}, {0, Latest},
            Latest - Base, Cap, ResetPeriod, AtScale, true);
        TestTrue(TEXT("Lost predecessor plus marked move is Exact near reset"), TwoLost.Result == EResult::Exact);
        TestTrue(TEXT("High-stamp prefix stays nonnegative"), TwoLost.Before >= 0.f);
        TestTrue(TEXT("High-stamp slices consume only accepted time"), FMath::Abs(
            TwoLost.Before + TwoLost.Reaction + TwoLost.After - (Latest - Base)) <= 2.f * 1.52587890625e-5f);
        const FJapanReactionOrigin LongFrame{{0, Base}, {0, Base + .4f}, Cap};
        const auto Long = JapanReactionTiming::Plan({0, Base}, {0, Base}, LongFrame.End,
            Cap, Cap, ResetPeriod, LongFrame, true);
        TestTrue(TEXT("High-stamp capped move remains Exact"), Long.Result == EResult::Exact);
        TestTrue(TEXT("High-stamp capped move starts with its reaction"), Long.Before == 0.f);
        TestTrue(TEXT("Discrepancy override or nonunit dilation requires counted clamp"),
            JapanReactionTiming::Plan({0, Prior}, {0, Prior}, {0, Latest}, Latest - Prior,
                Cap, ResetPeriod, AtScale, false).Result == EResult::Clamped);
    }
    const FJapanReactionOrigin TinyPrefix{{0, 1.e-7f}, {0, Step}, Step - 1.e-7f};
    const auto Folded = JapanReactionTiming::Plan({0, 0.f}, {0, 0.f}, {0, Step}, Step, Cap, ResetPeriod, TinyPrefix, true);
    TestTrue(TEXT("Sub-minimum prefix is folded without another movement call"), Folded.bFolded && Folded.Before == 0.f);
    TestTrue(TEXT("Folding retains the entire accepted duration"), Folded.Reaction == Step);
    return true;
}
#endif
