#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanSouthwestPieces
{
    const TArray<FString>& Parents();
    bool IsParent(const FString& Name);
    /** Complete separate native children, with original logical local bounds; no parent fallback. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
              TMap<FString,FBox>* LogicalBounds=nullptr);
}
