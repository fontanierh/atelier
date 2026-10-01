#pragma once
#include "CoreMinimal.h"

/** One frame of skate controls in skate. terms. Sticks: x to the right, y away from the player ("up"). */
struct FSkateInput
{
    FVector2D Left = FVector2D::ZeroVector, Right = FVector2D::ZeroVector;
    bool bPush = false, bBrake = false, bPowerslide = false, bGrabLeft = false, bGrabRight = false;
    /** Leave a ramp over its coping (a transfer) rather than come back down into it. A grab never asks for one. */
    bool bTransfer = false;
};
