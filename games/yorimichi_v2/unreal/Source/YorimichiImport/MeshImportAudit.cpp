#include "MeshImportAudit.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/MorphTarget.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "StaticMeshResources.h"
#include "Misc/FileHelper.h"
#include "HAL/IConsoleManager.h"
#include "StaticMeshCompiler.h"
#include "DistanceFieldAtlas.h"
#include "MeshCardBuild.h"

FMeshDerivedDataAudit UMeshImportAudit::InspectDerivedData(UStaticMesh* Mesh)
{
    FMeshDerivedDataAudit Result;
    if (!Mesh || !IsInGameThread())
    {
        Result.Error = TEXT("A mesh and the editor game thread are required");
        return Result;
    }
    auto CVar = [](const TCHAR* Name)
    {
        const IConsoleVariable* Value = IConsoleManager::Get().FindConsoleVariable(Name);
        return Value ? Value->GetInt() : -1;
    };
    Result.GenerateDistanceFields = CVar(TEXT("r.GenerateMeshDistanceFields"));
    Result.GenerateCards = CVar(TEXT("r.MeshCardRepresentation"));
    FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
    if (GDistanceFieldAsyncQueue)
    {
        GDistanceFieldAsyncQueue->BlockUntilBuildComplete(Mesh, false);
        Result.DistanceFieldTasks = GDistanceFieldAsyncQueue->GetNumOutstandingTasks(Mesh);
    }
    if (GCardRepresentationAsyncQueue)
    {
        GCardRepresentationAsyncQueue->BlockUntilBuildComplete(Mesh, false);
        Result.CardTasks = GCardRepresentationAsyncQueue->GetNumOutstandingTasks(Mesh);
    }
    if (Mesh->IsCompiling() || Result.DistanceFieldTasks != 0 || Result.CardTasks != 0)
    {
        Result.Error = TEXT("Selected-mesh compilation did not complete or a compiler is unavailable");
        return Result;
    }
    Result.MeshRequestsDistanceField = Mesh->bGenerateMeshDistanceField;
    if (Mesh->GetNumSourceModels() > 0)
    {
        const FMeshBuildSettings& Settings = Mesh->GetSourceModel(0).BuildSettings;
        Result.HasSourceSettings = true;
        Result.DistanceFieldResolutionScale = Settings.DistanceFieldResolutionScale;
        Result.MaxLumenMeshCards = Settings.MaxLumenMeshCards;
    }
    // Compilation can replace render data. Never retain its pointers across the waits above.
    const FStaticMeshRenderData* Render = Mesh->GetRenderData();
    if (!Render || Render->LODResources.IsEmpty())
    {
        Result.Error = TEXT("No built LOD0 render data");
        return Result;
    }
    const FStaticMeshLODResources& LOD = Render->LODResources[0];
    if (const FDistanceFieldVolumeData* Field = LOD.DistanceFieldData)
    {
        Result.HasDistanceField = true;
        Result.DistanceFieldValid = Field->IsValid();
        Result.DistanceFieldBoundsFinite = Field->LocalSpaceMeshBounds.IsValid && !Field->LocalSpaceMeshBounds.ContainsNaN();
        Result.DistanceFieldAsyncBuilding = Field->bAsyncBuilding;
        Result.AlwaysLoadedBytes = Field->AlwaysLoadedMip.Num();
        Result.StreamableBytes = Field->StreamableMips.GetBulkDataSize();
        for (const FSparseDistanceFieldMip& Mip : Field->Mips)
        {
            Result.MipDimensions.Add(FIntVector(Mip.IndirectionDimensions));
            Result.MipBricks.Add(Mip.NumDistanceFieldBricks);
        }
    }
    if (const FCardRepresentationData* Cards = LOD.CardRepresentationData)
    {
        Result.HasCards = true;
        Result.CardCount = Cards->MeshCardsBuildData.CardBuildData.Num();
        Result.CardBoundsFinite = Cards->MeshCardsBuildData.Bounds.IsValid && !Cards->ContainsNaN();
    }
    if (Result.DistanceFieldAsyncBuilding)
    {
        Result.Error = TEXT("Distance-field payload still reports a pending build");
        return Result;
    }
    Result.Completed = true;
    return Result;
}

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

bool UMeshImportAudit::DumpSkeletalMesh(USkeletalMesh* Mesh, const FString& Path)
{
    FSkeletalMeshRenderData* Render = Mesh ? Mesh->GetResourceForRendering() : nullptr;
    if (!Render || Render->LODRenderData.IsEmpty()) return false;
    const FSkeletalMeshLODRenderData& LOD = Render->LODRenderData[0];
    const FReferenceSkeleton& Skeleton = Mesh->GetRefSkeleton();
    const FPositionVertexBuffer& Positions = LOD.StaticVertexBuffers.PositionVertexBuffer;
    const FStaticMeshVertexBuffer& Vertices = LOD.StaticVertexBuffers.StaticMeshVertexBuffer;
    const FSkinWeightVertexBuffer* Weights = LOD.GetSkinWeightVertexBuffer();
    if (!Weights) return false;
    TArray<FString> Lines;
    for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
        for (uint32 V = Section.BaseVertexIndex; V < Section.BaseVertexIndex + Section.NumVertices; ++V)
        {
            const FVector3f P = Positions.VertexPosition(V);
            const FVector4f N = Vertices.VertexTangentZ(V);
            const FVector2f UV = Vertices.GetVertexUV(V, 0);
            FString Line = FString::Printf(TEXT("v %d %.6f %.6f %.6f %.5f %.5f %.5f %.6f %.6f"), Section.MaterialIndex,
                                           P.X, P.Y, P.Z, N.X, N.Y, N.Z, UV.X, UV.Y);
            const FSkinWeightInfo Info = Weights->GetVertexSkinWeights(V);
            for (int32 I = 0; I < MAX_TOTAL_INFLUENCES; ++I)
                if (Info.InfluenceWeights[I] > 0)
                    Line += FString::Printf(TEXT(" %s:%.5f"), *Skeleton.GetBoneName(Section.BoneMap[Info.InfluenceBones[I]]).ToString(),
                                            Info.InfluenceWeights[I] / 65535.f);
            Lines.Add(Line);
        }
    TArray<uint32> Indices;
    LOD.MultiSizeIndexContainer.GetIndexBuffer(Indices);
    for (int32 I = 0; I + 2 < Indices.Num(); I += 3)
        Lines.Add(FString::Printf(TEXT("f %u %u %u"), Indices[I], Indices[I + 1], Indices[I + 2]));
    for (const UMorphTarget* Morph : Mesh->GetMorphTargets())
    {
        if (!Morph) continue;
        int32 Num = 0;
        const FMorphTargetDelta* Deltas = Morph->GetMorphTargetDelta(0, Num);
        for (int32 I = 0; I < Num; ++I)
            Lines.Add(FString::Printf(TEXT("m %s %u %.6f %.6f %.6f"), *Morph->GetName(), Deltas[I].SourceIdx,
                                      Deltas[I].PositionDelta.X, Deltas[I].PositionDelta.Y, Deltas[I].PositionDelta.Z));
    }
    return FFileHelper::SaveStringArrayToFile(Lines, *Path);
}
