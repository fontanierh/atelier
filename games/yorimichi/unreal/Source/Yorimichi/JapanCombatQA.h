#pragma once
#include "CoreMinimal.h"
class UWorld;
namespace JapanCombatQA
{
    /** Opt-in same-machine native probe. Files coordinate strike stimuli only;
     * player inputs, authoritative decisions and reactions use the real network. */
    bool Finalize(const FString& Folder, FString& Error);
    bool Tick(UWorld* World, bool Server, const FString& Folder, FString& Error);
}
