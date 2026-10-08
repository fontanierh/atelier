#pragma once
#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "JapanBikeState.h"
#include "JapanSailState.h"
#include "JapanActivityState.generated.h"

UENUM()
enum class EJapanActivity : uint8 { OnFoot, Skate, Bike, Sailboat, Zeppelin };

/** Server-owned handoff. The epoch invalidates every old movement, pose and action packet together. */
USTRUCT()
struct FJapanActivityState
{
    GENERATED_BODY()
    UPROPERTY() uint32 Epoch = 1;
    UPROPERTY() EJapanActivity Kind = EJapanActivity::OnFoot;
    UPROPERTY() FVector_NetQuantize100 Location = FVector::ZeroVector;
    UPROPERTY() FRotator Rotation = FRotator::ZeroRotator;
    UPROPERTY() FVector_NetQuantize100 Velocity = FVector::ZeroVector;
    UPROPERTY() bool bFalling = false;
    /** 0: ordinary activity; 1: input timeout; 2: excessive simulation-time burst. */
    UPROPERTY() uint8 ClockCorrection = 0;
    UPROPERTY() FJapanBikeState Bike;
    UPROPERTY() FJapanSailState Sail;
    /** Optional post-exit reaction, using the existing bounded foot checkpoint.
     * Published with the epoch so prediction cannot start from the pre-hit state. */
    UPROPERTY() bool bFootReaction = false;
    UPROPERTY() TArray<uint8> FootBytes;
    UPROPERTY() FName FootAction;
};
