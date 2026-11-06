#pragma once
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

namespace JapanTreehousePieces
{
    /** Complete bounded rendering membership; never return a whole-parent fallback. */
    bool Read(const TSharedPtr<FJsonObject>& Manifest,TArray<FString>& Result);
}
