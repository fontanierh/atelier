#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "YorimichiCloth.generated.h"

class USkeletalMesh;

/** Editor scripting for character cloth (import scripts run it; Python cannot create or bind clothing data itself). */
UCLASS()
class YORIMICHI_API UYorimichiClothLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Makes the LOD 0 section drawn with material slot SlotName simulate as Chaos cloth (Scripts/import_modori.py: his
     *  coat). Its vertex colours' red is the pin mask: 1 follows the skin, 0 hangs free up to MaxDistanceCm from it; the
     *  mesh's physics asset (its capsules and spheres) is what the cloth collides with. Replaces cloth bound before
     *  (a reimport drops the binding, so the import runs this after every import). Returns a summary, empty on failure.
     *  Editor only. */
    UFUNCTION(BlueprintCallable, Category = "Yorimichi|Editor")
    static FString AddSectionCloth(USkeletalMesh* Mesh, FName SlotName, float MaxDistanceCm);
};
