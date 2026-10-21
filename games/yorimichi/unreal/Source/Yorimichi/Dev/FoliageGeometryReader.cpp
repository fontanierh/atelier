#include "FoliageGeometryReader.h"
#include "Engine/StaticMesh.h"

#if WITH_EDITOR
#include "StaticMeshAttributes.h"
#include "StaticMeshResources.h"
#include "MeshDescription.h"
#include "StaticMeshCompiler.h"
#include "UObject/Package.h"
#include "Misc/PackageName.h"
#include "HAL/FileManager.h"
#include "AssetRegistry/AssetRegistryModule.h"

namespace
{
bool ReadUInt(FArchive& File, uint32& Value)
{
    uint8 Bytes[4];
    File.Serialize(Bytes, sizeof(Bytes));
    if (File.IsError()) return false;
    Value=uint32(Bytes[0]) | uint32(Bytes[1])<<8 | uint32(Bytes[2])<<16 | uint32(Bytes[3])<<24;
    return true;
}

bool ReadFloat(FArchive& File, float& Value)
{
    uint32 Bits;
    if (!ReadUInt(File,Bits)) return false;
    static_assert(sizeof(Value)==sizeof(Bits));
    FMemory::Memcpy(&Value,&Bits,sizeof(Value));
    return FMath::IsFinite(Value);
}
}
#endif

UStaticMesh* UYorimichiFoliageGeometryReader::BuildVariant(UStaticMesh* Source,
    const FString& GeometryPath, const TArray<float>& Screens, const FString& Destination,
    UMaterialInterface* NearCanopy, UMaterialInterface* FarCanopy)
{
#if WITH_EDITOR
    if (!Source || !NearCanopy || !FarCanopy || !IsInGameThread() ||
        Screens.IsEmpty() || Screens.Num()>MAX_STATIC_MESH_LODS) return nullptr;
    for (float Screen:Screens)
        if (!FMath::IsFinite(Screen) || Screen<0.f || Screen>1.f) return nullptr;
    TUniquePtr<FArchive> File(IFileManager::Get().CreateFileReader(*GeometryPath));
    if (!File) return nullptr;
    static constexpr ANSICHAR Magic[]="ATELIER-MESH-1\n";
    ANSICHAR Header[sizeof(Magic)-1];
    File->Serialize(Header,sizeof(Header));
    uint32 LevelCount;
    if (File->IsError() || FMemory::Memcmp(Header,Magic,sizeof(Header)) ||
        !ReadUInt(*File,LevelCount) || LevelCount!=uint32(Screens.Num())) return nullptr;
    const FString Name=FPackageName::GetLongPackageAssetName(Destination);
    UPackage* Package=CreatePackage(*Destination);
    Package->FullyLoad();
    if (!Package->IsFullyLoaded()) return nullptr;
    UStaticMesh* Mesh=FindObject<UStaticMesh>(Package,*Name);
    if (!Mesh)
    {
        Mesh=NewObject<UStaticMesh>(Package,*Name,RF_Public|RF_Standalone);
        FAssetRegistryModule::AssetCreated(Mesh);
    }
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    Mesh->Modify();Mesh->GetStaticMaterials()=Source->GetStaticMaterials();
    Mesh->GetStaticMaterials().Add(FStaticMaterial(NearCanopy,TEXT("CanopyNear")));
    Mesh->GetStaticMaterials().Add(FStaticMaterial(FarCanopy,TEXT("CanopyFar")));
    TArray<FMeshDescription> Descriptions;Descriptions.SetNum(LevelCount);
    TArray<const FMeshDescription*> Pointers;
    Mesh->SetNumSourceModels(LevelCount);
    const uint32 ExpectedChannels=FMath::Max(1,Source->GetNumTexCoords(0));
    for (uint32 L=0;L<LevelCount;++L)
    {
        uint32 Channels,Triangles;
        if (!ReadUInt(*File,Channels) || !ReadUInt(*File,Triangles) ||
            Channels!=ExpectedChannels || Channels<1 || Channels>8 || Triangles>uint32(MAX_int32/3)) return nullptr;
        const uint64 Bytes=uint64(Triangles)*(4+3*(10+2*Channels)*4);
        if (File->Tell()>File->TotalSize() || Bytes>uint64(File->TotalSize()-File->Tell())) return nullptr;
        FMeshDescription& D=Descriptions[L];FStaticMeshAttributes A(D);A.Register();
        auto P=A.GetVertexPositions();auto N=A.GetVertexInstanceNormals();
        auto UV=A.GetVertexInstanceUVs();auto C=A.GetVertexInstanceColors();
        auto Names=A.GetPolygonGroupMaterialSlotNames();UV.SetNumChannels(Channels);
        TArray<FPolygonGroupID> Groups;
        for (const FStaticMaterial& Material:Mesh->GetStaticMaterials())
        {
            const FPolygonGroupID G=D.CreatePolygonGroup();
            Names[G]=Material.MaterialSlotName;Groups.Add(G);
        }
        for (uint32 Triangle=0;Triangle<Triangles;++Triangle)
        {
            uint32 Slot;
            if (!ReadUInt(*File,Slot) || Slot>=uint32(Groups.Num())) return nullptr;
            TArray<FVertexInstanceID> Corners;
            for (int32 Corner=0;Corner<3;++Corner)
            {
                float Values[10];
                for (float& Value:Values) if (!ReadFloat(*File,Value)) return nullptr;
                const FVertexID Vertex=D.CreateVertex();P[Vertex]=FVector3f(Values[0],Values[1],Values[2]);
                const FVertexInstanceID Instance=D.CreateVertexInstance(Vertex);
                N[Instance]=FVector3f(Values[3],Values[4],Values[5]);
                C[Instance]=FVector4f(Values[6],Values[7],Values[8],Values[9]);
                for (uint32 Channel=0;Channel<Channels;++Channel)
                {
                    float U,V;
                    if (!ReadFloat(*File,U) || !ReadFloat(*File,V)) return nullptr;
                    UV.Set(Instance,Channel,FVector2f(U,V));
                }
                Corners.Add(Instance);
            }
            D.CreateTriangle(Groups[Slot],Corners);
        }
        Pointers.Add(&D);
        auto& Model=Mesh->GetSourceModel(L);
        Model.ReductionSettings=FMeshReductionSettings{};
        Model.ReductionSettings.BaseLODModel=L;
        Model.BuildSettings.bRecomputeNormals=false;Model.BuildSettings.bRecomputeTangents=true;
        Model.BuildSettings.bRemoveDegenerates=false;
        Model.BuildSettings.bGenerateLightmapUVs=false;Model.BuildSettings.bUseFullPrecisionUVs=true;
        Model.BuildSettings.DistanceFieldResolutionScale=0;Model.BuildSettings.MaxLumenMeshCards=0;
        Model.ScreenSize.Default=Screens[L];
    }
    if (File->IsError() || File->Tell()!=File->TotalSize() || !File->Close()) return nullptr;
    File.Reset();
    Mesh->SetAutoComputeLODScreenSize(false);Mesh->bGenerateMeshDistanceField=false;
    UStaticMesh::FBuildMeshDescriptionsParams Params;
    if (!Mesh->BuildFromMeshDescriptions(Pointers,Params)) return nullptr;
    Mesh->SetLightMapCoordinateIndex(0);Mesh->MarkPackageDirty();
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    return Mesh;
#else
    return nullptr;
#endif
}
