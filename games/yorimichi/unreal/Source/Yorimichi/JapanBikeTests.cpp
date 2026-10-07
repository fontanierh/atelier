#include "JapanBikeState.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanBikeCheckpointTest, "Yorimichi.Network.BikeCheckpoint",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanBikeCheckpointTest::RunTest(const FString&)
{
    FJapanBikeState Original;
    Original.State=5;Original.Clip=TEXT("BikeCrash");Original.Resume=TEXT("BikeRide");
    Original.Serial=193;Original.Yaw=135.f;Original.ClipTime=.2f;Original.Speed=-200.f;
    Original.Steering=.35f;Original.StillTime=.1f;Original.AppliedYaw=13.f;
    Original.Crank=-354.f;Original.Coast=.3f;Original.Recoil=60.f;Original.Terminal=false;Original.Pedalling=true;
    TArray<uint8> Bytes;FMemoryWriter Writer(Bytes,true);
    TestTrue(TEXT("Recoil checkpoint encodes"),Original.SerializeCheckpoint(Writer));
    TestEqual(TEXT("Fixed bike checkpoint size"),Bytes.Num(),FJapanBikeState::CheckpointBytes);
    FJapanBikeState Restored;FMemoryReader Reader(Bytes,true);
    TestTrue(TEXT("Checkpoint decodes"),Restored.SerializeCheckpoint(Reader));
    TestEqual(TEXT("Facing is restored before replaying relative turns"),Restored.Yaw,135.f);
    TestEqual(TEXT("Crash recoil survives correction"),Restored.Recoil,60.f);
    TestEqual(TEXT("Authored crank phase survives independent of rendered blend"),Restored.Crank,-354.f);
    TestEqual(TEXT("Clip identity survives without process-local name indices"),Restored.Clip,FName(TEXT("BikeCrash")));
    TestEqual(TEXT("Transition destination survives"),Restored.Resume,FName(TEXT("BikeRide")));
    TestEqual(TEXT("One-shot serial survives"),Restored.Serial,193u);
    TestTrue(TEXT("Remote pedal audio follows the accepted input"),Restored.Pedalling);
    FJapanBikeState Bad=Restored;Bad.State=2;Bad.Terminal=true;
    TestFalse(TEXT("Riding cannot be a terminal parking state"),Bad.IsValid());
    Bad=Restored;Bad.Clip=TEXT("UnknownBikeAction");TestFalse(TEXT("Unknown clip rejected"),Bad.IsValid());
    Bad=Restored;Bad.Speed=1201.f;TestFalse(TEXT("Out-of-policy velocity rejected"),Bad.IsValid());
    Bytes[1]=255;FMemoryReader BadReader(Bytes,true);FJapanBikeState Rejected;
    TestFalse(TEXT("Wire vocabulary out of bounds is rejected before lookup"),Rejected.SerializeCheckpoint(BadReader));
    return true;
}
#endif
