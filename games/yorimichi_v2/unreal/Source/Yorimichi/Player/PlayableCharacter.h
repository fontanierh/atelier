#pragma once
#include "CoreMinimal.h"

class AWandererCharacter;

/**
 * A playable character, so the player's generic code (-rider=, the character switch, a shared game's roster and pawn)
 * needs no branch per character. Each is a Blueprint of AMoverCharacter, BP_<Name>, registered from its readiness record,
 * Content/Data/<id>/character.json (Scan), when the registry is first read.
 *
 * One entry is the default (character.toml [game] default: Cairo). Every entry uses its character's merged move set,
 * in normal play, scripted sessions and shared games. The character switch and -rider= use the same names.
 */
struct YORIMICHI_API FPlayableCharacter
{
    /** As -rider= and the character switch name it. */
    FString Name;
    /** Its id (assets/characters/<id>, Content/Data/<id>/): stable across renames. */
    FString Id;
    /** Its pawn class. */
    TFunction<UClass*()> Class;
    /** Its assets are imported, checked without loading them (unset: always). */
    TFunction<bool()> IsBuilt;
    /** The build step that imports it, named when -rider= asks for it unbuilt. */
    FString BuildStep;
    /** The default character (see above). */
    bool bDefault = false;
    /** Older launch names resolve to this same character, never another move set or a menu entry. */
    TArray<FString> Aliases;

    bool Built() const { return !IsBuilt || IsBuilt(); }
    /** Every registered character, by name. */
    static const TArray<FPlayableCharacter>& All();
    static const FPlayableCharacter* Find(const FString& Name);
    /** The default character. */
    static const FPlayableCharacter& Default();

    static FString Requested();
    static UClass* PawnOverride();
    static TArray<FString> Available();
    static FString NameOf(const AWandererCharacter* Character);
    static FString Label(const FString& Name) { return Name; }
    static AWandererCharacter* SwitchPlayer(AWandererCharacter* From, const FString& Name);
    /** Registers every data-defined character whose readiness record is staged (Content/Data/<id>/character.json) and not
     *  yet registered; returns how many it added. Run at startup and by `yorimichi.RescanCharacters` while the game runs
     *  (a shared game keeps its catalogue for the session). */
    static int32 Scan();

private:
    static TArray<FPlayableCharacter>& Registry();
};
