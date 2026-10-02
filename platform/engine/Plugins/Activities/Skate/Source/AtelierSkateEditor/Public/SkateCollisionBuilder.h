#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkateCollisionBuilder.generated.h"
class UWorld;
class UStaticMesh;
class USkateCollisionAsset;

/** Explicit validation result for Python, which treats bool returns with out parameters as success flags. */
USTRUCT(BlueprintType)
struct ATELIERSKATEEDITOR_API FSkateCollisionValidationReport
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category="Skate|Collision")
    bool bValid = false;

    UPROPERTY(BlueprintReadOnly, Category="Skate|Collision")
    TArray<FString> Errors;

    UPROPERTY(BlueprintReadOnly, Category="Skate|Collision")
    TArray<FString> Warnings;
};

/** Editor-only baking: no render CPU access is needed by the cooked runtime. */
UCLASS()
class ATELIERSKATEEDITOR_API USkateCollisionBuilderLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Strip render CPU retention on explicit world meshes without changing their collision geometry.
     * Finish compilation, save if requested, then bake/validate the final catalog before cooking.
     * Caller may exclude diagnostic experiment meshes; skeletal meshes are never accepted here. */
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static bool StripWorldMeshCpuAccess(const TArray<UStaticMesh*>& Meshes,bool bSave,
        TArray<FString>& Errors,TArray<FString>& Warnings);
    /** Bake explicit meshes, including unloaded streamed maps' assets supplied by the caller. */
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static USkateCollisionAsset* BuildCatalog(const TArray<UStaticMesh*>& Meshes,const FString& CatalogPackage,
        bool bSave,TArray<FString>& Errors,TArray<FString>& Warnings);
    /** Collect all currently loaded blocking static/instanced meshes in a world. */
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static USkateCollisionAsset* BuildForWorld(UWorld* World,const FString& CatalogPackage,
        bool bSave,TArray<FString>& Errors,TArray<FString>& Warnings);
    /** Explicit source loading is editor-only. Checks every mesh at identity, reflection and nonuniform transforms. */
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static bool ValidateCatalog(USkateCollisionAsset* Catalog,bool bLoadSourceMeshes,TArray<FString>& Errors,TArray<FString>& Warnings);
    /** Transient real components exercise material mapping and register/move/remove/ISM/rail scene detection. */
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static bool ValidateSurfaceAndScene(UWorld* World,UStaticMesh* FixtureMesh,USkateCollisionAsset* Catalog,TArray<FString>& Errors,TArray<FString>& Warnings);
    /** Compare the former live CPU-buffer snapshot with the cooked path at every loaded instance transform. */
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static bool ValidateWorld(UWorld* World,USkateCollisionAsset* Catalog,TArray<FString>& Errors,TArray<FString>& Warnings);

    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static FSkateCollisionValidationReport StripWorldMeshCpuAccessReport(const TArray<UStaticMesh*>& Meshes,bool bSave);
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static FSkateCollisionValidationReport ValidateCatalogReport(USkateCollisionAsset* Catalog,bool bLoadSourceMeshes);
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static FSkateCollisionValidationReport ValidateWorldReport(UWorld* World,USkateCollisionAsset* Catalog);
    UFUNCTION(BlueprintCallable, Category="Skate|Collision")
    static FSkateCollisionValidationReport ValidateSurfaceAndSceneReport(UWorld* World,UStaticMesh* FixtureMesh,USkateCollisionAsset* Catalog);
};
