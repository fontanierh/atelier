#pragma once
#include "CoreMinimal.h"

/**
 * Ride's own numbers, in Unreal units (cm, s): the ride's start on the floor, the bail's get-up and the
 * transitions between foot and board. Riding itself is the simulation's session, tuned by its own data and USkateSettings.
 * skate.RideTune "Name=Value Name=Value" overrides any of them live.
 */
struct FRideTuning
{
    // The ride's start on the floor (USkateComponent::SettleRideStart) and the transitions' floor probes.
    float WheelRadius = 3.1f;         // cm, the simulation rig's wheels
    float StepUp = 6.f;               // ground rising more than this under the board is a wall (cm)
    float StartRecover = 40.f;        // a ride starting inside the floor finds its top up to this far above (cm)
    float WallSlope = .5f;            // a contact whose normal is within acos(this) of up is ground

    // Bails.
    float BailSettle = 2.2f;          // s down before getting up
    float GetUpBoardReach = 60.f;     // cm: a get-up steps onto a board lying this close, wheels down; farther, it dissolves
                                      // out where it lies and back in under the feet

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

    /** The current tuning: these defaults with the live skate.RideTune overrides applied. */
    static const FRideTuning& Get();
    /** Apply "Name=Value" words; unknown names are logged. Returns false when a word does not parse. */
    bool Apply(const FString& Words);
};
