#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SkateAssistZones.generated.h"

/** A box in the world (UE cm, turned YawDeg about +Z) inside which the rider's assistance is limited: the vert assist
 *  (FSkateFeel::VertAssist) is at most VertAssistMax there, so a kicker that should send the rider forward does, whatever
 *  the player's setting. */
struct FSkateAssistZone
{
    FName Id;
    FVector Centre = FVector::ZeroVector, HalfExtent = FVector::ZeroVector;
    float YawDeg = 0.f;
    float VertAssistMax = 1.f;
    /** The place that added it (a park); a zone whose owner is gone no longer applies. */
    TWeakObjectPtr<const UObject> Owner;
    bool Contains(const FVector& At) const;
};

/** Every assist zone in the world. A game adds them as it builds its places (a park's park.json); the skating reads
 *  them each frame (USkateComponent, README "Assist zones"). With none, nothing changes. */
UCLASS()
class ATELIERSKATE_API USkateAssistSubsystem : public UWorldSubsystem
{
    GENERATED_BODY()
public:
    TArray<FSkateAssistZone> Zones;
    void Add(FSkateAssistZone Zone);
    /** Removes the zones Owner added. */
    void Remove(const UObject* Owner);
    /** The lowest VertAssistMax of the zones that contain any of the points, 1 (no limit) outside them all. */
    float VertAssistLimit(std::initializer_list<FVector> At) const;
};
