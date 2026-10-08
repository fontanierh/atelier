#pragma once
#include "CoreMinimal.h"
class UWorld;
class UJapanCharacterMovement;

namespace JapanReactionDeliveryQA
{
    // Development-only real-pair stimuli. All scheduling changes are reported
    // explicitly; ordinary runs never enter a hook or hold a send.
    bool Tick(UWorld* World, bool Server, const FString& Folder, FString& Error);
    void AfterCapture(UJapanCharacterMovement* Movement, bool Pending, bool Captured, bool GoodAckEligible);
    bool HoldSend(UJapanCharacterMovement* Movement);
    void AfterSend(UJapanCharacterMovement* Movement, bool Serialized);
}
