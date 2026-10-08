#pragma once
#include "CoreMinimal.h"
class UJapanCharacterMovement;
class FJsonObject;
struct FJapanMoveResponse;

// Passive delivery evidence. The separate stimulus driver owns all deliberate
// scheduling holds; a serialized response is never called a received response.
namespace JapanReactionDeliveryQA
{
    void State(const UJapanCharacterMovement* Movement, const TCHAR* Event, bool Pending, bool Captured,
        float Stamp = -1.f);
    void Response(const UJapanCharacterMovement* Movement, const TCHAR* Event, const FJapanMoveResponse& Response);
    TSharedPtr<FJsonObject> Snapshot(const UJapanCharacterMovement* Movement);
}
