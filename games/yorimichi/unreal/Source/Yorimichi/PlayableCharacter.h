#pragma once
#include "CoreMinimal.h"

class AWandererCharacter;

/**
 * A hand-made playable character (ACairoCharacter, AModoriCharacter), registered from its own .cpp
 * (FPlayableCharacter::FRegister), so the player's generic code (-rider=, the character switch, a shared game's roster
 * and pawn) needs no branch per character.
 *
 * One entry is the default (Cairo): the character a player plays when nothing names one, whose class decides its own
 * move set at BeginPlay. Its MoveSet entry (CairoAdventure) is the same character with the merged move set: what the "Move
 * set" setting picks and what a shared game plays by default. -rider= and a shared game name any entry but the default;
 * the character switch offers the default (as its MoveSet twin when chosen) and then every other entry but that twin.
 */
struct YORIMICHI_API FPlayableCharacter
{
    /** As -rider= and the character switch name it. */
    FString Name;
    /** Its pawn class. */
    UClass* (*Class)() = nullptr;
    /** Its assets are imported, checked without loading them (null: always). */
    bool (*IsBuilt)() = nullptr;
    /** The build step that imports it, named when -rider= asks for it unbuilt. */
    FString BuildStep;
    /** Called on a pawn the character switch spawned as Name, before it finishes spawning (null: nothing). */
    void (*Prepare)(AWandererCharacter* Pawn, const FString& Name) = nullptr;
    /** The default character (see above). */
    bool bDefault = false;
    /** The default's twin with the merged move set (the default's entry only). */
    FString MoveSet;

    bool Built() const { return !IsBuilt || IsBuilt(); }
    /** -rider= and a shared game may ask for it by name. */
    bool IsRequestable() const { return !bDefault; }

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

    struct YORIMICHI_API FRegister
    {
        explicit FRegister(FPlayableCharacter Character);
    };
private:
    static TArray<FPlayableCharacter>& Registry();
};
