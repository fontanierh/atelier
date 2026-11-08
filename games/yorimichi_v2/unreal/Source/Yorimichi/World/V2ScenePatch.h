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
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "V2") FName Region;
    /** The world.json instance key (or SkyDome, Sea) whose instances this patch holds. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "V2") FString SourceKey;
    /** Stable identity: hash of region, key, mesh, role and patch cell, so a rerun finds it instead of duplicating it. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "V2") FString V2Id;
    /** What the migration saved here, one "mesh|tags|instances" entry per component, sorted. A saved patch whose
     *  components no longer match (a child deleted or swapped in the editor) fails the world's readiness. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "V2") TArray<FString> ExpectedMembers;

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
    /** The environment region saved every instance no region box of the map holds (an open-water piece such as
     *  HD_Sea): those are saved patches too. RegionBoundsCm are the map's region boxes at that migration. */
    UPROPERTY(EditAnywhere, Category = "V2") bool bEnvironmentMigrated = false;
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FBox2D> RegionBoundsCm;
    /** A slice or test map: no runtime instance scenery anywhere, and of the region services only RuntimeServices. */
    UPROPERTY(EditAnywhere, Category = "V2") bool bOnlyMigrated = false;
    /** Pieces saved in this map instead of spawned: SkyDome, Sea, SkatePark.Scenery (the pier's meshes and trees;
     *  its look, rails and spawns stay runtime). */
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FName> MigratedServices;
    /** With bOnlyMigrated: the region services that still start (AJapanWorld::Load's names, e.g. SkatePark). */
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FName> RuntimeServices;
    /** Runtime-region scenery groups saved in this map as one patch each, "<region tag>:<mesh name>" (for example
     *  brinecove:SM_BC_Ships_2_2, the wreck): ABelmonteRegion::Spawn skips only these, and its service still runs.
     *  Park pieces saved the same way (megapark:SM_MP_..., craterpark:SM_CP_...) are listed here too: ASuperUltraMegaPark::
     *  Spawn skips only those render and collision pieces; the park's rails, zones and trees stay runtime. The hippodrome's
     *  meshes too (hippodrome:SM_HD_...): AHippodrome::Spawn skips only those, the course and its race service stay runtime. */
    UPROPERTY(EditAnywhere, Category = "V2") TArray<FString> MigratedGroups;

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
    bool CoversGroup(FName Tag, const FString& MeshName) const { return GroupSet().Contains(Tag.ToString() + TEXT(":") + MeshName); }
    /** MigratedGroups as a set for CoversGroup, a transient cache (not saved): rebuilt when the list's length changes, which
     *  is the only way the migration changes it (entries are added, never replaced). */
    const TSet<FString>& GroupSet() const
    {
        if (GroupSetCount != MigratedGroups.Num())
        {
            GroupSetCache.Reset();
            for (const FString& Group : MigratedGroups) GroupSetCache.Add(Group);
            GroupSetCount = MigratedGroups.Num();
        }
        return GroupSetCache;
    }
    mutable TSet<FString> GroupSetCache;
    mutable int32 GroupSetCount = -1;
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
     *  AV2ScenePatch actors, one per group and PatchCm cell (one size per region, then the environment's), each component a copy of the one Load made. An instance
     *  inside no box of BoundsCm or HeldCm (every region of the map) is ServicesRegion's, the environment's. Services
     *  (SkyDome, Sea) become whole-world patches of ServicesRegion; SkatePark.Scenery becomes one patch of the
     *  region holding the pier. Existing V2Ids are kept, not recreated. Returns
     *  the number of actors created, or -1 with Error set. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateStaticScenery(UObject* WorldContext, const TArray<FName>& Regions, const TArray<FBox2D>& BoundsCm,
        const TArray<FBox2D>& HeldCm, const TArray<float>& PatchCm, FName ServicesRegion, const TArray<FName>& Services, TArray<AActor*>& OutCreated,
        int32& OutKept, FString& Error);

    /** Saves runtime-region scenery groups (ABelmonteRegion's runtime.json `groups`, by mesh name) as objects: one
     *  AV2ScenePatch per object (Objects[i] names the object of Meshes[i]; a statue cut into cells is one object of
     *  several groups), owned by Region, at the region's origin, holding for each of its groups the component
     *  ABelmonteRegion::MakeGroup builds with the same instances. The groups are listed in the map's manifest
     *  MigratedGroups so the runtime skips only them. An object already saved (its V2Id: region, tag, object) is kept
     *  as it is, edits included. Plant groups, which join the island's tree lists, are refused. Returns the number of
     *  actors created, or -1 with Error set. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateRegionGroups(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Meshes, const TArray<FString>& Objects, TArray<AActor*>& OutCreated, int32& OutKept,
        FString& Error);
    /** Saves a park's render and collision pieces (DataFile, its park.json under Content/Data; ASuperUltraMegaPark::Spawn
     *  reads it) as objects: one AV2ScenePatch per unit, owned by Region, at the park's placement (location_cm, yaw_deg),
     *  holding for each of its pieces the component ASuperUltraMegaPark::MakePiece builds. Pieces[i] is the mesh name of
     *  one render or collision entry, Units[i] the object it joins and IsCollision[i] whether it is a collision piece;
     *  every piece is listed once and must be of the kind the file gives it. The pieces are listed in the map's manifest
     *  as Tag:mesh, so Spawn skips only them. A unit already saved (V2Id: region, tag, unit) is kept as it is. Returns
     *  the number of actors created, or -1 with Error set; nothing is changed on an error. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateParkPieces(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Pieces, const TArray<bool>& IsCollision, const TArray<FString>& Units,
        TArray<AActor*>& OutCreated, int32& OutKept, FString& Error);
    /** Saves the hippodrome's meshes (DataFile, hippodrome.json under Content/Data; AHippodrome::Spawn reads it) as objects:
     *  one AV2ScenePatch per unit, at the course origin, holding for each of its meshes the component AHippodrome::MakePiece
     *  builds. Pieces[i] is the mesh name of one of the file's meshes, listed once, and Units[i] the object it joins. The
     *  pieces are listed in the map's manifest as Tag:mesh, so Spawn skips only them. A unit already saved (V2Id: region,
     *  tag, unit) is kept as it is. Returns the number of actors created, or -1 with Error set; nothing changes on an error. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateHippodromePieces(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
        const TArray<FString>& Pieces, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept,
        FString& Error);
    /** Splits placed things out of the region's area patches (MigrateStaticScenery's, one key and mesh per cell): for
     *  each Objects[i], every component of the region's patches whose SourceKey is Keys[i] gives up its instances
     *  within ToleranceCm (in the plane) of PointsCm[i] to one new patch at that point (V2Id: region, key, "object",
     *  Objects[i]; tagged V2Object:<Tag>:<object>), a copy of each such component with those instances alone. The new
     *  patch keeps the key, so a rerun of the map migration counts that key and mesh as saved; an emptied source
     *  stays saved with no instances, keeping its V2Id. Every move is planned first: an object found nowhere or an
     *  instance two objects would take changes nothing. The instance count over all those patches is unchanged
     *  (checked). An object already saved is kept. OutChanged lists the sources that gave up instances. Returns the
     *  number of patches created, or -1 with Error set. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 SplitPatchObjects(UObject* WorldContext, FName Region, FName Tag, const TArray<FString>& Keys,
        const TArray<FString>& Objects, const TArray<FVector2D>& PointsCm, float ToleranceCm, TArray<AActor*>& OutCreated,
        TArray<AActor*>& OutChanged, int32& OutKept, FString& Error);
};
