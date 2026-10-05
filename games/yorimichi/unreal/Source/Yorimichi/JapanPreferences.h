#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "SkateFeel.h"
#include "JapanPreferences.generated.h"

class AWandererCharacter;
class SWidget;
class UMaterialInstanceDynamic;
struct FJapanPreference
{
    FString Key, Label;
    float Value, Minimum, Maximum;
    float Step = 0.f;       // a slider's increment (keys, gamepad, and the value it rounds to); 0: continuous
};

/** World and camera preferences belong to the game UI, independently of the animation system. */
UCLASS()
class YORIMICHI_API UJapanPreferences : public UObject
{
    GENERATED_BODY()
public:
    void Initialize(AWandererCharacter* Pawn);
    void Apply();
    const TArray<FJapanPreference>& GetValues() const { return Values; }
    bool SetValue(const FString& Key, float Value);
    void ToggleMenu();
    // Every Light key back to its default.
    void ResetLight();
    /** Opens the menu on its Skate feel page. */
    void OpenSkateMenu() { OpenMenu(true); }
    /** The skate_ values as the board's feel (FSkateFeel; docs/SKATE.md, "Feel"). */
    FSkateFeel GetSkateFeel() const;
    void CloseMenu();
    bool ShowFrameRate() const { return Get(TEXT("show_fps")) > .5f; }
    // Keys chosen per launch and never written to the shared settings file.
    static bool IsSessionOnly(const FString& Key);
    // Log the effective profile after applying, read back from the console variables themselves.
    void ReportProfile() const;
    // A setting as saved (the settings file, then -set= overrides), for a character choosing its definition before
    // its own preferences exist.
    static float Saved(const FString& Key, float Default);
private:
    UPROPERTY() TObjectPtr<AWandererCharacter> Owner;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
    TArray<FJapanPreference> Values;
    TMap<FString,FString> SavedValues;
    TMap<FString,float> DefaultValues;
    FString SettingsFile;
    TSharedPtr<SWidget> Menu;
    int32 AppliedPerformanceMode = -1;
    /** Show the menu's main page, or its Skate feel page. */
    void OpenMenu(bool bSkate);
    /** Every skate_ value back to the game's defaults (DefaultGame.ini and stock feel). */
    /** Custom's values (bCustom) or the stick, mouse and camera, back to their defaults. */
    void ResetSkate(bool bCustom);
    /** Every custom value is stock (the base difficulty aside). */
    bool IsSkateCustomStock() const;
    float Get(const TCHAR* Key) const;
    void Save();
    static bool IsToggle(const FString& Key);
    static FString FilePath();
    static TMap<FString,FString> ReadSaved();
};
