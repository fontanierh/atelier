#include "JapanWorld.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "TimerManager.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#if WITH_EDITOR
#include "AssetCompilingManager.h"
#endif

// Both the settings menu and the diagnostic command use the same validated swap.
// LOD0, materials, instances and collision stay unchanged; only distant leaf outlines differ.
static bool ApplyCityTreeLODs(AJapanWorld* Landscape,const FString& Tag,bool Enabled,int32 Forced,float DistanceScale=1.5f)
{
    if (!Landscape || !Landscape->bLoaded) return false;
    UWorld* World=Landscape->GetWorld();
    Forced=FMath::Clamp(Forced,0,3);
    DistanceScale=FMath::Clamp(DistanceScale,.5f,3.f);
    // UE's HISM renderer treats ForcedLodModel as a zero-based nonzero index.
    // A full-detail comparison uses the original single-LOD mesh, avoiding its
    // ambiguous zero/automatic case and preserving the production leaf geometry.
    const bool OptimizedMesh=Enabled && Forced!=1;
    TMap<FString,UStaticMesh*> Replacements;
    for (const FString Name:{TEXT("HD_ArcadeTree"),TEXT("HD_PlazaTreeGold"),TEXT("HD_PlazaTreeOrange")})
    {
        const FString Variant=Name+TEXT("_")+Tag;
        const FString Path=OptimizedMesh?FString::Printf(TEXT("/Game/Experiments/CityTrees/%s/%s.%s"),*Tag,*Variant,*Variant):
            FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"),*Name,*Name);
        auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);
        if (!Mesh) { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS missing %s; keeping current meshes"),*Path); return false; }
        Replacements.Add(Name,Mesh);
    }
#if WITH_EDITOR
    FAssetCompilingManager::Get().FinishAllCompilation();
#endif
    // Reject stale experiments imported in meters as centimeters. Validate
    // each LOD's actual vertex extent, not combined bounds containing LOD0.
    if (OptimizedMesh) for (const auto& Pair:Replacements)
    {
        auto* Original=LoadObject<UStaticMesh>(nullptr,*FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"),*Pair.Key,*Pair.Key));
        const auto* Data=Pair.Value->GetRenderData();
        if (!Original || !Data || Data->LODResources.Num()!=3) return false;
        const auto* OriginalData=Original->GetRenderData();
        if (!OriginalData || OriginalData->LODResources.Num()==0) return false;
        const auto& A=OriginalData->LODResources[0];const auto& B=Data->LODResources[0];
        const auto& AP=A.VertexBuffers.PositionVertexBuffer;const auto& BP=B.VertexBuffers.PositionVertexBuffer;
        if (!AP.GetVertexData() || !BP.GetVertexData() ||
            !A.VertexBuffers.StaticMeshVertexBuffer.GetTangentData() || !B.VertexBuffers.StaticMeshVertexBuffer.GetTangentData() ||
            AP.GetNumVertices()!=BP.GetNumVertices() ||
            A.GetNumTriangles()!=B.GetNumTriangles() || Original->GetMaterial(0)!=Pair.Value->GetMaterial(0))
        { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS changed production LOD0; refusing swap %s"),*Pair.Key);return false; }
        for (uint32 V=0;V<AP.GetNumVertices();++V)
            if (!AP.VertexPosition(V).Equals(BP.VertexPosition(V),.01f) ||
                !A.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(V).Equals(B.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(V),.001f))
            { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS changed production positions/normals; refusing swap %s"),*Pair.Key);return false; }
        UE_LOG(LogTemp,Display,TEXT("CITY TREE LOD0 VERIFIED %s vertices=%u triangles=%u production_material=1 positions_normals=1"),
            *Pair.Key,AP.GetNumVertices(),A.GetNumTriangles());
        const double Expected=Original->GetBounds().BoxExtent.Size();
        for (const auto& LOD:Data->LODResources)
        {
            FBox3f Bounds(ForceInit);
            const auto& Positions=LOD.VertexBuffers.PositionVertexBuffer;
            if (!Positions.GetVertexData() || Positions.GetNumVertices()==0 || Expected<=0.)
            { UE_LOG(LogTemp,Error,TEXT("Experiment LOD has no CPU positions for unit validation; refusing swap")); return false; }
            for (uint32 V=0;V<Positions.GetNumVertices();++V) Bounds+=Positions.VertexPosition(V);
            const double Ratio=Bounds.GetExtent().Size()/Expected;
            if (!FMath::IsFinite(Ratio) || Ratio<0.8 || Ratio>1.15)
            { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS invalid LOD scale %s ratio=%.5f; keeping originals"),*Pair.Key,Ratio); return false; }
        }
    }
    for (const auto& Pair:Replacements)
        if (const auto* Data=Pair.Value->GetRenderData())
            for (int32 LOD=0;LOD<Data->LODResources.Num();++LOD)
                UE_LOG(LogTemp,Display,TEXT("CITY TREE LOD DATA %s lod=%d triangles=%u screen=%.5f"),
                    *Pair.Value->GetName(),LOD,Data->LODResources[LOD].GetNumTriangles(),Data->ScreenSize[LOD].GetValue());
    int32 Groups=0,Instances=0;
    {
        for (auto* Group:Landscape->Groups)
            if (Group && Group->GetStaticMesh())
                for (const auto& Pair:Replacements)
                    if (Group->GetStaticMesh()->GetName()==Pair.Key ||
                        (Group->GetStaticMesh()->GetPathName().StartsWith(TEXT("/Game/Experiments/CityTrees/")) && Group->GetStaticMesh()->GetName().StartsWith(Pair.Key+TEXT("_"))))
                    {
                        if (Group->GetStaticMesh()!=Pair.Value)
                        {
                            // Static registered components reject mesh changes
                            // after BeginPlay. Preserve mobility and instances,
                            // rebuild their registration around the mesh swap.
                            const bool Registered=Group->IsRegistered();
                            if (Registered) Group->UnregisterComponent();
                            const bool Changed=Group->SetStaticMesh(Pair.Value);
                            if (Registered) Group->RegisterComponent();
                            if (!Changed || Group->GetStaticMesh()!=Pair.Value)
                            { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS failed mesh swap %s"),*Pair.Key); return false; }
                        }
                        Group->SetForcedLodModel(OptimizedMesh && Forced>=2 ? Forced-1 : 0);
                        Group->SetLODDistanceScale(Enabled ? DistanceScale : 1.f);
                        // No minimum-LOD override may permanently remove near detail.
                        if (Group->bOverrideMinLOD || Group->MinLOD!=0)
                        {
                            Group->bOverrideMinLOD=false;Group->MinLOD=0;
                            Group->MarkRenderStateDirty();
                        }
                        ++Groups;Instances+=Group->GetInstanceCount();break;
                    }
        const FName Prepared(TEXT("CityTreeLODPrepared"));
        if (Enabled && !Landscape->Tags.Contains(Prepared))
        {
            Landscape->Tags.Add(Prepared);
            // Same startup capture timing issue as full-detail city tiles:
            // first-load compilation can capture the sky before its dome.
            // Refresh once after ticking resumes, never every frame/toggle.
            FTimerHandle Refresh;
            World->GetTimerManager().SetTimer(Refresh,FTimerDelegate::CreateWeakLambda(Landscape,[World]()
            {
                for (TActorIterator<ASkyLight> Sky(World);Sky;++Sky)
                    if (auto* Light=Sky->GetLightComponent(); Light && !Light->IsRealTimeCaptureEnabled()) Light->RecaptureSky();
                USkyLightComponent::UpdateSkyCaptureContents(World);
                UE_LOG(LogTemp,Display,TEXT("CITY TREE LODS refreshed startup sky"));
            }),2.f,false);
        }
    }
    UE_LOG(LogTemp,Display,TEXT("CITY TREE LODS tag=%s enabled=%d forced=%d groups=%d instances=%d distance_scale=%.2f"),*Tag,Enabled,Forced,Groups,Instances,DistanceScale);
    return true;
}

bool AJapanWorld::ApplyTreeOptimization(bool bEnabled,int32 LODMode,float DistanceScale)
{
    if (!bLoaded) return false;
    LODMode=FMath::Clamp(LODMode,0,3);DistanceScale=FMath::Clamp(DistanceScale,.5f,3.f);
    if (AppliedTreeOptimization == int32(bEnabled) && AppliedTreeLODMode==LODMode &&
        FMath::IsNearlyEqual(AppliedTreeDistanceScale,DistanceScale)) return true;
    // A failed swap may have touched an earlier group: force a real rollback/retry.
    AppliedTreeOptimization = -1;
    if (!ApplyCityTreeLODs(this,TEXT("v4"),bEnabled,LODMode,DistanceScale)) return false;
    AppliedTreeOptimization = int32(bEnabled);
    AppliedTreeLODMode=LODMode;AppliedTreeDistanceScale=DistanceScale;
    return true;
}

// Keep forced-LOD experiments available without changing a player's saved setting.
static FAutoConsoleCommandWithWorldAndArgs CityTreeLODCommand(TEXT("japan.CityTreeLODs"),
    TEXT("TAG 0|1: original or leaf-outline LODs. Optional forced LOD: 0 auto, 1 full, 2 medium, 3 far."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    {
        if (!World || Args.Num()<2 || Args.Num()>3 || (Args[1]!=TEXT("0") && Args[1]!=TEXT("1"))) return;
        const FString Tag=Args[0];
        if (Tag.IsEmpty()) return;
        for (TCHAR C:Tag) if (!FChar::IsAlnum(C) && C!=TEXT('_')) return;
        if (Args.Num()==3 && Args[2]!=TEXT("0") && Args[2]!=TEXT("1") && Args[2]!=TEXT("2") && Args[2]!=TEXT("3")) return;
        const bool Enabled=Args[1]==TEXT("1");
        const int32 Forced=Enabled && Args.Num()==3?FCString::Atoi(*Args[2]):0;
        for (TActorIterator<AJapanWorld> It(World);It;++It) ApplyCityTreeLODs(*It,Tag,Enabled,Forced);
    }));
