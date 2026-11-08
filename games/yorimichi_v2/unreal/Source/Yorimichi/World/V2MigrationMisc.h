#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "V2MigrationMisc.generated.h"

class AActor;
class AV2WorldManifest;

/** True when the map saved this mesh as an object (its tag's group is listed in the manifest, `Tag:Mesh`) and the
 *  mesh's committed package exists, so the runtime skips its spawn and the saved object draws it. A map without the
 *  manifest (the migration's own build, a standalone map) spawns it as before. PackageRoot is the mesh's folder. */
bool V2StaticSaved(const AV2WorldManifest* Manifest, const TCHAR* Tag, const TCHAR* MeshName, const TCHAR* PackageRoot);

/** The static pieces of the map that are not part of a region's runtime file: the mini Mega ramp (W03, world.json
 *  "mega") and the Ronin camp's static props (W13, SpawnRoninCamp). Each is saved as objects of its own, one AV2ScenePatch
 *  per unit, with the components the runtime builds (AMegaRamp::MakePiece, the camp prop placement and collision of
 *  SpawnRoninCamp), and listed in the manifest so the runtime skips only those meshes. */
UCLASS()
class YORIMICHI_API UV2MigrationMisc : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Saves Meshes[i] (Mega_Ramp, Mega_Trim, SM_CampFirePit, SM_CampJinmaku, SM_CampWeaponRack or SM_CampBales) as the
     *  unit Units[i]: the meshes of one unit share one placement (the ramp's origin, or the prop's ground point). Region
     *  and Tag name the object's record (V2Id: region, tag, unit). A unit already saved is kept as it is. Returns the number
     *  of actors created, or -1 with Error set; nothing changes on an error. */
    UFUNCTION(BlueprintCallable, Category = "V2 Migration", meta = (WorldContext = "WorldContext"))
    static int32 MigrateStaticMeshes(UObject* WorldContext, FName Region, FName Tag, const TArray<FString>& Meshes,
        const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error);
};
