#include "JapanWorld.h"
#include "CitySurfacePieces.h"
#include "AtelierData.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "TimerManager.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "UObject/StrongObjectPtr.h"
#if WITH_EDITOR
#include "StaticMeshCompiler.h"
#endif

static const TCHAR* CityTreeParents[]={TEXT("HD_ArcadeTree"),TEXT("HD_PlazaTreeGold"),TEXT("HD_PlazaTreeOrange")};

namespace
{
struct FCityTreeManifestCache
{
    bool bLoaded = false;
    bool bValid = false;
    TMap<FString,FString> PiecePaths;   // exact child piece name -> original /Game/Experiments/CitySurfaces/v1_128m/... path
    TSet<FName> AcceptedTags;
};

const FCityTreeManifestCache& GetCityTreeManifest()
{
    static FCityTreeManifestCache Cache;
    if (!Cache.bLoaded)
    {
        Cache.bLoaded = true;
        TMap<FString,TArray<FString>> CityPieces;
        if (JapanCityPieces::Read(AtelierReadJson(AtelierDataPath(TEXT("city_surface_tiles/v1_128m/manifest.json"))),CityPieces))
        {
            Cache.bValid = true;
            for (const TCHAR* Parent : CityTreeParents)
            {
                const auto* Paths = CityPieces.Find(Parent);
                if (!Paths || Paths->IsEmpty()) { Cache.bValid = false; Cache.PiecePaths.Reset(); Cache.AcceptedTags.Reset(); break; }
                for (const FString& Path : *Paths)
                {
                    const FString Base = FPaths::GetBaseFilename(Path);
                    Cache.PiecePaths.Add(Base, Path);
                    Cache.AcceptedTags.Add(FName(*(TEXT("CityPiece:") + Base)));
                    Cache.AcceptedTags.Add(FName(*(TEXT("CityPiece:city:") + Base)));
                    Cache.AcceptedTags.Add(FName(*(TEXT("city:") + Base)));
                }
            }
        }
    }
    return Cache;
}

struct FCityTreeVariantSet
{
    TMap<FString,TStrongObjectPtr<UStaticMesh>> Originals;
    TMap<FString,TStrongObjectPtr<UStaticMesh>> Optimized;
    bool bValidatedOptimized = false;
    bool bLoggedOriginal = false;
};

const FCityTreeVariantSet* PrepareCityTreeVariant(const FString& Tag, bool bOptimizedMesh)
{
    const FCityTreeManifestCache& Manifest = GetCityTreeManifest();
    if (!Manifest.bValid) return nullptr;
    static TMap<FString,FCityTreeVariantSet> Variants;
    FCityTreeVariantSet& Set = Variants.FindOrAdd(Tag);
    if (Set.Originals.Num() != Manifest.PiecePaths.Num())
    {
        Set.Originals.Reset();
        for (const auto& Pair : Manifest.PiecePaths)
        {
            UStaticMesh* Original = LoadObject<UStaticMesh>(nullptr, *Pair.Value);
            if (!Original) return nullptr;
            Set.Originals.Add(Pair.Key, TStrongObjectPtr<UStaticMesh>(Original));
        }
    }
    if (bOptimizedMesh && Set.Optimized.Num() != Manifest.PiecePaths.Num())
    {
        Set.Optimized.Reset();
        for (const auto& Pair : Manifest.PiecePaths)
        {
            const FString Variant = Pair.Key + TEXT("_") + Tag;
            const FString Path = FString::Printf(TEXT("/Game/Experiments/CityTrees/%s/%s.%s"), *Tag, *Variant, *Variant);
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *Path);
            if (!Mesh)
            {
                UE_LOG(LogTemp, Error, TEXT("CITY TREE LODS missing %s; keeping current meshes"), *Path);
                Set.Optimized.Reset();
                return nullptr;
            }
            Set.Optimized.Add(Pair.Key, TStrongObjectPtr<UStaticMesh>(Mesh));
        }
    }
#if WITH_EDITOR
    // Never call global FAssetCompilingManager::Get().FinishAllCompilation() in -game (which blocks the game thread
    // on thousands of unrelated streaming world assets). Finish only any still-compiling city-tree mesh itself.
    {
        TArray<UStaticMesh*> Compiling;
        for (const auto& Pair : Set.Originals)
            if (Pair.Value.IsValid() && Pair.Value->IsCompiling()) Compiling.Add(Pair.Value.Get());
        if (bOptimizedMesh)
            for (const auto& Pair : Set.Optimized)
                if (Pair.Value.IsValid() && Pair.Value->IsCompiling()) Compiling.Add(Pair.Value.Get());
        if (!Compiling.IsEmpty())
            FStaticMeshCompilingManager::Get().FinishCompilation(Compiling);
    }
#endif
    if (bOptimizedMesh && !Set.bValidatedOptimized)
    {
        for (const auto& Pair : Set.Optimized)
        {
            UStaticMesh* Candidate = Pair.Value.Get();
            UStaticMesh* Original = Set.Originals.FindChecked(Pair.Key).Get();
#if WITH_EDITORONLY_DATA
            const bool bNanite = Candidate->IsNaniteEnabled();
#else
            const bool bNanite = Candidate->HasValidNaniteData();
#endif
            if (bNanite)
            { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS require non-Nanite HISM meshes; refusing swap %s"),*Pair.Key); return nullptr; }
            const auto* Data = Candidate->GetRenderData();
            if (!Original || !Data || Data->LODResources.Num() != 3) return nullptr;
            const auto* OriginalData = Original->GetRenderData();
            if (!OriginalData || OriginalData->LODResources.Num() == 0) return nullptr;
            const auto& A = OriginalData->LODResources[0]; const auto& B = Data->LODResources[0];
            const auto& AP = A.VertexBuffers.PositionVertexBuffer; const auto& BP = B.VertexBuffers.PositionVertexBuffer;
            if (!AP.GetVertexData() || !BP.GetVertexData() ||
                !A.VertexBuffers.StaticMeshVertexBuffer.GetTangentData() || !B.VertexBuffers.StaticMeshVertexBuffer.GetTangentData() ||
                AP.GetNumVertices() != BP.GetNumVertices() ||
                A.GetNumTriangles() != B.GetNumTriangles() || Original->GetMaterial(0) != Candidate->GetMaterial(0))
            { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS changed production LOD0; refusing swap %s"),*Pair.Key); return nullptr; }
            for (uint32 V = 0; V < AP.GetNumVertices(); ++V)
                if (!AP.VertexPosition(V).Equals(BP.VertexPosition(V), .01f) ||
                    !A.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(V).Equals(B.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(V), .001f))
                { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS changed production positions/normals; refusing swap %s"),*Pair.Key); return nullptr; }
            UE_LOG(LogTemp,Display,TEXT("CITY TREE LOD0 VERIFIED %s vertices=%u triangles=%u production_material=1 positions_normals=1"),
                *Pair.Key, AP.GetNumVertices(), A.GetNumTriangles());
            const double Expected = Original->GetBounds().BoxExtent.Size();
            for (const auto& LOD : Data->LODResources)
            {
                FBox3f Bounds(ForceInit);
                const auto& Positions = LOD.VertexBuffers.PositionVertexBuffer;
                if (!Positions.GetVertexData() || Positions.GetNumVertices() == 0 || Expected <= 0.)
                { UE_LOG(LogTemp,Error,TEXT("Experiment LOD has no CPU positions for unit validation; refusing swap")); return nullptr; }
                for (uint32 V = 0; V < Positions.GetNumVertices(); ++V) Bounds += Positions.VertexPosition(V);
                const double Ratio = Bounds.GetExtent().Size() / Expected;
                if (!FMath::IsFinite(Ratio) || Ratio < 0.8 || Ratio > 1.15)
                { UE_LOG(LogTemp,Error,TEXT("CITY TREE LODS invalid LOD scale %s ratio=%.5f; keeping originals"),*Pair.Key,Ratio); return nullptr; }
            }
        }
        for (const auto& Pair : Set.Optimized)
            if (const auto* Data = Pair.Value->GetRenderData())
                for (int32 LOD = 0; LOD < Data->LODResources.Num(); ++LOD)
                    UE_LOG(LogTemp,Display,TEXT("CITY TREE LOD DATA %s lod=%d triangles=%u screen=%.5f"),
                        *Pair.Value->GetName(), LOD, Data->LODResources[LOD].GetNumTriangles(), Data->ScreenSize[LOD].GetValue());
        Set.bValidatedOptimized = true;
    }
    else if (!bOptimizedMesh && !Set.bLoggedOriginal)
    {
        for (const auto& Pair : Set.Originals)
            if (const auto* Data = Pair.Value->GetRenderData())
                for (int32 LOD = 0; LOD < Data->LODResources.Num(); ++LOD)
                    UE_LOG(LogTemp,Display,TEXT("CITY TREE LOD DATA %s lod=%d triangles=%u screen=%.5f"),
                        *Pair.Value->GetName(), LOD, Data->LODResources[LOD].GetNumTriangles(), Data->ScreenSize[LOD].GetValue());
        Set.bLoggedOriginal = true;
    }
    return &Set;
}

FString ResolveCityTreePieceForGroup(const UHierarchicalInstancedStaticMeshComponent* Group, const FCityTreeVariantSet& Set)
{
    if (!Group || !Group->GetStaticMesh()) return FString();
    // Exact child piece match by CityPiece: tag (handling optional "city:" prefix) or exact child StaticMesh identity.
    for (const FName& RawTag : Group->ComponentTags)
    {
        FString TagStr = RawTag.ToString();
        if (TagStr.RemoveFromStart(TEXT("CityPiece:"), ESearchCase::CaseSensitive) ||
            TagStr.RemoveFromStart(TEXT("city:"), ESearchCase::CaseSensitive))
        {
            TagStr.RemoveFromStart(TEXT("city:"), ESearchCase::CaseSensitive);
            if (Set.Originals.Contains(TagStr)) return TagStr;
        }
    }
    FString GroupObjName = Group->GetName();
    if (GroupObjName.RemoveFromStart(TEXT("city:"), ESearchCase::CaseSensitive) && Set.Originals.Contains(GroupObjName))
        return GroupObjName;
    const UStaticMesh* Current = Group->GetStaticMesh();
    for (const auto& Pair : Set.Originals)
        if (Pair.Value.Get() == Current) return Pair.Key;
    for (const auto& Pair : Set.Optimized)
        if (Pair.Value.Get() == Current) return Pair.Key;
    return FString();
}

bool SwapSingleCityTreeGroup(UHierarchicalInstancedStaticMeshComponent* Group, const FCityTreeVariantSet& Set,
    bool bEnabled, bool bOptimizedMesh, int32 Forced, float DistanceScale, FString& OutPiece)
{
    OutPiece = ResolveCityTreePieceForGroup(Group, Set);
    if (OutPiece.IsEmpty()) return true;   // Not a city-tree group.
    UStaticMesh* Target = (bOptimizedMesh ? Set.Optimized.FindChecked(OutPiece) : Set.Originals.FindChecked(OutPiece)).Get();
    if (!Target) return false;
    if (Group->GetStaticMesh() != Target)
    {
        // Static registered components reject mesh changes after BeginPlay.
        // Preserve mobility and instances, rebuilding registration around the swap.
        const bool Registered = Group->IsRegistered();
        if (Registered) Group->UnregisterComponent();
        const bool Changed = Group->SetStaticMesh(Target);
        if (Registered) Group->RegisterComponent();
        if (!Changed || Group->GetStaticMesh() != Target)
        {
            UE_LOG(LogTemp, Error, TEXT("CITY TREE LODS failed mesh swap %s"), *OutPiece);
            return false;
        }
    }
    // Groups are HISM: positive N selects LOD N. Plain ISM uses N-1 instead, so this mapping must remain HISM-only.
    Group->SetForcedLodModel(bOptimizedMesh && Forced >= 2 ? Forced - 1 : 0);
    Group->SetLODDistanceScale(bEnabled ? DistanceScale : 1.f);
    if (Group->bOverrideMinLOD || Group->MinLOD != 0)
    {
        Group->bOverrideMinLOD = false;
        Group->MinLOD = 0;
        Group->MarkRenderStateDirty();
    }
    return true;
}

void EnsureStartupSkyRefreshScheduled(AJapanWorld* Landscape, bool bEnabled)
{
    const FName Prepared(TEXT("CityTreeLODPrepared"));
    if (!bEnabled || !Landscape || Landscape->Tags.Contains(Prepared)) return;
    UWorld* World = Landscape->GetWorld();
    if (!World) return;
    Landscape->Tags.Add(Prepared);
    // Stagger away from the t = 2.0 s skate preload mark so RecaptureSky does not compound frame-114 work.
    FTimerHandle Refresh;
    World->GetTimerManager().SetTimer(Refresh, FTimerDelegate::CreateWeakLambda(Landscape, [World]()
    {
        for (TActorIterator<ASkyLight> Sky(World); Sky; ++Sky)
            if (auto* Light = Sky->GetLightComponent(); Light && !Light->IsRealTimeCaptureEnabled()) Light->RecaptureSky();
        USkyLightComponent::UpdateSkyCaptureContents(World);
        UE_LOG(LogTemp, Display, TEXT("CITY TREE LODS refreshed startup sky"));
    }), 2.35f, false);
}
}

bool AJapanWorld::IsCityTreePiece(const FName& Tag)
{
    const FCityTreeManifestCache& Manifest = GetCityTreeManifest();
    if (!Manifest.bValid) return false;
    if (Manifest.AcceptedTags.Contains(Tag)) return true;
    FString Str = Tag.ToString();
    if (Str.RemoveFromStart(TEXT("CityPiece:"), ESearchCase::CaseSensitive) ||
        Str.RemoveFromStart(TEXT("city:"), ESearchCase::CaseSensitive))
    {
        Str.RemoveFromStart(TEXT("city:"), ESearchCase::CaseSensitive);
        return Manifest.PiecePaths.Contains(Str);
    }
    return false;
}

// Both the settings menu and the diagnostic command use the same validated swap.
// LOD0, materials, instances and collision stay unchanged; only distant leaf outlines differ.
static bool ApplyCityTreeLODs(AJapanWorld* Landscape,const FString& Tag,bool Enabled,int32 Forced,float DistanceScale=1.5f)
{
    if (!Landscape || !Landscape->bLoaded) return false;
    Forced=FMath::Clamp(Forced,0,3);
    DistanceScale=FMath::Clamp(DistanceScale,.5f,3.f);
    // UE's HISM renderer treats ForcedLodModel as a zero-based nonzero index.
    // A full-detail comparison uses the original single-LOD mesh, avoiding its
    // ambiguous zero/automatic case and preserving the production leaf geometry.
    const bool OptimizedMesh=Enabled && Forced!=1;
    const FCityTreeVariantSet* Set = PrepareCityTreeVariant(Tag, OptimizedMesh);
    if (!Set) return false;
    int32 Groups=0,Instances=0;
    TSet<FString> AppliedPieces;
    for (auto* Group : Landscape->Groups)
    {
        if (!Group || !Group->GetStaticMesh()) continue;
        FString Piece;
        if (!SwapSingleCityTreeGroup(Group, *Set, Enabled, OptimizedMesh, Forced, DistanceScale, Piece)) return false;
        if (!Piece.IsEmpty())
        {
            AppliedPieces.Add(Piece);
            ++Groups;
            Instances += Group->GetInstanceCount();
        }
    }
    EnsureStartupSkyRefreshScheduled(Landscape, Enabled);
    UE_LOG(LogTemp,Display,TEXT("CITY TREE LODS tag=%s enabled=%d forced=%d pieces=%d/%d groups=%d instances=%d distance_scale=%.2f"),
        *Tag,Enabled,Forced,AppliedPieces.Num(),Set->Originals.Num(),Groups,Instances,DistanceScale);
    return true;
}

bool AJapanWorld::ApplyTreeOptimizationToGroup(UHierarchicalInstancedStaticMeshComponent* Group)
{
    if (!Group || !Group->GetStaticMesh() || RequestedTreeOptimization < 0) return true;
    const bool bEnabled = RequestedTreeOptimization != 0;
    const int32 Forced = FMath::Clamp(RequestedTreeLODMode, 0, 3);
    const float DistanceScale = FMath::Clamp(RequestedTreeDistanceScale, .5f, 3.f);
    const bool bOptimizedMesh = bEnabled && Forced != 1;
    const FCityTreeVariantSet* Set = PrepareCityTreeVariant(TEXT("v4"), bOptimizedMesh);
    if (!Set) return false;
    FString Piece;
    if (!SwapSingleCityTreeGroup(Group, *Set, bEnabled, bOptimizedMesh, Forced, DistanceScale, Piece)) return false;
    if (!Piece.IsEmpty()) EnsureStartupSkyRefreshScheduled(this, bEnabled);
    return true;
}

bool AJapanWorld::ApplyTreeOptimization(bool bEnabled,int32 LODMode,float DistanceScale)
{
    LODMode=FMath::Clamp(LODMode,0,3);DistanceScale=FMath::Clamp(DistanceScale,.5f,3.f);
    RequestedTreeOptimization=int32(bEnabled);RequestedTreeLODMode=LODMode;RequestedTreeDistanceScale=DistanceScale;
    if (!bLoaded) return false;
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
