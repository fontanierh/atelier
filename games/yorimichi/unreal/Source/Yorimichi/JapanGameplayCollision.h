#pragma once
#include "CoreMinimal.h"
#include "Engine/EngineTypes.h"
#include "CollisionQueryParams.h"
class AActor;
class UPrimitiveComponent;
class UWorld;

/** Fixed gameplay geometry is selected from authored owners, not NetRole or object type.
 * Park meshes may have WorldDynamic object type. Vehicle prediction still needs them. */
namespace JapanGameplayCollision
{
    constexpr ECollisionChannel Channel = ECC_GameTraceChannel1;
    bool IsFixed(const AActor* Actor);
    bool IsFixed(const UPrimitiveComponent* Component);
    /** Run after the static-world bootstrap on every peer, including solo/server. */
    void Install(UWorld* World);
    /** Ignore dynamic owners as well as using the explicit channel: future spawned
     * BlockAll primitives must never become accidental prediction geometry. */
    FCollisionQueryParams Query(UWorld* World, FName Tag, const TStatId& Stat, bool Complex);
    /** Component/key inventory with stable placement identifiers, suitable for parity receipts. */
    TArray<FString> Inventory(UWorld* World, TArray<FString>& Errors);
}
