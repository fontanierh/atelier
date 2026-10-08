#pragma once
#include "CoreMinimal.h"
class UJapanCharacterMovement;
class FJsonObject;
struct FJapanMoveResponse;
class FSavedMove_Japan;

/** Development-only delivery delay of a real host correction; production replay remains unchanged. */
namespace JapanJumpReplayQA
{
    bool Enabled();
    void Arm(UJapanCharacterMovement* Movement, const FString& Folder);
    void ObserveHost(UJapanCharacterMovement* Movement, const FString& Folder);
    bool Tick(FString& Error);
    bool ForceResponse(UJapanCharacterMovement* Movement);
    void Sent(const FJapanMoveResponse& Response);
    void HostMove(UJapanCharacterMovement* Movement, float Timestamp, float Dt);
    bool Defer(UJapanCharacterMovement* Movement, const FJapanMoveResponse& Response);
    void Move(UJapanCharacterMovement* Movement, const FSavedMove_Japan& Saved, bool Replay,
        const FVector& OriginalLocation, const FVector& OriginalVelocity);
    TSharedPtr<FJsonObject> Receipt(bool Server);
}
