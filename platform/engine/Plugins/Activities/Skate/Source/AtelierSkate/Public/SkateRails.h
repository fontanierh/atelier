#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SkateRails.generated.h"

/** A grindable line: rails, ledge and box edges, coping, curbs. Points are the top contact line (UE cm). */
struct FSkateRail
{
    FName Id;
    TArray<FVector> Points;
    TArray<float> Lengths;        // cumulative arc length at each point
    FBox Bounds = FBox(ForceInit);
    float Length() const { return Lengths.IsEmpty() ? 0.f : Lengths.Last(); }
};

/** Every grindable line in the world. The game adds them as it builds its places (a skate park, road guardrails). */
UCLASS()
class ATELIERSKATE_API USkateRailSubsystem : public UWorldSubsystem
{
    GENERATED_BODY()
public:
    TArray<FSkateRail> Rails;
    int32 Add(FSkateRail Rail);
    /** Point on rail R at arc length S, with the unit tangent toward increasing S. */
    FVector Sample(int32 R, float S, FVector& Tangent) const;
};
