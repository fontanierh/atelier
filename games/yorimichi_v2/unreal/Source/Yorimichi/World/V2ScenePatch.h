#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Info.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "V2ScenePatch.generated.h"

class UStaticMesh;

class AJapanWorld;
class UPrimitiveComponent;

/** Saved scenery (docs/YORIMICHI_V2_PLAN.md §6): one patch of the static world AJapanWorld::Load spawns at runtime in
 *  the original game, made once in the editor by UV2Migration from that same Load and saved in its own actor package.
 *  Its components keep every setting Load gave them; their V2 role tags say which of AJapanWorld's runtime lists they
 *  join (RegisterScenePatch), so the menu's performance settings, the screen-size cull and the see-through keep
 *  working unchanged. */
UCLASS()
class YORIMICHI_API AV2ScenePatch : public AActor
{
    GENERATED_BODY()
public:
    AV2ScenePatch();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;

    /** The region record that owns this actor (games/yorimichi_v2/world/regions/<id>). */
    UPROPERTY(VisibleAnywhere, Category = "V2") FName Region;
    /** The world.json instance key (or SkyDome, Sea) whose instances this patch holds. */
    UPROPERTY(VisibleAnywhere, Category = "V2") FString SourceKey;
    /** Stable identity: hash of region, key, mesh, role and patch cell, so a rerun finds it instead of duplicating it. */
    UPROPERTY(VisibleAnywhere, Category = "V2") FString V2Id;
    /** What the migration saved here, one "mesh|tags|instances" entry per component, sorted. A saved patch whose
     *  components no longer match (a child deleted or swapped in the editor) fails the world's readiness. */
    UPROPERTY(VisibleAnywhere, Category = "V2") TArray<FString> ExpectedMembers;

    /** This patch's members as saved now, in ExpectedMembers' form. */
    TArray<FString> Members() const;

    // Component tags naming the runtime list a saved component joins.
    static const FName RoleGroup, RoleBackdrop, RoleShadowTwin, RoleSeeThrough, RoleSkyDome, RoleSea;
};

/** What of the runtime world this map holds as saved actors instead. Placed once per map, never spatially loaded. */
UCLASS()
class YORIMICHI_API AV2WorldManifest : public AInfo
{
    GENERATED_BODY()
public:
    /** Unreal cm, half-open [Min, Max): world.json instances placed inside are saved patches, not spawned. */
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FBox2D> MigratedBoundsCm;
    /** A slice or test map: no runtime instance scenery anywhere, and of the region services only RuntimeServices. */
    UPROPERTY(EditAnywhere, Category = "V2") bool bOnlyMigrated = false;
    /** Pieces saved in this map instead of spawned: SkyDome, Sea, SkatePark.Scenery (the pier's meshes and trees;
     *  its look, rails and spawns stay runtime). */
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FName> MigratedServices;
    /** With bOnlyMigrated: the region services that still start (AJapanWorld::Load's names, e.g. SkatePark). */
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FName> RuntimeServices;

    static const AV2WorldManifest* Find(const UWorld* World);
    static bool InsideHalfOpen(const FBox2D& Box, const FVector2D& P)
    {
        return P.X >= Box.Min.X && P.X < Box.Max.X && P.Y >= Box.Min.Y && P.Y < Box.Max.Y;
    }
    bool CoversInstance(const FVector2D& P) const;
    /** The point whose region owns an instance: its placement, or for a world-space piece placed at the origin (the
     *  lake, the village ground, Hidamari's surfaces, the volcano) its geometry's centre. The migration and the runtime
     *  skip both use it, so a piece is never both saved and spawned. */
    static FVector2D OwnerPoint(const FTransform& Placement, const UStaticMesh* Mesh);
    bool CoversService(FName Service) const { return MigratedServices.Contains(Service); }
    bool Runs(FName Service) const { return !bOnlyMigrated || RuntimeServices.Contains(Service); }
};

/** The one-time editor migration (unreal/Scripts/migrate_map.py drives it). */
UCLASS()
class YORIMICHI_API UV2Migration : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Builds the world once as AJapanWorld::Load does (in a transient, migration-mode AJapanWorld) and moves every
     *  instance group's instances inside each region's bounds (Regions[i] owns BoundsCm[i], half-open) into
     *  AV2ScenePatch actors, one per group and PatchCm cell, each component a copy of the one Load made. An instance
     *  inside no box of BoundsCm or HeldCm (every region of the map) is ServicesRegion's, the environment's. Services
     *  (SkyDome, Sea) become whole-world patches of ServicesRegion; SkatePark.Scenery becomes one patch of the
     *  region holding the pier. Existing V2Ids are kept, not recreated. Returns
     *  the number of actors created, or -1 with Error set. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateStaticScenery(UObject* WorldContext, const TArray<FName>& Regions, const TArray<FBox2D>& BoundsCm,
        const TArray<FBox2D>& HeldCm, float PatchCm, FName ServicesRegion, const TArray<FName>& Services, TArray<AActor*>& OutCreated,
        int32& OutKept, FString& Error);
};
