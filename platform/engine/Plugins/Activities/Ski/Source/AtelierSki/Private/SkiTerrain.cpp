#include "SkiTerrain.h"
#include "SkiPark.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "CollisionQueryParams.h"

FQuat SkiFrame::RotationToWorld(const atelier::ski::Quat& Q)
{
    const FVector Forward = DirectionToWorld(atelier::ski::Rotate(Q, {1, 0, 0}));
    const FVector Up = DirectionToWorld(atelier::ski::Rotate(Q, {0, 0, 1}));
    return FRotationMatrix::MakeFromXZ(Forward, Up).ToQuat();
}

FSkiWorldTerrain::FSkiWorldTerrain(UWorld* InWorld, const AActor* InIgnore) : World(InWorld), Ignore(InIgnore) { Refresh(); }

void FSkiWorldTerrain::Refresh()
{
    Parks.Reset();
    if (World)
        for (TActorIterator<ASkiPark> It(World); It; ++It) Parks.Add(*It);
    LastX = LastY = 1e30;
}

double FSkiWorldTerrain::Height(double X, double Y) const
{
    Sample(X, Y);
    return LastHeight;
}

atelier::ski::Vec3 FSkiWorldTerrain::Normal(double X, double Y) const
{
    Sample(X, Y);
    return LastNormal;
}

void FSkiWorldTerrain::Sample(double X, double Y) const
{
    // The simulation asks for a point's height and then, in the snow, for its normal: one query answers both.
    if (X == LastX && Y == LastY) return;
    LastX = X; LastY = Y;
    const double WX = X * 100.0, WY = -Y * 100.0;
    for (const TWeakObjectPtr<ASkiPark>& Park : Parks)
    {
        double Z; FVector N;
        if (Park.IsValid() && Park->Sample(WX, WY, Z, N))
        {
            LastHeight = Z / 100.0;
            LastNormal = {N.X, -N.Y, N.Z};
            return;
        }
    }
    LastHeight = Nothing;
    LastNormal = {0, 0, 1};
    if (!World) return;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SkiSnow), true, Ignore);
    FHitResult Hit;
    const FVector From(WX, WY, (Hint + 6.0) * 100.0), To(WX, WY, (Hint - 40.0) * 100.0);
    if (World->LineTraceSingleByChannel(Hit, From, To, ECC_Pawn, Params) && Hit.ImpactNormal.Z > 0.05)
    {
        LastHeight = Hit.ImpactPoint.Z / 100.0;
        LastNormal = {Hit.ImpactNormal.X, -Hit.ImpactNormal.Y, Hit.ImpactNormal.Z};
    }
}
