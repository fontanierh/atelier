#include "V2ScenePatch.h"
#include "JapanWorld.h"
#include "JapanGameplayCollisionWorld.h"
#include "SkatePark.h"
#include "SuperUltraMegaPark.h"
#include "Hippodrome.h"
#include "AtelierData.h"
#include "BelmonteRegion.h"
#include "V2MigrationTowns.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#if WITH_EDITOR
#include "StaticMeshCompiler.h"
#endif

const FName AV2ScenePatch::RoleGroup(TEXT("V2Role:Group"));
const FName AV2ScenePatch::RoleBackdrop(TEXT("V2Role:Backdrop"));
const FName AV2ScenePatch::RoleShadowTwin(TEXT("V2Role:ShadowTwin"));
const FName AV2ScenePatch::RoleSeeThrough(TEXT("V2Role:SeeThrough"));
const FName AV2ScenePatch::RoleSkyDome(TEXT("V2Role:SkyDome"));
const FName AV2ScenePatch::RoleSea(TEXT("V2Role:Sea"));

TArray<FString> AV2ScenePatch::Members() const
{
    TArray<FString> Found;
    TArray<UStaticMeshComponent*> Components;
    GetComponents(Components);
    for (const UStaticMeshComponent* C : Components)
    {
        TArray<FString> Tags;
        for (const FName& Tag : C->ComponentTags) Tags.Add(Tag.ToString());
        Tags.Sort();
        const auto* H = Cast<UInstancedStaticMeshComponent>(C);
        Found.Add(FString::Printf(TEXT("%s|%s|%d"), C->GetStaticMesh() ? *C->GetStaticMesh()->GetPathName() : TEXT("none"),
            *FString::Join(Tags, TEXT(",")), H ? H->GetInstanceCount() : 1));
    }
    Found.Sort();
    return Found;
}

AV2ScenePatch::AV2ScenePatch()
{
    PrimaryActorTick.bCanEverTick = false;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

bool AV2ScenePatch::ClimbExempt() const
{
    if (ActorHasTag(TEXT("NoClimb")) || ActorHasTag(TEXT("SkatePark"))) return true;
    // The pier skatepark's saved patch, the mini Mega ramp (V2MigrationMisc), the railway, ferry and gondola units (SaveUnits in
    // V2MigrationTravel), and every saved unit of the Mega and Crater parks: their ramp, rail and wall pieces (MigrateParkPieces)
    // as well as their trees and props (V2MigrationParkDressing). At runtime those pieces belonged to ASuperUltraMegaPark,
    // which UAdventureMoveSet::Climbable never climbs, so a saved piece must not become climbable either.
    return SourceKey == TEXT("SkatePark") || SourceKey == TEXT("mega:ramp") ||
        SourceKey.StartsWith(TEXT("railway:")) || SourceKey.StartsWith(TEXT("ferry:")) || SourceKey.StartsWith(TEXT("gondola:")) ||
        SourceKey.StartsWith(TEXT("megapark:")) || SourceKey.StartsWith(TEXT("craterpark:"));
}

void AV2ScenePatch::BeginPlay()
{
    Super::BeginPlay();
    // Bike and horse probes trace the gameplay channel: a streamed patch is certified fixed like the startup world.
    if (auto* Collision = GetWorld() ? GetWorld()->GetSubsystem<UJapanGameplayCollisionWorld>() : nullptr)
        Collision->InstallFixed(this);
    // A patch streamed in after the world loaded joins its lists now; one there before is taken by Load.
    for (TActorIterator<AJapanWorld> It(GetWorld()); It; ++It)
        if (It->bLoaded) It->RegisterScenePatch(this);
}

void AV2ScenePatch::EndPlay(const EEndPlayReason::Type Reason)
{
    if (auto* Collision = GetWorld() ? GetWorld()->GetSubsystem<UJapanGameplayCollisionWorld>() : nullptr)
        Collision->RemoveFixed(this);
    for (TActorIterator<AJapanWorld> It(GetWorld()); It; ++It) It->UnregisterScenePatch(this);
    Super::EndPlay(Reason);
}

const AV2WorldManifest* AV2WorldManifest::Find(const UWorld* World)
{
    if (!World) return nullptr;
    TActorIterator<AV2WorldManifest> It(const_cast<UWorld*>(World));
    return It ? *It : nullptr;
}

FVector2D AV2WorldManifest::OwnerPoint(const FTransform& Placement, const UStaticMesh* Mesh)
{
    const FVector2D P(Placement.GetLocation());
    return P.IsZero() && Mesh ? FVector2D(Placement.TransformPosition(Mesh->GetBounds().Origin)) : P;
}

bool AV2WorldManifest::CoversInstance(const FVector2D& P) const
{
    if (bOnlyMigrated) return true;
    for (const FBox2D& Box : MigratedBoundsCm)
        if (InsideHalfOpen(Box, P)) return true;
    return bEnvironmentMigrated && !RegionBoundsCm.ContainsByPredicate([&P](const FBox2D& Box) { return InsideHalfOpen(Box, P); });
}

#if WITH_EDITOR
namespace
{
    FString StableId(const TArray<FString>& Parts)
    {
        return FMD5::HashAnsiString(*FString::Join(Parts, TEXT("\x1f"))).Left(16);
    }

    template <class T>
    T* CopyInto(AV2ScenePatch* Patch, const T* Source)
    {
        // A copy of the component Load made carries every setting Load chose (tags, collision, shadow, cull, custom
        // primitive data, bounds scale): one implementation for the runtime and the saved world.
        // The source's own class (an instanced park tree is a HISM under a UStaticMeshComponent pointer).
        T* Copy = CastChecked<T>(NewObject<UObject>(Patch, Source->GetClass(), NAME_None, RF_Transactional,
            const_cast<T*>(Source)));
        Copy->CreationMethod = EComponentCreationMethod::Instance;
        Copy->SetupAttachment(Patch->GetRootComponent());
        Copy->SetRelativeTransform(FTransform::Identity);
        Patch->AddInstanceComponent(Copy);
        // A copy of a saved patch's component (an Instance component) is not owned at construction
        // (UActorComponent::PostInitProperties leaves Instance components to their owner's initialization).
        Patch->AddOwnedComponent(Copy);
        return Copy;
    }
}
#endif

int32 UV2Migration::MigrateStaticScenery(UObject* WorldContext, const TArray<FName>& Regions, const TArray<FBox2D>& BoundsCm,
    const TArray<FBox2D>& HeldCm, const TArray<float>& PatchCm, FName ServicesRegion, const TArray<FName>& Services, TArray<AActor*>& OutCreated, int32& OutKept,
    FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Regions.Num() != BoundsCm.Num() || PatchCm.Num() != Regions.Num() + 1 || PatchCm.ContainsByPredicate([](float P) { return P < 100.f; }))
    {
        Error = TEXT("needs one bounds box per region and a patch size of 1 m or more per region and for the environment");
        return -1;
    }
    for (int32 R = 0; R < Regions.Num(); ++R)
        if (Regions[R].IsNone() || !BoundsCm[R].bIsValid) { Error = TEXT("a region needs an ID and valid bounds"); return -1; }
    if (!Services.IsEmpty() && ServicesRegion.IsNone()) { Error = TEXT("services need ServicesRegion"); return -1; }
    for (const FBox2D& Box : HeldCm)
        if (!Box.bIsValid) { Error = TEXT("a held region needs valid bounds"); return -1; }

    int32 Floating = 0;
    TMap<FString, AV2ScenePatch*> Existing;
    // A region's group (key and mesh) already saved under other IDs means another patch size: the run would copy that
    // scenery a second time, so it stops before anything is saved. A key's mesh not saved before (newly migrated) is new.
    TSet<FString> SavedGroups;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It)
    {
        Existing.Add(It->V2Id, *It);
        TArray<UStaticMeshComponent*> Parts;
        It->GetComponents(Parts);
        for (const UStaticMeshComponent* C : Parts)
            if (C->GetStaticMesh()) SavedGroups.Add(It->Region.ToString() + TEXT("|") + It->SourceKey + TEXT("|") + C->GetStaticMesh()->GetPathName());
    }
    int32 Duplicates = 0;

    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags = RF_Transient;
    Spawn.bHideFromSceneOutliner = true;
    AJapanWorld* Source = World->SpawnActor<AJapanWorld>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
    if (!Source) { Error = TEXT("could not spawn the migration world"); return -1; }
    Source->bMigrationBuild = true;
    Source->LoadForMigration();
    if (!Source->bLoaded) { Source->Destroy(); Error = TEXT("AJapanWorld::Load failed (world.json missing or unreadable)"); return -1; }
    // The roster checks a migrated map no longer runs at play time run here, on the world being copied: an
    // incomplete piece set (city, dressing, structure, southwest, lake, village...) is never saved as complete.
    if (!Source->MigrationIncomplete.IsEmpty())
    {
        Error = TEXT("the source world is incomplete: ") + FString::Join(Source->MigrationIncomplete, TEXT(", "));
        Source->Destroy();
        return -1;
    }
    // A mesh still compiling has no collision yet: the ground trace below needs this map's ground finished.
    FStaticMeshCompilingManager::Get().FinishAllCompilation();

    auto Patch = [&](FName RegionId, const FString& Key, const FString& Mesh, const FString& Role, const FVector& Centre,
        const FString& Id) -> AV2ScenePatch*
    {
        if (Existing.Contains(Id)) { ++OutKept; return nullptr; }
        if (SavedGroups.Contains(RegionId.ToString() + TEXT("|") + Key + TEXT("|") + Mesh))
        {
            if (Duplicates++ < 10)
                UE_LOG(LogTemp, Warning, TEXT("V2 MIGRATION duplicate %s %s %s %s at (%.0f, %.0f)"), *RegionId.ToString(), *Key,
                    *Mesh, *Role, Centre.X, Centre.Y);
            return nullptr;
        }
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(Centre, FRotator::ZeroRotator, Params);
        if (!Made) return nullptr;
        Made->Region = RegionId; Made->SourceKey = Key; Made->V2Id = Id;
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *RegionId.ToString(), *Key, *Role, *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + RegionId.ToString())));
        Existing.Add(Id, Made);
        OutCreated.Add(Made);
        return Made;
    };

    for (UHierarchicalInstancedStaticMeshComponent* Group : Source->Groups)
    {
        if (!Group || !Group->GetStaticMesh()) continue;
        const FString* Key = Source->MigrationKeys.Find(Group);
        UHierarchicalInstancedStaticMeshComponent* const* Twin = Source->MigrationTwins.Find(Group);
        const bool bBackdrop = Source->BackdropGroups.Contains(Group);
        const bool bSeeThrough = Source->SeeThroughGroups.Contains(Group);
        const FString Mesh = Group->GetStaticMesh()->GetPathName();
        const FString Role = bBackdrop ? TEXT("backdrop") : TEXT("near");
        // Load drops each backdrop tree with no ground under it once every region's ground is in (its last pass):
        // the same trace here, against this map's saved ground.
        const bool bTraceGround = bBackdrop && Group->GetStaticMesh()->GetName().StartsWith(TEXT("Tree"));
        const FCollisionQueryParams GroundQuery(SCENE_QUERY_STAT(V2BackdropGround), true);
        // Regions[R] takes what its box holds; the last pass (ServicesRegion, the environment) takes what no box of
        // the map's regions holds, migrated in this run or not, as the island's cells (an open-water piece such as
        // the harbour's HD_Sea).
        for (int32 R = 0; R <= Regions.Num(); ++R)
        {
        const bool bEnvironment = R == Regions.Num();
        if (bEnvironment && ServicesRegion.IsNone()) break;
        const FName Owner = bEnvironment ? ServicesRegion : Regions[R];
        const float Size = PatchCm[R];   // the region's saved grid: a map migrated in parts may hold more than one size
        auto Holds = [&](const FVector2D& P)
        {
            if (!bEnvironment) return AV2WorldManifest::InsideHalfOpen(BoundsCm[R], P);
            for (const FBox2D& Box : BoundsCm) if (AV2WorldManifest::InsideHalfOpen(Box, P)) return false;
            for (const FBox2D& Box : HeldCm) if (AV2WorldManifest::InsideHalfOpen(Box, P)) return false;
            return true;
        };
        TMap<FIntPoint, TArray<FTransform>> Cells;
        for (int32 I = 0; I < Group->GetInstanceCount(); ++I)
        {
            FTransform X;
            Group->GetInstanceTransform(I, X, true);
            const FVector2D P = AV2WorldManifest::OwnerPoint(X, Group->GetStaticMesh());
            if (!Holds(P)) continue;
            FHitResult Hit;
            if (bTraceGround && !World->LineTraceSingleByChannel(Hit, X.GetLocation() + FVector(0, 0, 300),
                    X.GetLocation() - FVector(0, 0, 400), ECC_Visibility, GroundQuery)) { ++Floating; continue; }
            Cells.FindOrAdd(FIntPoint(FMath::FloorToInt(P.X / Size), FMath::FloorToInt(P.Y / Size))).Add(X);
        }
        Cells.KeySort([](const FIntPoint& A, const FIntPoint& B) { return A.X != B.X ? A.X < B.X : A.Y < B.Y; });
        for (const auto& Cell : Cells)
        {
            const FString Id = StableId({Owner.ToString(), Key ? *Key : Mesh, Mesh, Role,
                FString::FromInt(Cell.Key.X), FString::FromInt(Cell.Key.Y)});
            const FVector Centre((Cell.Key.X + .5) * Size, (Cell.Key.Y + .5) * Size, 0.0);
            AV2ScenePatch* Made = Patch(Owner, Key ? *Key : Mesh, Mesh, Role, Centre, Id);
            if (!Made) continue;
            auto Fill = [&](const UHierarchicalInstancedStaticMeshComponent* From, const TArray<FName>& Roles)
            {
                UHierarchicalInstancedStaticMeshComponent* C = CopyInto(Made, From);
                C->ClearInstances();
                for (const FName& R : Roles) C->ComponentTags.AddUnique(R);
                C->bAutoRebuildTreeOnInstanceChanges = false;
                C->RegisterComponent();
                C->AddInstances(Cell.Value, false, true, false);
                C->BuildTreeIfOutdated(false, true);
                C->bAutoRebuildTreeOnInstanceChanges = true;
            };
            TArray<FName> Roles = {AV2ScenePatch::RoleGroup};
            if (bBackdrop) Roles.Add(AV2ScenePatch::RoleBackdrop);
            if (bSeeThrough) Roles.Add(AV2ScenePatch::RoleSeeThrough);
            Fill(Group, Roles);
            if (Twin && *Twin) Fill(*Twin, {AV2ScenePatch::RoleShadowTwin});
        }
        }
    }
    auto Whole = [&](UStaticMeshComponent* From, const FString& Key, FName Role)
    {
        if (!From) return;
        const FString Mesh = From->GetStaticMesh() ? From->GetStaticMesh()->GetPathName() : FString();
        AV2ScenePatch* Made = Patch(ServicesRegion, Key, Mesh, TEXT("whole"), FVector::ZeroVector, StableId({TEXT("world"), Key, Mesh}));
        if (!Made) return;
        UStaticMeshComponent* C = CopyInto(Made, From);
        C->SetWorldTransform(From->GetComponentTransform());
        C->ComponentTags.AddUnique(Role);
        C->RegisterComponent();
    };
    if (Services.Contains(TEXT("SkyDome"))) Whole(Source->SkyDome, TEXT("SkyDome"), AV2ScenePatch::RoleSkyDome);
    if (Services.Contains(TEXT("Sea")))
        for (UStaticMeshComponent* Sea : Source->SeaPieces)
            Whole(Sea, TEXT("Sea:") + (Sea && Sea->GetStaticMesh() ? Sea->GetStaticMesh()->GetName() : FString()), AV2ScenePatch::RoleSea);
    // The skate pier's meshes and garden trees (ASkatePark::Initialize with scenery): one patch in the region holding
    // the park, each component a copy of the park's, at the park's own transform. The runtime park keeps its look,
    // rails and spawns (Initialize without scenery when the manifest lists SkatePark.Scenery).
    if (Services.Contains(TEXT("SkatePark.Scenery")))
    {
        FActorSpawnParameters ParkParams;
        ParkParams.ObjectFlags = RF_Transient;
        ParkParams.bHideFromSceneOutliner = true;
        ASkatePark* Park = World->SpawnActor<ASkatePark>(FVector::ZeroVector, FRotator::ZeroRotator, ParkParams);
        if (!Park || !Park->Initialize(AtelierDataPath(TEXT("skatepark/park.json")), true))
        {
            if (Park) Park->Destroy();
            Source->Destroy();
            Error = TEXT("the skate pier did not load completely (skatepark/park.json and its meshes)");
            return -1;
        }
        FName Owner = ServicesRegion;
        for (int32 R = 0; R < Regions.Num(); ++R)
            if (AV2WorldManifest::InsideHalfOpen(BoundsCm[R], FVector2D(Park->GetActorLocation()))) Owner = Regions[R];
        if (AV2ScenePatch* Made = Patch(Owner, TEXT("SkatePark"), FString(), TEXT("scenery"), Park->GetActorLocation(),
                StableId({TEXT("skatepark"), Owner.ToString()})))
        {
            Made->SetActorRotation(Park->GetActorRotation());
            TArray<UStaticMeshComponent*> Parts;
            Park->GetComponents(Parts);
            for (UStaticMeshComponent* From : Parts)
            {
                UStaticMeshComponent* C = CopyInto(Made, From);
                C->SetRelativeTransform(From->GetRelativeTransform());
                C->RegisterComponent();
            }
        }
        Park->Destroy();
    }
    Source->Destroy();
    if (Duplicates)
    {
        for (AActor* Made : OutCreated) Made->Destroy();
        OutCreated.Reset();
        Error = FString::Printf(TEXT("%d patch(es) would copy scenery its region already saved under other IDs: is the "
            "region's patch size its saved one (region.toml patch_m, else run.py --patch-m)? Nothing was kept"), Duplicates);
        return -1;
    }
    for (AActor* Made : OutCreated)
    {
        AV2ScenePatch* Saved = CastChecked<AV2ScenePatch>(Made);
        Saved->ExpectedMembers = Saved->Members();
        Made->MarkPackageDirty();
    }
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION created %d patches, kept %d, dropped %d floating backdrop trees"),
        OutCreated.Num(), OutKept, Floating);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

int32 UV2Migration::MigrateRegionGroups(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Meshes, const TArray<FString>& Objects, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Meshes.IsEmpty() || Objects.Num() != Meshes.Num())
    {
        Error = TEXT("needs a region, its runtime tag, and one object name per mesh");
        return -1;
    }
    AV2WorldManifest* Manifest = nullptr;
    for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
    if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    // Every listed key is one group of this runtime file (V2MigrationTowns::GroupKeys), or a cell piece "<key>@x_y" of
    // one: the piece holds the group's instances in that 128 m cell. Each listed key is saved once.
    struct FSource
    {
        TSharedPtr<FJsonObject> Entry;
        bool bPiece = false;
        int32 CellX = 0, CellY = 0;
    };
    const TArray<FString> Keys = V2MigrationTowns::GroupKeys(Data);
    const TArray<TSharedPtr<FJsonValue>>& GroupValues = Data->GetArrayField(TEXT("groups"));
    TMap<FString, int32> IndexOf;
    for (int32 I = 0; I < Keys.Num(); ++I) IndexOf.Add(Keys[I], I);
    TMap<FString, FSource> Entries;
    TMap<FString, TArray<FString>> Groups;   // object -> its listed keys, in the order given
    TArray<FString> Order;
    for (int32 I = 0; I < Meshes.Num(); ++I)
    {
        const FString& Listed = Meshes[I];
        if (Entries.Contains(Listed)) { Error = Listed + TEXT(" is listed twice"); return -1; }
        FSource Source;
        FString Key = Listed;
        Source.bPiece = V2MigrationTowns::ParsePieceKey(Listed, Key, Source.CellX, Source.CellY);
        const int32* Index = IndexOf.Find(Key);
        if (!Index) { Error = Listed + TEXT(" is no group of ") + DataFile; return -1; }
        Source.Entry = GroupValues[*Index]->AsObject();
        Entries.Add(Listed, Source);
        if (!Groups.Contains(Objects[I])) Order.Add(Objects[I]);
        Groups.FindOrAdd(Objects[I]).Add(Listed);
    }
    const auto Clearance = V2MigrationTowns::GondolaClearance();
    TMap<FString, AV2ScenePatch*> Existing;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
    const auto& O = Data->GetArrayField(TEXT("origin_cm"));
    const FVector Origin(O[0]->AsNumber(), O[1]->AsNumber(), O[2]->AsNumber());
    for (const FString& Object : Order)
    {
        const FString Id = StableId({Region.ToString(), Tag.ToString(), Object});
        if (Existing.Contains(Id))
        {
            TArray<FString> Requested;
            for (const FString& Listed : Groups[Object]) Requested.Add(Tag.ToString() + TEXT(":") + Listed);
            if (!Manifest->KeptUnitCovers(Object, Requested, Error)) break;
            ++OutKept;
            continue;
        }
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(Origin, FRotator::ZeroRotator, Params);
        if (!Made) { Error = Object + TEXT(": could not spawn its patch"); break; }
        OutCreated.Add(Made);
        Made->Region = Region; Made->SourceKey = Tag.ToString() + TEXT(":") + Object; Made->V2Id = Id;
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *Region.ToString(), *Tag.ToString(), *Object, *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
        for (const FString& Listed : Groups[Object])
        {
            const FSource& Source = Entries[Listed];
            const auto& Entry = Source.Entry;
            auto* Mesh = LoadObject<UStaticMesh>(nullptr, *Entry->GetStringField(TEXT("asset")));
            if (!Mesh) { Error = Listed + TEXT(": its mesh is missing from V2 Content"); break; }
            const bool bPlant = Entry->GetBoolField(TEXT("plant"));
            int32 Missing = 0, Outside = 0;
            UHierarchicalInstancedStaticMeshComponent* C = ABelmonteRegion::MakeGroup(Made, Made->GetRootComponent(), Entry, Mesh, Tag, Missing);
            C->CreationMethod = EComponentCreationMethod::Instance;
            Made->AddInstanceComponent(C);
            C->bAutoRebuildTreeOnInstanceChanges = false;
            // A saved plant group joins the island's tree lists as the runtime's own plant groups do: RegisterScenePatch
            // adds a RoleGroup component to Landscape->Groups, once, and the runtime never spawns a saved group again.
            if (bPlant) C->ComponentTags.AddUnique(AV2ScenePatch::RoleGroup);
            C->RegisterComponent();
            // The runtime's own filters: plants by the gondola clearance, other groups by the district's bounds.
            TArray<FTransform> Placements = bPlant ? ABelmonteRegion::PlantTransforms(Data, Entry, Clearance)
                                                   : ABelmonteRegion::SceneryTransforms(Data, Entry, Outside);
            if (Source.bPiece)
                Placements.RemoveAll([&](const FTransform& T)
                {
                    int32 X = 0, Y = 0;
                    V2MigrationTowns::CellOf(Origin, T, X, Y);
                    return X != Source.CellX || Y != Source.CellY;
                });
            C->AddInstances(Placements, false, false, false);
            C->BuildTreeIfOutdated(false, true);
            C->bAutoRebuildTreeOnInstanceChanges = true;
            if (Missing || !C->GetInstanceCount()) { Error = Listed + TEXT(": missing materials or no instance inside the district"); break; }
        }
        if (!Error.IsEmpty()) break;
    }
    if (!Error.IsEmpty())
    {
        for (AActor* Made : OutCreated) Made->Destroy();
        OutCreated.Reset();
        return -1;
    }
    for (AActor* Made : OutCreated)
    {
        AV2ScenePatch* Saved = CastChecked<AV2ScenePatch>(Made);
        Saved->ExpectedMembers = Saved->Members();
        Made->MarkPackageDirty();
    }
    // Kept groups stay listed too: the runtime must never spawn a group this map saved.
    TArray<FString> Listed = Manifest->MigratedGroups;
    for (const FString& Name : Meshes) Listed.AddUnique(Tag.ToString() + TEXT(":") + Name);
    Listed.Sort();
    if (Listed != Manifest->MigratedGroups)
    {
        Manifest->Modify();
        Manifest->MigratedGroups = MoveTemp(Listed);
        Manifest->MarkPackageDirty();
    }
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s groups: created %d patches, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

// A unit saved before patches recorded their placement keeps no OriginalTransform, so a later move of it would not carry its
// rails and zones. A kept unit still standing at its placement records it now; one already moved is left alone and logged.
bool AV2WorldManifest::KeptUnitCovers(const FString& Unit, const TArray<FString>& Keys, FString& Error) const
{
    for (const FString& Key : Keys)
    {
        if (!MigratedGroups.Contains(Key))
        {
            Error = FString::Printf(TEXT("%s was saved without %s; delete its patch and rerun to remake it"), *Unit, *Key);
            return false;
        }
    }
    return true;
}

static void KeepOriginal(AV2ScenePatch* Kept, const FTransform& Placement)
{
    if (!Kept->OriginalTransform.Equals(FTransform::Identity, 0.)) return;
    if (!Kept->GetActorTransform().Equals(Placement, 1.))
    {
        UE_LOG(LogTemp, Warning, TEXT("V2 MIGRATION %s: moved before its placement was recorded; set OriginalTransform by hand"), *Kept->V2Id);
        return;
    }
    Kept->Modify();
    Kept->OriginalTransform = Placement;
    Kept->MarkPackageDirty();
}

int32 UV2Migration::MigrateParkPieces(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Pieces, const TArray<bool>& IsCollision, const TArray<FString>& Units, TArray<AActor*>& OutCreated,
    int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Pieces.IsEmpty() || IsCollision.Num() != Pieces.Num() || Units.Num() != Pieces.Num())
    {
        Error = TEXT("needs a region, its runtime tag, and one unit and kind per piece");
        return -1;
    }
    AV2WorldManifest* Manifest = nullptr;
    for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
    if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    FString MeshRoot = TEXT("/Game/MegaPark/Meshes");
    Data->TryGetStringField(TEXT("mesh_root"), MeshRoot);
    // Every listed piece is one render or collision entry of this park file, listed once and of the kind the file gives it.
    TMap<FString, TSharedPtr<FJsonObject>> Entries;
    TSet<FString> CollisionNames;
    for (const TCHAR* Kind : {TEXT("render"), TEXT("collision")})
    {
        for (const auto& Value : Data->GetArrayField(Kind))
        {
            const auto Entry = Value->AsObject();
            const FString Name = Entry->GetStringField(TEXT("name"));
            Entries.Add(Name, Entry);
            if (FCString::Strcmp(Kind, TEXT("collision")) == 0) CollisionNames.Add(Name);
        }
    }
    TMap<FString, TArray<int32>> ByUnit;   // unit -> the indices of its pieces, in the order given
    TArray<FString> Order;
    TSet<FString> Seen;
    for (int32 I = 0; I < Pieces.Num(); ++I)
    {
        const FString& Name = Pieces[I];
        if (!Entries.Contains(Name)) { Error = Name + TEXT(" is no render or collision piece of ") + DataFile; return -1; }
        if (Seen.Contains(Name)) { Error = Name + TEXT(" is listed twice"); return -1; }
        if (CollisionNames.Contains(Name) != IsCollision[I]) { Error = Name + TEXT(" is not the kind ") + DataFile + TEXT(" gives it"); return -1; }
        if (Units[I].IsEmpty()) { Error = Name + TEXT(" has no unit"); return -1; }
        Seen.Add(Name);
        if (!ByUnit.Contains(Units[I])) Order.Add(Units[I]);
        ByUnit.FindOrAdd(Units[I]).Add(I);
    }
    // The park's placement, as ASuperUltraMegaPark::Spawn places it: its pieces are relative to it.
    const auto& L = Data->GetArrayField(TEXT("location_cm"));
    const FTransform Placement(FRotator(0., Data->GetNumberField(TEXT("yaw_deg")), 0.),
        FVector(L[0]->AsNumber(), L[1]->AsNumber(), L[2]->AsNumber()));
    TMap<FString, AV2ScenePatch*> Existing;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
    for (const FString& Unit : Order)
    {
        const FString Id = StableId({Region.ToString(), Tag.ToString(), Unit});
        if (AV2ScenePatch** Kept = Existing.Find(Id))
        {
            TArray<FString> Requested;
            for (const int32 I : ByUnit[Unit]) Requested.Add(Tag.ToString() + TEXT(":") + Pieces[I]);
            if (!Manifest->KeptUnitCovers(Unit, Requested, Error)) break;
            ++OutKept;
            KeepOriginal(*Kept, Placement);
            continue;
        }
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(Placement.GetLocation(), Placement.Rotator(), Params);
        if (!Made) { Error = Unit + TEXT(": could not spawn its patch"); break; }
        OutCreated.Add(Made);
        Made->Region = Region; Made->SourceKey = Tag.ToString() + TEXT(":") + Unit; Made->V2Id = Id;
        Made->OriginalTransform = Placement;   // the park placement: Spawn moves the unit's rails and zones by its move
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *Region.ToString(), *Tag.ToString(), *Unit, *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
        for (const int32 I : ByUnit[Unit])
        {
            const FString& Name = Pieces[I];
            auto* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *MeshRoot, *Name, *Name));
            if (!Mesh) { Error = Name + TEXT(": its mesh is missing from V2 Content"); break; }
            UStaticMeshComponent* C = ASuperUltraMegaPark::MakePiece(Made, Made->GetRootComponent(), Entries[Name], Mesh, IsCollision[I]);
            C->CreationMethod = EComponentCreationMethod::Instance;
            Made->AddInstanceComponent(C);
            C->RegisterComponent();
        }
        if (!Error.IsEmpty()) break;
    }
    if (!Error.IsEmpty())
    {
        for (AActor* Made : OutCreated) Made->Destroy();
        OutCreated.Reset();
        return -1;
    }
    for (AActor* Made : OutCreated)
    {
        AV2ScenePatch* Saved = CastChecked<AV2ScenePatch>(Made);
        Saved->ExpectedMembers = Saved->Members();
        Made->MarkPackageDirty();
    }
    // Saved pieces stay listed, kept units too: the runtime must never spawn a piece this map saved.
    TArray<FString> Listed = Manifest->MigratedGroups;
    for (const FString& Name : Pieces) Listed.AddUnique(Tag.ToString() + TEXT(":") + Name);
    Listed.Sort();
    if (Listed != Manifest->MigratedGroups)
    {
        Manifest->Modify();
        Manifest->MigratedGroups = MoveTemp(Listed);
        Manifest->MarkPackageDirty();
    }
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s park: created %d, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

int32 UV2Migration::MigrateHippodromePieces(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Pieces, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Pieces.IsEmpty() || Units.Num() != Pieces.Num())
    {
        Error = TEXT("needs a region, its runtime tag, and one unit per piece");
        return -1;
    }
    AV2WorldManifest* Manifest = nullptr;
    for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
    if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    FString AssetRoot = TEXT("/Game/Hippodrome");
    Data->TryGetStringField(TEXT("asset_root"), AssetRoot);
    // Every listed piece is one mesh of this file, listed once.
    TMap<FString, TSharedPtr<FJsonObject>> Entries;
    for (const auto& Value : Data->GetArrayField(TEXT("meshes")))
    {
        const auto Entry = Value->AsObject();
        Entries.Add(Entry->GetStringField(TEXT("name")), Entry);
    }
    TMap<FString, TArray<int32>> ByUnit;   // unit -> the indices of its pieces, in the order given
    TArray<FString> Order;
    TSet<FString> Seen;
    for (int32 I = 0; I < Pieces.Num(); ++I)
    {
        const FString& Name = Pieces[I];
        if (!Entries.Contains(Name)) { Error = Name + TEXT(" is no mesh of ") + DataFile; return -1; }
        if (Seen.Contains(Name)) { Error = Name + TEXT(" is listed twice"); return -1; }
        if (Units[I].IsEmpty()) { Error = Name + TEXT(" has no unit"); return -1; }
        Seen.Add(Name);
        if (!ByUnit.Contains(Units[I])) Order.Add(Units[I]);
        ByUnit.FindOrAdd(Units[I]).Add(I);
    }
    // The course origin, where AHippodrome::Spawn places the actor (its meshes are offsets from it): Blender metres, Unreal cm.
    const auto& O = Data->GetArrayField(TEXT("origin"));
    if (O.Num() < 3) { Error = DataFile + TEXT(" has no origin"); return -1; }
    const FVector Placement(O[0]->AsNumber() * 100., -O[1]->AsNumber() * 100., O[2]->AsNumber() * 100.);
    TMap<FString, AV2ScenePatch*> Existing;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
    for (const FString& Unit : Order)
    {
        const FString Id = StableId({Region.ToString(), Tag.ToString(), Unit});
        if (AV2ScenePatch** Kept = Existing.Find(Id))
        {
            TArray<FString> Requested;
            for (const int32 I : ByUnit[Unit]) Requested.Add(Tag.ToString() + TEXT(":") + Pieces[I]);
            if (!Manifest->KeptUnitCovers(Unit, Requested, Error)) break;
            ++OutKept;
            KeepOriginal(*Kept, FTransform(FRotator::ZeroRotator, Placement));
            continue;
        }
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(Placement, FRotator::ZeroRotator, Params);
        if (!Made) { Error = Unit + TEXT(": could not spawn its patch"); break; }
        OutCreated.Add(Made);
        Made->Region = Region; Made->SourceKey = Tag.ToString() + TEXT(":") + Unit; Made->V2Id = Id;
        Made->OriginalTransform = FTransform(FRotator::ZeroRotator, Placement);   // the course origin, as spawned
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *Region.ToString(), *Tag.ToString(), *Unit, *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
        for (const int32 I : ByUnit[Unit])
        {
            const FString& Name = Pieces[I];
            auto* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AssetRoot, *Name, *Name));
            if (!Mesh) { Error = Name + TEXT(": its mesh is missing from V2 Content"); break; }
            UStaticMeshComponent* C = AHippodrome::MakePiece(Made, Made->GetRootComponent(), Entries[Name], Mesh);
            C->CreationMethod = EComponentCreationMethod::Instance;
            Made->AddInstanceComponent(C);
            C->RegisterComponent();
        }
        if (!Error.IsEmpty()) break;
    }
    if (!Error.IsEmpty())
    {
        for (AActor* Made : OutCreated) Made->Destroy();
        OutCreated.Reset();
        return -1;
    }
    for (AActor* Made : OutCreated)
    {
        AV2ScenePatch* Saved = CastChecked<AV2ScenePatch>(Made);
        Saved->ExpectedMembers = Saved->Members();
        Made->MarkPackageDirty();
    }
    // Saved meshes stay listed, kept units too: the runtime must never place a mesh this map saved.
    TArray<FString> Listed = Manifest->MigratedGroups;
    for (const FString& Name : Pieces) Listed.AddUnique(Tag.ToString() + TEXT(":") + Name);
    Listed.Sort();
    if (Listed != Manifest->MigratedGroups)
    {
        Manifest->Modify();
        Manifest->MigratedGroups = MoveTemp(Listed);
        Manifest->MarkPackageDirty();
    }
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s hippodrome pieces: created %d, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

int32 UV2Migration::SplitPatchObjects(UObject* WorldContext, FName Region, FName Tag, const TArray<FString>& Keys,
    const TArray<FString>& Objects, const TArray<FVector2D>& PointsCm, float ToleranceCm, TArray<AActor*>& OutCreated,
    TArray<AActor*>& OutChanged, int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutChanged.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Objects.IsEmpty() || Keys.Num() != Objects.Num() || PointsCm.Num() != Objects.Num()
        || ToleranceCm <= 0.f)
    {
        Error = TEXT("needs a region, its tag, a positive tolerance and one key and point per object");
        return -1;
    }
    TMap<FString, AV2ScenePatch*> Existing;
    TArray<AV2ScenePatch*> Sources;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It)
    {
        Existing.Add(It->V2Id, *It);
        if (It->Region == Region && Keys.Contains(It->SourceKey)) Sources.Add(*It);
    }
    // Plan every move before changing anything: each object takes, from every component of its key's patches, the
    // instances within the tolerance of its point. An object found nowhere, or an instance two objects would take,
    // stops the run with the world as it was.
    struct FMove { UHierarchicalInstancedStaticMeshComponent* From; TArray<int32> Indices; };
    TMap<FString, TArray<FMove>> Moves;   // object -> its instances
    TMap<UHierarchicalInstancedStaticMeshComponent*, TSet<int32>> Taken;
    TArray<int32> Todo;
    const double Tolerance2 = double(ToleranceCm) * ToleranceCm;
    for (int32 O = 0; O < Objects.Num(); ++O)
    {
        const FString Id = StableId({Region.ToString(), Keys[O], TEXT("object"), Objects[O]});
        if (Existing.Contains(Id)) { ++OutKept; continue; }
        Todo.Add(O);
        int32 Found = 0;
        for (AV2ScenePatch* Patch : Sources)
        {
            if (Patch->SourceKey != Keys[O]) continue;
            TArray<UHierarchicalInstancedStaticMeshComponent*> Parts;
            Patch->GetComponents(Parts);
            for (UHierarchicalInstancedStaticMeshComponent* C : Parts)
            {
                FMove Move{C, {}};
                for (int32 I = 0; I < C->GetInstanceCount(); ++I)
                {
                    FTransform X;
                    C->GetInstanceTransform(I, X, true);
                    if (FVector2D::DistSquared(FVector2D(X.GetLocation()), PointsCm[O]) > Tolerance2) continue;
                    bool bAlready = false;
                    Taken.FindOrAdd(C).Add(I, &bAlready);
                    if (bAlready)
                    {
                        Error = FString::Printf(TEXT("%s: an instance of %s at (%.0f, %.0f) is within %.0f cm of two objects"),
                            *Objects[O], *Patch->V2Id, X.GetLocation().X, X.GetLocation().Y, ToleranceCm);
                        return -1;
                    }
                    Move.Indices.Add(I);
                }
                if (!Move.Indices.IsEmpty()) { Found += Move.Indices.Num(); Moves.FindOrAdd(Objects[O]).Add(MoveTemp(Move)); }
            }
        }
        if (!Found)
        {
            Error = FString::Printf(TEXT("%s: no %s instance of %s lies within %.0f cm of (%.0f, %.0f)"), *Objects[O],
                *Keys[O], *Region.ToString(), ToleranceCm, PointsCm[O].X, PointsCm[O].Y);
            return -1;
        }
    }
    int64 Before = 0;
    for (AV2ScenePatch* Patch : Sources)
    {
        TArray<UHierarchicalInstancedStaticMeshComponent*> Parts;
        Patch->GetComponents(Parts);
        for (const auto* C : Parts) Before += C->GetInstanceCount();
    }
    // Each object: a new patch at its point holding a copy of each source component (every setting and tag the
    // migration saved) with its instances alone; the sources then drop them. An emptied component or patch stays,
    // saved with no instances, so a rerun of the map migration finds its V2Id and never makes it again.
    TSet<AV2ScenePatch*> Changed;
    for (int32 O : Todo)
    {
        const FString Id = StableId({Region.ToString(), Keys[O], TEXT("object"), Objects[O]});
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(FVector(PointsCm[O], 0.0), FRotator::ZeroRotator, Params);
        if (!Made)
        {
            Error = Objects[O] + TEXT(": could not spawn its patch");
            for (AActor* Spawned : OutCreated) Spawned->Destroy();   // no instance has left a source yet
            OutCreated.Reset();
            return -1;
        }
        // The key stays the source's: the map migration then counts this key and mesh as saved in this region.
        Made->Region = Region; Made->SourceKey = Keys[O]; Made->V2Id = Id;
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:object:%s:%s"), *Region.ToString(), *Keys[O], *Objects[O], *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
        Made->Tags.Add(FName(*(TEXT("V2Object:") + Tag.ToString() + TEXT(":") + Objects[O])));
        for (const FMove& Move : Moves[Objects[O]])
        {
            TArray<FTransform> Placed;
            for (int32 I : Move.Indices)
            {
                FTransform X;
                Move.From->GetInstanceTransform(I, X, true);
                Placed.Add(X);
            }
            UHierarchicalInstancedStaticMeshComponent* C = CopyInto(Made, Move.From);
            C->ClearInstances();
            C->bAutoRebuildTreeOnInstanceChanges = false;
            C->RegisterComponent();
            C->AddInstances(Placed, false, true, false);
            C->BuildTreeIfOutdated(false, true);
            C->bAutoRebuildTreeOnInstanceChanges = true;
            Changed.Add(CastChecked<AV2ScenePatch>(Move.From->GetOwner()));
        }
        OutCreated.Add(Made);
    }
    for (auto& Pair : Taken)
    {
        UHierarchicalInstancedStaticMeshComponent* C = Pair.Key;
        if (!Changed.Contains(CastChecked<AV2ScenePatch>(C->GetOwner()))) continue;
        C->Modify();
        TArray<int32> Indices = Pair.Value.Array();
        C->RemoveInstances(Indices);   // sorts and removes from the highest index down
        C->BuildTreeIfOutdated(false, true);
    }
    int64 After = 0;
    for (AV2ScenePatch* Patch : Sources)
    {
        TArray<UHierarchicalInstancedStaticMeshComponent*> Parts;
        Patch->GetComponents(Parts);
        for (const auto* C : Parts) After += C->GetInstanceCount();
    }
    for (AActor* Made : OutCreated)
    {
        TArray<UHierarchicalInstancedStaticMeshComponent*> Parts;
        Made->GetComponents(Parts);
        for (const auto* C : Parts) After += C->GetInstanceCount();
    }
    if (After != Before)
    {
        Error = FString::Printf(TEXT("the split would change the instance count from %lld to %lld"), Before, After);
        return -1;   // nothing is saved: the script refuses to save after an error
    }
    for (AActor* Made : OutCreated)
    {
        AV2ScenePatch* Saved = CastChecked<AV2ScenePatch>(Made);
        Saved->ExpectedMembers = Saved->Members();
        Made->MarkPackageDirty();
    }
    for (AV2ScenePatch* Patch : Changed)
    {
        Patch->Modify();
        Patch->ExpectedMembers = Patch->Members();
        Patch->MarkPackageDirty();
        OutChanged.Add(Patch);
    }
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s split: created %d objects from %d patches, kept %d"), *Region.ToString(),
        OutCreated.Num(), OutChanged.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}
