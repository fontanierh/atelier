#include "V2ScenePatch.h"
#include "JapanWorld.h"
#include "JapanGameplayCollisionWorld.h"
#include "SkatePark.h"
#include "AtelierData.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
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
    return false;
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
