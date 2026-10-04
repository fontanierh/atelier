#pragma once
// Native's ground speed model for the Ride backend (RIDE.md, "Speed"): UpdateSpeedModel (Native/SpeedModel.cpp) as
// GroundBoard applies it, in Ride's units (cm, s). Native's board rolls under full gravity; the model keeps a target
// speed that follows the slope only up to MaxGravityAcceleration (GravityLimit), less the surface's friction curve, and
// each tick pulls the board's speed toward it by a quarter of the difference, the difference and the target's lead both
// held within SpeedBound. On a slope steeper than the limit the board therefore climbs and falls at the target's pace,
// and the friction curves act through the target. Anything that moves the board by force (a push, a brake, a pump, a
// wall) starts the target afresh from the speed the board has next tick, and the model is off while the board pushes,
// brakes or slides. Native's no-input friction (FrictionVsSpeed_NoInput after NoInputTime, 3 s) is left out: Native's own
// runtime was measured never to apply it (no deceleration at or below 8 m/s after 10 s idle).
#include "CoreMinimal.h"

struct FRideTuning;

struct FRideSpeedModel
{
    /** The target starts afresh from the board's speed at the next step (Native's speed model flag 0x80000000: a push,
     *  brake or pump force, a collision; and a ride's start, a launch or a landing, so nothing is settled twice). */
    void Reset() { bReset = true; }
    /** One tick from the board's speed Speed (cm/s, along its travel): the target moves on by the gravity along the
     *  travel (Downhill, cm/s^2, positive downhill, before GravityLimit), less SurfaceFriction (cm/s^2; uphill only the
     *  larger of the two losses counts, as in Native) and ExtraFriction (cm/s^2, always: the manual's). Returns the
     *  speed change the model gives the board this tick (cm/s), 0 when it is off (bEnabled false). */
    float Step(const FRideTuning& Tune, float Speed, float Downhill, float SurfaceFriction, float ExtraFriction, bool bEnabled, float Dt);
    float GetTarget() const { return Target; }

private:
    float Target = 0;
    bool bReset = true;
};
