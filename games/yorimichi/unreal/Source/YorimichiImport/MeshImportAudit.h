#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MeshImportAudit.generated.h"

class UStaticMesh;
class USkeletalMesh;

/** Editor observations after the selected mesh's pending builds complete, not a cook certificate. */
USTRUCT(BlueprintType)
struct FMeshDerivedDataAudit
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 Version = 1;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") FString Error;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool Completed = false;
    // -1 preserves an unavailable CVar or queue; absence must not masquerade as disabled/idle.
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 GenerateDistanceFields = -1;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 GenerateCards = -1;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 DistanceFieldTasks = -1;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 CardTasks = -1;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool MeshRequestsDistanceField = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool HasSourceSettings = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") float DistanceFieldResolutionScale = 0;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 MaxLumenMeshCards = 0;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool HasDistanceField = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool DistanceFieldValid = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool DistanceFieldBoundsFinite = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool DistanceFieldAsyncBuilding = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int64 AlwaysLoadedBytes = 0;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int64 StreamableBytes = 0;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") TArray<FIntVector> MipDimensions;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") TArray<int32> MipBricks;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool HasCards = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") bool CardBoundsFinite = false;
    UPROPERTY(BlueprintReadOnly, Category="Import audit") int32 CardCount = 0;
};

/** Import audit: exports the actual built LOD geometry for source comparison. */
UCLASS()
class YORIMICHIIMPORT_API UMeshImportAudit : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool DumpMeshTriangles(UStaticMesh* Mesh, FVector Origin, const FString& Path);
    /** @cc [owner:fontanierh,label:correctness] observe-selected-mesh-derived-data
     * Wait only for this mesh's pending builds, then observe freshly acquired render data.
     * This MUST NOT save assets, change build settings or force a rebuild. Completed MUST require
     * no pending selected-mesh tasks; payload presence alone MUST NOT imply usable or cooked data.
     */
    UFUNCTION(BlueprintCallable) static FMeshDerivedDataAudit InspectDerivedData(UStaticMesh* Mesh);
    /** LOD 0 of a skeletal mesh as built, as text, to compare two imports (Scripts/character_snapshot.py): a line per
     *  render vertex (`v section x y z nx ny nz u v bone:weight...`, weights 0-1 by bone name), per triangle (`f a b c`)
     *  and per morph target delta (`m target vertex dx dy dz`). */
    UFUNCTION(BlueprintCallable) static bool DumpSkeletalMesh(USkeletalMesh* Mesh, const FString& Path);
};
