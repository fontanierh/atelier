#pragma once
#include "CoreMinimal.h"
#include "JapanBikeState.generated.h"

/** Simulation-only state at a CMC timestamp, also carried atomically by an activity handoff.
 * Audio, mesh blends, wheel rotation and terrain presentation never feed this state. */
USTRUCT()
struct FJapanBikeState
{
    GENERATED_BODY()
    UPROPERTY() uint8 State = 0;
    UPROPERTY() FName Clip;
    UPROPERTY() FName Resume;
    UPROPERTY() uint32 Serial = 0;
    static constexpr int32 CheckpointBytes = 44;
    UPROPERTY() float Yaw = 0.f;
    UPROPERTY() float ClipTime = 0.f;
    UPROPERTY() float Speed = 0.f;
    UPROPERTY() float Steering = 0.f;
    UPROPERTY() float StillTime = 0.f;
    UPROPERTY() float AppliedYaw = 0.f;
    UPROPERTY() float Crank = 0.f;
    UPROPERTY() float Coast = 0.f;
    UPROPERTY() float Recoil = 0.f;
    UPROPERTY() bool Sprint = false;
    UPROPERTY() bool Terminal = false;
    UPROPERTY() bool Pedalling = false;
    bool IsValid() const;
    /** Fixed vocabulary and scalar widths; never archive a process-local FName index. */
    bool SerializeCheckpoint(FArchive& Ar);
};
