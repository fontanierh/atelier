#pragma once
#include "CoreMinimal.h"
#include "RideFlick.h"

/** Grind and slide kinds. */
enum class ERideGrind : uint8 { FiftyFifty, FiveO, Nosegrind, Crooked, Boardslide, Lipslide };

/** Grabs: Indy (back hand, toe side), Melon (front hand, heel side) and their variations. */
enum class ERideGrab : uint8 { None, Indy, Melon, ChristAir, OneFoot, TuckKnee };

/** What the rider's body is doing, for the clip choice (RideAnimator). */
enum class ERideMotion : uint8 { Roll, Push, Brake, Powerslide, Manual, NoseManual, Load, Pop, Air, Land, Grind, Bail, GetUp };

/** The rider's pose request for one frame, filled by the session. */
struct FRideBodyPose
{
    ERideMotion Motion = ERideMotion::Roll;
    float MotionTime = 0;               // s since the motion started
    atelier::ride::Flick Trick = atelier::ride::Flick::None;
    float TrickTime = -1;               // s since the pop, -1 for none
    ERideGrab Grab = ERideGrab::None;
    float GrabWeight = 0;
    ERideGrind Grind = ERideGrind::FiftyFifty;
    float Lean = 0;                     // -1..1, toward the toe side positive
    float Crouch = 0;                   // 0 standing .. 1 crouched
    float PushPhase = 0;                // 0..1 through the push cycle
    float Sketchy = 0;                  // 0 clean .. 1 sketchy, for the landing
    float SlideAngle = 0;               // degrees, powerslide
    bool bGoofy = false, bFakie = false;
};

/** The board relative to the rider's root, for one frame. */
struct FRideBoardPose
{
    FTransform Deck = FTransform::Identity;   // SKATEBOARD_ROOT in root space
    float WheelSpin = 0;                      // degrees
    float TruckLean = 0;                      // degrees, positive leans the deck toward +Y
};
