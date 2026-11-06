#pragma once
#include "CoreMinimal.h"
class UWorld;
class UJapanCharacterMovement;
namespace JapanCombatQA
{
    /** Opt-in same-machine native probe. Files coordinate strike stimuli only;
     * player inputs, authoritative decisions and reactions use the real network. */
    void ReactionApplied(const UJapanCharacterMovement* Movement, uint32 Epoch, uint32 Sequence);
    bool Finalize(const FString& Folder, FString& Error);
    bool Tick(UWorld* World, bool Server, const FString& Folder, FString& Error);
}
