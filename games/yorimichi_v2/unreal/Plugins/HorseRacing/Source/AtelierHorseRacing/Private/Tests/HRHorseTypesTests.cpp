#include "HRHorseTypes.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRHorseTypesTest, "Atelier.HorseRacing.HorseValues",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FHRHorseTypesTest::RunTest(const FString&)
{
    const FHRGenePair Pair(MAX_int32, MAX_int32);
    TestEqual(TEXT("Unadmitted allele values cannot overflow their sum"), Pair.Sum(), int64(MAX_int32) * 2);
    TestEqual(TEXT("First allele retains its exact value"), Pair[0], MAX_int32);
    const FHRGenePair Normal(2, 4);
    TestEqual(TEXT("Valid reference allele sum"), Normal.Sum(), int64(6));
    TestEqual(TEXT("Second allele retains its exact value"), Normal[1], 4);
    FHRHorse Horse;
    Horse.Abilities = {MAX_int32, MAX_int32, MAX_int32, MAX_int32};
    TestEqual(TEXT("Unadmitted ability values cannot overflow their sum"), Horse.AbilitySum(), int64(MAX_int32) * 4);
    Horse.Abilities = {8,8,7,8};
    TestEqual(TEXT("Valid reference abilities retain their score"), Horse.AbilitySum(), int64(31));
    TestNotNull(TEXT("Horse state is reflected in the normal module"), FHRHorse::StaticStruct());
    return true;
}
#endif
