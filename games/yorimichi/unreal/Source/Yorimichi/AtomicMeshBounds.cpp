#include "AtomicMeshBounds.h"
#include "Engine/StaticMesh.h"
#if WITH_EDITOR
#include "StaticMeshResources.h"
#endif

/** @cc [owner:fontanierh,label:correctness] atomic-lod0-original-bounds
 * Independent rigid parts MUST preserve the original single-LOD MeshBuilder float32
 * AABB, center and maximum squared vertex-radius arithmetic. Missing, duplicate,
 * nonfinite, multi-LOD or inaccessible render data MUST refuse; an AABB diagonal
 * sphere or a source-derived substitute MUST NOT stand in for actual render vertices. */
bool AtomicMeshBounds::MeasureLod0PartsBounds(const TArray<UStaticMesh*>& Parts, FBoxSphereBounds& OutBounds)
{
    OutBounds = FBoxSphereBounds(ForceInit);
#if WITH_EDITOR
    if (Parts.IsEmpty()) return false;
    TSet<const UStaticMesh*> Seen;
    FBox3f Box(ForceInit);
    for (const UStaticMesh* Mesh : Parts)
    {
        if (!Mesh || Seen.Contains(Mesh) || !Mesh->GetRenderData()
            || Mesh->GetRenderData()->LODResources.Num() != 1) return false;
        Seen.Add(Mesh);
        const auto& Buffer = Mesh->GetRenderData()->LODResources[0].VertexBuffers.PositionVertexBuffer;
        if (!Buffer.GetVertexData() || Buffer.GetNumVertices() == 0) return false;
        for (uint32 Index = 0; Index < Buffer.GetNumVertices(); ++Index)
        {
            const FVector3f Position = Buffer.VertexPosition(Index);
            if (Position.ContainsNaN()) return false;
            Box += Position;
        }
    }
    if (!Box.IsValid) return false;
    const FVector3f Center = Box.GetCenter();
    float RadiusSquared = 0.f;
    for (const UStaticMesh* Mesh : Parts)
    {
        const auto& Buffer = Mesh->GetRenderData()->LODResources[0].VertexBuffers.PositionVertexBuffer;
        for (uint32 Index = 0; Index < Buffer.GetNumVertices(); ++Index)
            RadiusSquared = FMath::Max(RadiusSquared, (Buffer.VertexPosition(Index) - Center).SizeSquared());
    }
    OutBounds = FBoxSphereBounds(FVector(Center), FVector(Box.GetExtent()), FMath::Sqrt(RadiusSquared));
    return !OutBounds.ContainsNaN() && OutBounds.SphereRadius > 0.;
#else
    return false;
#endif
}
