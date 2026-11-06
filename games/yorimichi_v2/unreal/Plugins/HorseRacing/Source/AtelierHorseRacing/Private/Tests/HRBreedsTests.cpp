#include "HRBreeds.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRBreedsTest, "Atelier.HorseRacing.BreedInheritance",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FHRBreedsTest::RunTest(const FString&)
{
    // Complete dominance table; rows are maternal alleles, columns paternal.
    const TCHAR* Expected[4][4] = {
        {TEXT("Standard"), TEXT("Giant"), TEXT("Standard"), TEXT("Standard")},
        {TEXT("Giant"), TEXT("Giant"), TEXT("Giant"), TEXT("Giant")},
        {TEXT("Standard"), TEXT("Giant"), TEXT("Bone"), TEXT("Standard")},
        {TEXT("Standard"), TEXT("Giant"), TEXT("Standard"), TEXT("Spirit")}};
    for (int32 A = 0; A < 4; ++A)
        for (int32 B = 0; B < 4; ++B)
        {
            FString Out;
            const FHRGenePair Pair(A, B);
            TestTrue(TEXT("All valid allele combinations are accepted"), HRBreeds::TryExpress(&Pair, Out));
            TestEqual(FString::Printf(TEXT("Dominance %d/%d"), A, B), Out, FString(Expected[A][B]));
        }
    FString Breed;
    TestTrue(TEXT("A missing gene has the standard phenotype"), HRBreeds::TryExpress(nullptr, Breed));
    TestEqual(TEXT("Missing-gene phenotype"), Breed, FString(TEXT("Standard")));

    // Independently evaluated UTF-16/JSON reference vectors, including founder fallback per side.
    FHRGenePair Child;
    TestTrue(TEXT("Founder generation succeeds"), HRBreeds::TryGenerate(TEXT("seed"), nullptr, nullptr, Child));
    TestEqual(TEXT("Founder maternal reference"), Child.A, 0);
    TestEqual(TEXT("Founder paternal reference"), Child.B, 3);
    TMap<FString, FHRGenePair> Mother, Father;
    Mother.Add(HRBreeds::Gene, FHRGenePair(2, 3));
    Father.Add(HRBreeds::Gene, FHRGenePair(1, 0));
    TestTrue(TEXT("Inheritance succeeds"), HRBreeds::TryGenerate(TEXT("seed"), &Mother, &Father, Child));
    TestEqual(TEXT("Mother contributes her second allele"), Child.A, 3);
    TestEqual(TEXT("Father contributes his first allele"), Child.B, 1);
    TestTrue(TEXT("An absent maternal gene uses only that side's founder draw"),
        HRBreeds::TryGenerate(TEXT("seed"), nullptr, &Father, Child));
    TestEqual(TEXT("Missing maternal reference"), Child.A, 0);
    TestEqual(TEXT("Present paternal reference"), Child.B, 1);
    TMap<FString, FHRGenePair> Empty;
    TestTrue(TEXT("An existing genome without breed also uses founder fallback"),
        HRBreeds::TryGenerate(TEXT("seed"), &Mother, &Empty, Child));
    TestEqual(TEXT("Present maternal reference"), Child.A, 3);
    TestEqual(TEXT("Missing paternal reference"), Child.B, 3);
    TestTrue(TEXT("Non-BMP seed inheritance succeeds"), HRBreeds::TryGenerate(TEXT("é🦊"), &Mother, &Father, Child));
    TestEqual(TEXT("Non-BMP maternal reference"), Child.A, 2);
    TestEqual(TEXT("Non-BMP paternal reference"), Child.B, 0);
    TestEqual(TEXT("Mother remains unchanged"), Mother.FindChecked(HRBreeds::Gene)[1], 3);
    TestEqual(TEXT("Father remains unchanged"), Father.FindChecked(HRBreeds::Gene)[0], 1);

    Mother.Add(TEXT("other"), FHRGenePair(42, 73));
    Father.Add(TEXT("other"), FHRGenePair(19, 27));
    for (auto* Genome : {&Mother, &Father})
        for (const FString Key : {FString(HRBreeds::Gene), FString(TEXT("other"))})
        {
            FHRGenePair& Aliased = Genome->FindChecked(Key);
            const FHRGenePair Before = Aliased;
            TestFalse(TEXT("An output alias to either parent's gene is rejected"),
                HRBreeds::TryGenerate(TEXT("seed"), &Mother, &Father, Aliased));
            TestEqual(TEXT("Rejected alias preserves first allele"), Aliased.A, Before.A);
            TestEqual(TEXT("Rejected alias preserves second allele"), Aliased.B, Before.B);
        }

    for (const int32 Invalid : {MIN_int32, -1, 4, MAX_int32})
        for (int32 Side = 0; Side < 2; ++Side)
        {
            const FHRGenePair Bad = Side == 0 ? FHRGenePair(Invalid, 0) : FHRGenePair(0, Invalid);
            Breed = TEXT("unchanged");
            TestFalse(TEXT("Malformed phenotype is rejected"), HRBreeds::TryExpress(&Bad, Breed));
            TestEqual(TEXT("Rejected phenotype preserves output"), Breed, FString(TEXT("unchanged")));
            TMap<FString, FHRGenePair> BadGenome;
            BadGenome.Add(HRBreeds::Gene, Bad);
            for (int32 Parent = 0; Parent < 2; ++Parent)
            {
                Child = FHRGenePair(42, 73);
                TestFalse(TEXT("Either malformed parent is rejected"), HRBreeds::TryGenerate(TEXT("seed"),
                    Parent == 0 ? &BadGenome : &Mother, Parent == 1 ? &BadGenome : &Father, Child));
                TestEqual(TEXT("Rejected inheritance preserves maternal output"), Child.A, 42);
                TestEqual(TEXT("Rejected inheritance preserves paternal output"), Child.B, 73);
            }
        }
    return true;
}
#endif
