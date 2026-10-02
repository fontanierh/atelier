#pragma once
#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "SkateSettings.generated.h"

class USkateProfile;

/** Select the game's cooked skating profile in DefaultGame.ini. All tuning and content live in that asset. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Atelier Skate"))
class ATELIERSKATE_API USkateSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    USkateSettings();
    /** Cooked runtime data, collision catalogs, tuning, board and sound references. */
    UPROPERTY(Config, EditAnywhere, Category = "Skate") TSoftObjectPtr<USkateProfile> DefaultProfile;
};
