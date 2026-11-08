#include "V2MigrationMisc.h"
#include "V2ScenePatch.h"
#include "MegaRamp.h"
#include "SwordTrainer.h"
#include "AtelierData.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/PackageName.h"
#include "Misc/SecureHash.h"

bool V2StaticSaved(const AV2WorldManifest* Manifest, const TCHAR* Tag, const TCHAR* MeshName, const TCHAR* PackageRoot)
{
    return Manifest && Manifest->CoversGroup(FName(Tag), MeshName)
        && FPackageName::DoesPackageExist(FString::Printf(TEXT("%s/%s"), PackageRoot, MeshName));
}

#if WITH_EDITOR
namespace
{
    bool IsRampMesh(const FString& Mesh) { return Mesh == TEXT("Mega_Ramp") || Mesh == TEXT("Mega_Trim"); }

    // Both ramp meshes and the camp props are named by their mesh; anything else is refused before the editor saves.
    bool IsSavedMesh(const FString& Mesh) { return IsRampMesh(Mesh) || ASwordTrainer::FindRoninCampProp(*Mesh) != nullptr; }

    // The same id rule as the other migrations: region, tag and unit, hashed.
    FString StableId(const TArray<FString>& Parts)
    {
        return FMD5::HashAnsiString(*FString::Join(Parts, TEXT("\x1f"))).Left(16);
    }

    // The ramp's place: world.json "mega" origin in metres, placed as AMegaRamp::Initialize places it.
    bool RampPlacement(FVector& Out)
    {
        const auto Data = AtelierReadJson(AtelierDataPath(TEXT("world.json")));
        if (!Data) return false;
        const TSharedPtr<FJsonObject>* Mega = nullptr;
        if (!Data->TryGetObjectField(TEXT("mega"), Mega)) return false;
        const auto& O = (*Mega)->GetArrayField(TEXT("origin"));
        if (O.Num() < 3) return false;
        Out = FVector(O[0]->AsNumber() * 100., -O[1]->AsNumber() * 100., O[2]->AsNumber() * 100.);
        return true;
    }

    // A camp prop as SpawnRoninCamp's prop actor is: a static mesh that blocks everything and casts a shadow.
    UStaticMeshComponent* MakeCampProp(UObject* Outer, USceneComponent* Parent, UStaticMesh* Mesh, const FString& Name)
    {
        auto* C = NewObject<UStaticMeshComponent>(Outer, FName(*Name));
        C->SetStaticMesh(Mesh);
        C->SetupAttachment(Parent);
        C->SetCollisionProfileName(TEXT("BlockAll"));
        C->SetCastShadow(true);
        return C;
    }
}
#endif

int32 UV2MigrationMisc::MigrateStaticMeshes(UObject* WorldContext, FName Region, FName Tag, const TArray<FString>& Meshes,
    const TArray<FString>& Units, TArray<AActor*>& OutCreated, int32& OutKept, FString& Error)
{
    OutCreated.Reset(); OutKept = 0;
#if WITH_EDITOR
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World || World->IsGameWorld()) { Error = TEXT("needs the editor world"); return -1; }
    if (Region.IsNone() || Tag.IsNone() || Meshes.IsEmpty() || Units.Num() != Meshes.Num())
    {
        Error = TEXT("needs a region, its runtime tag, and one unit per mesh");
        return -1;
    }
    AV2WorldManifest* Manifest = nullptr;
    for (TActorIterator<AV2WorldManifest> It(World); It; ++It) Manifest = *It;
    if (!Manifest) { Error = TEXT("the map has no AV2WorldManifest"); return -1; }

    TMap<FString, TArray<FString>> ByUnit;   // unit -> its meshes, in the order given
    TArray<FString> Order;
    TSet<FString> Seen;
    for (int32 I = 0; I < Meshes.Num(); ++I)
    {
        const FString& Mesh = Meshes[I];
        if (!IsSavedMesh(Mesh)) { Error = Mesh + TEXT(" is not a ramp or Ronin camp mesh"); return -1; }
        if (Seen.Contains(Mesh)) { Error = Mesh + TEXT(" is listed twice"); return -1; }
        if (Units[I].IsEmpty()) { Error = Mesh + TEXT(" has no unit"); return -1; }
        Seen.Add(Mesh);
        if (!ByUnit.Contains(Units[I])) Order.Add(Units[I]);
        ByUnit.FindOrAdd(Units[I]).Add(Mesh);
    }
    // A unit is one place: ramp meshes share the ramp's origin, a camp prop is a unit of its own.
    for (const FString& Unit : Order)
    {
        const TArray<FString>& Its = ByUnit[Unit];
        for (const FString& Mesh : Its)
        {
            if (IsRampMesh(Mesh) != IsRampMesh(Its[0]) || (!IsRampMesh(Mesh) && Its.Num() > 1))
            {
                Error = Unit + TEXT(": a unit is the ramp or one camp prop");
                return -1;
            }
        }
    }

    TMap<FString, AV2ScenePatch*> Existing;
    for (TActorIterator<AV2ScenePatch> It(World); It; ++It) Existing.Add(It->V2Id, *It);
    for (const FString& Unit : Order)
    {
        const TArray<FString>& Its = ByUnit[Unit];
        const FString Id = StableId({Region.ToString(), Tag.ToString(), Unit});
        if (Existing.Contains(Id))
        {
            // A kept unit holds the meshes it was saved with, all listed in the manifest; a mesh it gained since would
            // be listed without geometry (the runtime would stop building it), so refuse instead.
            for (const FString& Mesh : Its)
            {
                if (!Manifest->MigratedGroups.Contains(Tag.ToString() + TEXT(":") + Mesh))
                {
                    Error = FString::Printf(TEXT("%s was saved without %s; delete its patch and rerun to remake it"),
                        *Unit, *Mesh);
                    break;
                }
            }
            if (!Error.IsEmpty()) break;
            ++OutKept;
            continue;
        }
        // Where the runtime puts it: the ramp's origin, or the camp prop's ground point and yaw (the same placement code).
        FVector Location = FVector::ZeroVector;
        FRotator Rotation = FRotator::ZeroRotator;
        if (IsRampMesh(Its[0]))
        {
            if (!RampPlacement(Location)) { Error = TEXT("world.json has no mega origin"); break; }
        }
        else
        {
            const ASwordTrainer::FRoninCampProp* Prop = ASwordTrainer::FindRoninCampProp(*Its[0]);
            Location = ASwordTrainer::RoninCampPropPlacement(World, *Prop, Rotation);
        }
        FActorSpawnParameters Params;
        Params.Name = MakeUniqueObjectName(World->PersistentLevel, AV2ScenePatch::StaticClass(), FName(*(TEXT("V2Patch_") + Id)));
        AV2ScenePatch* Made = World->SpawnActor<AV2ScenePatch>(Location, Rotation, Params);
        if (!Made) { Error = Unit + TEXT(": could not spawn its patch"); break; }
        OutCreated.Add(Made);
        Made->Region = Region; Made->SourceKey = Tag.ToString() + TEXT(":") + Unit; Made->V2Id = Id;
        Made->SetActorLabel(FString::Printf(TEXT("%s:%s:%s:%s"), *Region.ToString(), *Tag.ToString(), *Unit, *Id));
        Made->Tags.Add(FName(*(TEXT("V2Id:") + Id)));
        Made->Tags.Add(FName(*(TEXT("V2Region:") + Region.ToString())));
        for (const FString& Mesh : Its)
        {
            UStaticMeshComponent* C = nullptr;
            if (IsRampMesh(Mesh))
            {
                C = AMegaRamp::MakePiece(Made, Made->GetRootComponent(), Mesh == TEXT("Mega_Trim"));
                if (!C || !C->GetStaticMesh()) { Error = Mesh + TEXT(": its mesh is missing from V2 Content"); break; }
            }
            else
            {
                UStaticMesh* Asset = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/SwordCamp/Assets/%s.%s"), *Mesh, *Mesh));
                if (!Asset) { Error = Mesh + TEXT(": its mesh is missing from V2 Content"); break; }
                C = MakeCampProp(Made, Made->GetRootComponent(), Asset, Mesh);
            }
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
    // Saved meshes stay listed, kept units too: the runtime must never spawn a mesh this map saved.
    TArray<FString> Listed = Manifest->MigratedGroups;
    for (const FString& Mesh : Meshes) Listed.AddUnique(Tag.ToString() + TEXT(":") + Mesh);
    Listed.Sort();
    if (Listed != Manifest->MigratedGroups)
    {
        Manifest->Modify();
        Manifest->MigratedGroups = MoveTemp(Listed);
        Manifest->MarkPackageDirty();
    }
    UE_LOG(LogTemp, Display, TEXT("V2 MIGRATION %s static meshes: created %d, kept %d"), *Tag.ToString(), OutCreated.Num(), OutKept);
    return OutCreated.Num();
#else
    Error = TEXT("editor only");
    return -1;
#endif
}
