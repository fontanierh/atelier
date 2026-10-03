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
    /** Get on at a ground point, facing the board's rotation, moving at Velocity. */
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

    // Published each Step.
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
    float Curvature = 0;            // 1/cm along the travel, positive in a concave transition
    float Crouch = 0, PushTime = -1, BrakeTime = 0, LastSpeed = 0;
    bool bPushStrong = true, bPushed = false;
    float WheelSpin = 0;
    // A pop waiting for the end of its ground clip.
    atelier::ride::Flick PendingPop = atelier::ride::Flick::None;
    float PopTimer = 0, PendingLoad = 1;
    // Air.
    float AirTime = 0, SpinRate = 0, SpinTotal = 0;
    FVector TakeoffUp = FVector::UpVector;
    bool bPopped = false;
    // Landing prediction: a ballistic path traced a few segments per tick.
    FVector PredictFrom = FVector::ZeroVector, PredictVelocity = FVector::ZeroVector;
    float PredictTime = 0, LandTime = -1;
    FVector LandNormal = FVector::UpVector;
    // The flip in progress (the board's own rotation in the air).
    atelier::ride::Flick Trick_ = atelier::ride::Flick::None;
    float TrickTime = -1;
    bool bTrickFakie = false;
    ERideGrab Grab = ERideGrab::None;
    float GrabTime = 0, GrabWeight = 0;
    // Grind.
    int32 Rail = INDEX_NONE, LastRail = INDEX_NONE;
    float RailS = 0, RailSpeed = 0, RailCooldown = 0;
    ERideGrind GrindKind = ERideGrind::FiftyFifty;
    float GrindNose = 1;            // the board's nose along +S (+1) or -S (-1); slides: the deck's turn sign
    bool bGrindFront = true;        // the rail on the rider's toe side
    FVector RailUp = FVector::UpVector;
    // Manual.
    float Balance = 0;
    bool bNoseManual = false;
    uint32 Noise = 0x9E3779B9u;
    // Bail.
    FVector BailLinear = FVector::ZeroVector, BailAngular = FVector::ZeroVector, BodyPoint = FVector::ZeroVector;
    bool bFollowBody = false;
    // Landing quality for the pose.
    float Sketchy = 0;
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
    void AdvancePrediction(int32 Segments);
    bool Probe(const FVector& Base, const FVector& Up, float Above, float Below, FVector& Point, FVector& Normal, bool& bBlocked) const;
    bool Sweep(const FVector& From, const FVector& To, float Radius, FHitResult& Hit) const;
    bool FindGround(const FVector& At, const FQuat& Frame, float Below, FVector& OutP, FVector& OutUp, FVector& OutForward, bool& bBlocked) const;
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
