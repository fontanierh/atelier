#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SkateRails.h"
#include "SkatePark.generated.h"

class FJsonObject;

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
    /** The pier footprint, shared by local lighting and ambient-effect exclusion. */
    bool ContainsPlanar(const FVector& Position, float Margin = 0.f) const;
private:
    FVector2D DeckHalfSize = FVector2D::ZeroVector;
    FVector Origin = FVector::ZeroVector;   // UE cm
    float Yaw = 0.f;                         // degrees, Blender convention (counter-clockwise from above)
    FVector LocalToWorld(double X, double Y, double Z) const;
};
