#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "BelmonteRegion.generated.h"

class AJapanWorld;
class FJsonObject;
class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;

/** Belmonte's town and countryside, assembled from the committed environmental library.
 *  The island owns gameplay; this actor owns static scenery and no Haras systems.
 *  Brinecove (world/regions/brinecove) writes the same runtime.json schema and is placed by this actor too. */
UCLASS()
class YORIMICHI_API ABelmonteRegion : public AActor
{
    GENERATED_BODY()
public:
    ABelmonteRegion();
    static bool InClearance(const TSharedPtr<FJsonObject>& Data, double X, double Y);
    static void Clear(const TSharedPtr<FJsonObject>& WorldData, const FString& Path);
    static ABelmonteRegion* Spawn(AJapanWorld* Landscape, const FString& Path, FName Tag = TEXT("belmonte"));
    /** A runtime.json group's component as Spawn makes it (mesh, materials, collision, shadow, cull, plant fade), on
     *  Outer under Parent, unregistered and without instances; Missing counts its missing materials. The saved
     *  patches of UV2Migration::MigrateRegionGroups are built by this same function. */
    static UHierarchicalInstancedStaticMeshComponent* MakeGroup(UObject* Outer, USceneComponent* Parent,
        const TSharedPtr<FJsonObject>& Entry, UStaticMesh* Mesh, FName Tag, int32& Missing);
    /** A non-plant group's instances relative to the region's origin, without those outside the district. */
    static TArray<FTransform> SceneryTransforms(const TSharedPtr<FJsonObject>& Data, const TSharedPtr<FJsonObject>& Entry, int32& Outside);
    /** A plant group's instances relative to the region's origin, without those on the gondola's clearance (InClearance
     *  with Clearance, the gondola's data). Plants are not culled by the district's bounds. */
    static TArray<FTransform> PlantTransforms(const TSharedPtr<FJsonObject>& Data, const TSharedPtr<FJsonObject>& Entry, const TSharedPtr<FJsonObject>& Clearance);
    UFUNCTION(BlueprintCallable, Category = "Review") static int32 ReviewPendingShaderJobs();
    UFUNCTION(BlueprintCallable, Category = "Review") static FString ReviewMeshColours(const FString& Name);
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") bool bGameplayReady = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") int32 SceneryInstances = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") int32 PlantInstances = 0;
};
