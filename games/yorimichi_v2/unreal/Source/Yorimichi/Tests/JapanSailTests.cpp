#include "JapanSailState.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanSailCheckpointTest, "Yorimichi.Network.SailCheckpoint",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanSailCheckpointTest::RunTest(const FString&)
{
    FJapanSailState Original;
    Original.Equipped=true; Original.Serial=43; Original.Yaw=-179.f;
    Original.Speed=512.f; Original.Steering=-.75f;
    Original.SailAmount=.375f; Original.SailTarget=1.f;
    TArray<uint8> Bytes; FMemoryWriter Writer(Bytes,true);
    TestTrue(TEXT("Partly raised moving sail encodes"),Original.SerializeCheckpoint(Writer));
    TestEqual(TEXT("Fixed checkpoint size"),Bytes.Num(),FJapanSailState::CheckpointBytes);
    FJapanSailState Restored; FMemoryReader Reader(Bytes,true);
    TestTrue(TEXT("Partly raised moving sail decodes"),Restored.SerializeCheckpoint(Reader));
    TestTrue(TEXT("Equipped survives correction"),Restored.Equipped);
    TestEqual(TEXT("Action serial survives correction"),Restored.Serial,43u);
    TestEqual(TEXT("Yaw survives before relative steering replay"),Restored.Yaw,-179.f);
    TestEqual(TEXT("Speed survives correction"),Restored.Speed,512.f);
    TestEqual(TEXT("Steering survives correction"),Restored.Steering,-.75f);
    TestEqual(TEXT("Continuous sail phase survives correction"),Restored.SailAmount,.375f);
    TestEqual(TEXT("Sail destination survives correction"),Restored.SailTarget,1.f);
    for (int32 Length=0;Length<Bytes.Num();++Length)
    {
        TArray<uint8> Short=Bytes; Short.SetNum(Length);
        FMemoryReader Truncated(Short,true); FJapanSailState Rejected;
        TestFalse(TEXT("A truncated checkpoint cannot be applied"),Rejected.SerializeCheckpoint(Truncated));
    }
    TArray<uint8> Invalid=Bytes; Invalid[0]=2;
    FMemoryReader InvalidReader(Invalid,true); FJapanSailState Rejected;
    TestFalse(TEXT("Non-boolean equipped flag is rejected"),Rejected.SerializeCheckpoint(InvalidReader));
    FJapanSailState Bad=Original; Bad.Yaw=std::numeric_limits<float>::quiet_NaN();
    TestFalse(TEXT("NaN yaw cannot enter movement"),Bad.IsValid());
    Bad=Original; Bad.Speed=std::numeric_limits<float>::infinity();
    TestFalse(TEXT("Infinite speed cannot enter movement"),Bad.IsValid());
    Bad=Original; Bad.Speed=-.1f; TestFalse(TEXT("Negative sail speed is invalid"),Bad.IsValid());
    Bad=Original; Bad.SailAmount=1.01f; TestFalse(TEXT("Sail phase is bounded"),Bad.IsValid());
    Bad=Original; Bad.SailTarget=.5f; TestFalse(TEXT("Sail target is an input level"),Bad.IsValid());
    return true;
}
#endif
