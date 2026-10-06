#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MegaRamp.generated.h"
class FJsonObject;

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
};
