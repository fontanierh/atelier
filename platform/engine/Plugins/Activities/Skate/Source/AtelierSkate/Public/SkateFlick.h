#pragma once
#include "CoreMinimal.h"

/** One frame of skate controls in skate. terms. Sticks: x to the right, y away from the player ("up"). */
struct FSkateInput
{
    FVector2D Left = FVector2D::ZeroVector, Right = FVector2D::ZeroVector;
    bool bPush = false, bBrake = false, bPowerslide = false, bGrabLeft = false, bGrabRight = false;
};

/** A board trick popped by a flick: flips about the long axis (+ = the kickflip way) and a shove about the up axis
 *  (+ = backside), in regular-stance terms; the skate component mirrors them for goofy. */
struct FSkateTrick
{
    FName Name;
    float Flips = 0.f, Shove = 0.f;
    int32 Points = 0;
    bool bNollie = false;
    float Strength = 0.f;   // 0..1: how hard the pop was (mostly the flick's speed, then the load time)
    bool IsValid() const { return !Name.IsNone(); }
    bool MovesBoard() const { return Flips != 0.f || Shove != 0.f; }
};

/** Load and manual-band input conditioning. Trick recognition lives in SkateNative::Gestures. */
struct FSkateFlick
{
    float Load = 0.f;
    bool bNollieLoad = false;
    FString LastDebug;
    /** Mouse swipe strength; -1 uses the native sampled-gesture strength. */
    float Power = -1.f;
    void Reset() { Load = 0.f; bNollieLoad = false; Family = 0; CentreTime = 0.f; }
    static int32 ManualBand(FVector2D Stick)
    {
        const float Mag = Stick.Size();
        if (Mag < .28f || Mag > .78f || FMath::Abs(Stick.X) > .55f * Mag) return 0;
        return Stick.Y < 0.f ? 1 : -1;
    }
    void UpdateLoad(FVector2D Stick, float Dt)
    {
        const float Mag = Stick.Size();
        if (Mag < .3f)
        {
            CentreTime += Dt;
            if (CentreTime > .08f) Reset();
            Load = 0.f; bNollieLoad = false;
            return;
        }
        CentreTime = 0.f;
        if (Family == 0 && FMath::Abs(Stick.Y) > .38f * Mag) Family = Stick.Y < 0 ? 1 : -1;
        const bool Low = Stick.Y * Family < -.38f * Mag;
        Load = Family != 0 && Low ? FMath::SmoothStep(.3f, .9f, Mag) : 0.f;
        bNollieLoad = Family < 0 && Load > 0.f;
    }
private:
    int32 Family = 0;
    float CentreTime = 0.f;
};
