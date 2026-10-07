#include "YorimichiFit.h"
#include "Algo/Sort.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Rendering/SkeletalMeshRenderData.h"

FString UYorimichiFitLibrary::PropClearance(USkeletalMeshComponent* Body, UStaticMeshComponent* Prop, float MarginCm)
{
    if (!Body || !Prop || !Prop->GetStaticMesh() || !Body->GetSkeletalMeshAsset()) return TEXT("no body or piece");
    FSkeletalMeshRenderData* Render = Body->GetSkeletalMeshRenderData();
    if (!Render || !Render->LODRenderData.Num() || !Body->GetSkinWeightBuffer(0)) return TEXT("no render data");
    const FSkeletalMeshLODRenderData& Lod = Render->LODRenderData[0];
    TArray<FMatrix44f> RefToLocals;
    Body->CacheRefToLocalMatrices(RefToLocals);
    TArray<FVector3f> Skinned;
    USkinnedMeshComponent::ComputeSkinnedPositions(Body, Skinned, RefToLocals, Lod, *Body->GetSkinWeightBuffer(0));
    if (!Skinned.Num()) return TEXT("no skinned positions (CPU access?)");

    // The piece's shape in its own axes, in world centimetres: half sizes, the long (rod) or thin (disc) axis.
    const FBox Bounds = Prop->GetStaticMesh()->GetBoundingBox();
    const FTransform Piece = Prop->GetComponentTransform();
    const FVector Scale = Piece.GetScale3D().GetAbs();
    const FVector Half = Bounds.GetExtent() * Scale - FVector(MarginCm);
    if (Half.GetMin() <= 0.f) return TEXT("margin larger than the piece");
    int32 Order[3] = {0, 1, 2};   // largest first
    Algo::Sort(Order, [&](int32 A, int32 B) { return Half[A] > Half[B]; });
    const bool bRod = Half[Order[0]] > 2.f * Half[Order[1]];
    const int32 Axis = bRod ? Order[0] : Order[2], U = bRod ? Order[1] : Order[0], V = bRod ? Order[2] : Order[1];

    const FTransform ToWorld = Body->GetComponentTransform();
    const TArray<FSkeletalMaterial>& Materials = Body->GetSkeletalMeshAsset()->GetMaterials();
    int32 Total = 0;
    float Deepest = 0.f;
    FString Slots;
    for (const FSkelMeshRenderSection& Section : Lod.RenderSections)
    {
        int32 Inside = 0;
        float Depth = 0.f;
        for (uint32 I = Section.BaseVertexIndex; I < Section.BaseVertexIndex + Section.NumVertices && I < (uint32)Skinned.Num(); ++I)
        {
            const FVector Q = (Piece.InverseTransformPosition(ToWorld.TransformPosition(FVector(Skinned[I]))) - Bounds.GetCenter()) * Scale;
            const float Along = Half[Axis] - FMath::Abs(Q[Axis]);
            const float Round = FMath::Square(Q[U] / Half[U]) + FMath::Square(Q[V] / Half[V]);
            if (Along <= 0.f || Round >= 1.f) continue;
            ++Inside;
            Depth = FMath::Max(Depth, FMath::Min(Along, (1.f - FMath::Sqrt(Round)) * FMath::Min(Half[U], Half[V])));
        }
        if (!Inside) continue;
        Total += Inside;
        Deepest = FMath::Max(Deepest, Depth);
        const FName Slot = Materials.IsValidIndex(Section.MaterialIndex) ? Materials[Section.MaterialIndex].MaterialSlotName : NAME_None;
        Slots += FString::Printf(TEXT("; %s %d %.1f"), *Slot.ToString(), Inside, Depth);
    }
    return FString::Printf(TEXT("%s inside %d, deepest %.1f cm%s"), bRod ? TEXT("rod") : TEXT("disc"), Total, Deepest, *Slots);
}
