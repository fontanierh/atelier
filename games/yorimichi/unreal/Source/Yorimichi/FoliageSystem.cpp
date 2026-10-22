#include "FoliageSystem.h"
#include "FoliagePatchCoverage.h"
#include "JapanWorld.h"
#include "JapanPreferences.h"
#include "WandererCharacter.h"
#include "JapanGameplayCollision.h"
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
#include "HAL/PlatformMemory.h"
#include "RenderingThread.h"
#include "RHICommandList.h"
#include "RenderUtils.h"
#include "AI/Navigation/NavCollisionBase.h"
#include "PhysicsEngine/BodySetup.h"
#include "Misc/PackageName.h"
#include "UObject/GarbageCollection.h"
#if WITH_EDITOR
#include "StaticMeshCompiler.h"
#endif

void UYorimichiFoliageSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    bEnabled=UJapanPreferences::Saved(TEXT("foliage_optimization"),1.f)>.5f;
}

UStaticMesh* UYorimichiFoliageSubsystem::LoadMesh(UWorld* World,const FString& Path)
{
    FString Canonical=Path;
    if (!Canonical.Contains(TEXT("."))) Canonical+=TEXT(".")+FPackageName::GetLongPackageAssetName(Canonical);
    auto* System=World?World->GetSubsystem<UYorimichiFoliageSubsystem>():nullptr;
    if (System)
    {
        if (!System->LoadRegistry()) return nullptr;
        if (const auto* Asset=System->Assets.Find(Canonical);Asset && System->bEnabled)
        {
            const FString& Selected=Asset->Rigid.IsEmpty()?Asset->Optimized:Asset->Rigid;
            return LoadObject<UStaticMesh>(nullptr,*Selected);
        }
    }
    return LoadObject<UStaticMesh>(nullptr,*Canonical);
}

FString UYorimichiFoliageSubsystem::SourcePath(const UStaticMesh* Mesh)
{
    if (!Mesh) return FString();
    const FString Path=Mesh->GetPathName();
    for (TObjectIterator<UYorimichiFoliageSubsystem> It;It;++It)
        if (const FString* Source=It->ResidentSources.Find(Path)) return *Source;
    return Path;
}

FString UYorimichiFoliageSubsystem::SourceName(const UStaticMesh* Mesh)
{
    FString Path=SourcePath(Mesh),Name;
    return Path.Split(TEXT("."),nullptr,&Name)?Name:(Mesh?Mesh->GetName():FString());
}

FIntPoint UYorimichiFoliageSubsystem::LoadedModeCounts() const
{
    TSet<FString> Canonical,Prepared;
    for (const auto& Entry:Sources)
    {
        Canonical.Add(Entry.SourcePath);
        if (const auto* Asset=Assets.Find(Entry.SourcePath))
            for (const FString& Path:{Asset->Rigid,Asset->Optimized,Asset->Shadow,Asset->Patch})
                if (!Path.IsEmpty()) Prepared.Add(Path);
    }
    FIntPoint Counts(0,0);
    for (const auto& Path:Canonical) Counts.X+=IsValid(FindObject<UStaticMesh>(nullptr,*Path));
    for (const auto& Path:Prepared) Counts.Y+=IsValid(FindObject<UStaticMesh>(nullptr,*Path));
    return Counts;
}

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
    const auto Registry=AtelierReadJson(AtelierDataPath(TEXT("foliage_residency/registry.json")));
    double Version=0;
    if (!Registry || !Registry->TryGetNumberField(TEXT("version"),Version) || Version!=2)
    { Error=TEXT("Build unreal.foliage_residency before playing.");return false; }
    return ReadRegistry(Registry);
}

bool UYorimichiFoliageSubsystem::ReadRegistry(const TSharedPtr<FJsonObject>& Registry)
{
    Assets.Reset();ResidentSources.Reset();Words.Reset();LeafMaterials.Reset();ClassificationCache.Reset();bRegistryLoaded=false;
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
    if (!Registry || !PositiveInteger(Registry,TEXT("version"),Version) || (Version!=1 && Version!=2) ||
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
            Source.StartsWith(TEXT("/Game/FoliageSystem/")) || Source.StartsWith(TEXT("/Game/FoliageResident/")) || Assets.Contains(Source) ||
            !Row->TryGetStringField(TEXT("optimized"),Asset.Optimized) ||
                !(Asset.Optimized.StartsWith(TEXT("/Game/FoliageSystem/")) || Asset.Optimized.StartsWith(TEXT("/Game/FoliageResident/"))) ||
            !Row->TryGetStringField(TEXT("shadow"),Asset.Shadow) ||
                !(Asset.Shadow.StartsWith(TEXT("/Game/FoliageSystem/")) || Asset.Shadow.StartsWith(TEXT("/Game/FoliageResident/"))) ||
            !Row->TryGetStringField(TEXT("patch"),Asset.Patch) || !Asset.Patch.StartsWith(TEXT("/Game/FoliageSystem/")) ||
            !Row->TryGetBoolField(TEXT("aggregate"),Asset.Aggregate) ||
            !Row->TryGetStringField(TEXT("kind"),Asset.Kind) ||
            (Asset.Kind!=TEXT("tree") && Asset.Kind!=TEXT("shrub") && Asset.Kind!=TEXT("groundcover")) ||
            !PositiveInteger(Row,TEXT("source_triangles"),Asset.Triangles) ||
            !PositiveInteger(Row,TEXT("shadow_triangles"),Asset.ShadowTriangles) ||
            !Row->TryGetArrayField(TEXT("triangles"),Counts) || Counts->Num()!=4 ||
            !Row->TryGetArrayField(TEXT("canopy_bounds"),Bounds) || Bounds->Num()!=2) return Invalid();
        if (Version==2)
        {
            double Rigid=0.;const TArray<TSharedPtr<FJsonValue>> *Materials=nullptr,*RigidCounts=nullptr;
            if (!Asset.Optimized.StartsWith(TEXT("/Game/FoliageResident/")) || !Asset.Shadow.StartsWith(TEXT("/Game/FoliageResident/")) ||
                !Row->TryGetStringField(TEXT("rigid"),Asset.Rigid) ||
                !Row->TryGetNumberField(TEXT("rigid_triangles"),Rigid) || !FMath::IsFinite(Rigid) ||
                Rigid<0 || Rigid>MAX_int32 || Rigid!=FMath::FloorToDouble(Rigid) ||
                (Rigid==0)!=Asset.Rigid.IsEmpty() ||
                (!Asset.Rigid.IsEmpty() && !Asset.Rigid.StartsWith(TEXT("/Game/FoliageResident/"))) ||
                !Row->TryGetArrayField(TEXT("source_materials"),Materials) || Materials->IsEmpty() ||
                !Row->TryGetArrayField(TEXT("rigid_lod_triangles"),RigidCounts) ||
                (Rigid==0 && !RigidCounts->IsEmpty()) ||
                (Rigid>0 && RigidCounts->Num()!=1 && RigidCounts->Num()!=4)) return Invalid();
            Asset.RigidTriangles=int32(Rigid);
            for (const auto& Count:*RigidCounts)
            {
                if (!Count || Count->Type!=EJson::Number || !FMath::IsFinite(Count->AsNumber()) ||
                    Count->AsNumber()<0 || Count->AsNumber()>MAX_int32 || Count->AsNumber()!=FMath::FloorToDouble(Count->AsNumber())) return Invalid();
                Asset.RigidLODTriangles.Add(int32(Count->AsNumber()));
            }
            if (Rigid>0 && Asset.RigidLODTriangles[0]!=Asset.RigidTriangles) return Invalid();
            for (const auto& Material:*Materials)
            {
                if (!Material || Material->Type!=EJson::String ||
                    !(Material->AsString().StartsWith(TEXT("/Game/")) || Material->AsString().StartsWith(TEXT("/Engine/")))) return Invalid();
                Asset.SourceMaterials.Add(Material->AsString());
            }
            for (const FString& Path:{Asset.Rigid,Asset.Optimized,Asset.Shadow,Asset.Patch})
                if (!Path.IsEmpty())
                {
                    if (ResidentSources.Contains(Path)) return Invalid();
                    ResidentSources.Add(Path,Source);
                }
        }
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
        const TArray<TSharedPtr<FJsonValue>>* Coverage=nullptr;
        if (!Row->TryGetArrayField(TEXT("coverage"),Coverage) || Coverage->Num()>4096 ||
            (Asset.Aggregate && Coverage->IsEmpty())) return Invalid();
        for (const auto& Core:*Coverage)
        {
            // A generated subdivided octahedron has exactly 18 vertices. No
            // authored or masked source hull is eligible for this certificate.
            if (!Core || Core->Type!=EJson::Array || Core->AsArray().Num()!=18) return Invalid();
            TArray<FVector> Points;
            for (const auto& Point:Core->AsArray())
            {
                if (!Point || Point->Type!=EJson::Array || Point->AsArray().Num()!=3) return Invalid();
                FVector P;
                for (int32 Axis=0;Axis<3;++Axis)
                {
                    const auto& V=Point->AsArray()[Axis];
                    if (!V || V->Type!=EJson::Number || !FMath::IsFinite(V->AsNumber())) return Invalid();
                    P[Axis]=V->AsNumber();
                }
                Points.Add(P);
            }
            Asset.Coverage.Add(MoveTemp(Points));
        }
        Asset.Canopy=FBox(Corners[0],Corners[1]);Assets.Add(Source,MoveTemp(Asset));
    }
    bRegistryLoaded=true;Error.Reset();return true;
}

namespace
{
// Same ASCII/camel-case boundaries and plural rules as foliage_roles.py.
TSet<FString> SemanticTokens(FString Name)
{
    int32 Slash=INDEX_NONE;if (Name.FindLastChar(TEXT('/'),Slash)) Name.RightChopInline(Slash+1);
    Name=Name.Replace(TEXT("Treehouse"),TEXT("_"),ESearchCase::IgnoreCase).Replace(TEXT("Planter"),TEXT("_"),ESearchCase::IgnoreCase);
    const auto Lower=[](TCHAR C){return C>=TEXT('a') && C<=TEXT('z');};
    const auto Upper=[](TCHAR C){return C>=TEXT('A') && C<=TEXT('Z');};
    TSet<FString> Tokens;FString Token;
    const auto Finish=[&](){if (!Token.IsEmpty()) { Tokens.Add(Token.ToLower());Token.Reset(); }};
    for (int32 I=0;I<Name.Len();++I)
    {
        const TCHAR C=Name[I],Previous=I?Name[I-1]:0,Next=I+1<Name.Len()?Name[I+1]:0;
        if (!Lower(C) && !Upper(C)) { Finish();continue; }
        if (Upper(C) && (Lower(Previous) || (Upper(Previous) && Lower(Next)))) Finish();
        Token.AppendChar(C);
    }
    Finish();return Tokens;
}

bool HasWord(const TSet<FString>& Tokens,const FString& Word)
{
    if (Tokens.Contains(Word) || Tokens.Contains(Word+TEXT("s")) || Tokens.Contains(Word+TEXT("es"))) return true;
    TArray<FString> Parts;Word.ParseIntoArray(Parts,TEXT("_"));
    if (Parts.Num()<2) return false;
    for (const auto& Part:Parts) if (!Tokens.Contains(Part)) return false;
    return true;
}
}

bool UYorimichiFoliageSubsystem::OrdinaryAuthoredProp(const TArray<FStaticMaterial>& Slots,int32 Triangles)
{
    if (Slots.IsEmpty() || Triangles<=0 || Triangles>12288) return false;
    for (const auto& Slot:Slots)
        if (!Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageAuthored_"))) return false;
    return true;
}

bool UYorimichiFoliageSubsystem::RequiresRegistration(UStaticMeshComponent* Component) const
{
    UStaticMesh* Mesh=Component->GetStaticMesh();
    if (!Mesh || Component->ComponentHasTag(TEXT("FoliageSystemOwned")) ||
        Component->ComponentHasTag(TEXT("DetachedFoliageParticle"))) return false;
    bool CertifiedRigid=!Mesh->GetStaticMaterials().IsEmpty();
    for (const auto& Slot:Mesh->GetStaticMaterials())
        CertifiedRigid&=Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageRigid_"));
    if (CertifiedRigid) return false;
    if (ResidentSources.Contains(Mesh->GetPathName()) || Mesh->GetPathName().StartsWith(TEXT("/Game/FoliageSystem/"))) return true;
    if (Assets.Contains(Mesh->GetPathName())) return true;
    bool Authored=!Mesh->GetStaticMaterials().IsEmpty();
    for (const auto& Slot:Mesh->GetStaticMaterials())
        Authored&=Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageAuthored_"));
    if (Authored)
    {
#if WITH_EDITOR
        FStaticMeshCompilingManager::Get().FinishCompilation({Mesh});
#endif
        if (OrdinaryAuthoredProp(Mesh->GetStaticMaterials(),Mesh->GetNumTriangles(0))) return false;
    }
    const auto MeshWords=SemanticTokens(Mesh->GetName());
    for (const auto& Word:Words) if (HasWord(MeshWords,Word)) return true;
    for (const FStaticMaterial& Slot:Mesh->GetStaticMaterials())
        if (Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageRoles_")) ||
            Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageAuthored_"))) return true;
    for (UMaterialInterface* Material:Component->GetMaterials()) if (Material)
    {
        if (LeafMaterials.Contains(Material->GetPathName()) || Material->GetShadingModels().HasShadingModel(MSM_TwoSidedFoliage)) return true;
        const auto MaterialWords=SemanticTokens(Material->GetName());
        bool Rigid=false;
        for (const TCHAR* Part:{TEXT("bark"),TEXT("trunk"),TEXT("cane"),TEXT("stem"),TEXT("wood")})
            Rigid|=MaterialWords.Contains(Part);
        if (Rigid) continue;
        for (const auto& Word:Words)
            if (HasWord(MaterialWords,Word) &&
                (Material->GetBlendMode()==BLEND_Masked || (Word!=TEXT("grass") && Word!=TEXT("litter")))) return true;
    }
    return false;
}

bool UYorimichiFoliageSubsystem::CachedRequiresRegistration(UStaticMeshComponent* Component)
{
    if (Component->ComponentHasTag(TEXT("FoliageSystemOwned")) ||
        Component->ComponentHasTag(TEXT("DetachedFoliageParticle"))) return false;
    UStaticMesh* Mesh=Component->GetStaticMesh();if (!Mesh) return false;
    const auto& Slots=Mesh->GetStaticMaterials();const int32 Count=Component->GetNumMaterials();
    bool Authored=!Slots.IsEmpty();
    for (const auto& Slot:Slots) Authored&=Slot.MaterialSlotName.ToString().StartsWith(TEXT("FoliageAuthored_"));
    const int32 Triangles=Authored?Mesh->GetNumTriangles(0):0;
    auto* Cached=ClassificationCache.Find(Component);
    bool Unchanged=Cached && Cached->Mesh==Mesh && Cached->Materials.Num()==Count && Cached->Slots.Num()==Slots.Num() &&
        Cached->Triangles==Triangles;
    if (Unchanged) for (int32 I=0;I<Count;++I)
        if (Cached->Materials[I]!=Component->GetMaterial(I)) { Unchanged=false;break; }
    if (Unchanged) for (int32 I=0;I<Slots.Num();++I)
        if (Cached->Slots[I]!=Slots[I].MaterialSlotName) { Unchanged=false;break; }
    if (Unchanged) return Cached->Required;
    FClassification Verdict;Verdict.Mesh=Mesh;Verdict.Required=RequiresRegistration(Component);
    Verdict.Triangles=Authored?Mesh->GetNumTriangles(0):0;
    for (int32 I=0;I<Count;++I) Verdict.Materials.Add(Component->GetMaterial(I));
    for (const auto& Slot:Slots) Verdict.Slots.Add(Slot.MaterialSlotName);
    ClassificationCache.Add(Component,MoveTemp(Verdict));return ClassificationCache.FindChecked(Component).Required;
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
void ForestPatches(UInstancedStaticMeshComponent* Source,const FBox& Canopy,const TArray<TArray<FVector>>& Coverage,const FBox& Prototype,int32 DistantTriangles,
                   TArray<FTransform>& Singles,TArray<FTransform>& Near,TArray<FTransform>& Patches)
{
    using FoliagePatchCoverage::FCrown;
    struct FCell { TArray<FTransform> Local;TArray<FBox> BoundsPerTree;TArray<FCrown> Crowns;FBox Bounds=FBox(ForceInit); };
    TMap<FIntPoint,FCell> Cells;
    const FTransform World=Source->GetComponentTransform();
    const FVector WorldScale=World.GetScale3D();
    // A nonuniform parent can introduce shear when converting a world-aligned
    // patch back to a relative FTransform. Keep individual LODs in that case.
    const bool CanAggregate=!World.ContainsNaN() && WorldScale.X>UE_SMALL_NUMBER && FMath::IsNearlyEqual(WorldScale.X,WorldScale.Y) &&
        FMath::IsNearlyEqual(WorldScale.X,WorldScale.Z);
    for (int32 I=0;I<Source->GetInstanceCount();++I)
    {
        FTransform Local;Source->GetInstanceTransform(I,Local,false);
        if (!CanAggregate || Local.ContainsNaN()) { Singles.Add(Local);continue; }
        const FTransform Pose=Local*World;
        const FBox Bounds=Canopy.TransformBy(Pose);const FVector Centre=Bounds.GetCenter();
        auto& Cell=Cells.FindOrAdd(FIntPoint(FMath::FloorToInt(Centre.X/6400.),FMath::FloorToInt(Centre.Y/6400.)));
        Cell.Local.Add(Local);Cell.BoundsPerTree.Add(Bounds);Cell.Bounds+=Bounds;
        for (const auto& Core:Coverage) Cell.Crowns.Emplace(Core,Pose);
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
            // The prototype's XY silhouette is an inscribed octagon. Its .92
            // ellipse fits inside that polygon; keep the surrounding trees.
            if (FoliagePatchCoverage::Contains(FBox(Interior.GetCenter()-Interior.GetExtent()*FVector(.92,.92,1.),
                                                    Interior.GetCenter()+Interior.GetExtent()*FVector(.92,.92,1.)),
                                               Cell.BoundsPerTree[I])) InteriorTrees.Add(Cell.Local[I]);
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
    UStaticMesh* Mesh=Component->GetStaticMesh();
    const FString Canonical=SourcePath(Mesh);const FAsset* Asset=Assets.Find(Canonical);
    const auto Matches=[](const UStaticMesh* Candidate,const TArray<int32>& Counts)
    {
        if (!Candidate || !Candidate->GetRenderData() || Candidate->GetRenderData()->LODResources.Num()!=Counts.Num()) return false;
        for (int32 I=0;I<Counts.Num();++I)
            if (int32(Candidate->GetRenderData()->LODResources[I].GetNumTriangles())!=Counts[I]) return false;
        return true;
    };
    const FString Selected=Asset?(bEnabled?(Asset->Rigid.IsEmpty()?Asset->Optimized:Asset->Rigid):Canonical):FString();
    if (!Asset || !Mesh || Mesh->GetPathName()!=Selected ||
        (bEnabled && !Matches(Mesh,Asset->Rigid.IsEmpty()?Asset->LODTriangles:Asset->RigidLODTriangles)) ||
        (!bEnabled && (!Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty() ||
            int32(Mesh->GetRenderData()->LODResources[0].GetNumTriangles())!=Asset->Triangles)))
    { Error=TEXT("Uncertified or stale foliage: ")+Canonical+TEXT(". Build unreal.foliage_residency.");return false; }
    for (int32 I=0;I<Asset->SourceMaterials.Num();++I)
    {
        auto* Material=Component->GetMaterial(I);
        if (!Material || (Material!=Mesh->GetMaterial(I) && Material->GetPathName()!=Asset->SourceMaterials[I]))
        { Error=TEXT("Foliage material override needs a certified source variant: ")+Component->GetPathName();return false; }
    }
    FYorimichiFoliageSource Entry;
    Entry.Original=Component;Entry.SourceMesh=Mesh;Entry.SourcePath=Canonical;
    Entry.HasRigid=bEnabled && !Asset->Rigid.IsEmpty();Entry.Visible=Component->IsVisible();
    Entry.Hidden=Component->bHiddenInGame;Entry.CastShadow=Component->CastShadow;
    Entry.DistanceField=Component->bAffectDistanceFieldLighting;Entry.EvaluateWPO=Component->bEvaluateWorldPositionOffset;
    if (const auto* Instances=Cast<UInstancedStaticMeshComponent>(Component)) Entry.InstanceCount=Instances->GetInstanceCount();
    Entry.ShadowOnly=Entry.Hidden && Component->bCastHiddenShadow;Entry.Kind=Asset->Kind;
    if (!bEnabled) { Sources.Add(Entry);return true; }
    UStaticMesh* Optimized=Asset->Rigid.IsEmpty()?Mesh:LoadObject<UStaticMesh>(nullptr,*Asset->Optimized);
    UStaticMesh* Shadow=Entry.CastShadow?LoadObject<UStaticMesh>(nullptr,*Asset->Shadow):nullptr;
    UStaticMesh* Patch=Asset->Aggregate?LoadObject<UStaticMesh>(nullptr,*Asset->Patch):nullptr;
    if (!Matches(Optimized,Asset->LODTriangles) || (Entry.CastShadow && !Matches(Shadow,{Asset->ShadowTriangles})) ||
        (Asset->Aggregate && !Matches(Patch,{32})))
    { Error=TEXT("Required foliage representations are missing: ")+Canonical;return false; }
    if (!Entry.ShadowOnly)
    {
        if (auto* Instances=Cast<UInstancedStaticMeshComponent>(Component);Instances && Asset->Aggregate)
        {
            TArray<FTransform> Singles,Near,Patches;
            ForestPatches(Instances,Asset->Canopy,Asset->Coverage,Patch->GetBoundingBox(),Asset->LODTriangles.Last(),Singles,Near,Patches);
            Entry.Visual=RenderCopy(Component,Optimized,&Singles);
            if (!Near.IsEmpty()) Entry.NearVisual=RenderCopy(Component,Optimized,&Near);
            if (!Patches.IsEmpty()) Entry.Patches=RenderCopy(Component,Patch,&Patches);
            UE_LOG(LogTemp,Display,TEXT("FOLIAGE PATCHES %s individuals=%d near=%d patches=%d"),*Canonical,Singles.Num(),Near.Num(),Patches.Num());
        }
        else Entry.Visual=Entry.HasRigid?RenderCopy(Component,Optimized):Component;
        // A carrier uses original materials, while canopy LODs use certified
        // dither wrappers. Region assignments must not undo those wrappers.
        for (auto* Visual:{Entry.Visual.Get(),Entry.NearVisual.Get()}) if (Visual)
            for (int32 I=0;I<Optimized->GetStaticMaterials().Num();++I) Visual->SetMaterial(I,Optimized->GetMaterial(I));
    }
    if (Shadow) Entry.Shadow=RenderCopy(Component,Shadow);
    Sources.Add(Entry);Apply(Sources.Last());
#if WITH_EDITOR
    if (!GIsEditor && !IsRunningCommandlet() && !bStartupCompleted)
        for (UStaticMesh* Value:{Optimized,Shadow,Patch}) if (Value && Value!=Mesh) StartupVertexCopies.Add(Value);
#endif
    return true;
}

void UYorimichiFoliageSubsystem::ReleaseStartupVertexCopies()
{
#if WITH_EDITOR
    // These copies exist because uncooked -game retains editor CPU arrays.
    // Only our render-only assets qualify; active carriers still own collision and
    // CPU queries. The caller has completed GPU upload before entering here.
    if (GIsEditor || IsRunningCommandlet() || GetWorld()->WorldType!=EWorldType::Game || IsRayTracingEnabled()) return;
    check(IsInGameThread());
    int32 Released=0;TMap<FString,int32> Refusals;
    TSet<UStaticMesh*> Carriers;
    for (const auto& Entry:Sources) if (IsValid(Entry.Original)) Carriers.Add(Entry.Original->GetStaticMesh());
    for (auto It=StartupVertexCopies.CreateIterator();It;++It)
    {
        UStaticMesh* Mesh=It->Get();
        if (!Mesh) { It.RemoveCurrent();continue; }
        if (Carriers.Contains(Mesh))
        { ++Refusals.FindOrAdd(TEXT("carrier_mesh"));It.RemoveCurrent();continue; }
        auto* Render=Mesh->GetRenderData();
        const TCHAR* Refusal=!(Mesh->GetPathName().StartsWith(TEXT("/Game/FoliageSystem/")) ||
            Mesh->GetPathName().StartsWith(TEXT("/Game/FoliageResident/")))?TEXT("ownership"):
            Mesh->bAllowCPUAccess?TEXT("cpu_access"):Mesh->IsStreamable()?TEXT("streaming_registration"):
            Mesh->RenderResourceSupportsStreaming()?TEXT("streaming_support"):!Render?TEXT("no_render_data"):
            Render->NextCachedRenderData?TEXT("other_platforms"):Render->HasValidNaniteData()?TEXT("nanite"):nullptr;
        if (Refusal) { ++Refusals.FindOrAdd(Refusal);It.RemoveCurrent();continue; }
        if (Mesh->IsCompiling() || Mesh->HasPendingInitOrStreaming() || !Render->IsInitialized())
        { ++Refusals.FindOrAdd(TEXT("pending_initialization"));continue; }
        bool Ready=true;
        for (auto& LOD:Render->LODResources)
            if (LOD.GetNumVertices()>0 && (!LOD.VertexBuffers.StaticMeshVertexBuffer.IsValid() ||
                !LOD.VertexBuffers.PositionVertexBuffer.VertexBufferRHI.IsValid() ||
                (LOD.VertexBuffers.ColorVertexBuffer.GetNumVertices()>0 && !LOD.VertexBuffers.ColorVertexBuffer.VertexBufferRHI.IsValid()))) Ready=false;
        if (!Ready) { ++Refusals.FindOrAdd(TEXT("pending_rhi"));continue; }
        UBodySetup* Body=Mesh->GetBodySetup();
        UNavCollisionBase* Navigation=Mesh->GetNavCollision();
        if ((Body && Body->GetOuter()!=Mesh) || (Navigation && Navigation->GetOuter()!=Mesh))
        { ++Refusals.FindOrAdd(TEXT("shared_collision_owner"));It.RemoveCurrent();continue; }
        if (Body && Body->CurrentCookHelper)
        { ++Refusals.FindOrAdd(TEXT("pending_physics_cook"));continue; }
        const uint64 Before=FPlatformMemory::GetStats().UsedPhysical;
        uint64 NavigationBytes=0;
        if (Navigation)
        {
            auto& Triangles=Navigation->GetMutableTriMeshCollision();
            auto& Convex=Navigation->GetMutableConvexCollision();
            NavigationBytes=Triangles.VertexBuffer.GetAllocatedSize()+Triangles.IndexBuffer.GetAllocatedSize()+
                Convex.VertexBuffer.GetAllocatedSize()+Convex.IndexBuffer.GetAllocatedSize();
            Triangles.VertexBuffer.Empty();Triangles.IndexBuffer.Empty();
            Convex.VertexBuffer.Empty();Convex.IndexBuffer.Empty();
        }
        Mesh->MarkAsNotHavingNavigationData();
        const int32 PhysicsMeshes=Body?Body->TriMeshGeometries.Num():0;
        if (Body)
        {
            // No managed render copy owns physics or navigation. Never touch
            // the source/shared BodySetup, or cook/save a replacement here.
            Body->bNeverNeedsCookedCollisionData=true;
            Body->ClearPhysicsMeshes();
            check(Body->TriMeshGeometries.IsEmpty());
        }
        for (auto& LOD:Render->LODResources)
        {
            auto& Buffers=LOD.VertexBuffers;
            const uint32 Vertices=Buffers.StaticMeshVertexBuffer.GetNumVertices();
            const uint32 Channels=Buffers.StaticMeshVertexBuffer.GetNumTexCoords();
            const auto PositionRHI=Buffers.PositionVertexBuffer.VertexBufferRHI;
            const auto TangentRHI=Buffers.StaticMeshVertexBuffer.TangentsVertexBuffer.VertexBufferRHI;
            const auto UVRHI=Buffers.StaticMeshVertexBuffer.TexCoordVertexBuffer.VertexBufferRHI;
            Buffers.StaticMeshVertexBuffer.CleanUp();
            Buffers.PositionVertexBuffer.CleanUp();
            Buffers.ColorVertexBuffer.CleanUp();
            check(!Buffers.StaticMeshVertexBuffer.GetAllowCPUAccess() &&
                !Buffers.PositionVertexBuffer.GetAllowCPUAccess() && !Buffers.ColorVertexBuffer.GetAllowCPUAccess());
            check(Vertices==Buffers.StaticMeshVertexBuffer.GetNumVertices() && Channels==Buffers.StaticMeshVertexBuffer.GetNumTexCoords());
            check(PositionRHI==Buffers.PositionVertexBuffer.VertexBufferRHI &&
                TangentRHI==Buffers.StaticMeshVertexBuffer.TangentsVertexBuffer.VertexBufferRHI &&
                UVRHI==Buffers.StaticMeshVertexBuffer.TexCoordVertexBuffer.VertexBufferRHI);
        }
        UE_LOG(LogTemp,Display,TEXT("FOLIAGE STARTUP VERTEX RELEASE %s process_mib_before=%.1f process_mib_after=%.1f"),
            *Mesh->GetPathName(),Before/1048576.,FPlatformMemory::GetStats().UsedPhysical/1048576.);
        UE_LOG(LogTemp,Display,TEXT("FOLIAGE STARTUP UNUSED COLLISION %s physics_meshes=%d nav_mib=%.3f"),
            *Mesh->GetPathName(),PhysicsMeshes,NavigationBytes/1048576.);
        ++Released;It.RemoveCurrent();
    }
    FString Reasons;for (const auto& Item:Refusals) Reasons+=FString::Printf(TEXT(" %s=%d"),*Item.Key,Item.Value);
    UE_LOG(LogTemp,Display,TEXT("FOLIAGE STARTUP VERTEX SUMMARY released=%d pending=%d refusals:%s"),Released,StartupVertexCopies.Num(),*Reasons);
#endif
}

void UYorimichiFoliageSubsystem::Restore(FYorimichiFoliageSource& Entry)
{
    if (!IsValid(Entry.Original)) return;
    Entry.Original->SetVisibility(Entry.Visible,false);Entry.Original->SetHiddenInGame(Entry.Hidden,false);
    Entry.Original->SetCastShadow(Entry.CastShadow);Entry.Original->bAffectDistanceFieldLighting=Entry.DistanceField;
    if (Entry.Visual && Entry.Visual!=Entry.Original) { Entry.Visual->SetVisibility(false,false);Entry.Visual->SetCastShadow(false); }
    if (Entry.NearVisual) Entry.NearVisual->SetVisibility(false,false);
    if (Entry.Patches) Entry.Patches->SetVisibility(false,false);
    if (Entry.Shadow) { Entry.Shadow->SetCastShadow(false);Entry.Shadow->SetVisibility(false,false); }
}

void UYorimichiFoliageSubsystem::Apply(FYorimichiFoliageSource& Entry)
{
    if (!bEnabled) { Restore(Entry);return; }
    Entry.Original->SetVisibility(Entry.HasRigid && Entry.Visible,false);
    Entry.Original->SetHiddenInGame(Entry.Hidden,false);
    Entry.Original->SetCastShadow(Entry.HasRigid && Entry.CastShadow);
    Entry.Original->bAffectDistanceFieldLighting=false;
    // Rigid cloth and other authored motion remain independent of leaf sway.
    if (Entry.HasRigid)
    {
        Entry.Original->SetEvaluateWorldPositionOffset(Entry.EvaluateWPO);
        if (auto* Group=Cast<UHierarchicalInstancedStaticMeshComponent>(Entry.Original)) Group->SetLODDistanceScale(Detail);
    }
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
        const bool ShadowsEnabled=Entry.CastShadow && ShadowDistance>0.f && Entry.Visible && (!Entry.Hidden || Entry.ShadowOnly);
        Shadow->SetHiddenInGame(true,false);Shadow->bCastHiddenShadow=true;Shadow->SetCastShadow(ShadowsEnabled);
        Shadow->SetVisibility(ShadowsEnabled,false);Shadow->SetEvaluateWorldPositionOffset(false);
        if (auto* Group=Cast<UHierarchicalInstancedStaticMeshComponent>(Shadow))
            Group->SetCullDistances(FMath::RoundToInt(ShadowDistance*90),FMath::RoundToInt(ShadowDistance*100));
        else Shadow->SetCullDistance(ShadowDistance*100);
    }
}

bool UYorimichiFoliageSubsystem::Refresh()
{
    if (bModeLoadFailed) return false;
    if (GetWorld()->GetNetMode()==NM_DedicatedServer) return true;
    if (!LoadRegistry()) return false;
    for (auto It=ClassificationCache.CreateIterator();It;++It)
        if (!It.Key().IsValid() || !It.Key()->IsRegistered() || It.Key()->GetWorld()!=GetWorld()) It.RemoveCurrent();
    // Drop destroyed components and rebuild a changed source (the legacy city
    // comparison swaps assets live). Active carrier components own collision.
    for (int32 I=Sources.Num()-1;I>=0;--I)
    {
        auto& Entry=Sources[I];
        const auto* Instances=Cast<UInstancedStaticMeshComponent>(Entry.Original);
        if (!IsValid(Entry.Original) || Entry.Original->GetStaticMesh()!=Entry.SourceMesh ||
            (Instances && Instances->GetInstanceCount()!=Entry.InstanceCount))
        {
            Restore(Entry);
            DestroyRenderers(Entry);
            Sources.RemoveAt(I);
        }
    }
    // Finish only the initial population in bounded upload batches. Later live
    // refreshes and preference toggles must not introduce GPU-idle stalls.
    if (!bStartupCompleted)
        for (TActorIterator<AJapanWorld> It(GetWorld());It;++It)
            if (It->bGameplayReady)
            {
                const FIntPoint Counts=LoadedModeCounts();
                UE_LOG(LogTemp,Display,TEXT("FOLIAGE RESIDENCY managed_sources=%d legacy_meshes=%d prepared_meshes=%d process_mib=%.1f"),
                    Sources.Num(),Counts.X,Counts.Y,FPlatformMemory::GetStats().UsedPhysical/1048576.);
                UE_LOG(LogTemp,Display,TEXT("FOLIAGE STARTUP COMPLETE pending_vertex_copies=%d"),StartupVertexCopies.Num());
                bStartupCompleted=true;StartupMeasuredMeshes.Reset();break;
            }
    TSet<UStaticMeshComponent*> Registered;
    for (const auto& Entry:Sources) Registered.Add(Entry.Original);
    TArray<UStaticMeshComponent*> NewSources;
    for (TObjectIterator<UStaticMeshComponent> It;It;++It)
        if (It->GetWorld()==GetWorld() && It->IsRegistered() && !Registered.Contains(*It) && CachedRequiresRegistration(*It)) NewSources.Add(*It);
    int32 StartupBatch=0,StartupTotal=0;
    const auto DrainUploads=[&]()
    {
        const uint64 Before=FPlatformMemory::GetStats().UsedPhysical;
        ENQUEUE_RENDER_COMMAND(FoliageStartupUploadDrain)([](FRHICommandListImmediate& RHICmdList)
        { RHICmdList.SubmitAndBlockUntilGPUIdle(true); });
        FlushRenderingCommands();
        ReleaseStartupVertexCopies();
        UE_LOG(LogTemp,Display,TEXT("FOLIAGE STARTUP DRAIN registered=%d process_mib_before=%.1f process_mib_after=%.1f"),
            StartupTotal,Before/1048576.,FPlatformMemory::GetStats().UsedPhysical/1048576.);
        StartupBatch=0;
    };
    for (auto* Component:NewSources)
    {
        if (!Register(Component))
        {
            Component->SetVisibility(false,false);Component->SetCastShadow(false);
            UE_LOG(LogTemp,Error,TEXT("FOLIAGE SYSTEM %s"),*Error);return false;
        }
        if (!bStartupCompleted && GIsRHIInitialized)
        { ++StartupTotal;if (++StartupBatch==8) DrainUploads(); }
    }
    if (StartupBatch) DrainUploads();
    Error.Reset();return true;
}

bool UYorimichiFoliageSubsystem::RefreshSource(UStaticMeshComponent* Component)
{
    ClassificationCache.Remove(Component);
    for (int32 I=Sources.Num()-1;I>=0;--I) if (Sources[I].Original==Component)
    {
        auto& Entry=Sources[I];Restore(Entry);
        DestroyRenderers(Entry);
        Sources.RemoveAt(I);
    }
    return Refresh();
}

void UYorimichiFoliageSubsystem::SetSourceVisibility(UStaticMeshComponent* Component,bool Visible)
{
    for (auto& Entry:Sources) if (Entry.Original==Component)
    { Entry.Visible=Visible;Apply(Entry);return; }
    if (Component) Component->SetVisibility(Visible,false);
}

void UYorimichiFoliageSubsystem::DestroyRenderers(FYorimichiFoliageSource& Entry)
{
    for (auto* Renderer:{Entry.Visual.Get(),Entry.NearVisual.Get(),Entry.Patches.Get(),Entry.Shadow.Get()})
        if (IsValid(Renderer) && Renderer!=Entry.Original)
        {
            Renderer->UnregisterComponent();
            Renderer->SetStaticMesh(nullptr);
            Renderer->DestroyComponent();
        }
    Entry.Visual=nullptr;Entry.NearVisual=nullptr;Entry.Patches=nullptr;Entry.Shadow=nullptr;
}

bool UYorimichiFoliageSubsystem::SetEnabled(bool Enabled)
{
    if (!Refresh()) return false;
    if (Enabled==bEnabled) { RequestedEnabled.Reset();return true; }
    for (const auto& Entry:Sources)
    {
        const auto* Asset=Assets.Find(Entry.SourcePath);
        const FString Path=Enabled && Asset?(Asset->Rigid.IsEmpty()?Asset->Optimized:Asset->Rigid):Entry.SourcePath;
        if (!Asset || !FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(Path)))
        { Error=TEXT("Missing foliage mode asset: ")+Path;return false; }
    }
    // Preference/Slate/live callers may hold raw UObject pointers. Collect and
    // reload only from the subsystem tick, after those callbacks have returned.
    RequestedEnabled=Enabled;return true;
}

bool UYorimichiFoliageSubsystem::ReloadMode(bool Enabled)
{
    if (!Refresh()) return false;
    if (bEnabled==Enabled)
    { bReportedSetting=true;return true; }
    // Keep only component placements/state and canonical strings across the
    // transition. Never retain the inactive UStaticMesh through an entry/cache.
    TArray<FYorimichiFoliageSource> Plans=Sources;
    for (const auto& Plan:Plans)
    {
        const auto* Asset=Assets.Find(Plan.SourcePath);
        const FString Path=Enabled && Asset?(Asset->Rigid.IsEmpty()?Asset->Optimized:Asset->Rigid):Plan.SourcePath;
        if (!Asset || !FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(Path)))
        { Error=TEXT("Missing foliage mode asset: ")+Path;return false; }
    }
    const bool Previous=bEnabled;
    const auto Swap=[&](bool Target)
    {
        TSet<TWeakObjectPtr<UStaticMesh>> Retired;
        for (const auto& Entry:Sources)
            for (auto* Renderer:{Entry.Original.Get(),Entry.Visual.Get(),Entry.NearVisual.Get(),Entry.Patches.Get(),Entry.Shadow.Get()})
                if (Renderer && Renderer->GetStaticMesh()) Retired.Add(Renderer->GetStaticMesh());
        for (auto& Entry:Sources) { Restore(Entry);DestroyRenderers(Entry); }
        Sources.Reset();ClassificationCache.Reset();StartupVertexCopies.Reset();StartupMeasuredMeshes.Reset();
        for (auto& Plan:Plans)
        {
            Plan.Visual=nullptr;Plan.NearVisual=nullptr;Plan.Patches=nullptr;Plan.Shadow=nullptr;Plan.SourceMesh.Reset();
            if (IsValid(Plan.Original))
            {
                Plan.Original->UnregisterComponent();
                Plan.Original->SetStaticMesh(nullptr);
                Plan.Original->EmptyOverrideMaterials();
                if (Plan.Original->GetStaticMesh()) { Error=TEXT("Could not unload foliage carrier.");return false; }
            }
        }
        FlushRenderingCommands();
        ::CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS,true);
        // An explicit mode reload may wait: retire the old GPU resources BEFORE
        // loading the other set, rather than keeping both for instantaneous A/B.
        if (GIsRHIInitialized)
        {
            ENQUEUE_RENDER_COMMAND(FoliageModeUnload)([](FRHICommandListImmediate& RHICmdList)
            { RHICmdList.SubmitAndBlockUntilGPUIdle(true); });
            FlushRenderingCommands();
        }
        int32 StillResident=0;
        for (const auto& Mesh:Retired) if (Mesh.IsValid() && Mesh->GetPathName().StartsWith(TEXT("/Game/"))) ++StillResident;
        UE_LOG(LogTemp,Display,TEXT("FOLIAGE MODE UNLOAD old_meshes=%d still_resident=%d"),Retired.Num(),StillResident);
        if (StillResident) { Error=TEXT("Inactive foliage meshes are still referenced; refusing double residency.");return false; }
        bEnabled=Target;
        for (const auto& Plan:Plans) if (IsValid(Plan.Original))
        {
            auto* Mesh=LoadMesh(GetWorld(),Plan.SourcePath);
            if (!Mesh) { Error=TEXT("Cannot load foliage mode: ")+Plan.SourcePath;return false; }
            Plan.Original->SetStaticMesh(Mesh);
            if (Plan.Original->GetStaticMesh()!=Mesh) { Error=TEXT("Could not replace foliage carrier.");return false; }
            Plan.Original->SetVisibility(Plan.Visible,false);Plan.Original->SetHiddenInGame(Plan.Hidden,false);
            Plan.Original->SetCastShadow(Plan.CastShadow);Plan.Original->bAffectDistanceFieldLighting=Plan.DistanceField;
            Plan.Original->SetEvaluateWorldPositionOffset(Plan.EvaluateWPO);
            Plan.Original->RegisterComponent();
            if (auto* Instances=Cast<UHierarchicalInstancedStaticMeshComponent>(Plan.Original))
                Instances->BuildTreeIfOutdated(true,true);
            if (!Register(Plan.Original)) return false;
        }
        JapanGameplayCollision::Install(GetWorld());
        if (Target && GIsRHIInitialized)
        {
            TSet<UStaticMesh*> Carriers;
            for (const auto& Entry:Sources) if (IsValid(Entry.Original)) Carriers.Add(Entry.Original->GetStaticMesh());
            for (const auto& Entry:Sources)
                for (auto* Renderer:{Entry.Visual.Get(),Entry.NearVisual.Get(),Entry.Patches.Get(),Entry.Shadow.Get()})
                    if (Renderer && Renderer->GetStaticMesh() && !Carriers.Contains(Renderer->GetStaticMesh()))
                        StartupVertexCopies.Add(Renderer->GetStaticMesh());
            ENQUEUE_RENDER_COMMAND(FoliageModeUpload)([](FRHICommandListImmediate& RHICmdList)
            { RHICmdList.SubmitAndBlockUntilGPUIdle(true); });
            FlushRenderingCommands();ReleaseStartupVertexCopies();
            UE_LOG(LogTemp,Display,TEXT("FOLIAGE MODE UPLOAD pending_vertex_copies=%d"),StartupVertexCopies.Num());
        }
        return true;
    };
    if (!Swap(Enabled))
    {
        const FString Failure=Error;
        const bool Restored=Swap(Previous);
        Error=Failure+(Restored?TEXT(" Previous mode reloaded."):TEXT(" Previous mode could not reload."));
        if (!Restored)
        {
            bModeLoadFailed=true;
            for (TActorIterator<AJapanWorld> It(GetWorld());It;++It)
            { It->bGameplayReady=false;It->BootstrapError=Error; }
        }
        return false;
    }
    bReportedSetting=true;
    UE_LOG(LogTemp,Display,TEXT("FOLIAGE SYSTEM enabled=%d sources=%d inactive_meshes_released=1 process_mib=%.1f"),
        bEnabled,Sources.Num(),FPlatformMemory::GetStats().UsedPhysical/1048576.);
    return true;
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
    if (RequestedEnabled.IsSet())
    {
        const bool Target=RequestedEnabled.GetValue();RequestedEnabled.Reset();
        if (!ReloadMode(Target))
            for (TActorIterator<AWandererCharacter> It(GetWorld());It;++It)
                if (auto* Preferences=It->GetPreferences()) Preferences->FoliageReloadFailed(bEnabled,Error);
        AuditElapsed=0.f;return;
    }
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
    { Restore(Entry);DestroyRenderers(Entry); }
    Sources.Reset();ClassificationCache.Reset();Super::Deinitialize();
}

// Explicit diagnostic switch for paired captures/timings; settings remains the
// persistent player-facing control. Never changes another world's preferences.
static FAutoConsoleCommandWithWorldAndArgs FoliageComparison(TEXT("japan.FoliageOptimization"),
    TEXT("Temporary foliage comparison: 0 original, 1 optimized. Graphics settings saves the persistent choice."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World)
    { if (World && Args.Num()==1 && (Args[0]==TEXT("0") || Args[0]==TEXT("1")))
        if (auto* System=World->GetSubsystem<UYorimichiFoliageSubsystem>()) System->SetEnabled(Args[0]==TEXT("1")); }));
