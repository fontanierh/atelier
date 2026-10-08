#pragma once
#include "CoreMinimal.h"

class AWandererCharacter;

/**
 * A hand-made playable character (ACairoCharacter, AModoriCharacter), registered from its own .cpp
 * (FPlayableCharacter::FRegister), so the player's generic code (-rider=, the character switch, a shared game's roster
 * and pawn) needs no branch per character.
 *
 * One entry is the default (Cairo). Every entry uses its character's merged move set, in normal play, scripted
 * sessions and shared games. The character switch and -rider= use the same names.
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

    struct YORIMICHI_API FRegister
    {
        explicit FRegister(FPlayableCharacter Character);
    };
private:
    static TArray<FPlayableCharacter>& Registry();
};
