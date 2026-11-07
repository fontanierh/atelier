#pragma once
#include "CoreMinimal.h"
class UWorld;
namespace JapanGameplayQA
{
    // Opt-in native test only: drives the ordinary owning player's public inputs and observes host state.
    bool Tick(UWorld* World, bool Server, const FString& Folder, FString& Error);
}
