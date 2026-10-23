#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanCityPieces
{
    const TArray<FString>& Parents();
    bool IsParent(const FString& Name);
    /** Validate complete bounded membership before opening any native package. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
        TMap<FString,FBox>* LogicalBounds=nullptr);
}
