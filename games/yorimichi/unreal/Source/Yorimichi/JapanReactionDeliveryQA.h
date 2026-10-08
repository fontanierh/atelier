#pragma once
#include "CoreMinimal.h"
class UJapanCharacterMovement;
class FJsonObject;
struct FJapanMoveResponse;
struct FJapanMovementStats;
struct FJapanScheduledReaction;
struct FJapanReactionMarker;
struct FJapanActivityState;

// Passive delivery evidence. The separate stimulus driver owns all deliberate
// scheduling holds; a serialized response is never called a received response.
namespace JapanReactionDeliveryQA
{
    void State(const UJapanCharacterMovement* Movement, const TCHAR* Event, bool Pending, bool Captured,
        float Stamp = -1.f);
    void Response(const UJapanCharacterMovement* Movement, const TCHAR* Event, const FJapanMoveResponse& Response,
        float CorrectionCm = -1.f);
    void Scheduled(const UJapanCharacterMovement* Movement, const TCHAR* Event,
        const FJapanScheduledReaction& Reaction, const FJapanReactionMarker* Marker = nullptr);
    void DeadInput(const UJapanCharacterMovement* Movement, FName Button, uint16 Edge);
    void Activity(const UJapanCharacterMovement* Movement, const TCHAR* Event, const FJapanActivityState& State);
    void FirstMove(const UJapanCharacterMovement* Movement, float Stamp, float Dt, const FVector& Start);
    TSharedPtr<FJsonObject> Snapshot(const UJapanCharacterMovement* Movement);
    TSharedPtr<FJsonObject> LargestCorrection(const FJapanMovementStats& Stats);
}
