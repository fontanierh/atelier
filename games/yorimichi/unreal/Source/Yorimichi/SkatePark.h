#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Subsystems/WorldSubsystem.h"
#include "SkatePark.generated.h"

class FJsonObject;

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

/** Every grindable line in the world, from the skate pier and the road guardrails. */
UCLASS()
class YORIMICHI_API USkateRailSubsystem : public UWorldSubsystem
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

/** The skate pier: its meshes, rails and spawn points from Content/Data/skatepark/park.json (docs/SKATE.md). */
UCLASS()
class YORIMICHI_API ASkatePark : public AActor
{
    GENERATED_BODY()
public:
    ASkatePark();
    /** Reads park.json; returns false if the file is missing. Meshes that are not imported yet are skipped. */
    bool Initialize(const FString& Path);
    /** Vegetation clearance polygons (UE cm, XY) read before the world's instances are built. */
    static TArray<TArray<FVector2D>> LoadClearance(const FString& Path);
    static bool Inside(const TArray<TArray<FVector2D>>& Polygons, const FVector2D& P);
    /** The park spawn in Blender world metres and degrees (counter-clockwise), for the world map's travel list. */
    static bool ReadParkSpawn(const FString& Path, FVector& World, float& Yaw);
    FVector ParkSpawn = FVector::ZeroVector;
    float ParkSpawnYaw = 0.f;
    FVector PathTop = FVector::ZeroVector;
    float PathTopYaw = 0.f;
    int32 RailCount = 0;
private:
    FVector Origin = FVector::ZeroVector;   // UE cm
    float Yaw = 0.f;                         // degrees, Blender convention (counter-clockwise from above)
    FVector LocalToWorld(double X, double Y, double Z) const;
};
