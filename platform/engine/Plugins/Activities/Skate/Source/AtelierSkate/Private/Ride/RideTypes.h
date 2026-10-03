#pragma once
#include "CoreMinimal.h"
#include "RideFlick.h"

/** Grind and slide kinds. */
enum class ERideGrind : uint8 { FiftyFifty, FiveO, Nosegrind, Crooked, Boardslide, Lipslide };

/** Grabs: Indy (back hand, toe side), Melon (front hand, heel side) and their variations. */
enum class ERideGrab : uint8 { None, Indy, Melon, ChristAir, OneFoot, TuckKnee };

/** What the rider's body is doing, for the clip choice (RideAnimator). */
enum class ERideMotion : uint8 { Roll, Push, Brake, Powerslide, Manual, NoseManual, Load, Pop, Air, Land, Grind, Bail, GetUp };

/**
 * The rider's pose request for one frame, filled by the session from its state machine. Every time is in seconds
 * at the session's last tick; Lag says how far the drawn frame trails that tick (the pose is interpolated between
 * the last two ticks), so the clips can be sampled at the drawn time.
 */
struct FRideBodyPose
{
    ERideMotion Motion = ERideMotion::Roll;
    float MotionTime = 0;               // since this motion started
    ERideMotion PreviousMotion = ERideMotion::Roll;
    float Clock = 0;                    // since the ride started (idle loops)
    float Lag = 0;
    // The trick: popped on the ground (PopTime counts the pop clip's ground part), then flipped in the air from the
    // take-off (TrickTime).
    atelier::ride::Flick Trick = atelier::ride::Flick::None;
    float PopTime = -1, PopDelay = .2f;
    float TrickTime = -1;
    bool bTrickFakie = false;
    // Air.
    float AirTime = 0;
    float TimeToLand = -1;              // to the predicted touch-down, -1 when unknown
    ERideGrab Grab = ERideGrab::None;
    float GrabTime = 0, GrabWeight = 0;
    ERideGrab LastGrab = ERideGrab::None;
    float SinceGrab = -1;               // since the last grab was let go in this air, -1 for none
    // Ground.
    float Speed = 0;                    // cm/s along the board
    float Lean = 0;                     // -1..1, positive turning toward the rider's toes
    float Crouch = 0;                   // 0 standing .. 1 crouched
    float PushTime = -1;                // into the current push cycle, -1 when not pushing
    int32 PushCount = 0;                // pushes before this one in the current run of pushes
    float PushLead = 0, PushContact = 0, PushRecover = 0;   // the current cycle's phases
    float PushStrong = 0;               // 0 the slow push .. 1 the fast push (by speed)
    float StillTime = -1;               // braked to a stop this long ago, -1 while moving
    bool bWasStill = false;             // the previous motion ended standing still
    float LoadTime = 0;                 // the stick held on the rim before a flick
    bool bNoseLoad = false;
    float Balance = 0;                  // manual balance, -1..1
    float SlideAngle = 0;               // degrees, powerslide
    bool bSlideFront = true;            // powerslide turning the toes downhill (frontside)
    // Landing.
    float LandAge = -1;                 // since the last touch-down, -1 before the first
    float LandImpact = 0;               // cm/s into the ground at that touch-down
    bool bLandedFromGrab = false;
    float Sketchy = 0;                  // 0 clean .. 1 sketchy
    // Grind.
    ERideGrind Grind = ERideGrind::FiftyFifty;
    bool bGrindFront = true;            // the line on the rider's toe side
    // Bail.
    float BailTime = -1;                // since the bail started, -1 when not bailing
    bool bGoofy = false, bFakie = false;
};

/** The board relative to the rider's root (the deck's pivot at rest), for one frame. */
struct FRideBoardPose
{
    FTransform Deck = FTransform::Identity;   // SKATEBOARD_ROOT in root space
    float WheelSpin = 0;                      // degrees
    bool bOnWheels = false;                   // rolling (the ground, a manual, a powerslide): the hangers stay level
    float DeckHeight = 8.9f;                  // the deck's pivot above the ground at rest (cm)
};
