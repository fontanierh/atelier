#include "RideSpeedModel.h"
#include "RideTuning.h"

float FRideSpeedModel::Step(const FRideTuning& Tune, float Speed, float Downhill, float SurfaceFriction, float ExtraFriction, bool bEnabled, float Dt)
{
    const float Bound = FMath::Max(0.f, Tune.SpeedBound);
    if (bReset) { Target = Speed; bReset = false; }
    else Target = FMath::Clamp(Target, FMath::Max(0.f, Speed - Bound), Speed + Bound);
    // Downhill the target gains the slope's pull less the friction; uphill it loses the pull or the friction, whichever
    // is more (Native's surface delta).
    const float Pull = FMath::Clamp(Downhill, -Tune.GravityLimit, Tune.GravityLimit) * Dt, Friction = -SurfaceFriction * Dt;
    Target += Pull > 0 ? Pull + Friction : FMath::Min(Pull, Friction);
    Target = FMath::Max(0.f, Target - ExtraFriction * Dt);
    const float Error = FMath::Clamp(Target - Speed, -Bound, Bound);
    return bEnabled ? (Error < 0 ? Tune.SpeedGainDown : Tune.SpeedGain) * Error : 0.f;
}
