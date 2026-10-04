#pragma once
#include "CoreMinimal.h"
#include "SkateInput.h"
#include "RideFlick.h"
#include "RideTuning.h"
#include "RideTypes.h"
#include "RideAnimator.h"
#include "Engine/EngineTypes.h"
#include "CollisionQueryParams.h"
#include "Templates/PimplPtr.h"

class UWorld;
class AActor;
class USkateRailSubsystem;
struct FHitResult;
struct FRideNativeState;

/** What the session queries: collision that blocks pawns, the rider (ignored), and the grind lines. */
struct FRideWorld
{
    UWorld* World = nullptr;
    const AActor* Ignore = nullptr;
    const USkateRailSubsystem* Rails = nullptr;
    /** The rider: the pose mesh that plays the clips goes on it. */
    AActor* Owner = nullptr;
    /** The board's scale (USkateComponent::BoardScale): the deck shown and its collision box grow with it. */
    float BoardScale = 1.f;
};

/** One-shot sounds the session asks for; the component plays them. */
enum class ERideCue : uint8 { Push, Flick, Catch, Fall };

enum class ERideState : uint8 { Ground, Powerslide, Manual, Air, Grind, Bail, GetUp };

/** The rider's settings that USkateSettings supplies (scales on the tuning). */
struct FRidePreferences
{
    float Pop = 1, Spin = 1, PushSpeed = 1, PushPower = 1, VertAssist = 1;
};

/**
 * The Ride backend (RIDE.md): a rigid board on Unreal collision queries at a fixed 60 Hz, the rider pose from
 * clips, Flick-It tricks, grinds, manuals, scoring and a follow camera. It runs on the game thread inside PhysSkate
 * and publishes what USkateComponent consumes from either backend: a root, root-space bones on the native rig's
 * names, velocity, a state name, the trick line, score, manual balance and a camera.
 */
class FRideSession
{
public:
    FRideSession();
    /** Load the rig and clips (blocking on first use). */
    void Preload() { Animator.Preload(); }
    /** Get on at a ground point, facing the board's rotation, moving at Velocity. A transition clip the caller is
     *  playing through the animator (GetAnimator().SetOverride) keeps playing until the caller clears it. */
    void Activate(const FRideWorld& World, const FVector& GroundPoint, const FQuat& Rotation, const FVector& Velocity, bool bGoofy, const FRidePreferences& Preferences);
    void Configure(bool bGoofy, const FRidePreferences& Preferences);
    void Launch(const FVector& Velocity);
    /** Add host time and run whole 60 Hz ticks; then publish the interpolated pose and the camera. Pad is the canonical
     *  pad (SkatePad.h), the packet the Native backend would get for Input, which Flick-It samples. */
    void Step(float Dt, const FSkateInput& Input, const atelier::skate::XboxState& Pad, const FRideWorld& World);
    /** The rider was thrown and has come to rest (the component's ragdoll, or the session's own slide): stand the
     *  board up at this ground point facing Yaw and blend the rider back over GetUpTime. */
    void GetUp(const FVector& GroundPoint, float Yaw);
    /** Whether the component handles the fall with a ragdoll; otherwise the session slides the rider to a stop. */
    void SetRagdoll(bool bAvailable) { bRagdoll = bAvailable; }
    /** During a ragdoll bail: the ground point under the body, which the root and the camera follow. */
    void FollowBody(const FVector& GroundPoint) { BodyPoint = GroundPoint; bFollowBody = true; }
    /** A ground point the rider can get up at: GroundPoint if the root reaches it (Reaches), else where the root is. A
     *  body that went through a floor or a wall gets up on this side of it. */
    FVector ReachableGround(const FVector& GroundPoint) const { return Reaches(GroundPoint) ? GroundPoint : P; }
    /** Off the board (a dismount, a carry, a run-out): no board physics; the animator's override layers alone, their
     *  TRAJECTORY at TrajectoryWorld (the clips' root space), published like Step (Root, Names, Reference, Bones; the
     *  board bones are the clip's). */
    void StepOffBoard(float Dt, const FTransform& TrajectoryWorld);
    /** The rider's animation: clips, overrides, curves, the evaluated pose. It lives as long as the session. */
    FRideAnimator& GetAnimator() { return Animator; }
    const FRideAnimator& GetAnimator() const { return Animator; }
    /** What the body is doing this frame (the motion and its phase, the trick, the landing's impact, the grind or
     *  manual, the bail): the clip choice's input, also read by the physical rider. */
    const FRideBodyPose& GetBody() const { return BodyPose; }

    // Published each Step. The root is the deck's pivot at rest (DeckHeight above the ground under the board), as the
    // native runtime publishes it.
    FTransform Root = FTransform::Identity;
    TArray<FName> Names;
    TArray<FTransform> Reference, Bones;
    FVector Velocity = FVector::ZeroVector;
    FString State = TEXT("PhysicsGround"), Trick;
    float Score = 0, ManualBalance = 0;
    FTransform Camera = FTransform::Identity;
    float CameraFOV = 0;
    uint64 Ticks = 0;
    TArray<ERideCue> Cues;

    ERideState GetMode() const { return Mode; }
    bool IsBailing() const { return Mode == ERideState::Bail; }
    float GetUpAlpha() const { return Mode == ERideState::GetUp ? FMath::Clamp(ModeTime / FMath::Max(.05f, Tune.GetUpTime), 0.f, 1.f) : 1.f; }
    bool IsNoseManual() const { return Mode == ERideState::Manual && bNoseManual; }
    /** Rolling backward in the rider's frame: toward the board's tail, or toward its nose riding switch. */
    bool IsFakie() const { return RiderTravel() < 0; }
    /** Riding switch: the rider turned round on the board, the other foot forward (the board did not turn). */
    bool IsSwitch() const { return bSwitch; }
    float GetSlideAngle() const { return Mode == ERideState::Powerslide ? FMath::Abs(SlideYaw) : 0.f; }
    bool IsSliding() const { return Mode == ERideState::Grind && (GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide); }
    float BailTime() const { return Mode == ERideState::Bail ? ModeTime : 0.f; }
    /** The board's world velocity and spin when the rider was thrown, for the ragdoll and the loose board. */
    FVector GetBailVelocity() const { return BailLinear; }
    FVector GetBailSpin() const { return BailAngular; }
    bool HasRig() const { return Animator.HasRig(); }
    /** The air's spin so far, degrees about the board's up axis (with the left stick positive), for QA; 0 once landed. */
    float GetAirSpin() const { return SpinTotal; }
    /** Mean simulation cost per tick and the worst single tick over the last second (ms), and the world queries
     *  a tick made (their mean and the most). */
    float CostMean = 0, CostWorst = 0, QueriesMean = 0;
    int32 QueriesWorst = 0;
    /** The last air's start (ChooseLanding): its world queries (a lip air's candidate sweeps) and cost (ms). */
    int32 SelectQueries = 0;
    float SelectCost = 0;
    /** The published pose's health for QA: the main clip, the board's hold and lift, the fastest body bone (cm/s,
     *  root space), each foot's height above the deck's pivot and how many feet are off the deck, NaN bones, and the
     *  animator's cost (ms). */
    FString DescribePose() const;
    /** The last recognised trick (RideFlick.h's pop request), appended to DescribePose as gesture=... */
    FString DescribeFlick() const;

    /** A box swept from one pose to another, its rotation in steps that move no corner more than CornerStep (a nose
     *  turning into a wall is caught where the centre barely moves). Hit.Time is the fraction of the whole move;
     *  Reached (if given) the box's pose at the hit: touching the face, or the pose found inside something when the
     *  hit starts there (bStartPenetrating; the pose at Hit.Time before it is the last one found free). Counted in
     *  QueriesMean during a tick. Shared with the loose board (RideTransition.cpp, RidePhysicalRider.cpp). */
    static bool SweepBox(const UWorld& World, const FTransform& From, const FTransform& To, const FVector& Extent, ECollisionChannel Channel,
        const FCollisionQueryParams& Params, const FCollisionResponseParams& Response, FHitResult& Hit, FTransform* Reached = nullptr);

private:
    struct FFrame { FVector P = FVector::ZeroVector; FQuat Q = FQuat::Identity; FTransform Deck = FTransform::Identity; };
    struct FLineTrick { FString Name; float Points = 0; };

    FRideTuning Tune;
    FRidePreferences Prefs;
    FRideAnimator Animator;
    atelier::ride::FlickReader Flicks;
    FRideWorld Where;
    bool bGoofy = false, bRagdoll = true;
    // Riding switch: the rider turned round on the board, the other foot forward. The board did not turn: Q and
    // Travel stay the board's, and switch is the rider's alone: the stance in effect (GoofyNow), his travel
    // (RiderTravel) and his frame on the board (RiderQ), which the animator places the clips in.
    bool bSwitch = false;
    uint32 Turns = 0;
    // A turn round in progress (SwitchTime >= 0): the stance flips at FlipAt, then a push starts if one was asked.
    float SwitchTime = -1, FlipAt = 0, SwitchRate = 1;
    bool bSwitchPush = false;
    float FakieTime = 0;            // rolling fakie on flat ground this long
    bool GoofyNow() const { return bGoofy != bSwitch; }
    float RiderTravel() const { return bSwitch ? -Travel : Travel; }
    FQuat RiderQ() const { return bSwitch ? Q * FQuat(FVector::UpVector, PI) : Q; }   // half a turn about the deck normal
    float Accumulator = 0;

    // The ride frame: P is the ground point under the deck's centre; Q has X along the board's nose and Z along the
    // deck normal. In a powerslide the deck turns from Q by SlideYaw while Q keeps the travel.
    ERideState Mode = ERideState::Ground;
    float ModeTime = 0;
    FVector P = FVector::ZeroVector, V = FVector::ZeroVector;
    FQuat Q = FQuat::Identity;
    float Travel = 1;               // +1 rolling nose first, -1 fakie
    float TurnRate = 0;             // degrees/s about the deck normal
    float SlideYaw = 0;
    // The left stick's powerslide: whether the stick was in the start sector last step, and the slide it started
    // (+1 right, -1 left, 0 none).
    bool bStickSector = false;
    int8 StickSlide = 0;
    float Curvature = 0;           // 1/cm along the travel, positive in a concave transition
    // The ground's normal over the last stretch of travel (cm travelled, oldest first), for the curvature.
    static constexpr int32 TrailMax = 8;
    float Odometer = 0, TrailAt[TrailMax] = {};
    FVector TrailUp[TrailMax];
    int32 TrailNum = 0;
    float Crouch = 0, PushTime = -1, BrakeTime = 0, LastSpeed = 0;
    // Native's state (RideNative.cpp): its pumping.
    TPimplPtr<FRideNativeState, EPimplPtrMode::DeepCopy> Native;
    static TPimplPtr<FRideNativeState, EPimplPtrMode::DeepCopy> MakeNative();
    bool bPushStrong = true, bPushed = false;
    bool bPushFromRest = false;     // this push started slower than PushFromRest: nose-first, the board held through the wind-up
    // The push cycle in progress (from the clips when they are in the build): the lead-in before the foot touches,
    // the contact and the recovery; PushCount counts the pushes before this one in a run of pushes.
    int32 PushCount = 0;
    float PushLead = 0, PushContact = 0, PushRecover = 0, PushStrong = 0;
    // Braked to a stop this long ago (-1 while moving).
    float StillTime = -1;
    float WheelSpin = 0;
    // A pop waiting for its jump: the recognised trick's request (serial, gesture, mapped trick, stance, strength) and
    // the ground clip's time (PopTimer, from its manual entry for a flick out of a manual); the board leaves on the
    // tick the air clip takes over.
    atelier::ride::Flick PendingPop = atelier::ride::Flick::None;
    atelier::ride::FlickEvent PendingEvent;
    float PopTimer = 0, PendingLoad = 1, PopWait = .2f;
    bool bPopFromManual = false;
    // Native's ManualOutTimer (MotionGraphHost): a manual's end leaves this long (s) in which a flick still takes off
    // as from the manual; it counts down on the ground.
    float ManualOut = 0;
    // Native's physics mode for the gesture speed (0 easy, 1 normal, 2 hardcore), from the Difficulty setting.
    uint32 Difficulty = 1;
    // Air.
    float AirTime = 0, SpinRate = 0, SpinTotal = 0;
    // The body spin (native's PhysicalBodySpin, RIDE.md "Spins"), in native's terms: the left stick as the spin reads
    // it, its smoothed value, its filtered change and the last SpinTicks of it (the snap), the time in the air and the
    // snap's peak.
    static constexpr int32 SpinTicks = 30;
    float SpinIn = 0, SpinSmooth = 0, SpinFilt = 0, SpinClock = 0, SpinPeak = 0;
    float SpinHistory[SpinTicks] = {};
    int32 SpinAt = 0;
    FVector TakeoffUp = FVector::UpVector;
    // Why the board last left the ground (a pop, a crest, no ground below, ...), for skate.RideSelectLog.
    const TCHAR* LeaveWhy = TEXT("-");
    bool bPopped = false;
    // The air's flight is to start (ChooseLanding) this tick, after its launch corrections: set on entering the air,
    // by the lip's assist or a transfer, and by a late pop.
    bool bSelect = false;
    // A lip air: off a face steeper than the vert reach, flying straight back into it (TickAir, ChooseLanding).
    // LipOut is the face's level normal (away from the coping, into the ramp).
    bool bLipAir = false;
    FVector LipOut = FVector::ZeroVector;
    // The faces climbed in the last ticks on the ground (each tick's up vector; straight up while not climbing): a
    // board that leaves from the coping's rounded edge still takes off from the wall below it.
    static constexpr int32 ClimbTicks = 8;
    FVector ClimbUp[ClimbTicks];
    int32 ClimbNum = 0, ClimbAt = 0;
    // Landing prediction: a ballistic path traced a few segments per tick, to the first face the board can land on
    // (LandTime) or the first it cannot (PredictEnd, the trace stops there); either one overtaken by the flight starts
    // the trace again from where the board is.
    FVector PredictFrom = FVector::ZeroVector, PredictVelocity = FVector::ZeroVector;
    float PredictTime = 0, LandTime = -1, PredictStart = 0, PredictEnd = -1;
    FVector LandNormal = FVector::UpVector;
    // The flip in progress (the board's own rotation in the air).
    atelier::ride::Flick Trick_ = atelier::ride::Flick::None;
    float TrickTime = -1;
    bool bTrickFakie = false, bTrickSwitch = false;
    ERideGrab Grab = ERideGrab::None, LastGrab = ERideGrab::None;
    float GrabTime = 0, GrabWeight = 0, SinceGrab = -1;
    // Grind.
    int32 Rail = INDEX_NONE, LastRail = INDEX_NONE;
    float RailS = 0, RailSpeed = 0, RailCooldown = 0;
    ERideGrind GrindKind = ERideGrind::FiftyFifty;
    float GrindNose = 1;            // the board's nose along +S (+1) or -S (-1); slides: the deck's turn sign
    bool bGrindFront = true;        // the rail on the rider's toe side
    FVector RailUp = FVector::UpVector;
    // What is left of the board's offset from the line when it locked on, closing at LockSpeed (cm/s).
    FVector LockOffset = FVector::ZeroVector;
    float LockSpeed = 0;
    // A stalled grind stepping off its line (bSteppingOff until it lands): until the board is OffClear from the line (a
    // point on it and its direction), the air sweep passes through it (bThroughLine), since it starts inside it.
    bool bSteppingOff = false, bThroughLine = false;
    // Off a line's end or side (not a stall): the air that follows is the sphere's alone, as before the deck box (a box
    // that starts on the line and its corner would read them as walls and spoil the landing it was aiming at).
    bool bBoxOffLine = false;
    FVector OffPoint = FVector::ZeroVector, OffAlong = FVector::ForwardVector;
    float OffClear = 0;
    // Walls (ResetWalls clears them on every activation and placement). The board's box is the visible deck: ShownClip
    // is the clip's own motion of the deck (its pop, flip and tilt) on the session's DeckPose, from the last published
    // pose. SafeDeck is the deck where the last tick left it, at SafeP and SafeQ (bSafeDeck: since the last placement):
    // every move starts there. TickSlide: the powerslide's turn when the tick started. StuckTime: how long the box has
    // been inside a wall it cannot leave. The air's safety deadline counts from where it started (AirStartP, also the
    // lip a lip air's own wall is near) and how fast it climbed in its pop window (AirLaunchVz); AirGlance: how long it
    // has slid along faces it cannot land on.
    FTransform ShownClip = FTransform::Identity, SafeDeck = FTransform::Identity;
    FVector SafeP = FVector::ZeroVector;
    FQuat SafeQ = FQuat::Identity;
    bool bSafeDeck = false;
    bool bShownOff = false;   // the shown deck was off the riding deck at the last Publish (logged once per stretch)
    float TickSlide = 0, StuckTime = 0, AirLaunchVz = 0, AirGlance = 0;
    FVector AirStartP = FVector::ZeroVector;
    // Manual: Native's controller (RideManual.h), its side, and whether this tick's landing was too hard for one.
    atelier::ride::ManualControl Manuals;
    bool bNoseManual = false, bHardLanding = false;
    // Bail.
    FVector BailLinear = FVector::ZeroVector, BailAngular = FVector::ZeroVector, BodyPoint = FVector::ZeroVector;
    bool bFollowBody = false;
    // The last landing, for the pose.
    float Sketchy = 0, LandAge = -1, LandImpact = 0;
    bool bLandedFromGrab = false;
    // What the body is doing, tracked per tick: the motion, how long it has run and the one before it.
    ERideMotion Motion = ERideMotion::Roll, PreviousMotion = ERideMotion::Roll;
    float MotionTime = 0, Clock = 0;
    bool bWasStill = false, bStill = false;
    FRideBodyPose BodyPose;
    // Scoring: the line in progress and the banked total.
    TArray<FLineTrick> Line;
    float Banked = 0, Calm = 0, HeldPoints = 0;
    FString Holding;                // the grind, grab or manual being held, scored when it ends
    // Interpolation between the last two ticks.
    FFrame Previous, Current;
    // Camera (render rate).
    FVector CamPos = FVector::ZeroVector, CamHeading = FVector::ForwardVector;
    bool bCamValid = false;
    // Cost.
    double CostSum = 0, CostMax = 0, CostClock = 0; int32 CostCount = 0;
    int64 QuerySum = 0; int32 QueryMax = 0;
    // Pose health (DescribePose).
    TArray<FVector> LastBones;       // root space
    TArray<bool> BodyBone;
    int32 DeckBone = INDEX_NONE, ToeBone[2] = {INDEX_NONE, INDEX_NONE};
    float PoseStep = 0, FootHeight[2] = {0, 0}, AnimCost = 0;
    int32 PoseStepBone = INDEX_NONE;   // the bone of PoseStep
    float PoseDt = 0;                  // the frame PoseStep was measured over (s)
    int32 PoseNaN = 0, FeetOff = 0;
    // The hips above the board (HIPS over SKATEBOARD_ROOT along the root's up, cm), and the head's and the chest's
    // (SPINE3) facing from the travel (degrees on the root's plane, 0 looking along it); each bone's facing axis is the
    // one that points where the shoulders face in the rig's reference pose.
    int32 HipsBone = INDEX_NONE, HeadBone = INDEX_NONE, ChestBone = INDEX_NONE;
    FVector HeadAxis = FVector::ForwardVector, ChestAxis = FVector::ForwardVector;
    float HipBoard = 0, HeadYaw = 0, ChestYaw = 0;
    float FootAlong[2] = {0, 0};       // each toe along the travel from the deck's pivot (cm; left, right)
    void MeasurePose(float Dt);

    void Tick(const FSkateInput& In, const atelier::skate::XboxState& Pad);
    void TickGround(const FSkateInput& In, atelier::ride::Flick Flick);
    /** Native's Turning.Idle on plain ground: starts a manual when RideManual says so. */
    void TryManual(bool bLanding = false);
    void TickAir(const FSkateInput& In, atelier::ride::Flick Flick);
    void TickGrind(const FSkateInput& In, atelier::ride::Flick Flick);
    void TickBail();
    void SetMode(ERideState NewMode);
    void StartTrick(atelier::ride::Flick Flick);
    void TakeOff(float PopSpeed);
    /** The left stick as the body spin reads it, every tick (native's UpdateInput, and on the ground its smoothing). */
    void ReadSpinStick(const FSkateInput& In);
    /** The air's body spin this tick: SpinRate (degrees/s) from the stick, the snap and the time in the air. */
    void TickSpin(const FSkateInput& In);
    bool TryLand(const FVector& Point, const FVector& Normal);
    void StartBail(const TCHAR* Why);
    bool TryGrind(const FSkateInput& In);
    void LeaveGrind(float Up, bool bStall = false);
    /** Past the line's end: carry on into a line that continues it round a corner under GrindCorner. */
    bool TurnCorner();
    /** The first vertex between arc lengths From and To where the line turns more than GrindCorner. */
    bool SharpCorner(float From, float To, float& OutS) const;
    void AdvancePrediction(int32 Segments);
    /** The air's gravity (cm/s^2): VertGravity in a lip air, else AirGravity. */
    float Gravity() const;
    /** An air's start: a lip air's flight (bLipAir), the take-off velocity or one of six around it (native's cone),
     *  whichever comes back down into the face it left, steepest and furthest from the apex, with the least change;
     *  then the landing prediction starts again from the board. */
    void ChooseLanding();
    /** Native's departure off a vert and its launch adjustment on V, off the face Up (RideNative.cpp); bAligned when
     *  the climb was set upright (a lip air). False, V untouched, without native's settings. */
    bool NativeLipLaunch(const FVector& Up, bool& bAligned);
    /** Native's ground pumping this tick (RideNative.cpp): Speed gains its velocity change. */
    void Pump(float& Speed, bool bIntentional);
    /** Forget native's pumping (off the ground), or all of native's state (a new ride). */
    void ResetPump();
    void ResetNative();
    void ResetPrediction(const FVector& From);
    void StartPush(bool bFirstPush, float Speed);
    /** Turn round on the board (the switch clip), before a push from fakie (bPush) or by itself. */
    void StartSwitch(bool bPush);
    ERideMotion CurrentMotion() const;
    void TrackMotion();
    /** From the take-off to the board caught under the feet: the flip clip's, else the tuned time. */
    float CatchTime(atelier::ride::Flick Flick) const;
    /** A wheel's ground under Base. A face too steep to roll onto sets bBlocked, and Block (if given) keeps the
     *  blocking normal that Toward (the board's velocity) closes on fastest. */
    bool Probe(const FVector& Base, const FVector& Up, float Above, float Below, FVector& Point, FVector& Normal, bool& bBlocked, FVector* Block = nullptr, const FVector& Toward = FVector::ZeroVector) const;
    bool Sweep(const FVector& From, const FVector& To, float Radius, FHitResult& Hit) const;
    bool Trace(const FVector& From, const FVector& To, FHitResult& Hit) const;
    /** Whether the root reaches a ground point from where it is, straight or up and over (a step, a ledge's edge),
     *  never through a floor or a wall. */
    bool Reaches(const FVector& To) const;
    /** Whether the board can land on a hit face: one within WallSlope of level, a lip air's own wall, or a steeper face
     *  that curves up into a transition below the hit (not a wall, a rail's side or a box's face). The landing
     *  prediction and the flight's contacts use it. */
    bool IsLandable(const FHitResult& Hit) const;
    void ResetWalls();
    /** The visible deck in the world (its pivot, unscaled) for the session at (At, Frame): the
     *  clip's motion (ShownClip) on DeckPose on the root, lifted as the shown board grows about its wheels' contact. */
    FTransform DeckWorld(const FVector& At, const FQuat& Frame) const;
    /** The board's collision box for a deck (DeckWorld): centre and rotation, half extents in Extent, at the board's
     *  scale, from Clearance (cm) above the wheels' plane (lower faces are the wheels' and the probes') to the kicks. */
    FTransform DeckBox(const FTransform& Deck, float Clearance, FVector& Extent) const;
    /** The board's box from From to To. A face within WallSlope of Up (one it rolls on) stops it only when
     *  bStopOnSupport (Support); otherwise the box goes on along it, so a ramp or the floor under a tilted deck never
     *  hides a wall behind it. Wall: a steeper face stops it (Hit.Time the fraction of the move). Inside: it starts in
     *  a wall. */
    enum class EBoardHit : uint8 { Clear, Support, Wall, Inside };
    EBoardHit SweepBoard(const FTransform& From, const FTransform& To, const FVector& Extent, const FVector& Up, bool bStopOnSupport, FHitResult& Hit) const;
    /** The walls a box at Box overlaps (faces within WallSlope of Up are left to the ground): the summed way out of
     *  them (Push) and the deepest one's normal. False when it overlaps none. */
    bool WallOverlap(const FTransform& Box, const FVector& Extent, const FVector& Up, FVector& Push, FVector& Normal) const;
    /** MoveBoardPose, the one way the riding board moves: from SafeDeck (or the session's pose after a placement) to
     *  (ToP, ToQ), translation and rotation with the whole box. Clear: the pose is free. Corrected: ToP and ToQ are
     *  changed to where the box stops short of a wall (Wall the contact), or pushed out of one it would start in
     *  (bounded, whole-box, reached without crossing anything). Unresolved: no free pose; ToP and ToQ are the
     *  session's own (the board stays). */
    enum class EBoardMove : uint8 { Clear, Corrected, Unresolved };
    EBoardMove MoveBoardPose(FVector& ToP, FQuat& ToQ, float Clearance, FHitResult& Wall) const;
    /** Up beside a wall (a get-up): the board out of it along the ground, else turned along it and out. */
    void LeaveWallsStanding();
    /** Before a bail for being stuck in a wall: where (Site), the board's pose and speed, whether its box came from the
     *  last free pose, and the face it is inside or against (Wall), in the log. */
    void LogStuck(const TCHAR* Site, const FHitResult& Wall) const;
    /** Out of the walls the box at (ToP, ToQ) overlaps: up to three whole-box pushes (on the frame's plane when bOnPlane),
     *  the result free of walls and its centre reached from From's without crossing anything. */
    bool LeaveWall(const FTransform& From, FVector& ToP, const FQuat& ToQ, float Clearance, bool bOnPlane, FHitResult& Wall) const;
    /** A contact in the air the board does not land on: thrown when it comes in faster than WallBailSpeed, lies on a
     *  floor on its side or has slid along such faces for too long; otherwise it slides along without bouncing.
     *  True when the flight ended. */
    bool HitWallInAir(const FVector& Normal);
    /** A board contact in the air (a landing, a wall, the box or the sphere in a face) in the grab clip's danger zone:
     *  the bail, true when it bails. */
    bool DangerContact(const FVector& Normal, const TCHAR* What);
    bool FindGround(const FVector& At, const FQuat& Frame, float Below, FVector& OutP, FVector& OutUp, FVector& OutForward, bool& bBlocked, FVector* Block = nullptr, const FVector& Toward = FVector::ZeroVector) const;
    /** One step of rolling (Dt of the tick): walls, the ground, crests. False when the board left the ground, was
     *  thrown or stopped against something, which ends the tick's move. */
    bool MoveOnGround(float Dt, float& Speed);
    /** Bounce off a face (its normal in the deck's plane), turned along it. */
    void Deflect(const FVector& Normal, float& Speed);
    void AddTrail(float At, const FVector& Up);
    FTransform DeckPose() const;
    void AddTrick(const FString& Name, float Points);
    void Hold(const FString& Name, float PointsPerSecond, float Dt);
    void EndHold();
    void BankLine();
    void LoseLine();
    void Publish(float Alpha, float Dt, const FSkateInput& In);
    void UpdateCamera(const FVector& At, const FQuat& Frame, float Dt);
    /** Take-off speed for a pop whose stick rested Load seconds on the rim first. */
    float PopSpeed(float Load = 1.f) const;
    FString FlickName(atelier::ride::Flick Flick, bool bFakie, bool bSwitched = false) const;
    FString GrindName() const;
    FString SpinName(float Degrees) const;
};
