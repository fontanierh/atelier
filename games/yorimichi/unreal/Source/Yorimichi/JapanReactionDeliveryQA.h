#pragma once
#include "CoreMinimal.h"
class UJapanCharacterMovement;
class FJsonObject;
struct FJapanMoveResponse;
struct FJapanMovementStats;
struct FJapanScheduledReaction;
struct FJapanReactionMarker;

// Passive delivery evidence. The separate stimulus driver owns all deliberate
// scheduling holds; a serialized response is never called a received response.
namespace JapanReactionDeliveryQA
{
    void State(const UJapanCharacterMovement* Movement, const TCHAR* Event, bool Pending, bool Captured,
        float Stamp = -1.f);
    void Response(const UJapanCharacterMovement* Movement, const TCHAR* Event, const FJapanMoveResponse& Response);
    void Scheduled(const UJapanCharacterMovement* Movement, const TCHAR* Event,
        const FJapanScheduledReaction& Reaction, const FJapanReactionMarker* Marker = nullptr);
    TSharedPtr<FJsonObject> Snapshot(const UJapanCharacterMovement* Movement);
    TSharedPtr<FJsonObject> LargestCorrection(const FJapanMovementStats& Stats);
}
