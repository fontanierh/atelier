#include "HRRandom.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRRandomTest, "Atelier.HorseRacing.Random",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FHRRandomTest::RunTest(const FString&)
{
    // Reference vectors from Polozer/atelier PR3, cf3af197; extra escaped/non-BMP
    // vectors were independently calculated with JavaScript UTF-16/JSON.stringify.
    TestEqual(TEXT("Empty hash"), HRRandom::Hash(TEXT("")), 1947474976u);
    TestEqual(TEXT("ASCII hash"), HRRandom::Hash(TEXT("abc")), 2319914504u);
    TestEqual(TEXT("JSON key hash"), HRRandom::Hash(TEXT("[\"s\",\"t\",0]")), 1462672135u);
    TestEqual(TEXT("Accented hash"), HRRandom::Hash(TEXT("Écurie du Pont Clair")), 1916566790u);
    TestEqual(TEXT("Non-BMP UTF-16 hash"), HRRandom::Hash(TEXT("é🦊")), 4271627443u);
    TestEqual(TEXT("Small draw"), HRRandom::Draw(TEXT("seed"), TEXT("tag"), 6), 4);
    TestEqual(TEXT("Large draw"), HRRandom::Draw(TEXT("x"), TEXT("y"), 1000003), 345669);
    TestEqual(TEXT("Escaped key and non-BMP tag"), HRRandom::Draw(TEXT("a\"b\\c\n"), TEXT("é🦊"), 81), 16);
    TestEqual(TEXT("Maximum supported bound"), HRRandom::Draw(TEXT("seed"), TEXT("max"), MAX_int32), 1830695355);
    FString LoneHigh, LoneLow;
    LoneHigh.AppendChar(TCHAR(0xd800)); LoneLow.AppendChar(TCHAR(0xdc00));
    TestEqual(TEXT("Lone high surrogate uses well-formed JSON escaping"), HRRandom::Draw(LoneHigh, TEXT("tag"), 81), 34);
    TestEqual(TEXT("Lone low surrogate uses well-formed JSON escaping"), HRRandom::Draw(LoneLow, TEXT("tag"), 81), 65);
    for (int64 Bound : {int64(0), int64(-1), int64(MAX_int32) + 1, int64(1) << 32, int64(MAX_int64)})
    {
        int32 Out = 73;
        TestFalse(TEXT("Invalid bound is rejected without a rejection loop"), HRRandom::TryDraw(TEXT("seed"), TEXT("bad"), Bound, Out));
        TestEqual(TEXT("Invalid draw leaves output untouched"), Out, 73);
    }
    for (const TArray<int64>& Weights : {TArray<int64>{}, TArray<int64>{0,0}, TArray<int64>{1,-1},
             TArray<int64>{MAX_int64,1}, TArray<int64>{MAX_int32,1}})
    {
        int32 Out = 73;
        TestFalse(TEXT("Invalid weights fail without overflow"), HRRandom::TryPickWeighted(TEXT("seed"), TEXT("bad"), Weights, Out));
        TestEqual(TEXT("Invalid weights leave output untouched"), Out, 73);
    }
    int32 Only = -1;
    TestTrue(TEXT("Zero-weight alternatives are valid"), HRRandom::TryPickWeighted(TEXT("seed"), TEXT("weights"), {0,7,0}, Only));
    TestEqual(TEXT("Zero weights never win"), Only, 1);
    const TArray<int32> Original{0,1,2,3,4};
    const TArray<int32> Shuffled = HRRandom::Shuffled(Original, TEXT("seed"), TEXT("order"));
    TestTrue(TEXT("Shuffle retains the reference tag sequence"), Shuffled == TArray<int32>{0,4,2,1,3});
    TestTrue(TEXT("Shuffle does not mutate its input"), Original == TArray<int32>{0,1,2,3,4});
    FString EmbeddedNullTag = TEXT("a_b");
    EmbeddedNullTag[1] = TCHAR(0);
    TestEqual(TEXT("Embedded NUL fixture retains its full length"), EmbeddedNullTag.Len(), 3);
    TestTrue(TEXT("Shuffle retains embedded NUL in semantic tags"),
        HRRandom::Shuffled(Original, TEXT("seed"), EmbeddedNullTag) == TArray<int32>{1,4,0,2,3});
    HRRandom::Draw(TEXT("unrelated"), TEXT("operation"), 91);
    TestEqual(TEXT("Other draws cannot change a previous semantic draw"), HRRandom::Draw(TEXT("seed"), TEXT("tag"), 6), 4);
    return true;
}
#endif
