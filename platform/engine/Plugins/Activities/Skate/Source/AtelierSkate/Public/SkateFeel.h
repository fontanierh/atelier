#pragma once
#include "CoreMinimal.h"

/** The player's skating feel (README.md, "Feel"): everything that changes how the board rides, for a game's settings
 *  menu. Multipliers are on the active difficulty's authored values (1 is stock); a switch at -1 keeps the difficulty's
 *  own choice. USkateComponent::SetFeel applies it, live while riding. Defaults() starts from USkateSettings. */
struct ATELIERSKATE_API FSkateFeel
{
    // Already in USkateSettings (Defaults() reads them).
    FString Difficulty = TEXT("normal");        // easy, normal or hardcore: the base the multipliers scale
    float TruckTightness = .5f;                  // 0 loose .. 1 tight
    float Pop = 1.f;                             // ollie and nollie height (0.5..2)
    float Spin = 1.f;                            // body spin speed in the air (0.5..3)
    float PushSpeed = 1.f;                       // top pushing speed (0.5..2)
    float PushPower = 1.f;                       // speed gained per push (0.5..3)
    float VertAssist = 0.f;                      // airs back into quarter pipes short of vertical (0..1)

    // Flick-It.
    float FlickRadius = 1.f;                     // how far a flick may stray from a trick's shape (0.5..2)
    float FlickWindow = 1.f;                     // how long a flick may take (0.5..3)
    float FlickPace = 1.f;                       // flick speed needed for full pop; lower needs less (0.5..2)
    float StickDeadZone = .25f;                  // stick travel ignored, as a fraction (0.25..0.6)
    float StickReach = .95f;                     // stick travel that counts as full (0.6..1)
    float MouseFlick = 1.f;                      // the mouse's flick strength, beside the game's mouse sensitivity (0.25..4)

    // Air.
    float Gravity = 1.f;                         // below 1 floats, above 1 drops; jump heights stay (0.5..1.5)
    float Boneless = 1.f;                        // boneless height (0.5..3)
    float Hippy = 1.f;                           // hippy jump height (0.5..3)

    // Rails.
    float RailMagnetism = 1.f;                   // how far a jump is pulled onto a rail or ledge (0.25..3)
    float GrindPop = 1.f;                        // the pop off a grind (0.5..2)
    float GrindFriction = 1.f;                   // how fast a grind slows (0..3)

    // Rolling.
    float Braking = 1.f;                         // (0.25..3)
    float Steering = 1.f;                        // (0.5..2)
    float Carve = 1.f;                           // how hard a lean turns (0.5..2)
    float Grip = 1.f;                            // wheel grip in turns (0.5..2)
    float Powerslide = 1.f;                      // how hard a powerslide slows (0.25..3)
    float RollingFriction = 1.f;                 // rolling resistance (0..3)
    float HillSpeed = 1.f;                       // downhill pull (0..2)
    float Pump = 1.f;                            // speed from pumping transitions (0..3)

    // Balance.
    float Wobble = 1.f;                          // speed wobble size (0..3)
    float WobbleOnset = 1.f;                     // the speed it starts at (0.5..3)
    float ManualDrift = 1.f;                     // how much a manual drifts off balance (0..3)

    // Bails.
    float Landing = 1.f;                         // landing angles and speeds forgiven (0.5..3)
    float Impact = 1.f;                          // impacts survived (0.5..3)
    float GetUpDelay = 1.f;                      // time down after a bail (0.25..2)
    int8 AutoPush = -1;                          // -1 the difficulty's, 0 off, 1 on
    int8 AssistedAir = -1;                       // body spins and flips completed for you: -1 the difficulty's, 0, 1

    // Camera.
    float CameraDistance = 1.f;                  // (0.6..1.6)
    float CameraFOV = 0.f;                       // degrees added to the skate camera's (-20..20)

    /** USkateSettings' values and the stock feel. */
    static FSkateFeel Defaults();
    /** Every value within its range (Difficulty one of the three): false names the first that is not. */
    bool Validate(FString& Error) const;
    bool operator==(const FSkateFeel&) const = default;
};
