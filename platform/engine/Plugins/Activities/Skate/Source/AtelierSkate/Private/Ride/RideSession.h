#pragma once
#include "CoreMinimal.h"
#include "SkateInput.h"
#include "RideFlick.h"
#include "RideTuning.h"
#include "RideTypes.h"
#include "RideAnimator.h"

class UWorld;
class AActor;
class USkateRailSubsystem;
struct FHitResult;

/** What the session queries: collision that blocks pawns, the rider (ignored), and the grind lines. */
struct FRideWorld
{
    UWorld* World = nullptr;
    const AActor* Ignore = nullptr;
    const USkateRailSubsystem* Rails = nullptr;
    /** The rider: the pose mesh that plays the clips goes on it. */
    AActor* Owner = nullptr;
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
    /** Add host time and run whole 60 Hz ticks; then publish the interpolated pose and the camera. */
    void Step(float Dt, const FSkateInput& Input, const FRideWorld& World);
    /** The rider was thrown and has come to rest (the component's ragdoll, or the session's own slide): stand the
     *  board up at this ground point facing Yaw and blend the rider back over GetUpTime. */
    void GetUp(const FVector& GroundPoint, float Yaw);
    /** Whether the component handles the fall with a ragdoll; otherwise the session slides the rider to a stop. */
    void SetRagdoll(bool bAvailable) { bRagdoll = bAvailable; }
    /** During a ragdoll bail: the ground point under the body, which the root and the camera follow. */
    void FollowBody(const FVector& GroundPoint) { BodyPoint = GroundPoint; bFollowBody = true; }
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
    bool IsFakie() const { return Travel < 0; }
    float GetSlideAngle() const { return Mode == ERideState::Powerslide ? FMath::Abs(SlideYaw) : 0.f; }
    bool IsSliding() const { return Mode == ERideState::Grind && (GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide); }
    float BailTime() const { return Mode == ERideState::Bail ? ModeTime : 0.f; }
    /** The board's world velocity and spin when the rider was thrown, for the ragdoll and the loose board. */
    FVector GetBailVelocity() const { return BailLinear; }
    FVector GetBailSpin() const { return BailAngular; }
    bool HasRig() const { return Animator.HasRig(); }
    /** Mean and worst simulation cost per tick over the last second (ms). */
    float CostMean = 0, CostWorst = 0;
    /** The published pose's health for QA: the main clip, the board's hold and lift, the fastest body bone (cm/s,
     *  root space), each foot's height above the deck's pivot and how many feet are off the deck, NaN bones, and the
     *  animator's cost (ms). */
    FString DescribePose() const;

private:
    struct FFrame { FVector P = FVector::ZeroVector; FQuat Q = FQuat::Identity; FTransform Deck = FTransform::Identity; };
    struct FLineTrick { FString Name; float Points = 0; };

    FRideTuning Tune;
    FRidePreferences Prefs;
    FRideAnimator Animator;
    atelier::ride::FlickReader Flicks;
    FRideWorld Where;
    bool bGoofy = false, bRagdoll = true;
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
    bool bPushStrong = true, bPushed = false;
    // The push cycle in progress (from the clips when they are in the build): the lead-in before the foot touches,
    // the contact and the recovery; PushCount counts the pushes before this one in a run of pushes.
    int32 PushCount = 0;
    float PushLead = 0, PushContact = 0, PushRecover = 0, PushStrong = 0;
    // Braked to a stop this long ago (-1 while moving).
    float StillTime = -1;
    float WheelSpin = 0;
    // A pop waiting for the end of its ground clip.
    atelier::ride::Flick PendingPop = atelier::ride::Flick::None;
    float PopTimer = 0, PendingLoad = 1, PopWait = .2f;
    // Air.
    float AirTime = 0, SpinRate = 0, SpinTotal = 0;
    FVector TakeoffUp = FVector::UpVector;
    bool bPopped = false;
    // A lip air: off a face steeper than the vert reach, flying straight back into it (TickAir, ChooseLanding).
    // LipOut is the face's level normal (away from the coping, into the ramp).
    bool bLipAir = false;
    FVector LipOut = FVector::ZeroVector;
    // Landing prediction: a ballistic path traced a few segments per tick.
    FVector PredictFrom = FVector::ZeroVector, PredictVelocity = FVector::ZeroVector;
    float PredictTime = 0, LandTime = -1, PredictStart = 0;
    FVector LandNormal = FVector::UpVector;
    // The flip in progress (the board's own rotation in the air).
    atelier::ride::Flick Trick_ = atelier::ride::Flick::None;
    float TrickTime = -1;
    bool bTrickFakie = false;
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
    // Manual.
    float Balance = 0;
    bool bNoseManual = false;
    uint32 Noise = 0x9E3779B9u;
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
    // Pose health (DescribePose).
    TArray<FVector> LastBones;       // root space
    TArray<bool> BodyBone;
    int32 DeckBone = INDEX_NONE, ToeBone[2] = {INDEX_NONE, INDEX_NONE};
    float PoseStep = 0, FootHeight[2] = {0, 0}, AnimCost = 0;
    int32 PoseStepBone = INDEX_NONE;   // the bone of PoseStep
    float PoseDt = 0;                  // the frame PoseStep was measured over (s)
    int32 PoseNaN = 0, FeetOff = 0;
    void MeasurePose(float Dt);

    void Tick(const FSkateInput& In);
    void TickGround(const FSkateInput& In, atelier::ride::Flick Flick);
    void TickAir(const FSkateInput& In, atelier::ride::Flick Flick);
    void TickGrind(const FSkateInput& In, atelier::ride::Flick Flick);
    void TickBail();
    void SetMode(ERideState NewMode);
    void StartTrick(atelier::ride::Flick Flick);
    void TakeOff(float PopSpeed);
    bool TryLand(const FVector& Point, const FVector& Normal);
    void StartBail(const TCHAR* Why);
    bool TryGrind(const FSkateInput& In);
    void LeaveGrind(float Up);
    /** Past the line's end: carry on into a line that continues it round a corner under GrindCorner. */
    bool TurnCorner();
    /** The first vertex between arc lengths From and To where the line turns more than GrindCorner. */
    bool SharpCorner(float From, float To, float& OutS) const;
    void AdvancePrediction(int32 Segments);
    /** The air's gravity (cm/s^2): VertGravity in a lip air, else AirGravity. */
    float Gravity() const;
    /** A lip air's flight: the take-off velocity or one of six around it (native's cone), whichever comes back
     *  down into the face it left, steepest and furthest from the apex, with the least change. */
    void ChooseLanding(const FVector& From);
    void ResetPrediction(const FVector& From);
    void StartPush(bool bFirstPush, float Speed);
    ERideMotion CurrentMotion() const;
    void TrackMotion();
    /** From the take-off to the board caught under the feet: the flip clip's, else the tuned time. */
    float CatchTime(atelier::ride::Flick Flick) const;
    /** A wheel's ground under Base. A face too steep to roll onto sets bBlocked, and Block (if given) keeps the
     *  blocking normal that Toward (the board's velocity) closes on fastest. */
    bool Probe(const FVector& Base, const FVector& Up, float Above, float Below, FVector& Point, FVector& Normal, bool& bBlocked, FVector* Block = nullptr, const FVector& Toward = FVector::ZeroVector) const;
    bool Sweep(const FVector& From, const FVector& To, float Radius, FHitResult& Hit) const;
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
    float Random();
    /** Take-off speed for a pop whose stick rested Load seconds on the rim first. */
    float PopSpeed(float Load = 1.f) const;
    FString FlickName(atelier::ride::Flick Flick, bool bFakie) const;
    FString GrindName() const;
    FString SpinName(float Degrees) const;
};
