#include "JapanPreferences.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

// JapanPreferences.cpp: the release defaults and the table they are applied to.
const TArray<TPair<const TCHAR*, float>>& JapanReleaseDefaults();
TArray<FJapanPreference> JapanDefaultPreferences(TArray<FString>* Errors);

// The operator's preset (tests/fixtures/operator393-defaults.txt) is what a fresh install starts from: every value
// applies exactly, none is refused, and only retired or separately kept keys stay out of the preferences.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanReleaseDefaultsTest,"Yorimichi.Preferences.ReleaseDefaults",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanReleaseDefaultsTest::RunTest(const FString&)
{
    TArray<FString> Errors;
    const TArray<FJapanPreference> Values = JapanDefaultPreferences(&Errors);
    TestEqual(TEXT("Every release default names a preference within its range"), Errors.Num(), 0);
    for (const FString& Error : Errors) AddError(Error);
    auto Find = [&](const FString& Key) { return Values.FindByPredicate([&](const FJapanPreference& V) { return V.Key == Key; }); };
    for (const TPair<const TCHAR*, float>& Default : JapanReleaseDefaults())
    {
        const FJapanPreference* V = Find(Default.Key);
        if (!TestNotNull(FString::Printf(TEXT("%s is a preference"), Default.Key), V)) continue;
        TestTrue(FString::Printf(TEXT("%s starts at exactly %g (table %g)"), Default.Key, Default.Value, V->Value), V->Value == Default.Value);
    }
    // The preset covers every saved preference; desktop is a launch flag, never saved.
    for (const FJapanPreference& V : Values)
        if (V.Key != TEXT("desktop"))
            TestTrue(FString::Printf(TEXT("%s has a release default"), *V.Key),
                JapanReleaseDefaults().ContainsByPredicate([&](const TPair<const TCHAR*, float>& D) { return V.Key == D.Key; }));
    for (const TCHAR* Retired : {TEXT("cairo_botw"), TEXT("moveset"), TEXT("shield"), TEXT("soundbank"), TEXT("light_version")})
        TestNull(FString::Printf(TEXT("%s is not a preference"), Retired), Find(Retired));
    // A few of the changed defaults, spelled out.
    const TPair<const TCHAR*, float> Spot[] = {{TEXT("volume"), .3f}, {TEXT("skate_volume"), .5f}, {TEXT("soften_skate"), 1.f},
        {TEXT("soften_footsteps"), 1.f}, {TEXT("goofy"), 1.f}, {TEXT("stamina_rings"), 5.f}, {TEXT("fog_density"), .03f},
        {TEXT("tree_lod_mode"), 2.f}, {TEXT("skate_mode"), 3.f}, {TEXT("skate_grind_friction"), .55f}};
    for (const TPair<const TCHAR*, float>& S : Spot)
        if (const FJapanPreference* V = Find(S.Key)) TestEqual(FString::Printf(TEXT("%s default"), S.Key), V->Value, S.Value);
    return true;
}
#endif
