// The snow the native simulation stands on, read from the Unreal world (README.md, "World"). The simulation's frame is
// the world's in metres with y flipped to the left: sim (x, y, z) = world (X, -Y, Z) / 100. Inside a terrain park the
// park's exact surface answers; elsewhere a line trace on the Pawn channel against static collision does.
#pragma once
#include "CoreMinimal.h"
#include "Native/SkiSim.h"

class AActor;
class ASkiPark;
class UWorld;

namespace SkiFrame
{
inline FVector ToWorld(const atelier::ski::Vec3& V) { return FVector(V.x * 100.0, -V.y * 100.0, V.z * 100.0); }
inline FVector DirectionToWorld(const atelier::ski::Vec3& V) { return FVector(V.x, -V.y, V.z); }
inline atelier::ski::Vec3 FromWorld(const FVector& V) { return {V.X / 100.0, -V.Y / 100.0, V.Z / 100.0}; }
/** A body rotation in world space from its forward and up axes. */
FQuat RotationToWorld(const atelier::ski::Quat& Q);
}

class FSkiWorldTerrain final : public atelier::ski::Terrain
{
public:
    FSkiWorldTerrain(UWorld* InWorld, const AActor* InIgnore);
    /** Finds the parks again (call when the skis go on). */
    void Refresh();
    /** The traces search from a little above this height down (m, the skier's). */
    void SetHint(double Z) { Hint = Z; }
    /** Below everything: a point over nothing is never in the snow. */
    static constexpr double Nothing = -1e7;

    virtual double Height(double X, double Y) const override;
    virtual atelier::ski::Vec3 Normal(double X, double Y) const override;

private:
    void Sample(double X, double Y) const;

    UWorld* World = nullptr;
    const AActor* Ignore = nullptr;
    TArray<TWeakObjectPtr<ASkiPark>> Parks;
    double Hint = 0;
    mutable double LastX = 1e30, LastY = 1e30, LastHeight = Nothing;
    mutable atelier::ski::Vec3 LastNormal = {0, 0, 1};
};
