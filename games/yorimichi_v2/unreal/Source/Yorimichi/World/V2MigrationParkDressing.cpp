#include "V2MigrationParkDressing.h"
#include "V2ScenePatch.h"
#include "SuperUltraMegaPark.h"
#include "AtelierData.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#include "Misc/SecureHash.h"

#if WITH_EDITOR
namespace
{
    // The identity V2ScenePatch.cpp gives every saved unit, so a rerun finds the patch it saved.
    FString StableId(const TArray<FString>& Parts)
    {
        return FMD5::HashAnsiString(*FString::Join(Parts, TEXT("\x1f"))).Left(16);
    }

    // The placement ASuperUltraMegaPark::Spawn gives a park file: its pieces, trees and props are relative to it.
    FTransform ParkPlacement(const TSharedPtr<FJsonObject>& Data)
    {
        const auto& L = Data->GetArrayField(TEXT("location_cm"));
        return FTransform(FRotator(0., Data->GetNumberField(TEXT("yaw_deg")), 0.),
            FVector(L[0]->AsNumber(), L[1]->AsNumber(), L[2]->AsNumber()));
    }

    // A new patch for one unit at the placement, identified by Id and keyed by SourceKey (what the editor step reports).
    AV2ScenePatch* SpawnUnitPatch(UWorld* World, FName Region, FName Tag, const FTransform& Placement, const FString& Id,
        const FString& SourceKey)
    {
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(Placement.GetLocation(), Placement.Rotator(), Params);
        if (!Made) return nullptr;
        Made->Region = Region; Made->SourceKey = SourceKey; Made->V2Id = Id;
        Made->OriginalTransform = Placement;   // what the editor's moves of this unit are measured from
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *Region.ToString(), *Tag.ToString(), *SourceKey, *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
        return Made;
    }

    // Lists the entries in the manifest, sorted and once each. The manifest changes only when an entry is new.
    void ListInManifest(AV2WorldManifest* Manifest, const TArray<FString>& Entries)
    {
        TSet<FString> Listed;
        for (const FString& Group : Manifest->MigratedGroups) Listed.Add(Group);
        for (const FString& Entry : Entries) Listed.Add(Entry);
        TArray<FString> Sorted = Listed.Array();
        Sorted.Sort();
        if (Sorted != Manifest->MigratedGroups)
        {
            Manifest->Modify();
            Manifest->MigratedGroups = MoveTemp(Sorted);
            Manifest->MarkPackageDirty();
        }
    }
}
#endif

int32 UV2MigrationParkDressing::MigrateParkTrees(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Units.IsEmpty()) { Error = TEXT("needs a region, its runtime tag and at least one unit"); return -1; }
    TSet<FString> Wanted;
    for (const FString& Unit : Units)
    {
        if (Unit.IsEmpty() || Wanted.Contains(Unit)) { Error = Unit + TEXT(": empty or listed twice"); return -1; }
        Wanted.Add(Unit);
    }
    AV2WorldManifest* Manifest = nullptr;
    for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
    if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    const TSharedPtr<FJsonObject>* TreeGroups = nullptr;
    if (!Data->TryGetObjectField(TEXT("trees"), TreeGroups)) { Error = DataFile + TEXT(" has no trees"); return -1; }
    FParkTreeOwners Owners;
    if (!ASuperUltraMegaPark::LoadTreeOwners(Data, AtelierDataPath(DataFile), Owners))
    { Error = DataFile + TEXT(": its tree_units.json is missing or does not name every piece's unit"); return -1; }

    // Every tree of the named units, assigned by the runtime's rule: its species, its transform, in park.json's order.
    TMap<FString, TArray<FString>> UnitSpecies;                    // unit -> its species, in the order first met
    TMap<FString, TMap<FString, TArray<FTransform>>> UnitTrees;   // unit -> species -> its instances
    for (const auto& Pair : (*TreeGroups)->Values)
    {
        const FString Species(Pair.Key);
        const TArray<TSharedPtr<FJsonValue>>& List = Pair.Value->AsArray();
        for (int32 Index = 0; Index < List.Num(); ++Index)
        {
            FTransform X;
            if (!ASuperUltraMegaPark::TreeTransform(List[Index], X)) continue;
            const FString Unit = ASuperUltraMegaPark::TreeUnit(Owners, Species, X.GetLocation());
            if (Unit.IsEmpty() || !Wanted.Contains(Unit)) continue;
            TMap<FString, TArray<FTransform>>& Groups = UnitTrees.FindOrAdd(Unit);
            if (!Groups.Contains(Species)) UnitSpecies.FindOrAdd(Unit).Add(Species);
            Groups.FindOrAdd(Species).Add(X);
        }
    }
    for (const FString& Unit : Units)
        if (!UnitTrees.Contains(Unit)) { Error = Unit + TEXT(" holds no tree of ") + DataFile; return -1; }

    const FTransform Placement = ParkPlacement(Data);
    const FString TagKey = Tag.ToString().ToLower();   // Spawn reads the manifest under the lower-case tag
    TMap<FString, AV2ScenePatch*> Existing;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
    for (const FString& Unit : Units)
    {
        const FString Id = StableId({Region.ToString(), Tag.ToString(), TEXT("trees/") + Unit});
        if (Existing.Contains(Id)) { ++OutKept; continue; }
        AV2ScenePatch* Made = SpawnUnitPatch(World, Region, Tag, Placement, Id, TagKey + TEXT(":trees/") + Unit);
        if (!Made) { Error = Unit + TEXT(": could not spawn its patch"); break; }
        OutCreated.Add(Made);
        const TMap<FString, TArray<FTransform>>& Groups = UnitTrees.FindChecked(Unit);
        for (const FString& Sp : UnitSpecies.FindChecked(Unit))
        {
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Sp, *Sp));
            if (!Mesh) { Error = Sp + TEXT(": its mesh is missing from V2 Content"); break; }
            UHierarchicalInstancedStaticMeshComponent* H = ASuperUltraMegaPark::MakeTreeGroup(Made, Made->GetRootComponent(), Sp, Mesh);
            H->CreationMethod = EComponentCreationMethod::Instance;
            Made->AddInstanceComponent(H);
            H->RegisterComponent();
            H->AddInstances(Groups.FindChecked(Sp), false, false, false);
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
    // The units stay listed, kept units too: Spawn must never spawn a tree a saved unit holds.
    TArray<FString> Entries;
    for (const FString& Unit : Units) Entries.Add(TagKey + TEXT(":trees/") + Unit);
    ListInManifest(Manifest, Entries);
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s trees: created %d, kept %d"), *TagKey, OutCreated.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

int32 UV2MigrationParkDressing::MigrateParkProps(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Meshes, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Meshes.IsEmpty() || Units.Num() != Meshes.Num())
    {
        Error = TEXT("needs a region, its runtime tag, and one mesh and unit per prop");
        return -1;
    }
    AV2WorldManifest* Manifest = nullptr;
    for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
    if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    const TArray<TSharedPtr<FJsonValue>>* PropList = nullptr;
    if (!Data->TryGetArrayField(TEXT("props"), PropList)) { Error = DataFile + TEXT(" has no props"); return -1; }
    TMap<FString, TSharedPtr<FJsonObject>> Props;
    for (const TSharedPtr<FJsonValue>& Value : *PropList)
    {
        const TSharedPtr<FJsonObject> Entry = Value->AsObject();
        Props.Add(Entry->GetStringField(TEXT("mesh")), Entry);
    }

    // Every prop is checked before anything is made: it is a prop of the file, listed once, and has a unit.
    const FString TagKey = Tag.ToString().ToLower();
    TArray<FString> Order;
    TMap<FString, TArray<int32>> UnitPicks;
    TSet<FString> Seen;
    for (int32 I = 0; I < Meshes.Num(); ++I)
    {
        if (!Props.Contains(Meshes[I])) { Error = Meshes[I] + TEXT(" is no prop of ") + DataFile; return -1; }
        if (Seen.Contains(Meshes[I])) { Error = Meshes[I] + TEXT(" is listed twice"); return -1; }
        if (Units[I].IsEmpty()) { Error = Meshes[I] + TEXT(" has no unit"); return -1; }
        Seen.Add(Meshes[I]);
        if (!UnitPicks.Contains(Units[I])) Order.Add(Units[I]);
        UnitPicks.FindOrAdd(Units[I]).Add(I);
    }

    const FTransform Placement = ParkPlacement(Data);
    TMap<FString, AV2ScenePatch*> Existing;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
    for (const FString& Unit : Order)
    {
        const FString Id = StableId({Region.ToString(), Tag.ToString(), TEXT("props/") + Unit});
        if (Existing.Contains(Id))
        {
            TArray<FString> Requested;
            for (const int32 I : UnitPicks[Unit]) Requested.Add(TagKey + TEXT(":") + Meshes[I]);
            if (!Manifest->KeptUnitCovers(Unit, Requested, Error)) break;
            ++OutKept;
            continue;
        }
        AV2ScenePatch* Made = SpawnUnitPatch(World, Region, Tag, Placement, Id, TagKey + TEXT(":props/") + Unit);
        if (!Made) { Error = Unit + TEXT(": could not spawn its patch"); break; }
        OutCreated.Add(Made);
        for (const int32 I : UnitPicks[Unit])
        {
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Meshes[I], *Meshes[I]));
            if (!Mesh) { Error = Meshes[I] + TEXT(": its mesh is missing from V2 Content"); break; }
            UStaticMeshComponent* C = ASuperUltraMegaPark::MakeProp(Made, Made->GetRootComponent(), Props[Meshes[I]], Mesh);
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
    // Saved props are listed as Tag:Mesh, as the park pieces are: Spawn skips exactly those.
    TArray<FString> Entries;
    for (const FString& Mesh : Meshes) Entries.Add(TagKey + TEXT(":") + Mesh);
    ListInManifest(Manifest, Entries);
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s props: created %d, kept %d"), *TagKey, OutCreated.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}
