#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Hippodrome.generated.h"

class UStaticMeshComponent;

/**
 * The Hidamari Hippodrome's oval (world/regions/hippodrome/layout.py, docs/HIPPODROME.md). Distances are metres along
 * the centre line from the finish post in the running direction (counter-clockwise seen from above); an offset is
 * metres outwards from the centre line. Points come back in Unreal cm on the flat platform.
 */
struct FHippodromeCourse
{
    FVector2D Origin = FVector2D(600., 525.);   // Blender metres
    double Half = 60., Radius = 50., Width = 14., Lap = 0., FinishX = 600., Z = 0.;
    /** layout.centre: the point at S, Offset metres outwards, and the running yaw (Unreal degrees). */
    FVector At(double S, double Offset, float* Yaw = nullptr) const;
    /** layout.curvature_scale: how much further a runner Offset metres outwards travels per metre of centre line. */
    double CurvatureScale(double S, double Offset) const;
    bool InTurn(double S) const;
    /** Blender metres (x east, y north) to Unreal cm on the platform. */
    FVector World(double X, double Y, double Up = 0.) const { return FVector(X * 100., -Y * 100., (Z + Up) * 100.); }
};

/**
 * The Hidamari Hippodrome (docs/HIPPODROME.md): the racecourse on the slope north of the city. Places the imported
 * meshes (Content/Data/hippodrome/hippodrome.json, import_hippodrome.py) round the course origin.
 */
UCLASS()
class YORIMICHI_API AHippodrome : public AActor
{
    GENERATED_BODY()
public:
    bool bGameplayReady = false;
    AHippodrome();
    /** The hippodrome described by Path (hippodrome.json); null when the file or its meshes are missing. */
    static AHippodrome* Spawn(UWorld* World, const FString& Path);
    static AHippodrome* Find(const UObject* WorldContext);

    FHippodromeCourse Course;
    FVector ReturnGround = FVector::ZeroVector;
    float ReturnYaw = 0.f;

private:
    UPROPERTY() TObjectPtr<USceneComponent> Root;
    bool Initialize(const FString& Path);
};
