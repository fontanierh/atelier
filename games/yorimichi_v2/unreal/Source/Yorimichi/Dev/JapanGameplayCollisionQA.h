#pragma once
#include "CoreMinimal.h"
class UWorld;
class FJsonObject;
namespace JapanGameplayCollisionQA
{
    void Write(UWorld* World, const TSharedPtr<FJsonObject>& Report);
}
