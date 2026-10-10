#pragma once
#include "CoreMinimal.h"

/** One frame of skate controls in skate. terms. Sticks: x to the right, y away from the player ("up"). */
struct FSkateInput
{
    FVector2D Left = FVector2D::ZeroVector, Right = FVector2D::ZeroVector;
    bool bPush = false, bBrake = false, bPowerslide = false, bGrabLeft = false, bGrabRight = false;
    /** The triggers, 0..1 in the pad's 255 steps (Q and E press fully), as the simulation reads them: on the ground
     *  the deeper of the two crouches the rider (a pump), in the air any press grabs (bGrabLeft, bGrabRight). */
    float TriggerLeft = 0, TriggerRight = 0;
    /** How far each trigger is pulled: its depth, or a full pull for a trigger button pressed without one (a keyboard's
     *  grab key, or a caller that sets only the buttons). */
    float LeftPull() const { return TriggerLeft > 0 ? TriggerLeft : bGrabLeft ? 1.f : 0.f; }
    float RightPull() const { return TriggerRight > 0 ? TriggerRight : bGrabRight ? 1.f : 0.f; }
    /** Leave a ramp over its coping (a transfer) rather than come back down into it. A grab never asks for one. */
    bool bTransfer = false;
    /** Throw yourself off the board (both stick clicks with both triggers, as in the simulation's chord). */
    bool bBail = false;
};
