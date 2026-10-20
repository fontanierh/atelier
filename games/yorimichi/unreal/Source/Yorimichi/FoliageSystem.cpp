#include "FoliageSystem.h"
#include "FoliagePatchCoverage.h"
#include "JapanWorld.h"
#include "EngineUtils.h"
#include "AtelierData.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "StaticMeshResources.h"
#include "UObject/UObjectIterator.h"
#include "Dom/JsonObject.h"
#include "HAL/IConsoleManager.h"

UHierarchicalInstancedStaticMeshComponent* UYorimichiFoliageSubsystem::NewInstances(UObject* Outer,FName Name)
{
    // Registration happens after the caller assigns its mesh/materials/placements.
    // Refresh checks every static mesh, including future components outside this factory.
    return NewObject<UHierarchicalInstancedStaticMeshComponent>(Outer,Name);
}

bool UYorimichiFoliageSubsystem::DoesSupportWorldType(EWorldType::Type Type) const
{
    return Type==EWorldType::Game || Type==EWorldType::PIE;
}

bool UYorimichiFoliageSubsystem::LoadRegistry()
{
    if (bRegistryLoaded) return true;
    const auto Registry=AtelierReadJson(AtelierDataPath(TEXT("foliage_system/registry.json")));
    return ReadRegistry(Registry);
}

bool UYorimichiFoliageSubsystem::ReadRegistry(const TSharedPtr<FJsonObject>& Registry)
{
    Assets.Reset();Words.Reset();LeafMaterials.Reset();bRegistryLoaded=false;
    auto Invalid=[this]() { Error=TEXT("Foliage registry is missing, invalid or unsupported. Build unreal.foliage_system.");return false; };
    const auto PositiveInteger=[](const TSharedPtr<FJsonObject>& Object,const TCHAR* Key,int32& Out)
    {
        double Number=0.;
        if (!Object || !Object->TryGetNumberField(Key,Number) || !FMath::IsFinite(Number) ||
            Number<=0. || Number>MAX_int32 || Number!=FMath::FloorToDouble(Number)) return false;
        Out=int32(Number);return true;
    };
    int32 Version=0;
    const TArray<TSharedPtr<FJsonValue>> *RegistryWords=nullptr,*RegistryMaterials=nullptr,*Rows=nullptr;
    if (!Registry || !PositiveInteger(Registry,TEXT("version"),Version) || Version!=1 ||
        !Registry->TryGetArrayField(TEXT("words"),RegistryWords) || RegistryWords->IsEmpty() ||
        !Registry->TryGetArrayField(TEXT("materials"),RegistryMaterials) ||
        !Registry->TryGetArrayField(TEXT("assets"),Rows) || Rows->IsEmpty()) return Invalid();
    for (const auto& Word:*RegistryWords)
    { if (!Word || Word->Type!=EJson::String || Word->AsString().IsEmpty()) return Invalid();Words.Add(Word->AsString()); }
    for (const auto& Material:*RegistryMaterials)
    { if (!Material || Material->Type!=EJson::String || !Material->AsString().StartsWith(TEXT("/Game/"))) return Invalid();LeafMaterials.Add(Material->AsString()); }
    for (const auto& Value:*Rows)
    {
        if (!Value || Value->Type!=EJson::Object) return Invalid();
        const auto Row=Value->AsObject();FAsset Asset;FString Source;
        const TArray<TSharedPtr<FJsonValue>> *Bounds=nullptr,*Counts=nullptr;
        if (!Row->TryGetStringField(TEXT("source"),Source) || !Source.StartsWith(TEXT("/Game/")) ||
            Source.StartsWith(TEXT("/Game/FoliageSystem/")) || Assets.Contains(Source) ||
            !Row->TryGetStringField(TEXT("optimized"),Asset.Optimized) || !Asset.Optimized.StartsWith(TEXT("/Game/FoliageSystem/")) ||
            !Row->TryGetStringField(TEXT("shadow"),Asset.Shadow) || !Asset.Shadow.StartsWith(TEXT("/Game/FoliageSystem/")) ||
            !Row->TryGetStringField(TEXT("patch"),Asset.Patch) || !Asset.Patch.StartsWith(TEXT("/Game/FoliageSystem/")) ||
            !Row->TryGetBoolField(TEXT("aggregate"),Asset.Aggregate) ||
            !Row->TryGetStringField(TEXT("kind"),Asset.Kind) ||
            (Asset.Kind!=TEXT("tree") && Asset.Kind!=TEXT("shrub") && Asset.Kind!=TEXT("groundcover")) ||
            !PositiveInteger(Row,TEXT("source_triangles"),Asset.Triangles) ||
            !PositiveInteger(Row,TEXT("shadow_triangles"),Asset.ShadowTriangles) ||
            !Row->TryGetArrayField(TEXT("triangles"),Counts) || Counts->Num()!=4 ||
            !Row->TryGetArrayField(TEXT("canopy_bounds"),Bounds) || Bounds->Num()!=2) return Invalid();
        for (const auto& Count:*Counts)
        {
            if (!Count || Count->Type!=EJson::Number || Count->AsNumber()<=0 ||
                Count->AsNumber()>MAX_int32 || Count->AsNumber()!=FMath::FloorToDouble(Count->AsNumber())) return Invalid();
            Asset.LODTriangles.Add(int32(Count->AsNumber()));
        }
        FVector Corners[2];
        for (int32 I=0;I<2;++I)
        {
            const auto& Corner=(*Bounds)[I];
            if (!Corner || Corner->Type!=EJson::Array || Corner->AsArray().Num()!=3) return Invalid();
            for (int32 Axis=0;Axis<3;++Axis)
            {
                const auto& Coordinate=Corner->AsArray()[Axis];
                if (!Coordinate || Coordinate->Type!=EJson::Number || !FMath::IsFinite(Coordinate->AsNumber())) return Invalid();
                Corners[I][Axis]=Coordinate->AsNumber();
            }
        }
        if (Corners[0].X>Corners[1].X || Corners[0].Y>Corners[1].Y || Corners[0].Z>Corners[1].Z) return Invalid();
        Asset.Canopy=FBox(Corners[0],Corners[1]);Assets.Add(Source,MoveTemp(Asset));
    }
    bRegistryLoaded=true;Error.Reset();return true;
}

bool UYorimichiFoliageSubsystem::RequiresRegistration(UStaticMeshComponent* Component) const
{
    UStaticMesh* Mesh=Component->GetStaticMesh();
    if (!Mesh || Component->ComponentHasTag(TEXT("FoliageSystemOwned")) ||
        Component->ComponentHasTag(TEXT("DetachedFoliageParticle"))) return false;
    if (Mesh->GetPathName().StartsWith(TEXT("/Game/FoliageSystem/"))) return true;
    if (Assets.Contains(Mesh->GetPathName())) return true;
    const FString MeshName=Mesh->GetName().Replace(TEXT("Treehouse"),TEXT(""),ESearchCase::IgnoreCase).Replace(TEXT("Planter"),TEXT(""),ESearchCase::IgnoreCase);
    for (const auto& Word:Words) if (MeshName.Contains(Word,ESearchCase::IgnoreCase)) return true;
    for (const FStaticMaterial& Slot:Mesh->GetStaticMaterials())
        if (Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageRoles_")) ||
            Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageAuthored_"))) return true;
    for (UMaterialInterface* Material:Component->GetMaterials()) if (Material)
    {
        if (LeafMaterials.Contains(Material->GetPathName()) || Material->GetShadingModels().HasShadingModel(MSM_TwoSidedFoliage)) return true;
        const FString Name=Material->GetName().Replace(TEXT("Treehouse"),TEXT(""),ESearchCase::IgnoreCase).Replace(TEXT("Planter"),TEXT(""),ESearchCase::IgnoreCase);
        bool Rigid=false;
        for (const TCHAR* Part:{TEXT("bark"),TEXT("trunk"),TEXT("cane"),TEXT("stem"),TEXT("wood")})
            Rigid|=Name.Contains(Part,ESearchCase::IgnoreCase);
        if (Rigid) continue;
        for (const auto& Word:Words)
            if (Name.Contains(Word,ESearchCase::IgnoreCase) &&
                (Material->GetBlendMode()==BLEND_Masked || (Word!=TEXT("grass") && Word!=TEXT("litter")))) return true;
    }
    return false;
}

namespace
{
UStaticMeshComponent* RenderCopy(UStaticMeshComponent* Source,UStaticMesh* Mesh,const TArray<FTransform>* Selected=nullptr)
{
    UStaticMeshComponent* Copy;
    if (const auto* Instances=Cast<UInstancedStaticMeshComponent>(Source))
    {
        auto* Group=UYorimichiFoliageSubsystem::NewInstances(Source->GetOwner());
        Group->bAutoRebuildTreeOnInstanceChanges=false;
        TArray<FTransform> Transforms;Transforms.Reserve(Instances->GetInstanceCount());
        if (Selected) Transforms=*Selected;
        else for (int32 I=0;I<Instances->GetInstanceCount();++I)
            { FTransform T;Instances->GetInstanceTransform(I,T,false);Transforms.Add(T); }
        Group->SetStaticMesh(Mesh);Group->SetupAttachment(Source);
        Group->SetCullDistances(Instances->InstanceStartCullDistance,Instances->InstanceEndCullDistance);
        Group->SetMobility(Source->Mobility);Group->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Group->SetCanEverAffectNavigation(false);Group->RegisterComponent();
        Group->AddInstances(Transforms,false,false,false);Group->BuildTreeIfOutdated(true,true);
        Group->bAutoRebuildTreeOnInstanceChanges=true;Copy=Group;
    }
    else
    {
        Copy=NewObject<UStaticMeshComponent>(Source->GetOwner());Copy->SetStaticMesh(Mesh);Copy->SetupAttachment(Source);
        Copy->SetMobility(Source->Mobility);Copy->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Copy->SetCanEverAffectNavigation(false);Copy->SetCullDistance(Source->LDMaxDrawDistance);Copy->RegisterComponent();
    }
    Copy->SetGenerateOverlapEvents(false);Copy->SetCastShadow(false);Copy->bAffectDistanceFieldLighting=false;
    Copy->LightingChannels=Source->LightingChannels;
    Copy->SetRenderCustomDepth(Source->bRenderCustomDepth);
    Copy->SetCustomDepthStencilValue(Source->CustomDepthStencilValue);
    for (int32 I=0;I<Source->GetStaticMesh()->GetStaticMaterials().Num();++I)
        if (Source->GetMaterial(I)!=Source->GetStaticMesh()->GetMaterial(I)) Copy->SetMaterial(I,Source->GetMaterial(I));
    const TArray<float>& Data=Source->GetCustomPrimitiveData().Data;
    for (int32 I=0;I<Data.Num();++I) Copy->SetCustomPrimitiveDataFloat(I,Data[I]);
    Copy->ComponentTags.Add(TEXT("FoliageSystemOwned"));
    return Copy;
}

// Dense interiors can become one distant canopy per 64 m cell. Coverage testing
// keeps sparse groves, skyline edges and clearings as individual tree impostors.
// No placement or collision body moves; these transforms are rendering only.
void ForestPatches(UInstancedStaticMeshComponent* Source,const FBox& Canopy,const FBox& Prototype,int32 DistantTriangles,
                   TArray<FTransform>& Singles,TArray<FTransform>& Near,TArray<FTransform>& Patches)
{
    struct FCell { TArray<FTransform> Local;TArray<FBox> Crowns;FBox Bounds=FBox(ForceInit); };
    TMap<FIntPoint,FCell> Cells;
    const FTransform World=Source->GetComponentTransform();
    for (int32 I=0;I<Source->GetInstanceCount();++I)
    {
        FTransform Local;Source->GetInstanceTransform(I,Local,false);
        const FBox Crown=Canopy.TransformBy(Local*World);const FVector Centre=Crown.GetCenter();
        auto& Cell=Cells.FindOrAdd(FIntPoint(FMath::FloorToInt(Centre.X/6400.),FMath::FloorToInt(Centre.Y/6400.)));
        Cell.Local.Add(Local);Cell.Crowns.Add(Crown);Cell.Bounds+=Crown;
    }
    TArray<FIntPoint> Keys;Cells.GetKeys(Keys);Keys.Sort([](const FIntPoint& A,const FIntPoint& B){return A.X==B.X?A.Y<B.Y:A.X<B.X;});
    for (const FIntPoint& Key:Keys)
    {
        const auto& Cell=Cells[Key];
        // Aggregate only the certified interior; all boundary crowns keep their
        // individual LODs at every distance, preserving the authored silhouette.
        const FVector Inset=Cell.Bounds.GetSize()*FVector(.25,.25,0.);
        const FBox Interior(Cell.Bounds.Min+Inset,Cell.Bounds.Max-Inset);
        if (Cell.Local.Num()<12 || !FoliagePatchCoverage::Covered(Interior,Cell.Crowns))
            { Singles.Append(Cell.Local);continue; }
        TArray<FTransform> InteriorTrees;
        for (int32 I=0;I<Cell.Local.Num();++I)
            if (FoliagePatchCoverage::Contains(Interior,Cell.Crowns[I])) InteriorTrees.Add(Cell.Local[I]);
            else Singles.Add(Cell.Local[I]);
        if (!FoliagePatchCoverage::Worthwhile(InteriorTrees.Num(),DistantTriangles))
            { Singles.Append(InteriorTrees);continue; }
        Near.Append(InteriorTrees);
        const FVector Span=Interior.GetSize();
        const FVector Size=Prototype.GetSize();
        const FVector Scale(Span.X/FMath::Max(Size.X,1.),Span.Y/FMath::Max(Size.Y,1.),Span.Z/FMath::Max(Size.Z,1.));
        const FTransform Patch(FQuat::Identity,Interior.GetCenter()-Prototype.GetCenter()*Scale,Scale);
        Patches.Add(Patch.GetRelativeTransform(World));
    }
}
}

bool UYorimichiFoliageSubsystem::Register(UStaticMeshComponent* Component)
{
    UStaticMesh* Mesh=Component->GetStaticMesh();const FAsset* Asset=Assets.Find(Mesh->GetPathName());
    const auto* Data=Mesh->GetRenderData();
    if (!Asset || !Data || Data->LODResources.IsEmpty() || int32(Data->LODResources[0].GetNumTriangles())!=Asset->Triangles)
    { Error=FString::Printf(TEXT("Uncertified or stale foliage: %s. Build unreal.foliage_system."),*Mesh->GetPathName());return false; }
    for (int32 I=0;I<Mesh->GetStaticMaterials().Num();++I)
        if (Component->GetMaterial(I)!=Mesh->GetMaterial(I))
        { Error=TEXT("Foliage material override needs a certified source variant: ")+Component->GetPathName();return false; }
    UStaticMesh* Optimized=LoadObject<UStaticMesh>(nullptr,*Asset->Optimized);
    UStaticMesh* Shadow=LoadObject<UStaticMesh>(nullptr,*Asset->Shadow);
    UStaticMesh* Patch=LoadObject<UStaticMesh>(nullptr,*Asset->Patch);
    const auto Matches=[](const UStaticMesh* Candidate,const TArray<int32>& Counts)
    {
        if (!Candidate || !Candidate->GetRenderData() || Candidate->GetRenderData()->LODResources.Num()!=Counts.Num()) return false;
        for (int32 I=0;I<Counts.Num();++I)
            if (int32(Candidate->GetRenderData()->LODResources[I].GetNumTriangles())!=Counts[I]) return false;
        return true;
    };
    if (!Matches(Optimized,Asset->LODTriangles) || !Matches(Shadow,{Asset->ShadowTriangles}) || !Matches(Patch,{32}))
    { Error=TEXT("Required foliage representations are missing: ")+Mesh->GetPathName();return false; }
    FYorimichiFoliageSource Entry;
    Entry.Original=Component;Entry.SourceMesh=Mesh;Entry.Visible=Component->IsVisible();
    Entry.Hidden=Component->bHiddenInGame;Entry.CastShadow=Component->CastShadow;
    Entry.DistanceField=Component->bAffectDistanceFieldLighting;Entry.EvaluateWPO=Component->bEvaluateWorldPositionOffset;
    if (const auto* Instances=Cast<UInstancedStaticMeshComponent>(Component)) Entry.InstanceCount=Instances->GetInstanceCount();
    Entry.ShadowOnly=Entry.Hidden && Component->bCastHiddenShadow;Entry.Kind=Asset->Kind;
    if (!Entry.ShadowOnly)
    {
        if (auto* Instances=Cast<UInstancedStaticMeshComponent>(Component);Instances && Asset->Aggregate)
        {
            TArray<FTransform> Singles,Near,Patches;
            ForestPatches(Instances,Asset->Canopy,Patch->GetBoundingBox(),Asset->LODTriangles.Last(),Singles,Near,Patches);
            Entry.Visual=RenderCopy(Component,Optimized,&Singles);
            if (!Near.IsEmpty()) Entry.NearVisual=RenderCopy(Component,Optimized,&Near);
            if (!Patches.IsEmpty()) Entry.Patches=RenderCopy(Component,Patch,&Patches);
            UE_LOG(LogTemp,Display,TEXT("FOLIAGE PATCHES %s individuals=%d near=%d patches=%d"),*Mesh->GetName(),Singles.Num(),Near.Num(),Patches.Num());
        }
        else Entry.Visual=RenderCopy(Component,Optimized);
    }
    if (Entry.CastShadow) Entry.Shadow=RenderCopy(Component,Shadow);
    Sources.Add(Entry);Apply(Sources.Last());return true;
}

void UYorimichiFoliageSubsystem::Restore(FYorimichiFoliageSource& Entry)
{
    if (!IsValid(Entry.Original)) return;
    Entry.Original->SetVisibility(Entry.Visible,false);Entry.Original->SetHiddenInGame(Entry.Hidden,false);
    Entry.Original->SetCastShadow(Entry.CastShadow);Entry.Original->bAffectDistanceFieldLighting=Entry.DistanceField;
    if (Entry.Visual) { Entry.Visual->SetVisibility(false,false);Entry.Visual->SetCastShadow(false); }
    if (Entry.NearVisual) Entry.NearVisual->SetVisibility(false,false);
    if (Entry.Patches) Entry.Patches->SetVisibility(false,false);
    if (Entry.Shadow) { Entry.Shadow->SetCastShadow(false);Entry.Shadow->SetVisibility(false,false); }
}

void UYorimichiFoliageSubsystem::Apply(FYorimichiFoliageSource& Entry)
{
    if (!bEnabled) { Restore(Entry);return; }
    Entry.Original->SetVisibility(false,false);Entry.Original->SetCastShadow(false);
    Entry.Original->bAffectDistanceFieldLighting=false;
    if (auto* Near=Cast<UHierarchicalInstancedStaticMeshComponent>(Entry.NearVisual))
    { Near->SetVisibility(Entry.Visible,false);Near->SetHiddenInGame(Entry.Hidden,false);Near->SetLODDistanceScale(Detail);Near->SetCullDistances(20000,25000);Near->SetWorldPositionOffsetDisableDistance(FMath::RoundToInt(Sway*100.f));Near->SetEvaluateWorldPositionOffset(Entry.EvaluateWPO && Sway>0.f); }
    if (Entry.Patches) { Entry.Patches->SetVisibility(Entry.Visible,false);Entry.Patches->SetHiddenInGame(Entry.Hidden,false); }
    if (auto* Visual=Entry.Visual.Get())
    {
        Visual->SetVisibility(Entry.Visible,false);Visual->SetHiddenInGame(Entry.Hidden,false);
        Visual->SetEvaluateWorldPositionOffset(Entry.EvaluateWPO && Sway>0.f);
        Visual->SetWorldPositionOffsetDisableDistance(FMath::RoundToInt(Sway*100.f));
        if (auto* Group=Cast<UHierarchicalInstancedStaticMeshComponent>(Visual))
        {
            Group->SetLODDistanceScale(Detail);
            if (Entry.Kind==TEXT("groundcover")) Group->SetCullDistances(bPerformance?3500:6000,bPerformance?5000:8000);
            else if (Entry.Kind==TEXT("shrub")) Group->SetCullDistances(16000,20000);
        }
    }
    if (auto* Shadow=Entry.Shadow.Get())
    {
        const bool ShadowsEnabled=ShadowDistance>0.f && Entry.Visible && (!Entry.Hidden || Entry.ShadowOnly);
        Shadow->SetHiddenInGame(true,false);Shadow->bCastHiddenShadow=true;Shadow->SetCastShadow(ShadowsEnabled);
        Shadow->SetVisibility(ShadowsEnabled,false);Shadow->SetEvaluateWorldPositionOffset(false);
        if (auto* Group=Cast<UHierarchicalInstancedStaticMeshComponent>(Shadow))
            Group->SetCullDistances(FMath::RoundToInt(ShadowDistance*90),FMath::RoundToInt(ShadowDistance*100));
        else Shadow->SetCullDistance(ShadowDistance*100);
    }
}

bool UYorimichiFoliageSubsystem::Refresh()
{
    if (GetWorld()->GetNetMode()==NM_DedicatedServer) return true;
    if (!LoadRegistry()) return false;
    // Drop destroyed components and rebuild a changed source (the legacy city
    // comparison swaps originals live). Original components alone own collision.
    for (int32 I=Sources.Num()-1;I>=0;--I)
    {
        auto& Entry=Sources[I];
        const auto* Instances=Cast<UInstancedStaticMeshComponent>(Entry.Original);
        if (!IsValid(Entry.Original) || Entry.Original->GetStaticMesh()!=Entry.SourceMesh ||
            (Instances && Instances->GetInstanceCount()!=Entry.InstanceCount))
        {
            Restore(Entry);
            if (Entry.Visual) Entry.Visual->DestroyComponent();if (Entry.Shadow) Entry.Shadow->DestroyComponent();
            if (Entry.NearVisual) Entry.NearVisual->DestroyComponent();if (Entry.Patches) Entry.Patches->DestroyComponent();
            Sources.RemoveAt(I);
        }
    }
    TSet<UStaticMeshComponent*> Registered;
    for (const auto& Entry:Sources) Registered.Add(Entry.Original);
    TArray<UStaticMeshComponent*> NewSources;
    for (TObjectIterator<UStaticMeshComponent> It;It;++It)
        if (It->GetWorld()==GetWorld() && It->IsRegistered() && !Registered.Contains(*It) && RequiresRegistration(*It)) NewSources.Add(*It);
    for (auto* Component:NewSources) if (!Register(Component))
    {
        Component->SetVisibility(false,false);Component->SetCastShadow(false);
        UE_LOG(LogTemp,Error,TEXT("FOLIAGE SYSTEM %s"),*Error);return false;
    }
    Error.Reset();return true;
}

bool UYorimichiFoliageSubsystem::RefreshSource(UStaticMeshComponent* Component)
{
    for (int32 I=Sources.Num()-1;I>=0;--I) if (Sources[I].Original==Component)
    {
        auto& Entry=Sources[I];Restore(Entry);
        if (Entry.Visual) Entry.Visual->DestroyComponent();if (Entry.Shadow) Entry.Shadow->DestroyComponent();
        if (Entry.NearVisual) Entry.NearVisual->DestroyComponent();if (Entry.Patches) Entry.Patches->DestroyComponent();
        Sources.RemoveAt(I);
    }
    return Refresh();
}

bool UYorimichiFoliageSubsystem::SetEnabled(bool Enabled)
{
    if (!Refresh()) return false;
    if (bEnabled==Enabled && bReportedSetting) return true;
    bEnabled=Enabled;for (auto& Entry:Sources) Apply(Entry);
    bReportedSetting=true;
    UE_LOG(LogTemp,Display,TEXT("FOLIAGE SYSTEM enabled=%d sources=%d"),bEnabled,Sources.Num());return true;
}

void UYorimichiFoliageSubsystem::SetDistances(bool Performance,float InDetail,float InSway,float InShadow)
{
    if (!FMath::IsFinite(InDetail) || !FMath::IsFinite(InSway) || !FMath::IsFinite(InShadow)) return;
    if (bPerformance==Performance && Detail==InDetail && Sway==InSway && ShadowDistance==InShadow) return;
    bPerformance=Performance;Detail=FMath::Clamp(InDetail,.25f,2.f);Sway=FMath::Max(0.f,InSway);ShadowDistance=FMath::Max(0.f,InShadow);
    for (auto& Entry:Sources) if (IsValid(Entry.Original)) Apply(Entry);
}

void UYorimichiFoliageSubsystem::Tick(float Dt)
{
    AuditElapsed+=Dt;
    if (AuditElapsed>=.5f)
    {
        AuditElapsed=0.f;
        if (!Refresh()) for (TActorIterator<AJapanWorld> It(GetWorld());It;++It)
        { It->bGameplayReady=false;It->BootstrapError=Error; }
    }
}

void UYorimichiFoliageSubsystem::Deinitialize()
{
    for (auto& Entry:Sources)
    { Restore(Entry);if (Entry.Visual) Entry.Visual->DestroyComponent();if (Entry.Shadow) Entry.Shadow->DestroyComponent();
      if (Entry.NearVisual) Entry.NearVisual->DestroyComponent();if (Entry.Patches) Entry.Patches->DestroyComponent(); }
    Sources.Reset();Super::Deinitialize();
}

// Explicit diagnostic switch for paired captures/timings; settings remains the
// persistent player-facing control. Never changes another world's preferences.
static FAutoConsoleCommandWithWorldAndArgs FoliageComparison(TEXT("japan.FoliageOptimization"),
    TEXT("Temporary foliage comparison: 0 original, 1 optimized. Graphics settings saves the persistent choice."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    { if (World && Args.Num()==1 && (Args[0]==TEXT("0") || Args[0]==TEXT("1")))
        if (auto* System=World->GetSubsystem<UYorimichiFoliageSubsystem>()) System->SetEnabled(Args[0]==TEXT("1")); }));
