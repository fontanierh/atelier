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

/** Flick-It: reads the right stick and turns rim paths into tricks (README.md, "Flick-It").
 *  Sectors are numbered clockwise from up: 0 U, 1 UR, 2 R, 3 DR, 4 D, 5 DL, 6 L, 7 UL. U and D are 60 degrees wide,
 *  the others about 37, so a straight flick is an ollie and a diagonal has to be meant. */
struct FSkateFlick
{
    static constexpr float Rim = .70f, Centre = .30f, FlickWindow = .25f;
    /** 0..1 crouch from pulling the stick back (the load), for the pose; bNollieLoad when loading from the nose. */
    float Load = 0.f;
    bool bNollieLoad = false;
    /** Rim sectors of the current gesture, tail family (a nollie is turned upside down first). */
    TArray<int8> Path;
    /** Last recognised trick name and the raw path that made it, for the HUD/debug. */
    FString LastDebug;
    /** How hard this frame's input is flicking, 0..1, when the source knows better than the stick's travel (a mouse
     *  swipe's speed); -1 measures it from the stick's own speed. Set before each Update. */
    float Power = -1.f;

    void Reset() { Path.Reset(); bConsumed = false; LowHeld = 0.f; LastLow = -1.f; Family = 0; Load = 0.f; bNollieLoad = false; PeakQuick = 0.f; }

    /** The stick in the upper half at part deflection, without a load: the nose-manual band (and the manual for the
     *  lower half). Used by the component; the flick itself needs the rim. */
    static int32 ManualBand(FVector2D Stick)
    {
        const float Mag = Stick.Size();
        if (Mag < .28f || Mag > .78f || FMath::Abs(Stick.X) > .55f * Mag) return 0;
        return Stick.Y < 0.f ? 1 : -1;
    }

    /** Feed one frame. Returns a trick when a flick completes (one per gesture: the stick must come back to the centre
     *  before the next). bGoofy mirrors left and right so the names stay the same for either stance. */
    FSkateTrick Update(FVector2D Stick, float Dt, bool bGoofy)
    {
        // A hitch (a long frame) must not stretch a flick out of its window: count at most 34 ms per frame.
        Dt = FMath::Min(Dt, .034f);
        Clock += Dt;
        if (bGoofy) Stick.X = -Stick.X;
        // How fast the stick is travelling (a hard flick crosses the stick in a frame or two: 2 units in 30 ms is 60/s).
        const float Travel = (Stick - PrevStick).Size() / FMath::Max(Dt, 1e-3f);
        PrevStick = Stick;
        const float Quick = Power >= 0.f ? Power : FMath::Clamp((Travel - 8.f) / 40.f, 0.f, 1.f);
        const float Mag = Stick.Size();
        if (Mag < Centre)
        {
            // A fast flick passes through the middle: only a real return (80 ms) ends the gesture.
            FSkateTrick Out;
            if (!bConsumed && Family != 0 && Path.Num() >= 2 && IsSide(Path.Last()) && LowBefore(Path.Num() - 1) && Clock - LastLow <= FlickWindow + .1f)
                Out = Finish(Classify(Path, Family < 0), 1.f);   // a flick to the side released at once is still a shove-it
            CentreTime += Dt;
            if (CentreTime > .08f) Reset();
            Load = 0.f; bNollieLoad = false;
            return Out;
        }
        CentreTime = 0.f;
        const int8 Raw = SectorOf(Stick);
        if (Family == 0 && Mag >= Rim) { if (IsLow(Raw)) Family = 1; else if (IsHigh(Raw)) Family = -1; }
        const FVector2D S(Stick.X, Family < 0 ? -Stick.Y : Stick.Y);
        const int8 Sector = SectorOf(S);
        const bool bLow = S.Y < -.38f * Mag;
        // The flick's speed is what it does after leaving the load.
        PeakQuick = bLow ? 0.f : FMath::Max(PeakQuick, Quick);
        Load = Family != 0 && bLow ? FMath::SmoothStep(.3f, .9f, Mag) : 0.f;
        bNollieLoad = Family < 0 && Load > 0.f;
        if (bConsumed || Mag < Rim) return {};
        if (Path.IsEmpty() || Path.Last() != Sector) { Path.Add(Sector); SectorSince = Clock; }
        if (Family == 0) return {};   // a sweep that started at the side: wait for the load
        if (bLow) { LowHeld += Dt; LastLow = Clock; }
        if (LastLow < 0.f) return {};
        if (IsHigh(Sector) && Clock - LastLow <= FlickWindow) return Finish(Classify(Path, Family < 0), Mag);
        // A shove-it ends at the side; a sweep through the side toward the top keeps going, so it must rest there a moment.
        if (IsSide(Sector) && LowBefore(Path.Num() - 1) && Clock - SectorSince >= .06f && Clock - LastLow <= FlickWindow + .1f)
            return Finish(Classify(Path, Family < 0), Mag);
        return {};
    }

    /** Named by the rim path (tail family, regular stance); the final sector is the flick. */
    static FSkateTrick Classify(const TArray<int8>& P, bool bNollie)
    {
        FSkateTrick T;
        if (P.IsEmpty()) return T;
        const int8 Final = P.Last();
        const int32 D = P.IndexOfByKey(4), R = P.IndexOfByKey(2), L = P.IndexOfByKey(6);
        const bool bRBeforeD = R != INDEX_NONE && D != INDEX_NONE && R < D;
        const bool bLBeforeD = L != INDEX_NONE && D != INDEX_NONE && L < D;
        bool bDLAfter = false, bDRAfter = false, bLAfter = false, bRAfter = false;
        const int32 LastD = P.FindLastByPredicate([](int8 S) { return S == 4; });
        for (int32 I = LastD + 1; I < P.Num() - 1; ++I) { bDLAfter |= P[I] == 5; bDRAfter |= P[I] == 3; bLAfter |= P[I] == 6; bRAfter |= P[I] == 2; }
        const bool bLoadDR = P[0] == 3 && D == INDEX_NONE, bLoadDL = P[0] == 5 && D == INDEX_NONE;
        auto Set = [&](const TCHAR* Name, float Flips, float Shove, int32 Points) { T.Name = Name; T.Flips = Flips; T.Shove = Shove; T.Points = Points; };
        switch (Final)
        {
        case 0:
            if (bRBeforeD || bLAfter) Set(TEXT("360 Shove-it"), 0, 360, 250);
            else if (bLBeforeD || bRAfter) Set(TEXT("Frontside 360 Shove-it"), 0, -360, 250);
            else if (bDLAfter || bLoadDL) Set(TEXT("Hardflip"), 1, -180, 350);
            else if (bDRAfter || bLoadDR) Set(TEXT("Inward Heelflip"), -1, 180, 350);
            else Set(TEXT("Ollie"), 0, 0, 50);
            break;
        case 7:
            if (bRBeforeD) Set(TEXT("360 Flip"), 1, 360, 450);
            else if (bLoadDR || bLAfter) Set(TEXT("Varial Kickflip"), 1, 180, 250);
            else Set(TEXT("Kickflip"), 1, 0, 150);
            break;
        case 1:
            if (bLBeforeD) Set(TEXT("Laser Flip"), -1, -360, 450);
            else if (bLoadDL || bRAfter) Set(TEXT("Varial Heelflip"), -1, -180, 250);
            else Set(TEXT("Heelflip"), -1, 0, 150);
            break;
        case 6: Set(TEXT("Pop Shove-it"), 0, 180, 120); break;
        case 2: Set(TEXT("Frontside Pop Shove-it"), 0, -180, 120); break;
        default: break;
        }
        if (bNollie && T.IsValid()) { T.Name = T.Name == TEXT("Ollie") ? FName(TEXT("Nollie")) : FName(*(FString(TEXT("Nollie ")) + T.Name.ToString())); T.Points += 30; T.bNollie = true; }
        return T;
    }

    static int8 SectorOf(FVector2D S)
    {
        const float A = FMath::Fmod(FMath::RadiansToDegrees(FMath::Atan2(S.X, S.Y)) + 360.f, 360.f);
        if (A <= 30.f || A >= 330.f) return 0;
        if (FMath::Abs(A - 180.f) <= 30.f) return 4;
        if (A < 67.5f) return 1;
        if (A < 112.5f) return 2;
        if (A < 150.f) return 3;
        if (A < 247.5f) return 5;
        if (A < 292.5f) return 6;
        return 7;
    }
    static bool IsLow(int8 S) { return S == 3 || S == 4 || S == 5; }
    static bool IsHigh(int8 S) { return S == 7 || S == 0 || S == 1; }
    static bool IsSide(int8 S) { return S == 2 || S == 6; }

private:
    float Clock = 0.f, LowHeld = 0.f, LastLow = -1.f, SectorSince = 0.f, CentreTime = 0.f, PeakQuick = 0.f;
    FVector2D PrevStick = FVector2D::ZeroVector;
    int32 Family = 0;   // 1 tail (pulled back first), -1 nose (pushed forward first), 0 not yet known
    bool bConsumed = false;
    bool LowBefore(int32 End) const { for (int32 I = 0; I < End; ++I) if (IsLow(Path[I])) return true; return false; }
    FSkateTrick Finish(FSkateTrick Trick, float Mag)
    {
        bConsumed = true;
        LastDebug.Reset();
        for (int8 S : Path) LastDebug += FString::Printf(TEXT("%d "), S);
        if (!Trick.IsValid()) return Trick;
        LastDebug += Trick.Name.ToString();
        // Harder pops come mostly from flicking hard (the stick's speed, or the mouse swipe's), then from a longer load.
        const float Held = FMath::Clamp(LowHeld / .3f, 0.f, 1.f);
        Trick.Strength = FMath::Clamp(.2f + .3f * Held + .5f * PeakQuick, 0.f, 1.f) * FMath::Clamp(Mag, .85f, 1.f);
        return Trick;
    }
};
