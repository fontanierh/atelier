#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "SkateSettings.generated.h"

/** Rolling resistance for surfaces whose material name contains one of Keywords (comma-separated). */
USTRUCT()
struct FSkateSurfaceRule
{
    GENERATED_BODY()
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FString Keywords;
    /** 1 is smooth concrete; grass is about 20. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") float Drag = 1.f;
};

/** What skateboarding needs from the game, set in its DefaultGame.ini under [/Script/AtelierSkate.SkateSettings]. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Atelier Skate"))
class ATELIERSKATE_API USkateSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    USkateSettings();
    /** Use the complete recovered runtime when its local binary and converted banks are installed. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") bool UseRetailRuntime = true;
    /** Original controller preset: easy, normal or hardcore. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FString Difficulty = TEXT("normal");
    /** 0 loose / 1 tight; feeds the original steering scalar. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate", meta=(ClampMin="0", ClampMax="1")) float TruckTightness = .5f;
    /** The board parts (the board contract in the plugin README: deck top 9.05 cm above the ground, X nose). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath DeckMesh;
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath TruckMesh;
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FSoftObjectPath WheelMesh;
    /** Content folder of the board sounds: loops roll_01, grind_01, slide_01, skid_01, scrape_01 and one-shot banks
     *  <cue>_01.. (pop, land, ...). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") FString SoundFolder;
    /** Body hitting the ground in a bail (the "fall" cue). */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") TArray<FSoftObjectPath> FallSounds;
    /** First matching rule wins; anything else rolls as smooth concrete. Actors tagged SkatePark are always smooth. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") TArray<FSkateSurfaceRule> Surfaces;
};
