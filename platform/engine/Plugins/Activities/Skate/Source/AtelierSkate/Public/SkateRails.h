#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "SkateRails.generated.h"

enum class ESkateRailKind : uint8 { Rail, Ledge, Coping, Curb };

/** A grindable line: rails, ledge and box edges, coping, curbs. Points are the top contact line (UE cm). */
struct FSkateRail
{
    FName Id;
    ESkateRailKind Kind = ESkateRailKind::Rail;
    TArray<FVector> Points;
    TArray<float> Lengths;        // cumulative arc length at each point
    FVector Side = FVector::ZeroVector;   // ledges/coping: horizontal direction from the edge toward the open side
    float Radius = 2.5f;
    FBox Bounds = FBox(ForceInit);
    float Length() const { return Lengths.IsEmpty() ? 0.f : Lengths.Last(); }
    bool IsSlideSurface() const { return Kind != ESkateRailKind::Rail; }
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
    /** Nearest rail point to P within the capture box: horizontal distance <= MaxFlat, P between MinAbove and MaxAbove
     *  over the rail. Returns the rail index or INDEX_NONE. */
    int32 FindNear(const FVector& P, float MaxFlat, float MinAbove, float MaxAbove, float& OutS, FVector& OutPoint, FVector& OutTangent) const;
};
