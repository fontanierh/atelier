#pragma once
#include "CoreMinimal.h"
#include "UObject/WeakObjectPtrTemplates.h"

class UMorphTarget;
class USkeletalMesh;
class USkeletalMeshComponent;
class USkinMorphContactData;
class FSkinWeightVertexBuffer;
class FSkeletalMeshLODRenderData;

/**
 * Morph targets move a skeletal mesh's vertices before skinning. CPU readers of its skin (ground contact, clearance,
 * fit) that skin the static base positions miss them. This keeps the pre-skin offsets of LOD0's render vertices under
 * a set of morph weights, blended from the morphs' CPU deltas (read once per mesh, the blend rebuilt only when the
 * weights change), and skins an offset the way its vertex is skinned. With no morph active it is empty and a reader
 * keeps its existing behaviour.
 *
 * Cooked desktop builds keep a morph's deltas only for the GPU, so a mesh's captured USkinMorphContactData supplies
 * them (and is used first, so the editor reads what a cooked build reads). An update that needs a morph with neither,
 * or a mesh whose contact data does not validate, fails with an error, so a reader can report that it could not
 * measure the skin as shown instead of passing on the base skin.
 */
struct ATELIERCORE_API FSkinMorphOffsets
{
    /** The component's active morph weights, as it renders them. False (and no offsets) when one keeps no CPU deltas. */
    bool Update(const USkeletalMeshComponent* Component);
    /** Named weights on a mesh: a pose a character's own driver is about to show. False when a named morph is missing
     *  from the mesh or keeps no CPU deltas. */
    bool Update(const USkeletalMesh* Asset, TConstArrayView<TPair<FName, float>> Named);
    /** Render vertex V's offset in the bind pose (component space); null when no active morph moves it. */
    const FVector3f* Find(int32 Vertex) const { return Offsets.Find(Vertex); }
    bool IsEmpty() const { return Offsets.IsEmpty(); }
    /** Why the last update failed; empty when it succeeded. */
    const FString& GetError() const { return Error; }
    /** Render vertex V's pre-skin offset skinned by RefToLocals (USkinnedMeshComponent::CacheRefToLocalMatrices)
     *  through its section's (or the LOD's unified) bone map and its normalized skin weights, in component space. */
    static FVector3f Skin(const FSkeletalMeshLODRenderData& LOD, const FSkinWeightVertexBuffer& Weights,
                          TConstArrayView<FMatrix44f> RefToLocals, int32 Vertex, const FVector3f& Offset);
    /** Adds every offset, skinned, to LOD0 positions from USkinnedMeshComponent::ComputeSkinnedPositions. */
    void AddTo(TArray<FVector3f>& Positions, const FSkeletalMeshLODRenderData& LOD, const FSkinWeightVertexBuffer& SkinWeights,
               TConstArrayView<FMatrix44f> RefToLocals) const;

private:
    bool Blend(const USkeletalMesh* Asset, TArray<TPair<const UMorphTarget*, float>>& Active);
    TWeakObjectPtr<const USkeletalMesh> Mesh;
    TMap<const UMorphTarget*, TArray<TPair<int32, FVector3f>>> Deltas;
    TArray<TPair<const UMorphTarget*, float>> Applied;
    TMap<int32, FVector3f> Offsets;
    TWeakObjectPtr<const USkinMorphContactData> Contact;
    FString ContactError;
    FString Error;
};
