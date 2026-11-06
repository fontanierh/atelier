#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanIslandPieces
{
    /** Strict complete production inventory, with separate bounded native assets. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result);
}
