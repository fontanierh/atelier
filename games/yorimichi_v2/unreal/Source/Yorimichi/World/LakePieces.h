#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanLakePieces
{
    const TArray<FString>& Parents();
    bool IsParent(const FString& Name);
    /** Exact five logical owners and all separate native children, with original logical bounds. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
              TMap<FString,FBox>* LogicalBounds=nullptr);
}
