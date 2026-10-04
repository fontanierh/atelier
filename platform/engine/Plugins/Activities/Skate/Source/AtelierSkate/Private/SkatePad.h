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
    /** The project's 0.25 per-axis dead zone undone (DefaultInput.ini squeezes the stick): a real stick position. */
    inline float Unsqueeze(float A)
    {
        return std::fabs(A) > 1e-4f ? (A > 0.f ? 1.f : -1.f) * (.25f + .75f * std::fabs(A)) : 0.f;
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
