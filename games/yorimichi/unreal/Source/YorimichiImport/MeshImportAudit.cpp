#include "MeshImportAudit.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Misc/FileHelper.h"

bool UMeshImportAudit::DumpMeshTriangles(UStaticMesh* Mesh, FVector Origin, const FString& Path)
{
    if (!Mesh || !Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) return false;
    const FStaticMeshLODResources& LOD = Mesh->GetRenderData()->LODResources[0];
    const FIndexArrayView Indices = LOD.IndexBuffer.GetArrayView();
    const FPositionVertexBuffer& Positions = LOD.VertexBuffers.PositionVertexBuffer;
    TArray<uint8> Bytes;
    Bytes.Reserve(Indices.Num() * 3 * sizeof(double));
    for (int32 Index = 0; Index < Indices.Num(); ++Index)
    {
        const FVector P = Origin + FVector(Positions.VertexPosition(Indices[Index]));
        for (double Value : {P.X, P.Y, P.Z})
            Bytes.Append(reinterpret_cast<const uint8*>(&Value), sizeof(double));
    }
    return FFileHelper::SaveArrayToFile(Bytes, *Path);
}
