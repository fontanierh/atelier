#pragma once
#include "CoreMinimal.h"
#include "Engine/AssetUserData.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkinMorphContactData.generated.h"

class USkeletalMesh;

/** One morph target's deltas on a mesh LOD as it renders them: native render vertex indices and their component-local
 *  pre-skin position deltas (cm), in the engine's order. */
USTRUCT(BlueprintType)
struct ATELIERCORE_API FSkinMorphContactTarget
{
    GENERATED_BODY()

    /** The target's native name on the mesh, as imported (with any prefix the FBX importer added). */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skin")
    FName Target;
    UPROPERTY(VisibleAnywhere, Category = "Skin")
    TArray<int32> Vertices;
    UPROPERTY(VisibleAnywhere, Category = "Skin")
    TArray<FVector3f> Deltas;
};

/**
 * Morph target deltas kept for the CPU skin readers (FSkinMorphOffsets). Cooked desktop builds keep a morph's deltas
 * only for the GPU, so readers that sample the skin as drawn (contact, clearance, fit) need their own copy. It is
 * captured in the editor from the native imported mesh (USkinMorphContactLibrary::CaptureSkinMorphContacts) and stored
 * on that mesh as its asset user data, so it cooks, loads and is replaced with the mesh. It binds to the mesh, its LOD
 * and its render vertex count; Validate rejects data that no longer matches.
 */
UCLASS(BlueprintType)
class ATELIERCORE_API USkinMorphContactData : public UAssetUserData
{
    GENERATED_BODY()
public:
    /** The mesh it was captured from. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skin")
    TSoftObjectPtr<USkeletalMesh> Mesh;
    /** The LOD it was captured from; the readers use LOD 0. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skin")
    int32 LOD = 0;
    /** That LOD's render vertex count at capture. */
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skin")
    int32 VertexCount = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Skin")
    TArray<FSkinMorphContactTarget> Targets;

    /** The data a mesh carries, or null. */
    static const USkinMorphContactData* Find(const USkeletalMesh* Asset);
    /** The captured target with this native name, or null. */
    const FSkinMorphContactTarget* FindTarget(FName Target) const;
    /** Whether this is Asset's data as it renders: captured from Asset, LOD 0 with Asset's render vertex count; every
     *  target named once, on Asset, with as many deltas as Asset keeps for it (and, in the editor, which still has
     *  them, exactly those); indices in range and not repeated; deltas finite; and each Required target present
     *  with deltas. Receipt lists what it holds, or every problem found. */
    bool Validate(const USkeletalMesh* Asset, TConstArrayView<FName> Required, FString& Receipt) const;
};

UCLASS()
class ATELIERCORE_API USkinMorphContactLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Editor, after a native import: captures these targets' LOD 0 deltas from the mesh, validates them and stores them
     *  on the mesh as its USkinMorphContactData (replacing any earlier capture), marking its package dirty for the caller
     *  to save. Null, with the mesh unchanged, when a target is missing or has no deltas, or the capture does not
     *  validate. Receipt is the validation receipt, or why nothing was stored. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Skin")
    static USkinMorphContactData* CaptureSkinMorphContacts(USkeletalMesh* Mesh, const TArray<FName>& Targets, FString& Receipt);
    /** Editor: removes Mesh's contact data, marking its package dirty when it had some. For an importer whose source no
     *  longer carries the captured morphs: a reimport in place keeps the mesh's user data, which would then no longer
     *  match it. False when there was none. */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Skin")
    static bool ClearSkinMorphContacts(USkeletalMesh* Mesh);
    /** Whether Mesh carries valid contact data holding every Required target (USkinMorphContactData::Validate). */
    UFUNCTION(BlueprintCallable, Category = "Atelier|Skin")
    static bool ValidateSkinMorphContacts(USkeletalMesh* Mesh, const TArray<FName>& Required, FString& Receipt);
};
