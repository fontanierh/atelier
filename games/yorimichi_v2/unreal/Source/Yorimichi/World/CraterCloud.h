#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "CraterCloud.generated.h"

class UMaterialInstanceDynamic;
class UProceduralMeshComponent;

/** The lenticular cap cloud over Crater Park (docs/CRATERPARK.md, "Cap cloud"): nested translucent lens shells built
 *  from craterpark/cloud.json (world/regions/craterpark/cloud.py) and drawn with /Game/CraterPark/Cloud's materials
 *  (unreal/Scripts/crater_cloud_material.py). Dense from afar, a thin blurring veil from inside; scenery only: no
 *  collision, shadow, tick or replication. */
UCLASS()
class YORIMICHI_API ACraterCloud : public AActor
{
    GENERATED_BODY()
public:
    ACraterCloud();
    /** The cloud from its record; null, with a log line, when the record or the materials are missing. */
    static ACraterCloud* Spawn(UWorld* World, const FString& Path);
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> Shells;
    UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Looks;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Environment") int32 Triangles = 0;
};
