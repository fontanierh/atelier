#include "FoliageBuilder.h"
#include "Engine/StaticMesh.h"
#include "HAL/FileManager.h"
#include "MeshDescription.h"
#include "StaticMeshAttributes.h"
#include "StaticMeshCompiler.h"

namespace
{
// Versioned little-endian stream shared with atelier.mesh_geometry. Never hash
// struct padding, render-derived attributes, or a lossy JSON summary.
void UInt(FArchive& Out, uint32 Value)
{
    uint8 Bytes[4];
    for (uint32 I=0; I<4; ++I) Bytes[I]=uint8(Value>>(I*8));
    Out.Serialize(Bytes,4);
}
bool Float(FArchive& Out, float Value)
{
    if (!FMath::IsFinite(Value)) return false;
    uint32 Bits; FMemory::Memcpy(&Bits,&Value,sizeof(Bits)); UInt(Out,Bits);
    return !Out.IsError();
}
}

bool UYorimichiFoliageBuilder::ExportGeometrySnapshot(UStaticMesh* Mesh, const FString& Path)
{
    if (!IsInGameThread() || !Mesh || Path.IsEmpty()) return false;
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    const FString Temporary=Path+TEXT(".part");
    TUniquePtr<FArchive> Out(IFileManager::Get().CreateFileWriter(*Temporary));
    if (!Out) return false;
    bool Valid=true;
    const ANSICHAR Magic[]="ATELIER-MESH-1\n";
    Out->Serialize((void*)Magic,sizeof(Magic)-1);
    const int32 Count=Mesh->GetNumSourceModels();
    UInt(*Out,uint32(Count));
    Valid=Count>0;
    for (int32 L=0; Valid && L<Count; ++L)
    {
        const FMeshDescription* D=Mesh->GetMeshDescription(L);
        if (!D) { Valid=false;break; } // A render-buffer fallback cannot prove these attributes.
        FStaticMeshConstAttributes A(*D);
        auto P=A.GetVertexPositions();auto N=A.GetVertexInstanceNormals();
        auto C=A.GetVertexInstanceColors();auto UV=A.GetVertexInstanceUVs();
        auto Names=A.GetPolygonGroupMaterialSlotNames();
        if (!P.IsValid() || !N.IsValid() || !C.IsValid() || !UV.IsValid() || !Names.IsValid()) { Valid=false;break; }
        const int32 Channels=UV.GetNumChannels();
        if (Channels<1 || Channels>8 || D->PolygonGroups().Num()!=Mesh->GetStaticMaterials().Num() ||
            int64(D->Vertices().Num())!=int64(D->Triangles().Num())*3 ||
            int64(D->VertexInstances().Num())!=int64(D->Triangles().Num())*3) { Valid=false;break; }
        TMap<FPolygonGroupID,uint32> Slots;
        uint32 Slot=0;
        for (FPolygonGroupID Group:D->PolygonGroups().GetElementIDs())
        {
            if (Names[Group]!=Mesh->GetStaticMaterials()[Slot].MaterialSlotName) { Valid=false;break; }
            Slots.Add(Group,Slot++);
        }
        UInt(*Out,uint32(Channels));UInt(*Out,uint32(D->Triangles().Num()));
        int32 ExpectedCorner=0;
        for (FTriangleID Triangle:D->Triangles().GetElementIDs())
        {
            const uint32* Found=Slots.Find(D->GetTrianglePolygonGroup(Triangle));
            const auto Corners=D->GetTriangleVertexInstances(Triangle);
            if (!Valid || !Found || Corners.Num()!=3) { Valid=false;break; }
            UInt(*Out,*Found);
            for (FVertexInstanceID Corner:Corners)
            {
                // BuildVariant creates independent vertices in exact corner order.
                // Shared/rewired topology can change tangent construction even
                // when all corner positions happen to be equal.
                if (Corner.GetValue()!=ExpectedCorner || D->GetVertexInstanceVertex(Corner).GetValue()!=ExpectedCorner)
                { Valid=false;break; }
                ++ExpectedCorner;
                const FVector3f Position=P[D->GetVertexInstanceVertex(Corner)], Normal=N[Corner];
                const FVector4f Colour=C[Corner];
                for (float V:{Position.X,Position.Y,Position.Z,Normal.X,Normal.Y,Normal.Z,Colour.X,Colour.Y,Colour.Z,Colour.W})
                    if (!Float(*Out,V)) Valid=false;
                for (int32 Channel=0; Channel<Channels; ++Channel)
                {
                    const FVector2f Tex=UV.Get(Corner,Channel);
                    if (!Float(*Out,Tex.X) || !Float(*Out,Tex.Y)) Valid=false;
                }
            }
            if (!Valid) break;
        }
    }
    Valid=Out->Close() && !Out->IsError() && Valid;
    Out.Reset();
    if (Valid) Valid=IFileManager::Get().Move(*Path,*Temporary,true,true);
    if (!Valid) IFileManager::Get().Delete(*Temporary);
    return Valid;
}
