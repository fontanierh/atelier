#include "V2ScenePatch.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FV2ManifestCoverageTest,"Yorimichi.V2.ManifestCoverage",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FV2ManifestCoverageTest::RunTest(const FString&)
{
    TStrongObjectPtr<AV2WorldManifest> Manifest(NewObject<AV2WorldManifest>());
    // Two regions sharing the edge X = -12800, as w01-start and w04-pier-approach do.
    Manifest->MigratedBoundsCm.Add(FBox2D(FVector2D(-25600, 0), FVector2D(-12800, 12800)));
    Manifest->MigratedBoundsCm.Add(FBox2D(FVector2D(-12800, 0), FVector2D(0, 25600)));
    TestTrue(TEXT("Inside the first"), Manifest->CoversInstance(FVector2D(-20000, 100)));
    TestTrue(TEXT("Min edge is inside"), Manifest->CoversInstance(FVector2D(-25600, 0)));
    TestTrue(TEXT("Shared edge belongs to the second"), Manifest->CoversInstance(FVector2D(-12800, 12900)));
    TestFalse(TEXT("Max edge is outside"), Manifest->CoversInstance(FVector2D(0, 100)));
    TestFalse(TEXT("Max Y edge is outside"), Manifest->CoversInstance(FVector2D(-20000, 12800)));
    TestFalse(TEXT("Elsewhere"), Manifest->CoversInstance(FVector2D(5000, 5000)));
    const FBox2D First = Manifest->MigratedBoundsCm[0], Second = Manifest->MigratedBoundsCm[1];
    const FVector2D Edge(-12800, 6400);
    TestTrue(TEXT("A shared-edge point is in exactly one region"),
        AV2WorldManifest::InsideHalfOpen(First, Edge) != AV2WorldManifest::InsideHalfOpen(Second, Edge));
    TestTrue(TEXT("Services run unless the map is a slice"), Manifest->Runs(TEXT("Ferry")));
    Manifest->bOnlyMigrated = true;
    Manifest->RuntimeServices.Add(TEXT("SkatePark"));
    TestTrue(TEXT("A slice covers every instance"), Manifest->CoversInstance(FVector2D(5000, 5000)));
    TestTrue(TEXT("A slice keeps its listed service"), Manifest->Runs(TEXT("SkatePark")));
    TestFalse(TEXT("A slice drops the rest"), Manifest->Runs(TEXT("Ferry")));
    Manifest->MigratedServices.Add(TEXT("Sea"));
    TestTrue(TEXT("A listed service is saved"), Manifest->CoversService(TEXT("Sea")));
    TestFalse(TEXT("An unlisted one is not"), Manifest->CoversService(TEXT("SkyDome")));
    return true;
}
#endif
