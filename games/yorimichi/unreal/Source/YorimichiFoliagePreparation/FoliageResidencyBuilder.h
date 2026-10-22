#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "FoliageResidencyBuilder.generated.h"

class UStaticMesh;
class UMaterialInterface;

/** Transform certified saved descriptions without exporting original assets.
 * Rigid surfaces have one owner; leaf LOD0 retains exact authored corners and source material wrappers.
 * Multi-level originals retain their complete classified leaf chain and rendered screen thresholds.
 * Only single-level originals use the native reducer within material/categorical-role islands.
 * Only manifested standalone-tree trunks or bounded classified lower-trunk
 * capsules may own tree collision; a source simple shape is not a trunk witness. Mixed
 * scenery keeps exact rigid collision; leaf/shadow geometry never owns collision.
 * A caller must save and verify every output before publishing its receiving registry.
 */
UCLASS()
class YORIMICHIFOLIAGEPREPARATION_API UYorimichiFoliageResidencyBuilder : public UObject
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable)
    static bool SelfTest();
    UFUNCTION(BlueprintCallable)
    static FString Compact(UStaticMesh* Source, UStaticMesh* Prepared, UStaticMesh* PreparedShadow,
        const FString& Classification, const TArray<int32>& LeafSlots, int32 ExpectedRigidTriangles,
        bool SimpleTrunk, const TArray<int32>& SourceLODs, const TArray<float>& TrunkBounds, const FString& Directory, UMaterialInterface* NearInteraction=nullptr, bool Passable=false);
};
