#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "YorimichiCloth.generated.h"

class UPhysicsAsset;
class USkeletalMesh;

/** Editor scripting for character cloth (import scripts run it; Python cannot create or bind clothing data itself). */
UCLASS()
class YORIMICHI_API UYorimichiClothLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Makes the LOD 0 section drawn with material slot SlotName simulate as Chaos cloth (Scripts/import_modori.py: his
     *  coat). Its vertex colours' red is the pin mask: 1 follows the skin, 0 hangs free up to MaxDistanceCm from it; it
     *  collides with Colliders' capsules and spheres (MakeCapsuleColliders), or the mesh's physics asset when null.
     *  Replaces cloth bound before (a reimport drops the binding, so the import runs this after every import). Returns
     *  a summary, empty on failure. Editor only. */
    UFUNCTION(BlueprintCallable, Category = "Yorimichi|Editor")
    static FString AddSectionCloth(USkeletalMesh* Mesh, FName SlotName, float MaxDistanceCm, UPhysicsAsset* Colliders);

    /** A physics asset of kinematic capsules for cloth to collide with (not the mesh's own physics asset, which the
     *  skating rider reads): capsule I rides bone Bones[I], spans the reference-pose joints From[I] to To[I], radius
     *  RadiiCm[I]. Made or remade at PackagePath (e.g. /Game/Modori/PA_Modori_Cloth); the caller saves it. Editor only. */
    UFUNCTION(BlueprintCallable, Category = "Yorimichi|Editor")
    static UPhysicsAsset* MakeCapsuleColliders(USkeletalMesh* Mesh, const FString& PackagePath, const TArray<FName>& Bones,
        const TArray<FName>& From, const TArray<FName>& To, const TArray<float>& RadiiCm);

    /** A diagnostic summary of Mesh's cloth: its clothing asset's bones, physical mesh (vertices without bone weights,
     *  the max distance range) and each bound section's render-to-cloth mapping (entries pointing past the physical
     *  mesh). Editor only. */
    UFUNCTION(BlueprintCallable, Category = "Yorimichi|Editor")
    static FString DescribeCloth(USkeletalMesh* Mesh);
};
