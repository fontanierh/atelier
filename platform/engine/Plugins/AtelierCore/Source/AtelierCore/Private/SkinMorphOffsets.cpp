#include "SkinMorphOffsets.h"
#include "SkinMorphContactData.h"
#include "Animation/MorphTarget.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"

bool FSkinMorphOffsets::Update(const USkeletalMeshComponent* Component)
{
    const USkeletalMesh* Asset = Component ? Component->GetSkeletalMeshAsset() : nullptr;
    TArray<TPair<const UMorphTarget*, float>> Active;
    if (Asset)
        for (const TPair<const UMorphTarget*, int32>& Morph : Component->ActiveMorphTargets)
            if (Morph.Key && Component->MorphTargetWeights.IsValidIndex(Morph.Value))
                Active.Emplace(Morph.Key, Component->MorphTargetWeights[Morph.Value]);
    return Blend(Asset, Active);
}

bool FSkinMorphOffsets::Update(const USkeletalMesh* Asset, TConstArrayView<TPair<FName, float>> Named)
{
    TArray<TPair<const UMorphTarget*, float>> Active;
    for (const TPair<FName, float>& Morph : Named)
    {
        if (FMath::Abs(Morph.Value) <= UE_SMALL_NUMBER) continue;
        const UMorphTarget* Target = Asset ? Asset->FindMorphTarget(Morph.Key) : nullptr;
        if (!Target)
        {
            Offsets.Reset(); Applied.Reset();
            Error = FString::Printf(TEXT("morph %s is not on %s"), *Morph.Key.ToString(), Asset ? *Asset->GetName() : TEXT("no mesh"));
            return false;
        }
        Active.Emplace(Target, Morph.Value);
    }
    return Blend(Asset, Active);
}

bool FSkinMorphOffsets::Blend(const USkeletalMesh* Asset, TArray<TPair<const UMorphTarget*, float>>& Active)
{
    if (Mesh.Get() != Asset)
    {
        Mesh = Asset; Deltas.Reset(); Applied.Reset(); Offsets.Reset();
        // The mesh's captured deltas (the only ones a cooked desktop build keeps on the CPU), checked once per mesh.
        Contact = USkinMorphContactData::Find(Asset);
        ContactError.Reset();
        FString Receipt;
        if (Contact.IsValid() && !Contact->Validate(Asset, {}, Receipt)) ContactError = Receipt;
    }
    // The renderer skips weights this small (SkeletalRender.cpp's MinMorphTargetBlendWeight).
    Active.RemoveAll([](const TPair<const UMorphTarget*, float>& Morph) { return FMath::Abs(Morph.Value) <= UE_SMALL_NUMBER; });
    Active.Sort([](const TPair<const UMorphTarget*, float>& A, const TPair<const UMorphTarget*, float>& B) { return A.Key < B.Key; });
    if (Error.IsEmpty() && Active == Applied) return true;
    Applied.Reset(); Offsets.Reset(); Error.Reset();
    if (!Active.IsEmpty() && !ContactError.IsEmpty())
    {
        Error = ContactError;
        return false;
    }
    for (const TPair<const UMorphTarget*, float>& Morph : Active)
    {
        TArray<TPair<int32, FVector3f>>* Moves = Deltas.Find(Morph.Key);
        if (!Moves)
        {
            Moves = &Deltas.Add(Morph.Key);
            if (const FSkinMorphContactTarget* Captured = Contact.IsValid() ? Contact->FindTarget(Morph.Key->GetFName()) : nullptr)
                for (int32 I = 0; I < Captured->Vertices.Num(); ++I) Moves->Emplace(Captured->Vertices[I], Captured->Deltas[I]);
            else
                for (FMorphTargetDeltaIterator It = Morph.Key->GetDeltaIteratorForLOD(0); !It.AtEnd(); ++It)
                    Moves->Emplace(int32(It->SourceIdx), It->PositionDelta);
        }
        // A morph that renders deltas the CPU cannot read: the skin as shown is unknown here.
        if (Moves->IsEmpty() && Morph.Key->GetNumDeltasForLOD(0) > 0)
        {
            Deltas.Remove(Morph.Key); Offsets.Reset();
            Error = FString::Printf(TEXT("morph %s keeps no CPU deltas and no contact data"), *Morph.Key->GetName());
            return false;
        }
        for (const TPair<int32, FVector3f>& Move : *Moves) Offsets.FindOrAdd(Move.Key, FVector3f::ZeroVector) += Move.Value * Morph.Value;
    }
    Applied = MoveTemp(Active);
    return true;
}

FVector3f FSkinMorphOffsets::Skin(const FSkeletalMeshLODRenderData& LOD, const FSkinWeightVertexBuffer& Weights,
                                  TConstArrayView<FMatrix44f> RefToLocals, int32 Vertex, const FVector3f& Offset)
{
    int32 SectionIndex = INDEX_NONE, Local = INDEX_NONE;
    LOD.GetSectionFromVertexIndex(Vertex, SectionIndex, Local);
    if (!LOD.RenderSections.IsValidIndex(SectionIndex) || uint32(Vertex) >= Weights.GetNumVertices()) return FVector3f::ZeroVector;
    const FSkelMeshRenderSection& Section = LOD.RenderSections[SectionIndex];
    const TConstArrayView<FBoneIndexType> Bones = Section.HasUnifiedBoneMap() ? LOD.GetUnifiedBoneMap() : MakeArrayView(Section.BoneMap);
    FVector3f Skinned = FVector3f::ZeroVector;
    float Sum = 0.f;
    for (uint32 I = 0; I < Weights.GetMaxBoneInfluences(); ++I)
    {
        const float Weight = float(Weights.GetBoneWeight(Vertex, I));
        const uint32 Bone = Weights.GetBoneIndex(Vertex, I);
        if (Weight <= 0.f || !Bones.IsValidIndex(Bone) || !RefToLocals.IsValidIndex(Bones[Bone])) continue;
        Skinned += RefToLocals[Bones[Bone]].TransformVector(Offset) * Weight;
        Sum += Weight;
    }
    return Sum > 0.f ? Skinned / Sum : FVector3f::ZeroVector;
}

void FSkinMorphOffsets::AddTo(TArray<FVector3f>& Positions, const FSkeletalMeshLODRenderData& LOD, const FSkinWeightVertexBuffer& SkinWeights,
                              TConstArrayView<FMatrix44f> RefToLocals) const
{
    for (const TPair<int32, FVector3f>& Offset : Offsets)
        if (Positions.IsValidIndex(Offset.Key)) Positions[Offset.Key] += Skin(LOD, SkinWeights, RefToLocals, Offset.Key, Offset.Value);
}
