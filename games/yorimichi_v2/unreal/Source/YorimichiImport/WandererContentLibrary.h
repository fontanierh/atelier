#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "WandererContentLibrary.generated.h"

class UAnimSequence;
class UBlendSpace;
class USkeletalMesh;

/** Headless content authoring support; the resulting blend spaces are ordinary saved assets. */
UCLASS()
class YORIMICHIIMPORT_API UWandererContentLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="Wanderer|Authoring")
    static bool ConfigureBlendSpace(UBlendSpace* Asset, const TArray<UAnimSequence*>& Clips, const TArray<float>& Speeds);
    /** The same, each sample playing at its own rate (an adventure move set's locomotion plays one clip at several rates). */
    UFUNCTION(BlueprintCallable, Category="Wanderer|Authoring")
    static bool ConfigureBlendSpaceWithRates(UBlendSpace* Asset, const TArray<UAnimSequence*>& Clips, const TArray<float>& Speeds, const TArray<float>& Rates);
    UFUNCTION(BlueprintCallable, Category="Wanderer|Authoring")
    static bool ConfigureMeshLODs(USkeletalMesh* Asset);
};
