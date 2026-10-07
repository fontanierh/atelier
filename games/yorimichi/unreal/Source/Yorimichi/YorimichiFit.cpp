#include "YorimichiFit.h"
#include "Algo/Sort.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"

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
    // Every skinned vertex in the piece's frame (world centimetres about its centre).
    TArray<FVector> Local;
    Local.SetNumUninitialized(Skinned.Num());
    for (int32 I = 0; I < Skinned.Num(); ++I)
        Local[I] = (Piece.InverseTransformPosition(ToWorld.TransformPosition(FVector(Skinned[I]))) - Bounds.GetCenter()) * Scale;
    // A rod also counts the triangles its axis and four lines along its surface pass through: sparse geometry (hair
    // spikes) can cross it with no vertex inside.
    TArray<TPair<FVector, FVector>> Lines;
    if (bRod)
    {
        FVector A = FVector::ZeroVector, B = FVector::ZeroVector, Du = FVector::ZeroVector, Dv = FVector::ZeroVector;
        A[Axis] = -Half[Axis]; B[Axis] = Half[Axis]; Du[U] = .8f * Half[U]; Dv[V] = .8f * Half[V];
        for (const FVector& D : {FVector::ZeroVector, Du, -Du, Dv, -Dv}) Lines.Emplace(A + D, B + D);
    }
    const FRawStaticIndexBuffer16or32Interface* IndexBuffer = Lod.MultiSizeIndexContainer.GetIndexBuffer();
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
            const FVector& Q = Local[I];
            const float Along = Half[Axis] - FMath::Abs(Q[Axis]);
            const float Round = FMath::Square(Q[U] / Half[U]) + FMath::Square(Q[V] / Half[V]);
            if (Along <= 0.f || Round >= 1.f) continue;
            ++Inside;
            Depth = FMath::Max(Depth, FMath::Min(Along, (1.f - FMath::Sqrt(Round)) * FMath::Min(Half[U], Half[V])));
        }
        int32 Crossed = 0;
        if (Lines.Num() && IndexBuffer && IndexBuffer->Num())
            for (uint32 T = 0; T < Section.NumTriangles; ++T)
            {
                const uint32 I0 = IndexBuffer->Get(Section.BaseIndex + 3 * T), I1 = IndexBuffer->Get(Section.BaseIndex + 3 * T + 1),
                             I2 = IndexBuffer->Get(Section.BaseIndex + 3 * T + 2);
                if (!Local.IsValidIndex(I0) || !Local.IsValidIndex(I1) || !Local.IsValidIndex(I2)) continue;
                for (const TPair<FVector, FVector>& Line : Lines)
                {
                    FVector Hit, Normal;
                    if (FMath::SegmentTriangleIntersection(Line.Key, Line.Value, Local[I0], Local[I1], Local[I2], Hit, Normal)) { ++Crossed; break; }
                }
            }
        if (!Inside && !Crossed) continue;
        Total += Inside + Crossed;
        Deepest = FMath::Max(Deepest, Depth);
        const FName Slot = Materials.IsValidIndex(Section.MaterialIndex) ? Materials[Section.MaterialIndex].MaterialSlotName : NAME_None;
        Slots += FString::Printf(TEXT("; %s %d %.1f crossed %d"), *Slot.ToString(), Inside, Depth, Crossed);
    }
    // Where the skin and the piece were, to check the measure itself: the skin's world box and its box in the piece's
    // frame (centimetres about the piece's centre), and the piece's half sizes.
    FBox World(ForceInit), InPiece(ForceInit);
    for (int32 I = 0; I < Skinned.Num(); ++I)
    {
        World += ToWorld.TransformPosition(FVector(Skinned[I]));
        InPiece += Local[I];
    }
    return FString::Printf(TEXT("%s inside %d, deepest %.1f cm%s | skin %d verts, world %s, in piece %s, half %s, piece at %s"),
        bRod ? TEXT("rod") : TEXT("disc"), Total, Deepest, *Slots, Skinned.Num(), *World.ToString(), *InPiece.ToString(),
        *Half.ToString(), *Piece.GetLocation().ToString());
}
