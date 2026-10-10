#pragma once
#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "JapanAvatarState.generated.h"

/** Presentation for a simulated pawn. No replay clocks, damage decisions, or skating simulation run on this copy. */
USTRUCT()
struct FJapanAvatarState
{
    GENERATED_BODY()
    UPROPERTY() FName Action;
    UPROPERTY() uint32 ActionSerial = 0;
    UPROPERTY() float ServerTime = 0.f;
    UPROPERTY() float ActionTime = 0.f;
    UPROPERTY() float SourceStart = 0.f;
    UPROPERTY() float PlayRate = 1.f;
    UPROPERTY() float Duration = 0.f;
    UPROPERTY() float Blend = .16f;
    UPROPERTY() uint8 Mode = 0;
    UPROPERTY() uint8 Flags = 0;
    UPROPERTY() FVector_NetQuantize10 MeshLocation;
    UPROPERTY() FRotator MeshRotation = FRotator::ZeroRotator;
    UPROPERTY() FVector_NetQuantize10 Intent;
    UPROPERTY() float FlinchTime = -1.f;
    UPROPERTY() float FlinchAngle = 0.f;
    UPROPERTY() float FlinchPeak = .07f;
    UPROPERTY() float FlinchTwist = 0.f;
    UPROPERTY() FVector_NetQuantizeNormal FlinchAxis;
    UPROPERTY() float GuardBroken = 0.f;
    UPROPERTY() float GlideTurn = 0.f;
    UPROPERTY() float SwimYaw = 0.f;
    enum : uint8 { Loop = 1, Armed = 2, Guard = 4, Down = 8, Glider = 16, Locked = 32 };
};
