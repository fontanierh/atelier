#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "V2MigrationParkDressing.generated.h"

/** The editor migration of a park's dressing (tools/migrate/objects.py, guarded step `migrate.objects`): its trees, one
 *  object per unit, and its kei cars, one object each. Both are saved with the builders ASuperUltraMegaPark::Spawn uses
 *  (MakeTreeGroup, TreeTransform, MakeProp), so a saved tree or car looks and collides exactly as a spawned one. The
 *  manifest lists what it saved, so Spawn skips exactly those. Editor only; a rerun keeps every saved unit as it is. */
UCLASS()
class YORIMICHI_API UV2MigrationParkDressing : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Saves the trees of a park file (DataFile, park.json under Content/Data) as one AV2ScenePatch per unit, at the park's
     *  placement. Species[i] and Indices[i] name one tree: the species key of park.json's `trees` and its index in that
     *  species' list; Units[i] is the unit it joins. Each tree is listed once. A unit's patch holds one instanced component
     *  per species, with exactly the instances of that unit, in park.json's order. The manifest lists each unit as
     *  Tag:trees/Unit and each tree as Tag:tree/Species/Index (Spawn skips exactly those). A unit already saved (V2Id:
     *  region, tag, trees/unit) is kept as it is. Returns the number of actors created, or -1 with Error set; nothing is
     *  changed on an error. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateParkTrees(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Species, const TArray<int32>& Indices, const TArray<FString>& Units,
        TArray<AActor*>& OutCreated, int32& OutKept, FString& Error);

    /** Saves a park's props (the kei cars, park.json's `props`) as objects: Meshes[i] names one prop, listed once, and
     *  Units[i] the object it joins. One AV2ScenePatch per unit at the park's placement, holding for each of its props the
     *  component ASuperUltraMegaPark::MakeProp builds. The manifest lists each prop as Tag:Mesh, so Spawn skips exactly
     *  those. A unit already saved (V2Id: region, tag, props/unit) is kept as it is. Returns the number of actors created,
     *  or -1 with Error set; nothing is changed on an error. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateParkProps(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Meshes, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept,
        FString& Error);
};
