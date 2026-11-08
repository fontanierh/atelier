#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GameFramework/GameModeBase.h"
#include "JapanWorld.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MegaParkLayout.h"
#include "SuperUltraMegaPark.generated.h"

class FJsonObject;
class FJsonValue;
class UHierarchicalInstancedStaticMeshComponent;
class UStaticMesh;
class UStaticMeshComponent;
class USceneComponent;

/** Who owns each tree of a park: the unit of every render and collision piece (tree_units.json beside park.json, written
 *  by tools/migrate/parks.py), each piece's origin in the plane, and the species that stay runtime (no adopted record). */
struct FParkTreeOwners
{
    struct FPiece { FString Unit; double X = 0.; double Y = 0.; };
    TArray<FPiece> Pieces;          // render, then collision, in park.json's order
    TSet<FString> UnsavedSpecies;
};

/** The park's grind paths. In the standalone level, render and collision geometry are ordinary StaticMeshActors and
 *  the game mode spawns this actor from the level's AMegaParkLayout; in the island, Spawn places the park from its
 *  manifest and owns the meshes as components (docs/MEGAPARK.md). */
UCLASS()
class YORIMICHI_API ASuperUltraMegaPark : public AActor
{
    GENERATED_BODY()
public:
    ASuperUltraMegaPark();
    virtual void BeginPlay() override;
    /** Places the park in the island from Content/Data/megapark/park.json: the actor transform, the kept render and
     *  collision meshes (with the seam's) from /Game/MegaPark/Meshes, the original grind paths, the island trees that
     *  replace the original plants and the kei cars that replace its traffic cars. Null if the file is missing. */
    static ASuperUltraMegaPark* Spawn(UWorld* World, const FString& Path);
    /** One render or collision entry of park.json as a component of Parent, at its origin_cm: the settings Spawn gives
     *  every piece (collision: BlockAll, hidden; render: no collision). The caller adds and registers it. Shared with
     *  UV2Migration::MigrateParkPieces, so a piece is saved as an object or spawned at runtime, never both. */
    static UStaticMeshComponent* MakePiece(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& Entry,
        UStaticMesh* Mesh, bool bCollision);
    /** One species of park.json's trees as an instanced component of Parent, with the settings Spawn gives every tree of
     *  it (fade, cull, no collision). The caller registers it and adds its instances. Shared with
     *  UV2MigrationParkDressing::MigrateParkTrees, so a unit's trees are saved as the runtime builds them. */
    static UHierarchicalInstancedStaticMeshComponent* MakeTreeGroup(UObject* Outer, USceneComponent* Parent, const FString& Key,
        UStaticMesh* Mesh);
    /** One tree entry of park.json, [x, y, z, yaw, scale], as the instance transform Spawn places it with. False when the
     *  entry is too short to be a tree. */
    static bool TreeTransform(const TSharedPtr<FJsonValue>& Value, FTransform& Out);
    /** Reads the tree owners of the park file at ParkPath (its tree_units.json) for the park Root. False, with Out empty,
     *  when the file is missing or does not name the unit of every render and collision piece. */
    static bool LoadTreeOwners(const TSharedPtr<FJsonObject>& Root, const FString& ParkPath, FParkTreeOwners& Out);
    /** The unit that owns the tree of Species at Location (its place in park.json's frame): the unit of the piece whose
     *  origin is nearest in the plane, the earlier piece on a tie (the rule parks.py's tree_units mirrors). Empty for a
     *  species that stays runtime. Shared by Spawn and UV2MigrationParkDressing::MigrateParkTrees, so a tree is saved or
     *  spawned, never both. */
    static FString TreeUnit(const FParkTreeOwners& Owners, const FString& Species, const FVector& Location);
    /** The unit of the piece whose origin is nearest in the plane to Location (a tree's, a rail's first point, a zone's
     *  centre; park-local), the earlier piece on a tie. Empty when the owners name no piece. */
    static FString NearestUnit(const FParkTreeOwners& Owners, const FVector& Location);
    /** One kei car of park.json's props as a component of Parent: its basis and location, blocking collision. The caller
     *  adds and registers it. Shared with UV2MigrationParkDressing::MigrateParkProps. */
    static UStaticMeshComponent* MakeProp(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& Entry,
        UStaticMesh* Mesh);
    bool bGameplayReady = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Source") FMegaParkLayoutData Layout;
private:
    void RegisterRails();
    bool bRailsRegistered = false;
    int32 RegisteredRailCount = 0;
};

/** Standalone park level: uses the existing player without spawning the island over the imported park. */
UCLASS()
class YORIMICHI_API AMegaParkGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AMegaParkGameMode();
    /** -rider=<Name> plays as an adventure character (PlayableCharacter.h). */
    virtual UClass* GetDefaultPawnClassForController_Implementation(AController* Controller) override;
    /** Spawns the park's grind paths and player services from the level's AMegaParkLayout. A level saved before it had
     *  one (an old import) has neither: the error says to rebuild it. */
    virtual void StartPlay() override;
    virtual void BeginPlay() override;
};

/** Player services for an authored level, without generating the island or its effects. */
UCLASS()
class YORIMICHI_API AMegaParkWorld : public AJapanWorld
{
    GENERATED_BODY()
public:
    AMegaParkWorld();
    virtual void BeginPlay() override;
};

/** Review cameras for scenarios: frame a view of the park, then give the player back their camera. */
UCLASS()
class YORIMICHI_API UMegaParkValidation : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool ReviewCamera(FVector Location, FVector Target, float Fov = 65.f);
    UFUNCTION(BlueprintCallable) static void RestorePlayerCamera();
};
