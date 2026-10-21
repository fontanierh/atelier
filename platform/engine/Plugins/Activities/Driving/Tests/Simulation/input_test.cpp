// The kart's host input: the physical stick only steers, the triggers drive, and scripted intent may drive from Y.

#include "DrivingIntent.h"

#include <cstdio>

using atelier::driving::FDrivingIntent;
using atelier::driving::driving_intent;

namespace
{
int failures = 0;

void check(bool ok, const char* what, int line)
{
    if (!ok)
    {
        std::printf("FAIL line %d: %s\n", line, what);
        ++failures;
    }
}

void close(float a, float b, const char* what, int line)
{
    check((a > b ? a - b : b - a) < 1e-6f, what, line);
}
} // namespace

int main()
{
    // A gamepad's left stick held forward, no trigger: it steers only.
    FDrivingIntent stick_only = driving_intent(0.f, 0.f, false, 1.f);
    close(stick_only.steer, 0.f, "stick Y alone does not steer", __LINE__);
    close(stick_only.pedal, 0.f, "stick Y alone does not accelerate", __LINE__);

    // The trigger released while the stick is still forward: no throttle.
    close(driving_intent(0.f, 0.f, false, 1.f).pedal, 0.f, "trigger release with stick held", __LINE__);

    // The triggers drive, and the stick still steers.
    FDrivingIntent pad = driving_intent(.4f, .8f, false, 1.f);
    close(pad.steer, .4f, "stick X steers", __LINE__);
    close(pad.pedal, .8f, "right trigger accelerates", __LINE__);
    close(driving_intent(0.f, -.6f, false, 0.f).pedal, -.6f, "left trigger brakes", __LINE__);

    // Scripted intent (the live bridge's Drive) may drive from its Y, which is not a physical stick.
    FDrivingIntent scripted = driving_intent(.25f, 0.f, true, 1.f);
    close(scripted.steer, .25f, "scripted steer", __LINE__);
    close(scripted.pedal, 1.f, "scripted pedal", __LINE__);

    // A menu zeroes the throttle input before it reaches here.
    close(driving_intent(.2f, 0.f, false, 0.f).pedal, 0.f, "menu releases the pedal", __LINE__);

    if (!failures) std::printf("driving input: all checks passed\n");
    return failures ? 1 : 0;
}
