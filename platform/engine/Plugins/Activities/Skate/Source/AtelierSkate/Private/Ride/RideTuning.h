#pragma once
#include "CoreMinimal.h"

/**
 * Every number the Ride backend rides by, in Unreal units (cm, s, degrees). The defaults follow the measurements of
 * the native runtime listed in RIDE.md ("Numbers"); USkateSettings scales (pop, spin, push speed and power, vert
 * assist) apply on top in FRideSession. skate.RideTune "Name=Value Name=Value" overrides any of them live.
 */
struct FRideTuning
{
    // Board geometry (the native rig: deck 8.9 cm above the ground, axles at +-24.3 cm, wheels 3.1 cm).
    float DeckHeight = 8.9f;
    float AxleX = 24.3f;
    float WheelRadius = 3.1f;

    // Ground. Riding is nearly lossless up to about 8 m/s; above it rolling friction rises (RIDE.md).
    float RollingResistance = 5.f;    // cm/s^2 at any speed
    float GravityLimit = 700.f;       // largest slope acceleration, cm/s^2
    float StickGap = 4.5f;            // the board follows ground that falls away up to this far per step (cm) ...
    float StickPerSpeed = .18f;       // ... plus this fraction of the step's travel
    float StepUp = 6.f;               // ground rising more than this under a wheel in one step is a wall (cm)
    float WallSlope = .5f;            // a contact whose normal is within acos(this) of the deck is ground
    float LaunchFactor = 1.5f;        // a convex crest launches when v^2 * curvature exceeds this many g ...
    float CrestWindow = 50.f;         // ... the curvature measured over at least this much travel (cm) ...
    float CrestReach = 6.f;           // ... beyond the surface falling this far below the board's line over it (cm)
    float GroundStep = 15.f;          // the longest move between ground probes (cm; a tick moves in up to 8 steps)
    float CurbBail = 710.f;           // cm/s closing on a face too steep to roll onto, across the deck ...
    float CurbImpact = 6000.f;        // ... or along the deck's normal, that throws the rider
    float FallLineSteer = .6f;        // how much sideways gravity on a slope turns the board downhill

    // Pushing: one push per cycle, the force in the planted-foot window.
    float PushCycle = 1.f;            // s per push while push is held
    float PushContact = .42f;         // s from the push's start to the foot touching down
    float PushContactLength = .16f;   // s of foot contact
    float PushTarget = 450.f;         // speed a push aims for from rest (before PushSpeedScale)
    float PushTargetSlope = .82f;     // extra target per cm/s of current speed
    float PushTapTarget = 205.f;      // a tapped push (released before contact) adds about this much at rest
    float PushAccel = 3000.f;         // cm/s^2 during contact (before PushPowerScale)
    float PushTopSpeed = 850.f;       // pushing stops adding speed here (before PushSpeedScale)

    // Braking and powerslides.
    float BrakeDelay = .3f;           // s for the foot to reach the ground
    float BrakeDecel = 314.f;         // cm/s^2
    float SlideAngle = 85.f;          // the deck's angle to the travel at full slide (degrees)
    float SlideTurnRate = 220.f;      // how fast the deck turns into and out of a slide (degrees/s)
    float SlideDecel = 1.f;           // scale on the measured powerslide deceleration curve
    float SlideMinSpeed = 120.f;

    // Steering: full stick turns MaxYawRate at riding speed; the stick response is the native curve.
    float MaxYawRate = 60.f;          // degrees/s at full stick, at rest ...
    float YawRatePerSpeed = .045f;    // ... plus this per cm/s (68 at 2 m/s, 83 at 5, 100 at 9: the reference)
    float PivotRate = 90.f;           // degrees/s at rest (kick turns)
    float PivotSpeed = 120.f;         // below this speed steering blends into pivoting (cm/s)
    float SteerResponse = 7.f;        // 1/s
    float LeanAngle = 17.f;           // deck roll at full turn (degrees)

    // Pumping: extending in a concave transition gains speed, v *= exp(curvature * extension).
    float PumpExtension = 26.f;       // cm of centre-of-mass travel between compressed and extended
    float CrouchRate = 5.f;           // 1/s

    // Pop: the deck's rise grows with how long the stick was held down before the flick (the load), from
    // PopHeightQuick after a 4-tick load toward PopHeight, and with PopHeightScale^1.6 (the game's 1.15 gives the
    // reference's 0.64 m, 0.98 m after 10 ticks and 1.37 m after 40).
    float PopHeight = 109.6f;         // cm, a long load at PopHeightScale 1
    float PopHeightQuick = 51.2f;     // cm, a 4-tick load
    float PopLoadTime = .16f;         // s, the time constant of the load
    float NollieScale = .95f;
    float PopFromGrindScale = .8f;
    float PopDelay = .2f;             // s from the flick to the wheels leaving (the pop clip's ground part)
    float LateFlickWindow = .3f;      // s after leaving a lip in which a flick still pops

    // Air.
    float AirGravity = 1400.f;        // cm/s^2: the reference flies under stronger gravity than 9.81 (about 14-15)
    float SpinRate = 470.f;           // degrees/s at full stick off a lip (before AirSpinScale)
    float FlatSpinRate = 260.f;       // degrees/s at full stick off flat ground
    float SpinResponse = 7.f;         // 1/s
    float SpinCarry = .55f;           // fraction of the ground turn rate carried into the air
    float LevelLead = .15f;           // s before the predicted landing by which the deck matches the ground
    float VertSteepness = 50.f;       // lips steeper than this (degrees from level) send a straight air back in
    float VertReturn = 20.f;          // cm/s back into the ramp when vert assist applies
    float TransferPush = 160.f;       // cm/s over the coping when transferring
    float FlipTime = .34f;            // s for a flip's board rotation (360 flips and hardflips take a little longer)

    // Landing: deck tilt to the ground and deck angle to the travel (degrees).
    float CleanYaw = 12.f, SketchyYaw = 30.f;
    float BailTilt = 50.f;
    float SidewaysSafeSpeed = 950.f;  // below this a sideways landing turns the board instead of bailing
    float BailYawFast = 80.f;         // the allowed heading error at 20 m/s (the reference rides away up to 70)
    float BailImpact = 1350.f;        // cm/s into the ground

    // Walls.
    float WallBailSpeed = 800.f;      // cm/s into a wall
    float WallRestitution = .1f;

    // Grinds and slides.
    float GrindCapture = 30.f;        // horizontal distance from the rail (cm)
    float GrindAbove = 40.f, GrindBelow = 10.f;   // board bottom above / below the rail top
    float GrindAlign = 38.f;          // within this of the rail is a grind, beyond 90-this a slide (degrees)
    float GrindFriction = 97.f;       // cm/s^2
    float SlideFriction = 140.f;
    float GrindStall = 15.f;          // cm/s
    float GrindExitPop = 250.f;       // cm/s up when popping out
    float GrindRelock = .35f;         // s before the line just left can catch the board again
    float GrindMinAhead = 25.f;       // cm of line needed ahead of the travel to lock on
    float GrindCross = 65.f;          // the most the travel may cross the line to lock on (degrees)
    float GrindCorner = 45.f;         // a line turning less than this carries the grind on (degrees) ...
    float GrindJoin = 10.f;           // ... into a line that starts this close to where it ends (cm)
    float GrindLockSpeed = 400.f;     // the board closes onto the line at least this fast after locking (cm/s)

    // Manuals.
    float ManualInstability = .9f;    // 1/s, the balance's own drift
    float ManualControl = 2.2f;       // 1/s per unit of stick away from the band's centre
    float ManualWobble = .25f;        // random push on the balance, 1/s
    float ManualPitch = 20.f;         // degrees
    float ManualFriction = 30.f;      // extra cm/s^2

    // Bails.
    float BailSettle = 2.2f;          // s down before getting up
    float GetUpTime = 1.f;            // s blending from the fallen pose to the stance
    float BailSlideDecel = 700.f;     // cm/s^2, the rider sliding to a stop without a ragdoll

    // Getting on and off (RideTransition.cpp).
    float MountBlend = .35f;          // s, the pose's blend from on foot to the board
    float DismountBlend = .3f;        // s, the pose's blend from the board to on foot
    float MeshSettle = .25f;          // s, the body easing back onto the capsule after the capsule moved under it
    float BoardDissolveTime = .25f;   // s for the board to dissolve in or out
    float BoardHoldTime = 6.f;        // s a board stays in the hand after riding, unless the hands are needed
    float BoardLyingTime = 10.f;      // s a board lying in the world stays once out of reach
    float BoardReach = 150.f;         // cm within which a lying board can be picked up or stepped on
    float MomentumDecay = 250.f;      // cm/s^2: speed above a run carried off the board fades this fast with the stick held ...
    float MomentumBrake = 900.f;      // ... and this fast without it
    float ClipBlend = .2f;            // s, the pose's blend into and out of a mount or dismount clip
    float CarryBlend = .25f;          // s, the pose's blend into and out of the board-carry locomotion
    float RecoverBlend = .7f;         // s, a get-up on foot rising out of the fallen body's pose

    // Camera.
    float CameraDistance = 290.f;
    float CameraHeight = 120.f;
    float CameraLookHeight = 85.f;
    float CameraLookAhead = 50.f;
    float CameraFOV = 60.f;           // vertical degrees
    float CameraSpeedFOV = 8.f;       // extra degrees at CameraFOVSpeed
    float CameraFOVSpeed = 1200.f;
    float CameraTurnRate = 2.5f;      // 1/s, the heading's lag
    float CameraFollow = 8.f;         // 1/s horizontal, the position's lag
    float CameraFollowZ = 4.f;        // 1/s vertical

    /** The current tuning: these defaults with the live skate.RideTune overrides applied. */
    static const FRideTuning& Get();
    /** Apply "Name=Value" words; unknown names are logged. Returns false when a word does not parse. */
    bool Apply(const FString& Words);
};
