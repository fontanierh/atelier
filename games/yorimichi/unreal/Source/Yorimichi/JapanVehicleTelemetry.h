#pragma once
#include "CoreMinimal.h"
class AWandererCharacter;
class UWorld;
class FJsonObject;
struct FJapanMoveInput;
struct FJapanMoveCheckpoint;
struct FHitResult;

/** Bounded nonshipping observations; never mutates movement, activity or input. */
namespace JapanVehicleTelemetry
{
    void Reset(UWorld* World);
    void Handoff(AWandererCharacter* Rider,const FJapanMoveCheckpoint& Checkpoint);
    void FirstMove(AWandererCharacter* Rider);
    void Move(AWandererCharacter* Rider, const FJapanMoveInput& Input, float Dt, bool Replay,
        const FVector& Before, float BeforeYaw);
    void Crash(AWandererCharacter* Rider,const FHitResult& Hit,float Speed);
    void AcceptedMove(AWandererCharacter* Rider, uint32 Epoch);
    void RejectedMove(AWandererCharacter* Rider, uint32 Epoch);
    void Checkpoint(AWandererCharacter* Rider, bool Applied, int32 Bytes);
    void Presentation(AWandererCharacter* Rider, double Stamp);
    void Action(AWandererCharacter* Rider, FName Button, uint16 Edge, bool Accepted, bool Replay);
    void Request(AWandererCharacter* Rider, bool Bike, uint32 Epoch, bool Pending, bool Locked, bool Encounter);
    TSharedPtr<FJsonObject> Snapshot(const AWandererCharacter* Rider);
}
