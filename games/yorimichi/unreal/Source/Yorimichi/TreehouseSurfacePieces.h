#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanTreehouseSurfacePieces
{
    const TArray<FString>& Parents();
    bool IsParent(const FString& Name);
    /** Exact four logical surface owners and all separate native children, with original logical bounds. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
              TMap<FString,FBox>* LogicalBounds=nullptr);
}
