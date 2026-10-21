#pragma once

namespace atelier::driving
{
/** What the host feeds the kart: the stick only steers; the pedal comes from the triggers (or W / S). Scripted intent
 *  (the live bridge's Drive) may set the pedal from its Y because it is not a physical stick. */
struct FDrivingIntent
{
    float steer = 0.f;
    float pedal = 0.f;
};

inline FDrivingIntent driving_intent(float StickX, float Throttle, bool bScripted, float ScriptedY)
{
    return {StickX, bScripted ? ScriptedY : Throttle};
}
} // namespace atelier::driving
