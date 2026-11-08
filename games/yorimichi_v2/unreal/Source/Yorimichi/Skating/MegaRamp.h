#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MegaRamp.generated.h"
class FJsonObject;
class UStaticMeshComponent;
class USceneComponent;
class UObject;

/** The mini-mega ramp in the clearing: the Mega_Ramp mesh with its collision and the Mega_Trim mesh without (seams,
 *  coping), placed from world.json "mega". Scenery now; its scripted ride went with the old cruiser skateboard (in the
 *  prototype archive). */
UCLASS()
class YORIMICHI_API AMegaRamp : public AActor
{
    GENERATED_BODY()
public:
    AMegaRamp();
    void Initialize(const TSharedPtr<FJsonObject>& Data);
    /** One of the ramp's two meshes as Initialize builds it on Parent: Mega_Ramp (ridden, blocks) or, with bTrim,
     *  Mega_Trim (look only). The saved ramp object (V2MigrationMisc) builds its components with this too. */
    static UStaticMeshComponent* MakePiece(UObject* Outer, USceneComponent* Parent, bool bTrim);
    bool bGameplayReady = false;
};
