#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/GameModeBase.h"
#include "JapanWorld.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MegaParkLayout.h"
#include "SuperUltraMegaPark.generated.h"

/** The park's grind paths. In the standalone level, render and collision geometry are ordinary StaticMeshActors and
 *  the game mode spawns this actor from the level's AMegaParkLayout; in the island, Spawn places the park from its
 *  manifest and owns the meshes as components (docs/MEGAPARK.md). */
UCLASS()
class YORIMICHI_API ASuperUltraMegaPark : public AActor
{
    GENERATED_BODY()
public:
    ASuperUltraMegaPark();
    virtual void BeginPlay() override;
    /** Places the park in the island from Content/Data/megapark/park.json: the actor transform, the kept render and
     *  collision meshes (with the seam's) from /Game/MegaPark/Meshes, the original grind paths, the island trees that
     *  replace the original plants and the kei cars that replace its traffic cars. Null if the file is missing. */
    static ASuperUltraMegaPark* Spawn(UWorld* World, const FString& Path);
    bool bGameplayReady = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Source") FMegaParkLayoutData Layout;
private:
    void RegisterRails();
    bool bRailsRegistered = false;
    int32 RegisteredRailCount = 0;
};

/** Standalone park level: uses the existing player without spawning the island over the imported park. */
UCLASS()
class YORIMICHI_API AMegaParkGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AMegaParkGameMode();
    /** -rider=<Name> plays as an adventure character (PlayableCharacter.h). */
    virtual UClass* GetDefaultPawnClassForController_Implementation(AController* Controller) override;
    /** Spawns the park's grind paths and player services from the level's AMegaParkLayout. A level saved before it had
     *  one (an old import) has neither: the error says to rebuild it. */
    virtual void StartPlay() override;
    virtual void BeginPlay() override;
};

/** Player services for an authored level, without generating the island or its effects. */
UCLASS()
class YORIMICHI_API AMegaParkWorld : public AJapanWorld
{
    GENERATED_BODY()
public:
    AMegaParkWorld();
    virtual void BeginPlay() override;
};

/** Review cameras for scenarios: frame a view of the park, then give the player back their camera. */
UCLASS()
class YORIMICHI_API UMegaParkValidation : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool ReviewCamera(FVector Location, FVector Target, float Fov = 65.f);
    UFUNCTION(BlueprintCallable) static void RestorePlayerCamera();
};
