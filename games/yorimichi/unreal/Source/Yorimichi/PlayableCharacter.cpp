#include "PlayableCharacter.h"

TArray<FPlayableCharacter>& FPlayableCharacter::Registry()
{
    static TArray<FPlayableCharacter> Characters;
    return Characters;
}

FPlayableCharacter::FRegister::FRegister(FPlayableCharacter Character)
{
    TArray<FPlayableCharacter>& Characters = Registry();
    check(!Characters.ContainsByPredicate([&](const FPlayableCharacter& C) { return C.Name == Character.Name; }));
    Characters.Add(MoveTemp(Character));
    // Static registration runs in no set order across files: keep them by name.
    Characters.Sort([](const FPlayableCharacter& A, const FPlayableCharacter& B) { return A.Name < B.Name; });
}

const TArray<FPlayableCharacter>& FPlayableCharacter::All() { return Registry(); }

const FPlayableCharacter* FPlayableCharacter::Find(const FString& Name)
{
    return Name.IsEmpty() ? nullptr : Registry().FindByPredicate([&](const FPlayableCharacter& C) { return C.Name == Name; });
}

const FPlayableCharacter& FPlayableCharacter::Default()
{
    const FPlayableCharacter* Character = Registry().FindByPredicate([](const FPlayableCharacter& C) { return C.bDefault; });
    check(Character);
    return *Character;
}
