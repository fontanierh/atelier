#include "JapanSkateWire.h"
#include "JapanSkateBudget.h"
#include "JapanSkateClock.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopedCVar.h"
#include "Serialization/BitReader.h"
#include "Serialization/BitWriter.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanSkateWireTest, "Yorimichi.Network.SkateWire",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanSkateWireTest::RunTest(const FString&)
{
    FJapanSkateClock Clock;
    const double First = Clock.Map(9.94, 10.06); // 60 ms clock bias plus 60 ms inbound transit.
    const double SecondTime = Clock.Map(9.97, 10.09);
    const double Jitter = Clock.Map(10.00, 10.15); // Extra 30 ms delay must not distort capture spacing.
    TestTrue(TEXT("Skate capture clock maps onto host arrival time"), FMath::IsNearlyEqual(First, 10.06, .00001));
    TestTrue(TEXT("Constant latency preserves capture intervals"), FMath::IsNearlyEqual(SecondTime - First, .03, .00001));
    TestTrue(TEXT("Jitter retains capture spacing rather than receipt spacing"), FMath::IsNearlyEqual(Jitter - SecondTime, .03, .00001));
    TestTrue(TEXT("Expired minimum offset adapts to a changed route"), FMath::IsNearlyEqual(Clock.Map(12., 12.3), 12.3, .00001));
    for (int32 I = 0; I < 1000; ++I) Clock.Map(20. + I * .01, 20.2 + I * .01);
    TestTrue(TEXT("The shared pose/body/board clock has bounded history"), Clock.Samples.Num() <= 22);
    for (double ObserverOffset : {-12., 12.})
    {
        FJapanSkateClock Observer;
        TArray<double> LocalFrames;
        for (int32 I = 0; I < 12; ++I)
        {
            const double Capture = 20. + I / 30.;
            LocalFrames.Add(Observer.Map(Capture, Capture + ObserverOffset + .06));
        }
        const double ShowAt = 20. + 11./30. + ObserverOffset + .06 - .1;
        TestTrue(TEXT("An observer with either clock skew has buffered interpolation history"),
            LocalFrames[0] < ShowAt && ShowAt < LocalFrames.Last());
        TestTrue(TEXT("Observer mapping preserves capture spacing"),
            FMath::IsNearlyEqual(LocalFrames.Last() - LocalFrames[0], 11./30., .00001));
    }
    FJapanSkateChunk Chunk;
    Chunk.Epoch = 3; Chunk.Frame = 10; Chunk.Time = 5.f; Chunk.TotalBones = 64;
    Chunk.Bones.Init(FTransform(FRotator(25,-60,170), FVector(-120,53.2,240.5), FVector(1)), 32);
    Chunk.Root.SetLocation(FVector(45200, -68200, 180));
    FBitWriter Writer(8000, true);
    bool Success = false;
    Chunk.NetSerialize(Writer, nullptr, Success);
    TestTrue(TEXT("A complete 32-bone datagram encodes"), Success);
    TestTrue(TEXT("The datagram remains below the payload budget"), Writer.GetNumBits() <= 720 * 8);
    FBitReader Reader(Writer.GetData(), Writer.GetNumBits());
    FJapanSkateChunk Read;
    Read.NetSerialize(Reader, nullptr, Success);
    TestTrue(TEXT("It decodes within the same bounds"), Success);
    TestTrue(TEXT("Body component-space positions retain submillimetre precision"), Read.Bones[0].GetLocation().Equals(Chunk.Bones[0].GetLocation(), .06));
    TestTrue(TEXT("Bone turns retain their orientation"), Read.Bones[0].GetRotation().Equals(Chunk.Bones[0].GetRotation(), .0002));
    FJapanSkateAssembly Assembly;
    FJapanSkateFrame Complete;
    FJapanSkateChunk Second = Read; Second.Chunk = 1;
    TestFalse(TEXT("The second half arriving first stays incomplete"), Assembly.Add(Second, Complete));
    TestTrue(TEXT("The delayed first half completes the same frame"), Assembly.Add(Read, Complete));
    TestEqual(TEXT("No bones are silently omitted"), Complete.Bones.Num(), 64);
    TestFalse(TEXT("Duplicate chunks do not emit duplicate frames"), Assembly.Add(Read, Complete));
    FJapanSkateChunk Newer = Read; Newer.Frame += 3;
    TestFalse(TEXT("A new frame may reuse a fixed assembly slot"), Assembly.Add(Newer, Complete));
    TestFalse(TEXT("An old delayed chunk cannot evict the new frame"), Assembly.Add(Second, Complete));
    Newer.Chunk = 1;
    TestTrue(TEXT("The new frame still completes"), Assembly.Add(Newer, Complete));
    FBitReader Truncated(Writer.GetData(), Writer.GetNumBits()-8);
    FJapanSkateChunk Missing;
    {
        FScopedCVar<int32> OverflowLog(TEXT("net.BitReader.EnsureOnOverflow"), 0);
        AddExpectedErrorPlain(TEXT("FBitReader::SetOverflowed() called!"));
        Missing.NetSerialize(Truncated, nullptr, Success);
        TestFalse(TEXT("A truncated bone cannot be shown"), Success);
        TestTrue(TEXT("Truncation leaves the pose archive rejected"), Truncated.IsError());
    }
    for (const double Pitch : {89.99, 90., 90.01, -90., 180., 270.})
    {
        const FQuat Turn = FRotator(Pitch, 175., -123.).Quaternion();
        Chunk.Bones[0].SetRotation(Turn); Chunk.Deck.SetRotation(Turn); Chunk.Shown = .4f;
        FBitWriter TurnWriter(8000, true); Chunk.NetSerialize(TurnWriter, nullptr, Success);
        FBitReader TurnReader(TurnWriter.GetData(), TurnWriter.GetNumBits());
        FJapanSkateChunk TurnRead; TurnRead.NetSerialize(TurnReader, nullptr, Success);
        TestTrue(TEXT("Flip and gimbal-pole orientations decode"), Success);
        TestTrue(TEXT("Quaternion quantization preserves a flip across Euler singularities"),
            FMath::Abs(TurnRead.Bones[0].GetRotation() | Turn) > .999999);
        TestTrue(TEXT("Deck and bones share the captured orientation and time"),
            TurnRead.Deck.GetRotation().Equals(TurnRead.Bones[0].GetRotation(), .0001) && TurnRead.Time == Chunk.Time);
    }
    Chunk.Bones[0].SetScale3D(FVector(148.));
    FBitWriter CairoWriter(8000, true); Chunk.NetSerialize(CairoWriter, nullptr, Success);
    TestTrue(TEXT("Merged Cairo component-space root scale encodes"), Success);
    FBitReader CairoReader(CairoWriter.GetData(), CairoWriter.GetNumBits());
    FJapanSkateChunk CairoRead; CairoRead.NetSerialize(CairoReader, nullptr, Success);
    TestTrue(TEXT("The shared SK_Cairo scale survives exactly without increasing packet size"),
        Success && CairoRead.Bones[0].GetScale3D().Equals(FVector(148.), .00001) && CairoWriter.GetNumBits() <= 720 * 8);
    Chunk.TotalBones = FJapanSkateChunk::MaximumBones + 1;
    FBitWriter Oversized(8000, true);
    Chunk.NetSerialize(Oversized, nullptr, Success);
    TestFalse(TEXT("An unbounded peer count is rejected"), Success);
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanSkateBudgetTest, "Yorimichi.Network.SkateBudget",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanSkateBudgetTest::RunTest(const FString&)
{
    FJapanSkateBudget Budget;
    int64 PoseBytes = 0, BodyBytes = 0;
    for (int32 Tick = 0; Tick < 10000; ++Tick)
    {
        const double Now = Tick / 1000.;
        // Eight competing skaters cannot expand the connection budget.
        for (int32 Rider = 0; Rider < 8; ++Rider)
        {
            if (Budget.Spend(Now, 6 * 768, false)) PoseBytes += 6 * 768;
            if (Budget.Spend(Now, 768, true)) BodyBytes += 768;
        }
    }
    TestTrue(TEXT("Whole-pose traffic stays below ten seconds plus the bounded burst"),
        PoseBytes <= FJapanSkateBudget::PoseRate * 10.1);
    TestTrue(TEXT("Bail traffic has its own bounded share"), BodyBytes <= FJapanSkateBudget::BodyRate * 10.1);
    TestTrue(TEXT("Neither stream is starved"), PoseBytes > FJapanSkateBudget::PoseRate * 9. && BodyBytes > FJapanSkateBudget::BodyRate * 9.);
    FJapanSkateBudget Slow;
    int64 SlowPose = 0, SlowBody = 0;
    for (int32 Tick = 0; Tick < 300; ++Tick)
    {
        const double Now = Tick / 30.;
        Slow.Refill(Now);
        for (int32 Rider = 0; Rider < 8; ++Rider)
        {
            if (Slow.Spend(Now, 6 * 768, false)) SlowPose += 6 * 768;
            if (Slow.Spend(Now, 768, true)) SlowBody += 768;
        }
    }
    TestTrue(TEXT("30 fps obeys UE's 60 Hz refill ceiling for poses"), SlowPose <= FJapanSkateBudget::PoseRate * 5.1);
    TestTrue(TEXT("30 fps obeys UE's 60 Hz refill ceiling for bodies"), SlowBody <= FJapanSkateBudget::BodyRate * 5.1);
    TestTrue(TEXT("Slow ticks still serve both streams"), SlowPose > FJapanSkateBudget::PoseRate * 4.5 && SlowBody > FJapanSkateBudget::BodyRate * 4.5);
    const double Before = Budget.PoseTokens;
    TestFalse(TEXT("An oversized frame is refused before any chunks are sent"), Budget.Spend(10., 20000, false));
    TestTrue(TEXT("A refused frame consumes no tokens"), Budget.PoseTokens >= Before);
    TestFalse(TEXT("Invalid byte counts are refused"), Budget.Spend(10., -1, true));
    return true;
}
#endif
