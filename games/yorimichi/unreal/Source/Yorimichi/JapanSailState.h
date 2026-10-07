#pragma once
#include "CoreMinimal.h"
#include "JapanSailState.generated.h"
USTRUCT()
struct FJapanSailState
{
    GENERATED_BODY()
    static constexpr int32 CheckpointBytes=25;
    UPROPERTY() bool Equipped=false;
    UPROPERTY() uint32 Serial=0;
    UPROPERTY() float Yaw=0.f;
    UPROPERTY() float Speed=0.f;
    UPROPERTY() float Steering=0.f;
    UPROPERTY() float SailAmount=0.f;
    UPROPERTY() float SailTarget=0.f;
    bool IsValid() const;
    bool SerializeCheckpoint(FArchive& Ar);
};
