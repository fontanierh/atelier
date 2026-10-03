#pragma once
#include "CoreMinimal.h"

class UPrimitiveComponent;
class UAnimSequence;
class UProjectileMovementComponent;

/** Where the board is (RIDE.md, "Transitions"). */
enum class ERideBoard : uint8
{
    Away,       // dissolved: nothing shows
    Ride,       // under the rider, placed by the session
    Hand,       // carried on foot (placed by the off-board pose, or held at the hand in the character's own pose)
    World       // lying where it was left
};

/** What the body does off the board (RIDE.md, "Transitions"). */
enum class ERideFoot : uint8
{
    Off,        // the character's own animation
    Carry,      // the board in hand: the board-carry locomotion (BR_*_CYC) on the character's own movement
    Mount,      // a mount clip (BR_*_INTO_MOUNT) carries the character onto the board
    Dismount,   // a dismount clip (BR_DISMOUNT_*) carries the character off it, into the carry
    Air,        // in the air with the board in hand: a jump (JBR_*) or an air dismount (BR_DISMOUNT_*_INTO_BR_AIR)
    Land,       // a landing with the board in hand (BR_LAND_*), into the carry
    AirMount,   // the board thrown under the feet in the air (BR_*F_AIR_INTO_MOUNT_BSGRAB, a caveman)
    RunOut,     // a low-energy bail run out on foot (RUNOUT_*), the board rolling on alone
    Recover     // a fallen body getting up on foot where it lies (W_RECOVERY_*)
};

/**
 * USkateComponent's state between riding and on foot with the Ride backend (RideTransition.cpp): the board's place
 * and dissolve, the mesh's offset from its on-foot place, the speed carried off the board, and the clips that play
 * off the board (carry, mount, dismount).
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
    /** The mesh's turn from its on-foot rotation, in the actor's frame: a switch that turns the actor (upright on foot,
     *  tilted with the board) keeps the body's world rotation as well, and the turn eases away with the offset. */
    FQuat MeshTurn = FQuat::Identity, MeshTurnStart = FQuat::Identity;
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

    // Off the board.
    ERideFoot Foot = ERideFoot::Off;
    /** A mount or dismount clip (kept loaded by the session's animator): the time shown, its rate (clip seconds per
     *  second), length and stance mirror. Its root motion moves the capsule through a root motion source ("SkateDrive"),
     *  scaled from ScaleStart to ScaleEnd so the speed carries on from what the character had. */
    UAnimSequence* Clip = nullptr;
    float ClipTime = 0.f, ClipRate = 1.f, ClipLength = 0.f;
    float ScaleStart = 1.f, ScaleEnd = 1.f;
    /** Or, when SpeedStart >= 0, the capsule moves along the clip's travel at a speed going from SpeedStart to SpeedEnd
     *  (cm/s): the speed the character came in with carries through the clip. */
    float SpeedStart = -1.f, SpeedEnd = -1.f;
    bool bMirror = false, bClipStarted = false;
    /** The pose mesh's own cross-fade into the clip (0: a cut, the character's pose blend hides the switch). */
    float ClipBlendIn = 0.f;
    /** Mount: the clip time the board reaches the ground. Dismount: the time it leaves the ground. */
    float BoardContact = 0.f;
    /** The clips' trajectory in the world: on the capsule's floor, facing TrajYaw, displaced by TrajOffset (a dismount
     *  puts the clip's board on the deck it left) easing away over OffsetTime. */
    float TrajYaw = 0.f;
    FVector TrajOffset = FVector::ZeroVector;
    float OffsetTime = .35f;
    /** A mount ends with the capsule over the deck the ride starts on: the trajectory moves by TrajEnd from the
     *  capsule's floor over TrajEndTime, and on the ground the capsule moves on by as much (the body's path is the
     *  clip's). */
    FVector TrajEnd = FVector::ZeroVector;
    float TrajEndTime = 0.f;
    /** TrajEnd is worked out from the clip's own tracks; the posed board can sit off them (DeckDrift: where the pose
     *  has the deck less where the tracks do, last frame), and the trajectory takes that in too by TrajEndTime. */
    FVector DeckDrift = FVector::ZeroVector;
    /** A step onto a lying board: the first frame shown moves the trajectory so the posed board is on the lying one. */
    bool bMatchDeck = false;
    /** A clip whose trajectory turns (a run-out): TrajYaw turns as the clip's trajectory does (its yaw last frame). */
    bool bFollowYaw = false;
    float ClipYawLast = 0.f;
    /** A step onto a lying board: the trajectory is held in the world (Anchor, moved on by the clip's travel) so the
     *  clip's board stays on the lying one, and the capsule follows it. */
    bool bAnchored = false;
    FVector Anchor = FVector::ZeroVector;
    /** The body standing on the deck (1) or on the ground (0): RetargetRetailPose's OffBoardLift. */
    float Lift = 0.f;
    uint16 DriveId = 0;
    FVector DriveVelocity = FVector::ZeroVector;
    /** After the dismount: the carry starts at this phase of the run cycle (the clip's CADENCEENDPERCENT). */
    float EndPhase = 0.f;
    /** On the ground a clip's root motion moves the capsule (bDrive); in the air CharacterMovement keeps the fall and
     *  the clip's trajectory follows the capsule (its own arc is left out). */
    bool bDrive = true;
    /** In the air: the clip to chain when this one ends airborne (else its last frame is held until the landing), the
     *  landing clips' stride phase (0, 25 or 75), and where and when the character left the ground. */
    UAnimSequence* AirNext = nullptr;
    int32 LandPhase = 0;
    float AirStartZ = 0.f, AirTime = 0.f, FallSpeed = 0.f;
    /** The trajectory's offset from the capsule's floor last frame (a clip that follows another starts from it), and
     *  a clip started from the character's own pose puts its pelvis where the character's was. */
    FVector AppliedOffset = FVector::ZeroVector;
    bool bMatchPelvis = false;
    /** The clip ends standing: moving the stick after 40% of it runs off into the carry. */
    bool bEndsStanding = false;

    // Carrying: the board-carry cycles (stand, walk, run, sprint), their lengths and their stride (cm per cycle).
    UAnimSequence* Cycle[4] = {};
    float CycleLength[4] = {}, CycleStride[4] = {}, CycleSpeed[4] = {};
    bool bClipsTried = false, bClips = false;
    float Phase = 0.f, StandTime = 0.f, HoldTime = 0.f;
    /** The carry pose is shown (on the ground); in the air the character's own pose shows with the board in hand. */
    bool bCarryShown = false;
    /** The board is attached to this hand bone (the character's own pose holds it there). */
    FName HandBone;
    /** The character's own stride, for the mount clip's phase: the feet's distance apart along the facing, its rate,
     *  and the time between the feet passing each other. */
    float FootDiff = 0.f, FootRate = 0.f, HalfPeriod = .3f, SinceCross = 0.f;
    bool bFeetKnown = false;
    /** A lying board dissolving away to come back in the hand (the board button). */
    bool bRecall = false;

    // Bails left on foot.
    /** The physical rider handed over a run-out (OnBailStart): it starts after the ride's frame (TickTransition). */
    bool bRunOutPending = false;
    UAnimSequence* PendingClip = nullptr;
    /** A settled body gets up on foot: where it lies, the way it faces (head from hips) and how it lies. */
    bool bRecoverPending = false, bRecoverFaceUp = false;
    FVector RecoverGround = FVector::ZeroVector;
    float RecoverYaw = 0.f;
    /** A get-up's first frame held while the physical rider hands its bodies over to the animation (s). */
    float WaitTime = 0.f;
    /** A board kicked away (a kick-out) flies as a small sphere moved by a projectile movement (LooseBoard), turning
     *  with the spin it was kicked with; once it stops, or a run-out leaves it, it settles flat onto the ground
     *  (SettleFrom to SettleTo, SettleTime from 0). */
    TWeakObjectPtr<UProjectileMovementComponent> Flight;
    FVector FlightSpin = FVector::ZeroVector;
    FQuat FlightRotation = FQuat::Identity;
    float FlightTime = 0.f, SettleTime = -1.f;
    FTransform SettleFrom = FTransform::Identity, SettleTo = FTransform::Identity;
    /** The kick-out and run-out clips have the board until they end: its velocity and spin, measured from the frames
     *  shown, launch it (LaunchBoard). */
    bool bKickOut = false, bDeckKnown = false;
    FTransform LastDeck = FTransform::Identity;
    FVector KickVelocity = FVector::ZeroVector;

    // skate.RideTrace (TraceTransition): the frames still to log, what the last frame showed (a switch is a change of
    // it), and that frame's line, logged when a switch starts a trace.
    int32 TraceLeft = 0;
    uint32 TraceSerial = 0;
    uint8 TraceMode = 0, TraceFoot = 0;
    bool bTracePose = false;
    const UAnimSequence* TraceClip = nullptr;
    FString TraceLast;
    /** The ride's clips are loaded on foot ahead of the first mount (TickTransition), retried after this long (s). */
    float ClipsRetry = 0.f;
};
