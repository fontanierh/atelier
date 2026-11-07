#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanVillagePieces
{
    const TArray<FString>& Parents();
    bool IsParent(const FString& Name);
    /** Exact complete logical Village inventory; saved source children stay separate. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
              TMap<FString,FBox>* LogicalBounds=nullptr);
}
