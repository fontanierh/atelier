#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BelmonteRegion.generated.h"

class AJapanWorld;
class FJsonObject;

/** Belmonte's town and countryside, assembled from the committed environmental library.
 *  The island owns gameplay; this actor owns static scenery and no Haras systems. */
UCLASS()
class YORIMICHI_API ABelmonteRegion : public AActor
{
    GENERATED_BODY()
public:
    ABelmonteRegion();
    static void Clear(const TSharedPtr<FJsonObject>& WorldData, const FString& Path);
    static ABelmonteRegion* Spawn(AJapanWorld* Landscape, const FString& Path);
    UFUNCTION(BlueprintCallable, Category = "Review") static int32 ReviewPendingShaderJobs();
    UFUNCTION(BlueprintCallable, Category = "Review") static FString ReviewMeshColours(const FString& Name);
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") bool bGameplayReady = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") int32 SceneryInstances = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") int32 PlantInstances = 0;
};
