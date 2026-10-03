#pragma once
#include "CoreMinimal.h"

class UPrimitiveComponent;

/** Where the board is (RIDE.md, "Transitions"). */
enum class ERideBoard : uint8
{
    Away,       // dissolved: nothing shows
    Ride,       // under the rider, placed by the session
    Hand,       // carried on foot
    World       // lying where it was left
};

/**
 * USkateComponent's state between riding and on foot with the Ride backend (RideTransition.cpp): the board's place
 * and dissolve, the mesh's offset from its on-foot place, and the speed carried off the board.
 */
struct FRideTransition
{
    ERideBoard Board = ERideBoard::Away;
    /** The board's dissolve: 1 whole, 0 gone. Shown moves toward ShownTarget over BoardDissolveTime. */
    float Shown = 0.f, ShownTarget = 0.f;
    bool bFadeMaterial = false;         // the board's parts wear the dissolve material
    float BoardTime = 0.f;              // a lying board: how long the rider has been out of reach
    /** The mesh's offset from its on-foot place, in the actor's frame. A switch moves the capsule under the body;
     *  the offset keeps the body's world place, is kept while riding (the pose is anchored on the board) and eases
     *  away on foot over MeshSettle from MeshOffsetStart. */
    FVector MeshOffset = FVector::ZeroVector, MeshOffsetStart = FVector::ZeroVector;
    float MeshSettleTime = -1.f;        // -1: not easing
    /** Speed above the character's own carried off the board: an additive root motion source ("SkateMomentum")
     *  whose velocity fades at MomentumDecay, faster without the stick. */
    float Momentum = 0.f;
    FVector MomentumDirection = FVector::ZeroVector;
    uint16 MomentumId = 0;
    /** A board lying in the world as a body of its own (taken from the physical rider after a bail). */
    TWeakObjectPtr<UPrimitiveComponent> LooseBoard;
    /** The skate button was pressed during a bail: once the rider is up, step off on foot. */
    bool bGetUpOnFoot = false;
};
