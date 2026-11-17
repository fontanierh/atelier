#include "JapanPreferences.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "HAL/FileManager.h"
#include "AtelierSettings.h"

// JapanPreferences.cpp: the release defaults, the table they are applied to, and early laptop-mode resolution.
const TArray<TPair<const TCHAR*, float>>& JapanReleaseDefaults();
TArray<FJapanPreference> JapanDefaultPreferences(TArray<FString>* Errors);
bool JapanLaptopModeFromSaved(const TMap<FString,FString>& Saved, bool bAutoDefault);

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
    // The preset covers every saved preference.
    for (const FJapanPreference& V : Values)
        TestTrue(FString::Printf(TEXT("%s has a release default"), *V.Key),
            JapanReleaseDefaults().ContainsByPredicate([&](const TPair<const TCHAR*, float>& D) { return V.Key == D.Key; }));
    for (const TCHAR* Retired : {TEXT("desktop"), TEXT("cairo_botw"), TEXT("moveset"), TEXT("shield"), TEXT("soundbank"), TEXT("light_version")})
        TestNull(FString::Printf(TEXT("%s is not a preference"), Retired), Find(Retired));
    // A few of the changed defaults, spelled out.
    const TPair<const TCHAR*, float> Spot[] = {{TEXT("volume"), .3f}, {TEXT("skate_volume"), .5f}, {TEXT("soften_skate"), 1.f},
        {TEXT("soften_footsteps"), 1.f}, {TEXT("goofy"), 1.f}, {TEXT("stamina_rings"), 5.f}, {TEXT("fog_density"), .03f},
        {TEXT("tree_lod_mode"), 0.f}, {TEXT("skate_mode"), 3.f}, {TEXT("skate_grind_friction"), .55f}};
    for (const TPair<const TCHAR*, float>& S : Spot)
        if (const FJapanPreference* V = Find(S.Key)) TestEqual(FString::Printf(TEXT("%s default"), S.Key), V->Value, S.Value);
    return true;
}

// Early laptop-mode detection (UJapanPreferences::IsLaptopModeConfigured) honors -set= overrides over the saved
// settings file, explicit 0 or 1 over the hardware auto-default, and the hardware auto-default when absent.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanLaptopModePrecedenceTest,"Yorimichi.Preferences.LaptopModePrecedence",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanLaptopModePrecedenceTest::RunTest(const FString&)
{
    const TMap<FString,FString> Absent;
    const TMap<FString,FString> Zero = {{TEXT("laptop"), TEXT("0")}};
    const TMap<FString,FString> One = {{TEXT("laptop"), TEXT("1")}};
    TestFalse(TEXT("Absent with desktop hardware default stays off"), JapanLaptopModeFromSaved(Absent, false));
    TestTrue(TEXT("Absent with laptop hardware default turns on"), JapanLaptopModeFromSaved(Absent, true));
    TestFalse(TEXT("Explicit 0 overrides laptop hardware default"), JapanLaptopModeFromSaved(Zero, true));
    TestTrue(TEXT("Explicit 1 overrides desktop hardware default"), JapanLaptopModeFromSaved(One, false));

    const FString SavedCmdLine = FCommandLine::Get();
    const FString TempPath = FPaths::ConvertRelativePathToFull(
        FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Automation"), TEXT("laptop_precedence_settings.txt")));
    ON_SCOPE_EXIT
    {
        FCommandLine::Set(*SavedCmdLine);
        IFileManager::Get().Delete(*TempPath);
    };

    IFileManager::Get().Delete(*TempPath);
    FCommandLine::Set(*FString::Printf(TEXT("-preferencesfile=\"%s\""), *TempPath));
    const bool bHardwareDefault = UJapanPreferences::IsLaptopModeConfigured();

    TestTrue(TEXT("Write saved laptop=0"), AtelierSettings::WriteFile(TempPath, Zero));
    TestFalse(TEXT("Saved laptop=0 disables laptop mode"), UJapanPreferences::IsLaptopModeConfigured());

    FCommandLine::Set(*FString::Printf(TEXT("-preferencesfile=\"%s\" -set=laptop=1"), *TempPath));
    TestTrue(TEXT("-set=laptop=1 overrides saved laptop=0"), UJapanPreferences::IsLaptopModeConfigured());

    TestTrue(TEXT("Write saved laptop=1"), AtelierSettings::WriteFile(TempPath, One));
    FCommandLine::Set(*FString::Printf(TEXT("-preferencesfile=\"%s\""), *TempPath));
    TestTrue(TEXT("Saved laptop=1 enables laptop mode"), UJapanPreferences::IsLaptopModeConfigured());

    FCommandLine::Set(*FString::Printf(TEXT("-preferencesfile=\"%s\" -set=laptop=0"), *TempPath));
    TestFalse(TEXT("-set=laptop=0 overrides saved laptop=1"), UJapanPreferences::IsLaptopModeConfigured());

    IFileManager::Get().Delete(*TempPath);
    FCommandLine::Set(*FString::Printf(TEXT("-preferencesfile=\"%s\""), *TempPath));
    TestEqual(TEXT("Missing file without -set falls back to hardware default"),
        UJapanPreferences::IsLaptopModeConfigured(), bHardwareDefault);
    return true;
}
#endif
