#include "V2MigrationTravel.h"
#include "V2ScenePatch.h"
#include "AtelierData.h"
#include "BelmonteTrack.h"
#include "FerryService.h"
#include "GondolaService.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/SecureHash.h"

namespace
{
    FString StableId(const TArray<FString>& Parts)
    {
        // The same identity as V2ScenePatch.cpp's: region, tag and unit, so a rerun finds the patch it saved.
        return FMD5::HashAnsiString(*FString::Join(Parts, TEXT("\x1f"))).Left(16);
    }

    // Builds one unit's components into its patch from the entries given, or fails with Error.
    using FBuildUnit = TFunctionRef<bool(AV2ScenePatch* Made, const TArray<FString>& Entries, FString& Error)>;

    // A built component joins its patch as an instance component, as the other migrations' parts do.
    template <class T>
    void AddPart(AV2ScenePatch* Made, T* Component)
    {
        Component->CreationMethod = EComponentCreationMethod::Instance;
        Made->AddInstanceComponent(Component);
        Component->RegisterComponent();
    }

    // One AV2ScenePatch per unit (in the order the units first appear), at the origin the services spawn at, listed in the
    // map's manifest as "<tag>:<name>" for every entry, so the runtime service skips exactly the saved entries.
    int32 SaveUnits(UObject* WorldContext, FName Region, FName Tag, const TArray<FString>& Names, const TArray<FString>& Units,
        FBuildUnit Build, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
    {
        OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
        UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
        if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
        if (Region.IsNone() || Tag.IsNone() || Names.IsEmpty() || Units.Num() != Names.Num())
        {
            Error = TEXT("needs a region, its runtime tag, and one unit per entry");
            return -1;
        }
        AV2WorldManifest* Manifest = nullptr;
        for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
        if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }
        TMap<FString, TArray<FString>> ByUnit;   // unit -> its entries, in the order given
        TArray<FString> Order;
        TSet<FString> Seen;
        for (int32 I = 0; I < Names.Num(); ++I)
        {
            if (Seen.Contains(Names[I])) { Error = Names[I] + TEXT(" is listed twice"); return -1; }
            if (Units[I].IsEmpty()) { Error = Names[I] + TEXT(" has no unit"); return -1; }
            Seen.Add(Names[I]);
            if (!ByUnit.Contains(Units[I])) Order.Add(Units[I]);
            ByUnit.FindOrAdd(Units[I]).Add(Names[I]);
        }
        TMap<FString, AV2ScenePatch*> Existing;
        for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
        for (const FString& Unit : Order)
        {
            const FString Id = StableId({Region.ToString(), Tag.ToString(), Unit});
            if (Existing.Contains(Id))
            {
                TArray<FString> Requested;
                for (const FString& Name : ByUnit[Unit]) Requested.Add(Tag.ToString() + TEXT(":") + Name);
                if (!Manifest->KeptUnitCovers(Unit, Requested, Error)) break;
                ++OutKept;
                continue;
            }
            FActorSpawnParameters Params;
            Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
            AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(FVector::ZeroVector, FRotator::ZeroRotator, Params);
            if (!Made) { Error = Unit + TEXT(": could not spawn its patch"); break; }
            OutCreated.Add(Made);
            Made->Region = Region; Made->SourceKey = Tag.ToString() + TEXT(":") + Unit; Made->V2Id = Id;
            Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *Region.ToString(), *Tag.ToString(), *Unit, *Id));
            Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
            Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
            if (!Build(Made, ByUnit[Unit], Error)) break;
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
        // Every listed entry stays listed, kept units too: the runtime must never build an entry this map saved.
        TArray<FString> Listed = Manifest->MigratedGroups;
        for (const FString& Name : Names) Listed.AddUnique(Tag.ToString() + TEXT(":") + Name);
        Listed.Sort();
        if (Listed != Manifest->MigratedGroups)
        {
            Manifest->Modify();
            Manifest->MigratedGroups = MoveTemp(Listed);
            Manifest->MarkPackageDirty();
        }
        return OutCreated.Num();
#else
        Error = TEXT("editor only");
        return -1;
#endif
    }

    TMap<FString, TSharedPtr<FJsonObject>> ByName(const TArray<TSharedPtr<FJsonValue>>& Values, const TCHAR* Field)
    {
        TMap<FString, TSharedPtr<FJsonObject>> Out;
        for (const auto& Value : Values)
        {
            const auto Object = Value->AsObject();
            Out.Add(Object->GetStringField(Field), Object);
        }
        return Out;
    }
}

int32 UV2MigrationTravel::MigrateRailwayPieces(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Names, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
#if WITH_EDITOR
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { OutCreated.Reset(); OutKept = 0; Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    const TMap<FString, TSharedPtr<FJsonObject>> Pieces = ByName(Data->GetArrayField(TEXT("pieces")), TEXT("name"));
    TMap<FString, TSharedPtr<FJsonObject>> Groups;
    for (const auto& Value : Data->GetArrayField(TEXT("instances")))
    {
        const auto Group = Value->AsObject();
        Groups.Add(ABelmonteTrack::GroupName(Group), Group);
    }
    const TSharedPtr<FJsonObject> Cull = Data->GetObjectField(TEXT("cull_cm"));
    const int32 Count = SaveUnits(WorldContext, Region, Tag, Names, Units,
        [&](AV2ScenePatch* Made, const TArray<FString>& Entries, FString& Err) -> bool
        {
            for (const FString& Entry : Entries)
            {
                if (const TSharedPtr<FJsonObject>* Piece = Pieces.Find(Entry))
                {
                    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *(*Piece)->GetStringField(TEXT("mesh")));
                    if (!Mesh) { Err = Entry + TEXT(": its mesh is missing from V2 Content"); return false; }
                    AddPart(Made, ABelmonteTrack::MakePiece(Made, Made->GetRootComponent(), Cull, *Piece, Mesh));
                }
                else if (const TSharedPtr<FJsonObject>* Group = Groups.Find(Entry))
                {
                    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *(*Group)->GetStringField(TEXT("mesh")));
                    if (!Mesh) { Err = Entry + TEXT(": its mesh is missing from V2 Content"); return false; }
                    AddPart(Made, ABelmonteTrack::MakeGroup(Made, Made->GetRootComponent(), *Group, Mesh));
                }
                else if (int32 At = INDEX_NONE; Entry.FindLastChar(TEXT('@'), At) && Groups.Find(Entry.Left(At)))
                {
                    // One row of a group, "mesh#key@row": its own patch, the row's index in the group's instances.
                    const TSharedPtr<FJsonObject> Row = *Groups.Find(Entry.Left(At));
                    const FString Suffix = Entry.RightChop(At + 1);
                    const auto& Rows = Row->GetArrayField(TEXT("instances"));
                    if (!Suffix.IsNumeric() || !Rows.IsValidIndex(FCString::Atoi(*Suffix))
                        || Rows[FCString::Atoi(*Suffix)]->AsArray().Num() < 5)
                    { Err = Entry + TEXT(": no such fitting row in its group"); return false; }
                    UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *Row->GetStringField(TEXT("mesh")));
                    if (!Mesh) { Err = Entry + TEXT(": its mesh is missing from V2 Content"); return false; }
                    const TArray<int32> Only{ FCString::Atoi(*Suffix) };
                    AddPart(Made, ABelmonteTrack::MakeGroup(Made, Made->GetRootComponent(), Row, Mesh, &Only));
                }
                else
                {
                    Err = Entry + TEXT(" is no piece or group of ") + DataFile;
                    return false;
                }
            }
            return true;
        }, OutCreated, OutKept, Error);
    if (Count >= 0) UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s railway: created %d, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return Count;
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

int32 UV2MigrationTravel::MigrateFerryTerminals(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Names, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
#if WITH_EDITOR
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { OutCreated.Reset(); OutKept = 0; Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    const TMap<FString, TSharedPtr<FJsonObject>> Terminals = ByName(Data->GetArrayField(TEXT("terminals")), TEXT("key"));
    const int32 Count = SaveUnits(WorldContext, Region, Tag, Names, Units,
        [&](AV2ScenePatch* Made, const TArray<FString>& Entries, FString& Err) -> bool
        {
            for (const FString& Entry : Entries)
            {
                const TSharedPtr<FJsonObject>* Terminal = Terminals.Find(Entry);
                if (!Terminal) { Err = Entry + TEXT(" is no terminal of ") + DataFile; return false; }
                TArray<UStaticMeshComponent*> Parts;
                UStaticMeshComponent* Collision = nullptr;
                int32 Missing = 0;
                AFerryService::MakeTerminal(Made, Made->GetRootComponent(), *Terminal, Parts, Collision, Missing);
                if (Missing > 0) { Err = Entry + TEXT(": its meshes are missing from V2 Content"); return false; }
                for (UStaticMeshComponent* Part : Parts) AddPart(Made, Part);
                if (Collision) AddPart(Made, Collision);
            }
            return true;
        }, OutCreated, OutKept, Error);
    if (Count >= 0) UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s ferry terminals: created %d, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return Count;
#else
    Error = TEXT("editor only");
    return -1;
#endif
}

int32 UV2MigrationTravel::MigrateGondolaStatics(UObject* WorldContext, FName Region, FName Tag, const FString& DataFile,
    const TArray<FString>& Names, const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
#if WITH_EDITOR
    const auto Data = AtelierReadJson(AtelierDataPath(DataFile));
    if (!Data) { OutCreated.Reset(); OutKept = 0; Error = DataFile + TEXT(" is missing or unreadable"); return -1; }
    const TMap<FString, TSharedPtr<FJsonObject>> Statics = ByName(Data->GetArrayField(TEXT("static")), TEXT("name"));
    const int32 Count = SaveUnits(WorldContext, Region, Tag, Names, Units,
        [&](AV2ScenePatch* Made, const TArray<FString>& Entries, FString& Err) -> bool
        {
            for (const FString& Entry : Entries)
            {
                const TSharedPtr<FJsonObject>* Static = Statics.Find(Entry);
                if (!Static) { Err = Entry + TEXT(" is no static entry of ") + DataFile; return false; }
                UStaticMeshComponent* C = AGondolaService::MakeStatic(Made, Made->GetRootComponent(), *Static);
                if (!C) { Err = Entry + TEXT(": its mesh is missing from V2 Content"); return false; }
                AddPart(Made, C);
            }
            return true;
        }, OutCreated, OutKept, Error);
    if (Count >= 0) UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s gondola statics: created %d, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return Count;
#else
    Error = TEXT("editor only");
    return -1;
#endif
}
