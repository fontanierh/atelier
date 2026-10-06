#pragma once
// The canonical pad: the packet the host gives either skate backend each tick, Native's Xbox state (Native/Input.h).
// USkateComponent reads the player's controls (FSkateInput, plus the raw controller keys the legacy button adapter
// forwards) and packs them here, so both backends' sessions sample the same bytes. Plain C++, no engine types.
#include "Native/Input.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

/** What the host read this tick (USkateComponent::ReadHostPad). Outside any namespace, so the component's reflected
 *  header can declare it. */
struct FSkateHostPad
{
    // FSkateInput: the sticks as real positions (right stick y up), the push, brake, transfer, powerslide and grabs.
    double LeftX = 0, LeftY = 0, RightX = 0, RightY = 0;
    bool bPush = false, bBrake = false, bTransfer = false, bPowerslide = false, bGrabLeft = false, bGrabRight = false;
    /** Rolling on the ground (ESkateMode::Ground): a powerslide then holds the left stick on a rear diagonal. */
    bool bGround = false;
    // The player's controller, when it is what drives the ride (not scripted input, not blocked, the mouse not free):
    // the buttons the legacy adapter forwards and the analog triggers. Y, the d-pad, start and back are not.
    bool bController = false;
    bool bFaceLeft = false, bFaceBottom = false, bW = false, bUp = false;
    bool bLeftShoulder = false, bRightShoulder = false, bLeftThumb = false, bRightThumb = false, bQ = false, bE = false;
    float LeftTrigger = 0, RightTrigger = 0;
};

namespace atelier::skate_pad
{
    /** The engine's 0.25 per-axis dead zone undone (BaseInput.ini squeezes the stick): a real stick position. */
    inline float Unsqueeze(float A)
    {
        return std::fabs(A) > 1e-4f ? (A > 0.f ? 1.f : -1.f) * (.25f + .75f * std::fabs(A)) : 0.f;
    }

    /** A stick (real positions) remapped so DeadZone..Reach of its travel spans the native pad's live range, 0.25..0.95
     *  (Input.cpp's ConditionStick): less than DeadZone reads as centred, Reach and past it as full. Identity at
     *  0.25 and 0.95. */
    inline void Retravel(float& X, float& Y, float DeadZone, float Reach)
    {
        const float R = std::sqrt(X * X + Y * Y);
        if (R < 1e-4f) return;
        const float To = R <= DeadZone ? R * (.25f / DeadZone) : .25f + (std::fmin(R, Reach) - DeadZone) * (.7f / (Reach - DeadZone));
        const float Scale = (R >= Reach ? 1.f / R : To / R);
        X *= Scale; Y *= Scale;
    }

    /** The left stick (real position, x) that balances a nose or tail slide, and a blunt on a thin rail: Native's
     *  GrindTipslide. Native holds it only by that stick: TipStability pushes the deck toward the rail by lx x 37, signed
     *  by normal.(direction x offset), the direction the way the board travels, and with the stick centred nothing
     *  pulls it back, so the deck walks out of the tip window (0.243..0.458 m along the deck) in a few tenths of a
     *  second. This keeps the deck's centre `Centre` m across from the rail, the window's middle, by its distance and
     *  how fast it moves out. Strength (0..1) scales it. Native coordinates (metres, y up): Deck the deck's origin,
     *  Point the nearest rail point, Tangent the rail's direction either way, Velocity the board's. */
    inline double TipBalance(const std::array<double, 3>& Deck, const std::array<double, 3>& Point, const std::array<double, 3>& Tangent,
        const std::array<double, 3>& Velocity, double Strength, double Centre = .35)
    {
        const double Along = Tangent[0] * Velocity[0] + Tangent[2] * Velocity[2];
        const double Flat = std::sqrt(Tangent[0] * Tangent[0] + Tangent[2] * Tangent[2]);
        if (Flat < 1e-6 || std::fabs(Along) < 1e-6) return 0;
        const double DirX = (Along > 0 ? Tangent[0] : -Tangent[0]) / Flat, DirZ = (Along > 0 ? Tangent[2] : -Tangent[2]) / Flat;
        const double OffX = Deck[0] - Point[0], OffZ = Deck[2] - Point[2];
        // Across the rail (up x direction), and which way the deck's centre lies from it.
        const double Across = DirZ * OffX - DirX * OffZ, Out = Across > 0 ? 1. : -1.;
        const double Outward = (DirZ * Velocity[0] - DirX * Velocity[2]) * Out;
        const double Push = std::clamp(10. * (std::fabs(Across) - Centre) + 1.5 * Outward, -1., 1.);
        // TipStability's sign: up.(direction x offset), which is Across.
        const double Balance = Out * Push * std::clamp(Strength, 0., 1.);
        if (std::fabs(Balance) < .02) return 0;
        // The native pad's live range starts at 0.25 of the stick's travel (ConditionStick).
        return (Balance > 0 ? 1. : -1.) * (.25 + .7 * std::fmin(1., std::fabs(Balance)));
    }

    /** FMath::RoundToInt: the floor of the value plus a half, in the value's own width. */
    inline std::int32_t RoundToInt(float F) { return static_cast<std::int32_t>(std::floor(F + .5f)); }
    inline std::int64_t RoundToInt(double F) { return static_cast<std::int64_t>(std::floor(F + .5)); }

    // Native's Xbox buttons (the bits ConvertXbox reads) and the host's transfer bit, which GameplaySession takes off
    // before sampling.
    inline constexpr std::uint16_t ButtonLeftThumb = 0x0040, ButtonRightThumb = 0x0080, ButtonLeftShoulder = 0x0100,
        ButtonRightShoulder = 0x0200, ButtonTransfer = 0x0800, ButtonA = 0x1000, ButtonB = 0x2000, ButtonX = 0x4000;

    using HostPad = FSkateHostPad;

    /** The packet: push A, brake B, transfer on the host bit; X on its own bit (and no longer A unless A, W or Up is
     *  held too); shoulders and stick clicks; triggers from the grabs (full) or the pulls, or the controller's analog
     *  axes (Q and E full); the sticks quantised to 32767. */
    inline skate::XboxState Pack(const HostPad& In)
    {
        std::int32_t Buttons = (In.bPush ? ButtonA : 0) | (In.bBrake ? ButtonB : 0) | (In.bTransfer ? ButtonTransfer : 0);
        std::int32_t LeftTrigger = In.bGrabLeft ? 255 : std::clamp(RoundToInt(255 * In.LeftTrigger), 0, 255),
            RightTrigger = In.bGrabRight ? 255 : std::clamp(RoundToInt(255 * In.RightTrigger), 0, 255);
        if (In.bController)
        {
            if (In.bFaceLeft)
            {
                Buttons |= ButtonX;
                if (!In.bFaceBottom && !In.bW && !In.bUp) Buttons &= ~ButtonA;
            }
            if (In.bLeftShoulder) Buttons |= ButtonLeftShoulder;
            if (In.bRightShoulder) Buttons |= ButtonRightShoulder;
            if (In.bLeftThumb) Buttons |= ButtonLeftThumb;
            if (In.bRightThumb) Buttons |= ButtonRightThumb;
            LeftTrigger = In.bQ ? 255 : std::clamp(RoundToInt(255 * In.LeftTrigger), 0, 255);
            RightTrigger = In.bE ? 255 : std::clamp(RoundToInt(255 * In.RightTrigger), 0, 255);
        }
        const auto Stick = [](double X, double Y)
        {
            return std::array<std::int16_t, 2>{static_cast<std::int16_t>(RoundToInt(std::clamp(X, -1., 1.) * 32767)),
                static_cast<std::int16_t>(RoundToInt(std::clamp(Y, -1., 1.) * 32767))};
        };
        skate::XboxState Out;
        Out.buttons = static_cast<std::uint16_t>(Buttons);
        Out.triggers = {static_cast<std::uint8_t>(LeftTrigger), static_cast<std::uint8_t>(RightTrigger)};
        // The start query requires a rear diagonal, including a nonzero angle.
        const bool bSlide = In.bPowerslide && In.bGround;
        Out.left = bSlide ? Stick(In.LeftX < 0 ? -.6 : .6, -.8) : Stick(In.LeftX, In.LeftY);
        Out.right = Stick(In.RightX, In.RightY);
        return Out;
    }
}
