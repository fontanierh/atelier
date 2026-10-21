#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "FoliageBuilder.generated.h"

class UStaticMesh;
class UMaterialInterface;

/** Shared derivative adapter; only StampSourceRoles writes metadata at the source import boundary. */
UCLASS()
class YORIMICHIIMPORT_API UYorimichiFoliageBuilder : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Source import boundary: certify UV5 face roles in cooked slot names. */
    UFUNCTION(BlueprintCallable) static bool StampSourceRoles(UStaticMesh* Source);
    /** Synchronous commandlet collection; no future editor tick is required. */
    UFUNCTION(BlueprintCallable) static void CollectUnused();
    /** Explicit Entry-map diagnostic only: register Python-created review instances; never publishes readiness. */
    UFUNCTION(BlueprintCallable) static int32 RegisterReviewInstances(UWorld* World);
    UFUNCTION(BlueprintCallable) static bool MaterialIsMasked(UMaterialInterface* Material);
    UFUNCTION(BlueprintCallable) static bool MaterialUsesFoliageShading(UMaterialInterface* Material);
    UFUNCTION(BlueprintCallable) static bool ExportSource(UStaticMesh* Source, const TArray<int32>& LeafSlots,
        const FString& Classification, const FString& Kind, const FString& Path, int32 LODIndex=0);
    UFUNCTION(BlueprintCallable) static UStaticMesh* BuildVariant(UStaticMesh* Source, const FString& JsonPath,
        const FString& Destination, UMaterialInterface* NearCanopy, UMaterialInterface* FarCanopy, bool ShadowOnly);
};
