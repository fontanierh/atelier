#include "PlayableCharacter.h"
#include "AtelierData.h"
#include "JapanNetwork.h"
#include "WandererCharacter.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "Misc/PackageName.h"
#include "Dom/JsonObject.h"

// The data-defined characters' readiness records: Content/Data/<id>/character.json, which Scripts/character_pawn.py
// writes last, after BP_<Name> and its move set are saved. A record names the character, its Blueprint class, the move
// record and definition that must be present, its build step, and whether it is the default (with older launch names).

namespace
{
    bool PackageExists(const FString& ObjectPath)
    {
        return FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(ObjectPath));
    }
}

int32 FPlayableCharacter::Scan()
{
    TArray<FString> Folders;
    const FString Data = AtelierDataPath(FString());
    IFileManager::Get().FindFiles(Folders, *(Data / TEXT("*")), false, true);
    Folders.Sort();
    // The whole proposed catalogue is checked before it replaces the registry: on any conflict the game keeps the
    // catalogue it has.
    TArray<FPlayableCharacter> Proposed = Registry();
    int32 Added = 0;
    const auto Refuse = [](const FString& Folder, const TCHAR* Why)
    {
        UE_LOG(LogTemp, Error, TEXT("Characters: %s/character.json %s; the catalogue is unchanged"), *Folder, Why);
        return 0;
    };
    for (const FString& Folder : Folders)
    {
        const FString Path = Data / Folder / TEXT("character.json");
        if (!IFileManager::Get().FileExists(*Path)) continue;
        const TSharedPtr<FJsonObject> Record = AtelierReadJson(Path);
        FString Name, Id, ClassPath, Definition, BuildStep;
        if (!Record || !Record->TryGetStringField(TEXT("name"), Name) || !Record->TryGetStringField(TEXT("id"), Id)
            || !Record->TryGetStringField(TEXT("class"), ClassPath) || !Record->TryGetStringField(TEXT("definition"), Definition))
            return Refuse(Folder, TEXT("is malformed"));
        if (Id != Folder) return Refuse(Folder, TEXT("names another id"));
        // Registered already (by its stable id): a record never replaces a character in play.
        if (Proposed.ContainsByPredicate([&](const FPlayableCharacter& C) { return C.Id == Id; })) continue;
        if (!ClassPath.StartsWith(TEXT("/Game/")) || !ClassPath.EndsWith(TEXT("_C")) || !PackageExists(ClassPath) || !PackageExists(Definition))
            return Refuse(Folder, TEXT("names a pawn class or definition that is not built"));
        if (Proposed.ContainsByPredicate([&](const FPlayableCharacter& C) { return C.Name == Name; }))
            return Refuse(Folder, TEXT("reuses a registered name"));
        Record->TryGetStringField(TEXT("build_step"), BuildStep);
        FPlayableCharacter Character;
        Character.Name = Name;
        Character.Id = Id;
        Character.Class = [ClassPath] { return LoadClass<AWandererCharacter>(nullptr, *ClassPath); };
        // Checked on disk, never loaded: the character switch asks every time the menu opens.
        const FString Move = AtelierDataPath(Id / TEXT("adventure.json"));
        Character.IsBuilt = [Move, Definition, ClassPath]
        {
            return IFileManager::Get().FileExists(*Move) && PackageExists(Definition) && PackageExists(ClassPath);
        };
        Character.BuildStep = BuildStep;
        Record->TryGetBoolField(TEXT("default"), Character.bDefault);
        if (const TArray<TSharedPtr<FJsonValue>>* Aliases; Record->TryGetArrayField(TEXT("aliases"), Aliases))
            for (const TSharedPtr<FJsonValue>& Alias : *Aliases) Character.Aliases.Add(Alias->AsString());
        Proposed.Add(MoveTemp(Character));
        ++Added;
    }
    TSet<FString> Names;
    int32 Defaults = 0;
    for (const FPlayableCharacter& Character : Proposed)
    {
        Defaults += Character.bDefault;
        TArray<FString> Called = Character.Aliases;
        Called.Add(Character.Name);
        for (const FString& Name : Called)
        {
            bool bTaken = false;
            Names.Add(Name, &bTaken);
            if (Name.IsEmpty() || bTaken)
            {
                UE_LOG(LogTemp, Error, TEXT("Characters: '%s' names two characters; the catalogue is unchanged"), *Name);
                return 0;
            }
        }
    }
    if (Defaults > 1)
    {
        UE_LOG(LogTemp, Error, TEXT("Characters: %d defaults; the catalogue is unchanged"), Defaults);
        return 0;
    }
    Proposed.Sort([](const FPlayableCharacter& A, const FPlayableCharacter& B) { return A.Name < B.Name; });
    Registry() = MoveTemp(Proposed);
    for (const FPlayableCharacter& Character : Registry())
        UE_LOG(LogTemp, Display, TEXT("Character registered: %s"), *Character.Name);
    return Added;
}

// A shared game's catalogue is fixed while it is connected (the host and every peer must agree on it): a character added
// meanwhile appears after reconnecting.
static FAutoConsoleCommandWithWorld RescanCharacters(
    TEXT("yorimichi.RescanCharacters"),
    TEXT("Register every playable character whose readiness record (Content/Data/<id>/character.json) appeared since the last scan."),
    FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
    {
        if (JapanNetwork::IsOnline(World)) { UE_LOG(LogTemp, Warning, TEXT("Characters: no rescan during a shared game")); return; }
        UE_LOG(LogTemp, Display, TEXT("Characters added: %d"), FPlayableCharacter::Scan());
    }));
