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
    float GravityLimit = 700.f;       // the speed model's largest slope acceleration, cm/s^2 (native's MaxGravityAcceleration)
    // Native's ground speed model (RideSpeedModel.h, RIDE.md "Speed"; its physics_speed_conservation): the board rolls
    // under full gravity and its speed is pulled each tick by SpeedGain of its difference from the target
    // (SpeedGainDown when it is faster), the difference and the target's lead held within SpeedBound (cm/s). With
    // SpeedPumpReset 1 a pump starts the target afresh, as Native's pump force does (0: only pushes, brakes and walls).
    // NativeSpeed 0 goes back to Ride's own rule (the slope's pull capped at GravityLimit, the friction on the board).
    float NativeSpeed = 1.f;
    float SpeedGain = .25f;
    float SpeedGainDown = .25f;
    float SpeedBound = 30.f;
    float SpeedPumpReset = 1.f;
    // A concave transition's load on the board (speed^2 x curvature) beyond LoadFree (cm/s^2) scrubs LoadFriction of
    // it: Native's physical board loses about 80 cm/s entering a quarter's transition, faster than its speed model
    // makes up, and little in a wide bowl's. Fitted to the reference's climbs, LoadFree was 1000; it is raised so a
    // timed pump through the pump bowl's floor keeps its gain over a coasting one (RIDE.md "Speed").
    float LoadFriction = .2f;
    float LoadFree = 2500.f;
    float StickGap = 4.5f;            // the board follows ground that falls away up to this far per step (cm) ...
    float StickPerSpeed = .18f;       // ... plus this fraction of the step's travel
    float StepUp = 6.f;               // ground rising more than this under a wheel in one step is a wall (cm)
    float StartRecover = 40.f;        // a ride starting inside the floor finds its top up to this far above (cm)
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
    float PushTarget = 433.f;         // speed a push aims for from rest (before PushSpeedScale)
    float PushTargetSlope = .82f;     // extra target per cm/s of current speed
    float PushTapTarget = 205.f;      // a tapped push (released before contact) adds about this much at rest
    // Native's push: a velocity change each tick of the foot's contact (cm/s, before PushPowerScale), PushDvStart from
    // rest easing to PushDvEnd at PushFastFrom (cm/s) and faster.
    float PushDvStart = 60.f;
    float PushDvEnd = 50.f;
    float PushFastFrom = 850.f;
    float PushTopSpeed = 850.f;       // pushing stops adding speed here (before PushSpeedScale)
    float PushFromRest = 30.f;        // slower than this a push goes nose-first, the board still through the wind-up (cm/s)

    // Braking and powerslides.
    float BrakeDelay = .3f;           // s for the foot to reach the ground
    float BrakeDecel = 314.f;         // cm/s^2
    float SlideAngle = 120.f;         // the deck's angle to the travel at full slide (degrees; native's slides turn 120)
    float SlideTurnRate = 220.f;      // how fast the deck turns into and out of a slide (degrees/s)
    float SlideDecel = 1.f;           // scale on the measured powerslide deceleration curve
    float SlideMinSpeed = 120.f;

    // Steering: full stick turns MaxYawRate at riding speed; the stick response is the native curve.
    float MaxYawRate = 60.f;          // degrees/s at full stick, at rest ...
    float YawRatePerSpeed = .045f;    // ... plus this per cm/s (68 at 2 m/s, 83 at 5, 100 at 9: the reference)
    float PivotRate = 90.f;           // degrees/s at rest (kick turns)
    float PivotSpeed = 120.f;         // below this speed steering blends into pivoting (cm/s)
    float SteerResponse = 7.f;        // 1/s

    // Pumping (native's own UpdateGroundPumping, RIDE.md "Pumping"): the triggers crouch the rider, the ground's angle at
    // least MinCrouchVsGroundAngle; standing up through a concave transition gains speed, by native's settings.
    float PumpDepth = 37.5f;          // cm the centre of mass drops from standing to the full crouch
    float CoastPump = 1.f;            // scale on native's UnintentionalPumpScalar (.7): the pump with no trigger held
    float CrouchRate = 5.f;           // 1/s

    // Pop: the deck's rise grows with how long the stick was held down before the flick (the load), from
    // PopHeightQuick after a 4-tick load toward PopHeight, and with PopHeightScale^1.6. Fitted to the reference's flat
    // ollies (109.6 and 51.2 cm: at the game's 1.15, 0.64 m, 0.98 m after 10 ticks and 1.37 m after 40), then raised
    // 10%: at the fit, Ride's airs in native's film shots rose 10 to 20% less than native's (road_tech, road_flips,
    // road_sketchy).
    float PopHeight = 120.6f;         // cm, a long load at PopHeightScale 1
    float PopHeightQuick = 56.3f;     // cm, a 4-tick load
    float PopLoadTime = .16f;         // s, the time constant of the load
    float NollieScale = .95f;
    float PopFromGrindScale = .8f;
    float PopDelay = .2f;             // s from the flick to the wheels leaving (the pop clip's ground part)
    float LateFlickWindow = .3f;      // s after leaving a lip in which a flick still pops

    // Air.
    float AirGravity = 1400.f;        // cm/s^2: the reference flies under stronger gravity than 9.81 (about 14-15)
    float SpinCarry = .55f;           // fraction of the ground turn rate carried into the air, up to SpinCarryMax
    float SpinCarryMax = 115.f;       // degrees/s
    float LevelLead = .15f;           // s before the predicted landing by which the deck matches the ground
    float VertSteepness = 50.f;       // lips steeper than this (degrees from level, at VertAssist 1) send a straight air back in
    float VertClimb = .66f;           // and only a take-off this steep: up over (up and into the face), as native
    float VertLean = 3.f;             // degrees from vertical, into the ramp, that a lip air's climb is turned to
                                      // (with VertNative 0)
    float VertNative = 0.f;           // 0: a lip air leaves by VertClimb and VertLean; 1: by native's departure and launch
                                      // adjustment (its 1.15 degree lean, its climb test)
    float VertGravity = 1000.f;       // cm/s^2 in a lip air (the reference's board: 9.3 to 10.8 m/s^2 on vert airs)
    float TransferPush = 160.f;       // cm/s over the coping when transferring
    float FlipTime = .34f;            // s for a flip's board rotation (360 flips and hardflips take a little longer)

    // Landing: deck tilt to the ground and deck angle to the travel (degrees).
    float CleanYaw = 12.f, SketchyYaw = 30.f;
    float BailTilt = 50.f;
    // Native's bad landing (WipeoutBadLanding, normal mode): the heading's angle to the travel past max_landing_angle
    // at the speed along the face (RideSession's LandingAngleCurve: 92 degrees up to 9.3 m/s, 45 at 17, 15 from
    // 27.8 m/s), the speed into the face past BailImpact or into a line past BailGrindImpact; all three limits scaled by
    // BailScale (bad_landing_scale: 1, easy 1.5). BailImpact stays above native's 11.2 m/s until Ride's airs come down
    // where native's do: the reference's second transition window meets the bank at 3 m/s into it, Ride's path the
    // flat beside it at 12.4.
    float BailScale = 1.f;
    float BailImpact = 1350.f;        // cm/s into the ground (native's max_landing_speed is 1120)
    float BailGrindImpact = 800.f;    // cm/s into a line (max_grind_speed)
    // Native's DangerZone (CheckWipeoutAir): while the grab clip playing carries DANGERZONE (a Christ air's or a
    // one-foot grab's into and cycle, the Christ air's out whole, the one-foot out's first .29 s), a board contact in
    // the air after its first BailDangerFrames ticks wipes out when it closes faster than BailDangerAcross across the
    // deck's up or BailDangerAlong along it (xz_trick, y_trick).
    float BailDangerFrames = 4.f;     // ticks (ignore_danger_frames)
    float BailDangerAcross = 10.f;    // cm/s (xz_trick)
    float BailDangerAlong = 60.f;     // cm/s (y_trick)

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
    float GrindStallHop = 110.f;      // cm/s up when a stalled grind steps off the line (a 4 cm hop)
    float GrindExitPop = 250.f;       // cm/s up when popping out
    float GrindRelock = .35f;         // s before the line just left can catch the board again
    float GrindMinAhead = 25.f;       // cm of line needed ahead of the travel to lock on
    float GrindCross = 65.f;          // the most the travel may cross the line to lock on (degrees)
    float GrindCorner = 45.f;         // a line turning less than this carries the grind on (degrees) ...
    float GrindJoin = 10.f;           // ... into a line that starts this close to where it ends (cm)
    float GrindLockSpeed = 400.f;     // the board closes onto the line at least this fast after locking (cm/s)

    // Manuals: Ride's one-axis deck under Native's controller (RideManual.h, ManualDeck), shown without the rig.
    float ManualDeckGain = .8f;       // share of the controller's displacement that turns the deck about the axle
    float ManualDeckDamping = 50.f;   // 1/s
    float ManualDeckWeight = 120.f;   // rad/s^2 pulling the raised end down

    // Bails.
    float BailSettle = 2.2f;          // s down before getting up
    float GetUpTime = 1.f;            // s blending from the fallen pose to the stance
    float GetUpBoardReach = 60.f;     // cm: a get-up steps onto a board lying this close, wheels down; farther, it dissolves
                                      // out where it lies and back in under the feet
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

    // Turning round on the board (native's B_SWITCH, RideSession): from fakie into switch, or back.
    float SwitchMinSpeed = 100.f;     // cm/s rolling fakie before the rider turns round by himself (a push: PushFromRest)
    float FakieSwitchTime = .6f;      // s rolling fakie on flat ground before the rider turns round by himself
    float SwitchPushRate = 1.25f;     // the clip's rate when a push from fakie turns round first ...
    float SwitchPushLead = .25f;      // ... the push starting this long before the clip's end

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
