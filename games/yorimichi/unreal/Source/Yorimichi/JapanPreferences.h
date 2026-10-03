#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "JapanPreferences.generated.h"

class AWandererCharacter;
class SWidget;
class UMaterialInstanceDynamic;
struct FJapanPreference
{
    FString Key, Label;
    float Value, Minimum, Maximum;
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
    FString SettingsFile;
    TSharedPtr<SWidget> Menu;
    int32 AppliedPerformanceMode = -1;
    float Get(const TCHAR* Key) const;
    void Save();
    static bool IsToggle(const FString& Key);
    static FString FilePath();
    static TMap<FString,FString> ReadSaved();
};
