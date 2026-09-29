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

// Diagnostic only. Original material, scatter, component culling and collision remain unchanged.
static FAutoConsoleCommandWithWorldAndArgs GrassArtCommand(TEXT("japan.GrassArt"),
    TEXT("TAG 0|1: original or isolated grass art. Optional forced LOD: 0 auto, 1 full, 2 medium, 3 far."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    {
        if (!World || Args.Num()<2 || Args.Num()>3 || (Args[1]!=TEXT("0") && Args[1]!=TEXT("1"))) return;
        const FString Tag=Args[0];
        if (Tag.IsEmpty()) return;
        for (TCHAR C:Tag) if (!FChar::IsAlnum(C) && C!=TEXT('_')) return;
        if (Args.Num()==3 && Args[2]!=TEXT("0") && Args[2]!=TEXT("1") && Args[2]!=TEXT("2") && Args[2]!=TEXT("3")) return;
        const bool Enabled=Args[1]==TEXT("1");
        const int32 Forced=Enabled && Args.Num()==3?FCString::Atoi(*Args[2]):0;
        TMap<FString,UStaticMesh*> Replacements;
        for (const FString Name:{TEXT("Grass_A"),TEXT("Grass_B")})
        {
            const FString Variant=Name+TEXT("_")+Tag;
            const FString Path=Enabled?FString::Printf(TEXT("/Game/Experiments/Grass/%s/%s.%s"),*Tag,*Variant,*Variant):
                FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"),*Name,*Name);
            auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Path);
            if (!Mesh) { UE_LOG(LogTemp,Error,TEXT("GRASS ART missing %s; keeping current meshes"),*Path); return; }
            Replacements.Add(Name,Mesh);
        }
#if WITH_EDITOR
        FAssetCompilingManager::Get().FinishAllCompilation();
#endif
        // Reject stale experiments imported in meters as centimeters. Validate
        // each LOD's actual vertex extent, not combined bounds containing LOD0.
        if (Enabled) for (const auto& Pair:Replacements)
        {
            auto* Original=LoadObject<UStaticMesh>(nullptr,*FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"),*Pair.Key,*Pair.Key));
            const auto* Data=Pair.Value->GetRenderData();
            if (!Original || !Data || Data->LODResources.Num()!=3) return;
            const double Expected=Original->GetBounds().BoxExtent.Size();
            for (const auto& LOD:Data->LODResources)
            {
                FBox3f Bounds(ForceInit);
                const auto& Positions=LOD.VertexBuffers.PositionVertexBuffer;
                if (!Positions.GetVertexData() || Positions.GetNumVertices()==0 || Expected<=0.)
                { UE_LOG(LogTemp,Error,TEXT("Experiment LOD has no CPU positions for unit validation; refusing swap")); return; }
                for (uint32 V=0;V<Positions.GetNumVertices();++V) Bounds+=Positions.VertexPosition(V);
                const double Ratio=Bounds.GetExtent().Size()/Expected;
                if (!FMath::IsFinite(Ratio) || Ratio<0.6 || Ratio>1.15)
                { UE_LOG(LogTemp,Error,TEXT("GRASS ART invalid LOD scale %s ratio=%.5f; keeping originals"),*Pair.Key,Ratio); return; }
            }
        }
        for (const auto& Pair:Replacements)
            if (const auto* Data=Pair.Value->GetRenderData())
                for (int32 LOD=0;LOD<Data->LODResources.Num();++LOD)
                    UE_LOG(LogTemp,Display,TEXT("GRASS ART LOD DATA %s lod=%d triangles=%u screen=%.5f"),
                        *Pair.Value->GetName(),LOD,Data->LODResources[LOD].GetNumTriangles(),Data->ScreenSize[LOD].GetValue());
        int32 Groups=0,Instances=0;
        for (TActorIterator<AJapanWorld> It(World);It;++It)
        {
            for (auto* Group:It->Groups)
                if (Group && Group->GetStaticMesh())
                    for (const auto& Pair:Replacements)
                        if (Group->GetStaticMesh()->GetName()==Pair.Key ||
                            (Group->GetStaticMesh()->GetPathName().StartsWith(TEXT("/Game/Experiments/Grass/")) && Group->GetStaticMesh()->GetName().StartsWith(Pair.Key+TEXT("_"))))
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
                                { UE_LOG(LogTemp,Error,TEXT("GRASS ART failed mesh swap %s"),*Pair.Key); return; }
                            }
                            Group->SetForcedLodModel(Forced);
                            ++Groups;Instances+=Group->GetInstanceCount();break;
                        }
            const FName Prepared(TEXT("GrassArtPrepared"));
            if (Enabled && !It->Tags.Contains(Prepared))
            {
                It->Tags.Add(Prepared);
                // Same startup capture timing issue as full-detail city tiles:
                // first-load compilation can capture the sky before its dome.
                // Refresh once after ticking resumes, never every frame/toggle.
                FTimerHandle Refresh;
                World->GetTimerManager().SetTimer(Refresh,FTimerDelegate::CreateWeakLambda(*It,[World]()
                {
                    for (TActorIterator<ASkyLight> Sky(World);Sky;++Sky)
                        if (auto* Light=Sky->GetLightComponent(); Light && !Light->IsRealTimeCaptureEnabled()) Light->RecaptureSky();
                    USkyLightComponent::UpdateSkyCaptureContents(World);
                    UE_LOG(LogTemp,Display,TEXT("GRASS ART refreshed startup sky"));
                }),2.f,false);
            }
        }
        UE_LOG(LogTemp,Display,TEXT("GRASS ART tag=%s enabled=%d forced=%d groups=%d instances=%d"),*Tag,Enabled,Forced,Groups,Instances);
    }));
