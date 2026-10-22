#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanCityPieces
{
    bool IsParent(const FString& Name);
    /** Validate complete bounded membership before opening any native package. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result);
}
