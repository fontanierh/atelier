#include "SkateCollisionBuilder.h"
#include "SkateCollisionAsset.h"
#include "SkateCollisionWorld.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SplineMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"
#include "PhysicsEngine/BodySetup.h"
#include "StaticMeshResources.h"
#include "StaticMeshCompiler.h"
#include "UObject/UObjectIterator.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/Package.h"
#include "UObject/SavePackage.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "HAL/FileManager.h"
#include "Serialization/MemoryWriter.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace
{
    void MeshError(UStaticMesh* Mesh,const FString& Text,TArray<FString>& Errors)
    {Errors.Add(GetPathNameSafe(Mesh)+TEXT(": ")+Text);}
    bool UnsupportedShapes(const FKAggregateGeom& G)
    {return !G.TaperedCapsuleElems.IsEmpty()||!G.LevelSetElems.IsEmpty()||!G.SkinnedLevelSetElems.IsEmpty()
        ||!G.MLLevelSetElems.IsEmpty()||!G.SkinnedTriangleMeshElems.IsEmpty();}
    bool BakeMesh(UStaticMesh* Mesh,USkateCollisionMeshData& Data,TArray<FString>& Errors,TArray<FString>& Warnings)
    {
        const int32 Before=Errors.Num();
        if(!Mesh){Errors.Add(TEXT("Null collision mesh"));return false;}
        UStaticMesh* One=Mesh;FStaticMeshCompilingManager::Get().FinishCompilation(MakeArrayView(&One,1));
        UBodySetup* Body=Mesh->GetBodySetup();
        if(!Body){Warnings.Add(Mesh->GetPathName()+TEXT(": no UBodySetup; no collision record is baked"));return false;}
        Data.SourceMesh=Mesh;Data.FormatVersion=1;Data.SourceLODForCollision=Mesh->LODForCollision;Data.SourceBodySetupGuid=Body->BodySetupGuid;
        if(UnsupportedShapes(Body->AggGeom))MeshError(Mesh,TEXT("tapered capsules, level sets or skinned collision are unsupported"),Errors);
        for(const FKConvexElem& Hull:Body->AggGeom.ConvexElems)
        {
            auto& Out=Data.ConvexIndices.AddDefaulted_GetRef();
            Out.Indices=Hull.IndexData.IsEmpty()?Hull.GetChaosConvexIndices():Hull.IndexData;
            if(!Hull.VertexData.IsEmpty()&&Out.Indices.IsEmpty())MeshError(Mesh,TEXT("convex hull has vertices but no triangle indices"),Errors);
        }
        if(Body->GetCollisionTraceFlag()==CTF_UseComplexAsSimple)
        {
            if(Mesh->ComplexCollisionMesh)MeshError(Mesh,TEXT("custom ComplexCollisionMesh requires a separate supported bake; the former snapshot read this mesh's own LOD"),Errors);
            const FStaticMeshRenderData* Render=Mesh->GetRenderData();
            if(!Render||Render->LODResources.IsEmpty())MeshError(Mesh,TEXT("complex collision has no render LOD data"),Errors);
            else
            {
                Data.BakedLOD=FMath::Clamp(Mesh->LODForCollision,0,Render->LODResources.Num()-1);
                const auto& LOD=Render->LODResources[Data.BakedLOD];
                const auto& Positions=LOD.VertexBuffers.PositionVertexBuffer;
                const auto& Tangents=LOD.VertexBuffers.StaticMeshVertexBuffer;
                if(!Positions.GetVertexData()||Positions.GetNumVertices()==0||!Tangents.GetTangentData()
                    ||Tangents.GetNumVertices()!=Positions.GetNumVertices()||LOD.IndexBuffer.GetNumIndices()==0||LOD.IndexBuffer.GetIndexDataSize()==0)
                    MeshError(Mesh,TEXT("missing CPU position/tangent/index data; bake in the editor before buffers are stripped"),Errors);
                else
                {
                    for(uint32 I=0;I<Positions.GetNumVertices();++I)
                    {Data.Positions.Add(Positions.VertexPosition(I));Data.TangentZ.Add(Tangents.VertexTangentZ(I));}
                    const FIndexArrayView Indices=LOD.IndexBuffer.GetArrayView();
                    for(int32 I=0;I<Indices.Num();++I)Data.Indices.Add(int32(Indices[I]));
                    Data.TriangleMaterialSlots.Init(INDEX_NONE,Data.Indices.Num()/3);
                    for(const FStaticMeshSection& Section:LOD.Sections)
                    {
                        if(Section.FirstIndex%3!=0||uint64(Section.FirstIndex)+uint64(Section.NumTriangles)*3>uint64(Data.Indices.Num()))
                        {MeshError(Mesh,TEXT("render section is not aligned to the triangle index stream"),Errors);continue;}
                        for(uint32 I=0;I<Section.NumTriangles;++I)Data.TriangleMaterialSlots[Section.FirstIndex/3+I]=Section.MaterialIndex;
                        // The former gather traverses the entire index stream, even disabled sections.
                        if(!Section.bEnableCollision)Warnings.AddUnique(Mesh->GetPathName()+TEXT(": collision-disabled render sections are retained to match the former snapshot"));
                    }
                }
            }
        }
        Data.Validate(Errors);
        TArray<uint8> Bytes;FMemoryWriter Writer(Bytes);
        Writer<<Data.Positions;Writer<<Data.TangentZ;Writer<<Data.Indices;Writer<<Data.TriangleMaterialSlots;
        for(auto& Hull:Data.ConvexIndices)Writer<<Hull.Indices;
        Data.GeometryHash=FMD5::HashBytes(Bytes.GetData(),Bytes.Num());
        return Before==Errors.Num();
    }
    void CopyMesh(const USkateCollisionMeshData& From,USkateCollisionMeshData& To)
    {
        To.SourceMesh=From.SourceMesh;To.FormatVersion=From.FormatVersion;To.SourceLODForCollision=From.SourceLODForCollision;
        To.BakedLOD=From.BakedLOD;To.SourceBodySetupGuid=From.SourceBodySetupGuid;To.GeometryHash=From.GeometryHash;
        To.Positions=From.Positions;To.TangentZ=From.TangentZ;To.Indices=From.Indices;
        To.TriangleMaterialSlots=From.TriangleMaterialSlots;To.ConvexIndices=From.ConvexIndices;
    }
    template<class T> T* Asset(const FString& PackageName,TArray<FString>& Errors)
    {
        const FString Name=FPackageName::GetLongPackageAssetName(PackageName),Path=PackageName+TEXT(".")+Name;
        if(T* Existing=LoadObject<T>(nullptr,*Path,nullptr,LOAD_NoWarn|LOAD_Quiet))return Existing;
        UPackage* Package=CreatePackage(*PackageName);
        if(FindObject<UObject>(Package,*Name)) {Errors.Add(TEXT("Asset has incompatible class: ")+Path);return nullptr;}
        T* Created=NewObject<T>(Package,*Name,RF_Public|RF_Standalone);FAssetRegistryModule::AssetCreated(Created);return Created;
    }
    bool Save(UObject* Object,TArray<FString>& Errors)
    {
        UPackage* Package=Object->GetOutermost();Package->MarkPackageDirty();
        const FString Filename=FPackageName::LongPackageNameToFilename(Package->GetName(),FPackageName::GetAssetPackageExtension());
        IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename),true);
        FSavePackageArgs Args;Args.TopLevelFlags=RF_Public|RF_Standalone;Args.SaveFlags=SAVE_NoError;
        if(!UPackage::SavePackage(Package,Object,*Filename,Args)) {Errors.Add(TEXT("Could not save ")+Filename);return false;}
        return true;
    }
    TArray<UStaticMesh*> WorldMeshes(UWorld* World,TArray<FString>& Errors,TArray<FString>& Warnings)
    {
        TArray<UStaticMesh*> Meshes;
        if(!World){Errors.Add(TEXT("Missing world"));return Meshes;}
        for(TObjectIterator<UStaticMeshComponent> It;It;++It)
            if(It->GetWorld()==World&&It->IsRegistered()&&It->IsCollisionEnabled()&&It->GetCollisionResponseToChannel(ECC_Pawn)==ECR_Block)
            {
                if(UStaticMesh* Mesh=It->GetStaticMesh())Meshes.AddUnique(Mesh);
                if(Cast<USplineMeshComponent>(*It))
                    Warnings.AddUnique(It->GetPathName()+TEXT(": spline deformation is not included; the former base-mesh snapshot is retained"));
                for(int32 Slot=0;Slot<It->GetNumMaterials();++Slot)
                    if(const UMaterialInterface* Material=It->GetMaterial(Slot))if(Material->GetPhysicalMaterialMask())
                        Warnings.AddUnique(It->GetPathName()+TEXT(": physical material masks are unsupported; the section physical material is used"));
            }
        for(TObjectIterator<UPrimitiveComponent> It;It;++It)
            if(!Cast<UStaticMeshComponent>(*It)&&It->GetWorld()==World&&It->IsRegistered()&&It->IsCollisionEnabled()
                &&It->GetCollisionResponseToChannel(ECC_Pawn)==ECR_Block)
                Warnings.Add(It->GetPathName()+TEXT(": unsupported non-static-mesh collision component"));
        return Meshes;
    }
    // Byte-for-byte former render-buffer reader, retained only in this editor validation path.
    void LegacySurface(FSkateCollisionSnapshot& Snapshot,UStaticMesh* Mesh,const FTransform& T)
    {
        if(!Mesh->GetRenderData()||Mesh->GetRenderData()->LODResources.IsEmpty())return;
        const auto& LODs=Mesh->GetRenderData()->LODResources;
        const FStaticMeshLODResources& LOD=LODs[FMath::Clamp(Mesh->LODForCollision,0,LODs.Num()-1)];
        const FPositionVertexBuffer& Positions=LOD.VertexBuffers.PositionVertexBuffer;
        if(!Positions.GetVertexData()||Positions.GetNumVertices()==0||LOD.IndexBuffer.GetNumIndices()==0)return;
        const FIndexArrayView Indices=LOD.IndexBuffer.GetArrayView();
        for(int32 I=0;I+2<Indices.Num()&&!Snapshot.Full();I+=3)
        {
            FVector P[3];
            for(int32 K=0;K<3;++K)P[K]=T.TransformPosition(FVector(Positions.VertexPosition(Indices[I+K])));
            const FVector Authored=T.TransformVectorNoScale(FVector(FVector3f(LOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(Indices[I]))));
            if(FVector::DotProduct(FVector::CrossProduct(P[1]-P[0],P[2]-P[0]),Authored)<0)Swap(P[1],P[2]);
            Snapshot.Add(P[0],P[1],P[2]);
        }
    }
    bool CompareAt(UStaticMesh* Mesh,const USkateCollisionMeshData& Data,const FTransform& T,TArray<FString>& Errors)
    {
        if(T.ContainsNaN()) {MeshError(Mesh,TEXT("non-finite component/instance transform"),Errors);return false;}
        const UBodySetup* Body=Mesh->GetBodySetup();
        if(!Body)return false;
        FSkateCollisionSnapshot Live,Baked;
        // Covers the whole transformed mesh without changing the Add filters.
        FBox Region=Mesh->GetBoundingBox().TransformBy(T);
        Region+=Body->AggGeom.CalcAABB(T);Region=Region.ExpandBy(1.);
        Live.Region=Region;Baked.Region=Region;
        Live.Budget=MAX_int32;Baked.Budget=MAX_int32;
        if(Body->GetCollisionTraceFlag()==CTF_UseComplexAsSimple)
        {LegacySurface(Live,Mesh,T);Baked.AddSurface(Data,T,nullptr,TConstArrayView<USkateCollisionAsset*>());}
        else
        {
            for(const FKBoxElem& E:Body->AggGeom.BoxElems)
            {Live.AddBox(E.GetTransform()*T,FVector(E.X,E.Y,E.Z)*.5);Baked.AddBox(E.GetTransform()*T,FVector(E.X,E.Y,E.Z)*.5);}
            for(const FKSphereElem& E:Body->AggGeom.SphereElems)
            {Live.AddCapsule(E.GetTransform()*T,E.Radius,0);Baked.AddCapsule(E.GetTransform()*T,E.Radius,0);}
            for(const FKSphylElem& E:Body->AggGeom.SphylElems)
            {Live.AddCapsule(E.GetTransform()*T,E.Radius,E.Length*.5);Baked.AddCapsule(E.GetTransform()*T,E.Radius,E.Length*.5);}
            for(int32 I=0;I<Body->AggGeom.ConvexElems.Num();++I)
            {
                const FKConvexElem& E=Body->AggGeom.ConvexElems[I];
                const TArray<int32> Indices=E.IndexData.IsEmpty()?E.GetChaosConvexIndices():E.IndexData;
                Live.AddHull(E,E.GetTransform()*T,Indices);
                Baked.AddHull(E,E.GetTransform()*T,Data.ConvexIndices[I].Indices);
            }
        }
        FString Difference;
        if(!SkateCollisionSnapshotsEqual(Live,Baked,Difference)) {MeshError(Mesh,Difference,Errors);return false;}
        if(Baked.Num()>0&&!SkateValidateNativeCollisionSnapshot(Baked,Difference)) {MeshError(Mesh,Difference,Errors);return false;}
        return true;
    }
}
bool USkateCollisionBuilderLibrary::StripWorldMeshCpuAccess(const TArray<UStaticMesh*>& Meshes,
    bool bSave,TArray<FString>& Errors,TArray<FString>& Warnings)
{
    check(IsInGameThread());Errors.Reset();Warnings.Reset();
    TArray<UStaticMesh*> Unique;TSet<UStaticMesh*> Seen;
    for(UStaticMesh* Mesh:Meshes)
    {
        if(!Mesh){Errors.Add(TEXT("Null world mesh in CPU-strip request"));continue;}
        if(!Seen.Contains(Mesh)){Seen.Add(Mesh);Unique.Add(Mesh);}
    }
    if(!Errors.IsEmpty())return false;
    if(Unique.IsEmpty()){Errors.Add(TEXT("CPU-strip request contains no world meshes"));return false;}
    FStaticMeshCompilingManager::Get().FinishCompilation(MakeArrayView(Unique));
    for(UStaticMesh* Mesh:Unique)
    {
        // The editor keeps render CPU data independently of this cook flag.
        // PostEditChangeProperty would rebuild the mesh and regenerate its
        // BodySetupGuid; the direct property write preserves collision data.
        if(Mesh->bAllowCPUAccess)
        {
            Mesh->Modify();Mesh->bAllowCPUAccess=false;Mesh->MarkPackageDirty();
        }
        if(bSave)Save(Mesh,Errors);
    }
    return Errors.IsEmpty();
}
USkateCollisionAsset* USkateCollisionBuilderLibrary::BuildCatalog(const TArray<UStaticMesh*>& Meshes,
    const FString& CatalogPackage,bool bSave,TArray<FString>& Errors,TArray<FString>& Warnings)
{
    check(IsInGameThread());Errors.Reset();Warnings.Reset();
    if(!CatalogPackage.StartsWith(TEXT("/Game/"))||!FPackageName::IsValidLongPackageName(CatalogPackage))
    {Errors.Add(TEXT("Catalog must be a valid /Game asset package"));return nullptr;}
    TArray<TStrongObjectPtr<USkateCollisionMeshData>> Drafts;TSet<UStaticMesh*> Seen;
    for(UStaticMesh* Mesh:Meshes)
    {
        if(Seen.Contains(Mesh))continue;
        Seen.Add(Mesh);
        TStrongObjectPtr<USkateCollisionMeshData> Draft(NewObject<USkateCollisionMeshData>());
        if(BakeMesh(Mesh,*Draft,Errors,Warnings))Drafts.Add(MoveTemp(Draft));
    }
    if(!Errors.IsEmpty())return nullptr;
    const FString ObjectName=FPackageName::GetLongPackageAssetName(CatalogPackage);
    USkateCollisionAsset* Existing=LoadObject<USkateCollisionAsset>(nullptr,*(CatalogPackage+TEXT(".")+ObjectName),nullptr,LOAD_NoWarn|LOAD_Quiet);
    USkateCollisionAsset* Catalog=bSave?Asset<USkateCollisionAsset>(CatalogPackage,Errors):NewObject<USkateCollisionAsset>();
    if(!Catalog)return nullptr;
    if(Existing&&Catalog!=Existing)Catalog->SurfaceProfiles=Existing->SurfaceProfiles;
    Catalog->Meshes.Reset();Catalog->FormatVersion=1;Catalog->Revision=Existing?Existing->Revision+1:1;
    const FString Folder=FPackageName::GetLongPackagePath(CatalogPackage)+TEXT("/CollisionMeshes/");
    for(const auto& Draft:Drafts)
    {
        const FString SourcePath=Draft->SourceMesh.ToString();FTCHARToUTF8 Encoded(*SourcePath);
        const FString Stable=FMD5::HashBytes(reinterpret_cast<const uint8*>(Encoded.Get()),Encoded.Length());
        USkateCollisionMeshData* Data=bSave?Asset<USkateCollisionMeshData>(Folder+TEXT("DA_")+Stable,Errors):NewObject<USkateCollisionMeshData>();
        if(!Data)continue;
        CopyMesh(*Draft,*Data);Catalog->Meshes.Add(Data);
    }
    Catalog->Validate(Errors);
    if(!Errors.IsEmpty())return nullptr;
    if(bSave)
    {
        for(USkateCollisionMeshData* Data:Catalog->Meshes)Save(Data,Errors);
        Save(Catalog,Errors);
    }
    return Errors.IsEmpty()?Catalog:nullptr;
}
USkateCollisionAsset* USkateCollisionBuilderLibrary::BuildForWorld(UWorld* World,const FString& CatalogPackage,
    bool bSave,TArray<FString>& Errors,TArray<FString>& Warnings)
{
    check(IsInGameThread());Errors.Reset();Warnings.Reset();
    const auto Meshes=WorldMeshes(World,Errors,Warnings);if(!Errors.IsEmpty())return nullptr;
    TArray<FString> BakeErrors,BakeWarnings;
    auto* Catalog=BuildCatalog(Meshes,CatalogPackage,bSave,BakeErrors,BakeWarnings);
    Errors.Append(BakeErrors);Warnings.Append(BakeWarnings);return Catalog;
}
bool USkateCollisionBuilderLibrary::ValidateWorld(UWorld* World,USkateCollisionAsset* Catalog,
    TArray<FString>& Errors,TArray<FString>& Warnings)
{
    check(IsInGameThread());Errors.Reset();Warnings.Reset();
    if(!World||!Catalog){Errors.Add(TEXT("Missing world or collision catalog"));return false;}
    Catalog->Validate(Errors);WorldMeshes(World,Errors,Warnings);
    if(!Errors.IsEmpty())return false;
    for(TObjectIterator<UStaticMeshComponent> It;It;++It)
    {
        UStaticMeshComponent* C=*It;
        if(C->GetWorld()!=World||!C->IsRegistered()||!C->IsCollisionEnabled()||C->GetCollisionResponseToChannel(ECC_Pawn)!=ECR_Block)continue;
        UStaticMesh* Mesh=C->GetStaticMesh();if(!Mesh||!Mesh->GetBodySetup())continue;
        const auto* Data=Catalog->FindMesh(Mesh);
        if(!Data){MeshError(Mesh,TEXT("missing cooked collision record"),Errors);continue;}
        USkateCollisionMeshData* LiveData=NewObject<USkateCollisionMeshData>();
        if(!BakeMesh(Mesh,*LiveData,Errors,Warnings))continue;
        if(Data->GeometryHash!=LiveData->GeometryHash) {MeshError(Mesh,TEXT("live CPU geometry differs from baked record"),Errors);continue;}
        if(auto* ISM=Cast<UInstancedStaticMeshComponent>(C))
        {
            for(int32 I=0;I<ISM->GetInstanceCount();++I)
            {FTransform T;if(ISM->GetInstanceTransform(I,T,true))CompareAt(Mesh,*Data,T,Errors);else MeshError(Mesh,TEXT("unreadable instance transform"),Errors);}
        }
        else CompareAt(Mesh,*Data,C->GetComponentTransform(),Errors);
    }
    return Errors.IsEmpty();
}

bool USkateCollisionBuilderLibrary::ValidateCatalog(USkateCollisionAsset* Catalog,bool bLoadSourceMeshes,
    TArray<FString>& Errors,TArray<FString>& Warnings)
{
    check(IsInGameThread());Errors.Reset();Warnings.Reset();
    if(!Catalog){Errors.Add(TEXT("Missing collision catalog"));return false;}
    Catalog->Validate(Errors);if(!Errors.IsEmpty())return false;
    const FTransform Transforms[]={FTransform::Identity,FTransform(FQuat::Identity,FVector::ZeroVector,FVector(-1,1,1)),
        FTransform(FQuat::MakeFromEuler(FVector(13,29,7)),FVector(.1234,-17.875,513.25),FVector(-.37,1.9,2.6))};
    for(const USkateCollisionMeshData* Data:Catalog->Meshes)
    {
        UStaticMesh* Mesh=bLoadSourceMeshes?Data->SourceMesh.LoadSynchronous():Data->SourceMesh.Get();
        if(!Mesh){Errors.Add(Data->SourceMesh.ToString()+TEXT(": source mesh is not loaded for live comparison"));continue;}
        TStrongObjectPtr<USkateCollisionMeshData> Live(NewObject<USkateCollisionMeshData>());
        if(!BakeMesh(Mesh,*Live,Errors,Warnings))continue;
        if(!Data->Validate(Errors))continue;
        if(Data->GeometryHash!=Live->GeometryHash){MeshError(Mesh,TEXT("live CPU geometry differs from baked record"),Errors);continue;}
        for(const auto& T:Transforms)CompareAt(Mesh,*Data,T,Errors);
    }
    return Errors.IsEmpty();
}

FSkateCollisionValidationReport USkateCollisionBuilderLibrary::StripWorldMeshCpuAccessReport(
    const TArray<UStaticMesh*>& Meshes,bool bSave)
{
    FSkateCollisionValidationReport Report;
    Report.bValid=StripWorldMeshCpuAccess(Meshes,bSave,Report.Errors,Report.Warnings);
    return Report;
}

FSkateCollisionValidationReport USkateCollisionBuilderLibrary::ValidateCatalogReport(
    USkateCollisionAsset* Catalog,bool bLoadSourceMeshes)
{
    FSkateCollisionValidationReport Report;
    Report.bValid=ValidateCatalog(Catalog,bLoadSourceMeshes,Report.Errors,Report.Warnings);
    return Report;
}

FSkateCollisionValidationReport USkateCollisionBuilderLibrary::ValidateWorldReport(
    UWorld* World,USkateCollisionAsset* Catalog)
{
    FSkateCollisionValidationReport Report;
    Report.bValid=ValidateWorld(World,Catalog,Report.Errors,Report.Warnings);
    return Report;
}

FSkateCollisionValidationReport USkateCollisionBuilderLibrary::ValidateSurfaceAndSceneReport(
    UWorld* World,UStaticMesh* FixtureMesh,USkateCollisionAsset* Catalog)
{
    FSkateCollisionValidationReport Report;
    Report.bValid=ValidateSurfaceAndScene(World,FixtureMesh,Catalog,Report.Errors,Report.Warnings);
    return Report;
}
