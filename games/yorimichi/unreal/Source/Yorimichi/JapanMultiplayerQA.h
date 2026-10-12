#pragma once
#include "CoreMinimal.h"
class UWorld;
namespace JapanMultiplayerQA
{
bool Tick(UWorld* World, bool Server, const FString& Folder, FString& Error);
}
