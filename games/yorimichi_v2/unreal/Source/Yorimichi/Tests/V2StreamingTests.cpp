#include "World/V2Streaming.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "Engine/World.h"

// The committed Slice map loads its scenery as far as the original shows it: with the engine's 256 m default, V2
// lost Hidamari's far town and harbour and the hills behind (PARITY, far views).
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FV2StreamingRangeTest, "Yorimichi.V2.StreamingRange",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FV2StreamingRangeTest::RunTest(const FString&)
{
    UWorld* World = LoadObject<UWorld>(nullptr, TEXT("/Game/V2/Maps/Slice.Slice"));
    if (!TestNotNull(TEXT("The Slice map loads"), World)) return false;
    AddInfo(UV2Streaming::DescribeLoadingRanges(World));
    const float Range = UV2Streaming::MinLoadingRange(World);
    TestTrue(FString::Printf(TEXT("Every streaming layer loads %.0f cm or more (smallest %.0f cm)"),
        UV2Streaming::IslandRangeCm(), Range), Range >= UV2Streaming::IslandRangeCm());
    return true;
}
#endif
