#include "JapanPreferences.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "AtelierSettings.h"
#include "WandererCharacter.h"

// JapanPreferences.cpp: what Initialize applies from a saved file, and what Save writes.
TArray<FJapanPreference> JapanDefaultPreferences(TArray<FString>* Errors);
void JapanApplySaved(TArray<FJapanPreference>& Values, const TMap<FString,FString>& Saved);
TMap<FString,FString> JapanValuesToSave(const TMap<FString,FString>& Saved, const TArray<FJapanPreference>& Values);

// Original is the only soundbank (operator 494). A settings file saved when soundbank was 1, 2 or 3 (the retired
// alternatives) loads exactly as Original: the key changes no preference, and the next save drops it while keeping
// every other key. The file is written and read back with the game's own settings format.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanRetiredSoundbankSaveTest,"Yorimichi.Preferences.RetiredSoundbankSave",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanRetiredSoundbankSaveTest::RunTest(const FString&)
{
    const TArray<FJapanPreference> Defaults = JapanDefaultPreferences(nullptr);
    const FString Path = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Automation"), TEXT("retired_soundbank_settings.txt"));
    for (const int32 Bank : {1, 2, 3})
    {
        const TMap<FString,FString> Old = {{TEXT("soundbank"), FString::FromInt(Bank)}, {TEXT("volume"), TEXT("0.7")},
            {TEXT("music"), TEXT("0")}, {TEXT("a_key_from_another_build"), TEXT("4")}};
        TestTrue(TEXT("The old file is written"), AtelierSettings::WriteFile(Path, Old));
        const TMap<FString,FString> Read = AtelierSettings::ReadFile(Path);
        TestEqual(FString::Printf(TEXT("soundbank=%d reads back"), Bank), Read.FindRef(TEXT("soundbank")), FString::FromInt(Bank));

        TArray<FJapanPreference> Values = Defaults;
        JapanApplySaved(Values, Read);
        TestNull(TEXT("soundbank is not a preference"), Values.FindByPredicate([](const FJapanPreference& V) { return V.Key.Contains(TEXT("soundbank")); }));
        for (int32 I = 0; I < Values.Num(); ++I)
        {
            const FString& Key = Values[I].Key;
            const float Want = Key == TEXT("volume") ? .7f : Key == TEXT("music") ? 0.f : Defaults[I].Value;
            TestEqual(FString::Printf(TEXT("soundbank=%d: %s loads as with Original"), Bank, *Key), Values[I].Value, Want);
        }

        const TMap<FString,FString> Next = JapanValuesToSave(Read, Values);
        TestFalse(FString::Printf(TEXT("Save drops soundbank=%d"), Bank), Next.Contains(TEXT("soundbank")));
        TestEqual(TEXT("Save keeps the saved volume"), FCString::Atof(*Next.FindRef(TEXT("volume"))), .7f);
        TestEqual(TEXT("Save keeps music off"), FCString::Atof(*Next.FindRef(TEXT("music"))), 0.f);
        TestEqual(TEXT("Save keeps a key it does not know"), Next.FindRef(TEXT("a_key_from_another_build")), FString(TEXT("4")));
        TestTrue(TEXT("The saved file is written"), AtelierSettings::WriteFile(Path, Next));
        TestFalse(TEXT("The written file has no soundbank"), AtelierSettings::ReadFile(Path).Contains(TEXT("soundbank")));
    }
    IFileManager::Get().Delete(*Path);
    return true;
}

// The live menu (main page and Skate feel page) of the running game has no soundbank control: no bank picker and no
// bank preview. Run from a game (atelier play), where the player's preferences exist.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanRetiredSoundbankMenuTest,"Yorimichi.Preferences.RetiredSoundbankMenu",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanRetiredSoundbankMenuTest::RunTest(const FString&)
{
    UJapanPreferences* Preferences = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (UWorld* World = Context.World(); World && World->IsGameWorld())
            if (APlayerController* PC = World->GetFirstPlayerController())
                if (auto* Pawn = Cast<AWandererCharacter>(PC->GetPawn())) Preferences = Pawn->GetPreferences();
    if (!TestNotNull(TEXT("A running game with the player's preferences (run in play)"), Preferences)) return false;
    const bool bWasOpen = Preferences->IsMenuOpen();
    if (bWasOpen) Preferences->CloseMenu();
    for (const bool bSkate : {false, true})
    {
        if (bSkate) Preferences->OpenSkateMenu(); else Preferences->ToggleMenu();
        const TArray<FString> Keys = Preferences->MenuControlKeys();
        const TCHAR* Page = bSkate ? TEXT("Skate feel page") : TEXT("main page");
        TestTrue(FString::Printf(TEXT("The %s is open with its controls"), Page), Keys.Num() > 5);
        for (const FString& Key : Keys)
            TestFalse(FString::Printf(TEXT("%s control %s is not a soundbank control"), Page, *Key), Key.Contains(TEXT("soundbank")));
        TestTrue(FString::Printf(TEXT("The %s is the real menu"), Page),
            Keys.Contains(bSkate ? FString(TEXT("back")) : FString(TEXT("skate_feel"))));
        Preferences->CloseMenu();
    }
    return true;
}
#endif
