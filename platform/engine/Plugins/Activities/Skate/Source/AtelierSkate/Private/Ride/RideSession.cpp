#include "RideSession.h"
#include "SkateRails.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "HAL/PlatformTime.h"
#include "HAL/IConsoleManager.h"
#include "Engine/OverlapResult.h"
#include "Components/PrimitiveComponent.h"
#include "PhysicsEngine/BodyInstance.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "SkateSettings.h"

using atelier::ride::Flick;
using atelier::ride::IsNollie;

namespace
{
    constexpr float Tick60 = 1.f / 60.f;
    constexpr float G = 980.f;
    // The landing's give plays for this long after a touch-down (RideAnimator).
    constexpr float LandHold = 1.f;
    // A turn round by itself flips the stance this long before the switch clip's end, or this long when a push was
    // asked during it (native's Turning.Switch WillExpire .02 and .075).
    constexpr float SwitchEndLead = .02f, SwitchQueueLead = .075f;
    // The board's box (DeckBox) holds Native's whole board (BoardPhysicsSettings, DeckGeometry): half the length from
    // tail to nose (the 59 cm middle and the 15.75 cm ends turned up 12.5 and 13 degrees, with the deck's 0.75 cm half
    // thickness), half the deck's 24 cm width (the wheels sit 9.5 cm out), and the kicks' top over the deck's pivot (cm
    // at board scale 1); it reaches down to the wheels' plane. Rolling and flying, the box starts StepUp + BoxClearance
    // above that plane: lower faces are the wheels' probes'.
    constexpr float DeckHalfLength = 45.6f, DeckHalfWidth = 12.f, DeckKick = 4.3f, BoxClearance = .5f;
    // The world queries the session made (QueriesMean, QueriesWorst).
    int32 BoardQueries = 0;
    // SweepBox turns the box in steps that move no corner more than CornerStep (cm), at most RotationSteps a sweep;
    // SweepBoard goes on along faces the board rolls on at most SupportSlides times a sweep.
    constexpr float CornerStep = 4.f;
    constexpr int32 RotationSteps = 8, SupportSlides = 3;
    // A move starts from the deck the last tick left (SafeDeck) when that is within SafeReach (cm) of where it goes;
    // farther, something placed the board. A board pushed out of a wall moves at most MaxPush (cm); inside one it
    // cannot leave for StuckLimit (s), the rider falls.
    constexpr float SafeReach = 100.f, MaxPush = 45.f, StuckLimit = .3f;
    // A bail's root follows the body's ground along a line this high over both, or up to this high over the higher (cm).
    constexpr float FollowLow = 30.f, FollowHigh = 100.f;
    // The shown clip's own motion of the deck (ShownClip: its pop, flip and tilt) the box follows, within ShownReach (cm)
    // of the session's deck pivot. Farther, the deck bone is not the riding deck (a mount still blending in from the
    // board's last place, the board in a hand) and the box keeps the session's deck.
    constexpr float ShownReach = 45.f;
    // In the air with no landing in sight, the board turns back toward upright at this rate (degrees/s).
    constexpr float RightRate = 180.f;
    // The air's safety deadline (a guard, not native behaviour: native bounds only how far a prediction looks): an air
    // that has had the time to fall AirDrop (cm) below where it started, at the climb of its pop window under the
    // weaker gravity, ends in a bail; so does one that slides GlanceLimit (s) along faces it cannot land on.
    constexpr float AirDrop = 3000.f, GlanceLimit = .5f;
    // IsLandable: a steep face is a transition when the surface this far below the hit (cm, down the face) is turned
    // up from it by MinBend to MaxBend degrees. A lip air's own wall is a face turned toward LipOut no more than LipBack
    // (cm) behind the lip's plane or LipBand in front of it.
    constexpr float BendProbes[] = {30.f, 80.f, 150.f, 250.f, 400.f};
    constexpr float MinBend = 2.f, MaxBend = 50.f, LipBack = 40.f, LipBand = 150.f;

    // Native's flick out of a manual (motion graph, TakeOff.FromManual): the pop clip jumps in at its MANUALINTO
    // attribute, two thirds through every ground clip (animation metadata), and a manual's end leaves ManualOutTime
    // (SetManualOutTimer) in which a flick still takes off that way.
    constexpr float ManualInto = 2.f / 3.f, ManualOutTime = .1f;

    // Native's settings and gesture sets, read once from the native bundle (the files Native loads) with Native's own
    // loaders, and shared by every ride.
    std::shared_ptr<const atelier::ride::FlickBank> RideFlickBank(std::string& Error)
    {
        static std::string LoadError;
        static const std::shared_ptr<const atelier::ride::FlickBank> Bank = []
        {
            const FString Root = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Data/SkateNative"));
            TArray<uint8> Settings, Gestures;
            if (!FFileHelper::LoadFileToArray(Settings, *(Root / TEXT("settings.skate"))) ||
                !FFileHelper::LoadFileToArray(Gestures, *(Root / TEXT("gestures.skate"))))
            {
                LoadError = TCHAR_TO_UTF8(*FString::Printf(TEXT("cannot read settings.skate and gestures.skate in %s"), *Root));
                return std::shared_ptr<const atelier::ride::FlickBank>();
            }
            return atelier::ride::FlickBank::Load(std::vector<std::uint8_t>(Settings.GetData(), Settings.GetData() + Settings.Num()),
                std::vector<std::uint8_t>(Gestures.GetData(), Gestures.GetData() + Gestures.Num()), LoadError);
        }();
        Error = LoadError;
        return Bank;
    }

    template <int32 N>
    float Curve(const float (&Points)[N][2], float X)
    {
        if (X <= Points[0][0]) return Points[0][1];
        for (int32 I = 1; I < N; ++I)
            if (X <= Points[I][0])
                return FMath::Lerp(Points[I - 1][1], Points[I][1], (X - Points[I - 1][0]) / FMath::Max(1e-4f, Points[I][0] - Points[I - 1][0]));
        return Points[N - 1][1];
    }
    // The native stick response: the share of the full turn rate for a stick deflection (RIDE.md, "Steering").
    const float SteerCurve[][2] = {{0, 0}, {.059f, 0}, {.25f, .034f}, {.375f, .078f}, {.509f, .172f}, {.69f, .335f}, {.858f, .564f}, {1, .835f}};
    // Rolling friction on smooth ground (cm/s -> cm/s^2): none up to 8 m/s.
    const float FrictionCurve[][2] = {{0, 0}, {812, 0}, {1042, 3}, {1205, 16.3f}, {1286, 60}, {1433, 90}, {1840, 105}, {2698, 120}};
    // Native's MinCrouchVsGroundAngle (physics_pumping): the least crouch by the ground's angle (a share of 90 degrees).
    const float MinCrouchCurve[][2] = {{0, 0}, {.09f, 0}, {.161f, .03f}, {.34f, .365f}, {.461f, .537f}, {.607f, .666f}, {.792f, .75f}, {1, .794f}};
    // Native's body spin (physics_bodyspin, normal mode) by the time in the air (s): the rate at full stick (rad/s,
    // before SetSpinScale), the most the rate changes in a tick (rad/s) and the same for the landing's alignment; and
    // the snap's weight by the age of the stick's change (s, negative before the take-off).
    const float SpinPropCurve[][2] = {{0, 3.15f}, {.052f, 6.364f}, {.127f, 7.779f}, {.244f, 7.939f}, {.368f, 7.714f}, {.564f, 6.975f}, {.906f, 5.689f}, {2, 3.664f}};
    const float SpinMaxDeltaCurve[][2] = {{0, .993f}, {.116f, .761f}, {.256f, .507f}, {.394f, .35f}, {.533f, .225f}, {.678f, .171f}, {.878f, .157f}, {1, .154f}};
    const float SpinAutoCurve[][2] = {{0, 1}, {.107f, .739f}, {.2f, .643f}, {.301f, .557f}, {.388f, .507f}, {.498f, .489f}, {.71f, .482f}, {1, .475f}};
    const float SpinSnapCurve[][2] = {{-.497f, 0}, {-.375f, .05f}, {-.254f, 1}, {0, 1}, {.135f, 1}, {.228f, .629f}, {.337f, .386f}, {.5f, .286f}};
    // The spin's stick: native's conditioned left x (Input.cpp, ConditionStick), the stick's length less a quarter over
    // three quarters (at most 1) along its direction, so a stick within a quarter of the centre spins nothing and a
    // half-pushed one a third.
    float SpinStickX(const FVector2D& Left)
    {
        const float Length = Left.Size();
        return Length < .001f ? 0.f : float(Left.X) * FMath::Clamp((Length - .25f) / .75f, 0.f, 1.f) / Length;
    }

    TAutoConsoleVariable<int32> CVarRideSelectLog(TEXT("skate.RideSelectLog"), 0,
        TEXT("Log every air's start (ChooseLanding): why the board left the ground, where and how fast, and a lip air's\n")
        TEXT("candidate flights, their landings and ranks, and the one it flies (0: off)."));
    // The native LandingSpeedScalarVsGroundNormalY: coming down a face between 46 and 65 degrees, the speed along it
    // grows by up to 15% (by the landing normal's up component).
    const float LandingCurve[][2] = {{.42f, 1}, {.45f, 1.075f}, {.49f, 1.13f}, {.53f, 1.15f}, {.58f, 1.15f}, {.62f, 1.13f}, {.66f, 1.075f}, {.69f, 1}};
    // Powerslide deceleration by speed (cm/s -> cm/s^2), as measured on the native runtime.
    const float SlideCurve[][2] = {{0, 150}, {360, 230}, {560, 410}, {850, 560}, {1130, 630}, {2000, 700}};

    FQuat Frame(const FVector& Up, const FVector& Forward) { return FRotationMatrix::MakeFromZX(Up, Forward).ToQuat(); }
    FQuat Turn(const FVector& Axis, float Degrees) { return FQuat(Axis, FMath::DegreesToRadians(Degrees)); }
    float Damp(float Rate, float Dt) { return 1.f - FMath::Exp(-Rate * Dt); }
    FQuat TiltToward(const FQuat& Q, const FVector& Up, float Fraction)
    {
        const FQuat Full = FQuat::FindBetweenNormals(Q.GetUpVector(), Up);
        return (FQuat::Slerp(FQuat::Identity, Full, FMath::Clamp(Fraction, 0.f, 1.f)) * Q).GetNormalized();
    }
    float AngleBetween(const FVector& A, const FVector& B)
    {
        return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(A.GetSafeNormal(), B.GetSafeNormal())), -1.f, 1.f)));
    }

    /** A flip's board motion and score: roll about the board's length, turn about its up axis (degrees, regular
     *  stance riding forward) and the time to the catch. */
    struct FFlipInfo { float Roll, Yaw, Time, Points; };
    FFlipInfo FlipInfo(Flick F)
    {
        switch (F)
        {
        case Flick::Ollie: return {0, 0, .3f, 100};
        case Flick::Nollie: return {0, 0, .3f, 120};
        case Flick::Kickflip: return {-360, 0, .34f, 250};
        case Flick::Heelflip: return {360, 0, .34f, 250};
        case Flick::ShoveIt: return {0, 180, .3f, 200};
        case Flick::FsShoveIt: return {0, -180, .3f, 200};
        case Flick::Shove360: return {0, 360, .4f, 350};
        case Flick::FsShove360: return {0, -360, .4f, 350};
        case Flick::VarialKickflip: return {-360, 180, .42f, 350};
        case Flick::VarialHeelflip: return {360, -180, .36f, 350};
        case Flick::Hardflip: return {-360, -180, .38f, 400};
        case Flick::InwardHeelflip: return {360, 180, .38f, 400};
        case Flick::TreFlip: return {-360, 360, .42f, 500};
        case Flick::LaserFlip: return {360, -360, .42f, 500};
        case Flick::Hardflip360: return {-360, -360, .42f, 600};
        case Flick::InwardHeelflip360: return {360, 360, .45f, 600};
        // The nollie family: the same board motion off the nose, worth a little more (as the nollie is the ollie's).
        case Flick::NollieKickflip: return {-360, 0, .34f, 270};
        case Flick::NollieHeelflip: return {360, 0, .34f, 270};
        case Flick::NollieShoveIt: return {0, 180, .3f, 220};
        case Flick::NollieFsShoveIt: return {0, -180, .3f, 220};
        case Flick::NollieShove360: return {0, 360, .4f, 370};
        case Flick::NollieFsShove360: return {0, -360, .4f, 370};
        case Flick::NollieVarialKickflip: return {-360, 180, .42f, 370};
        case Flick::NollieVarialHeelflip: return {360, -180, .36f, 370};
        case Flick::NollieHardflip: return {-360, -180, .38f, 420};
        case Flick::NollieInwardHeelflip: return {360, 180, .38f, 420};
        case Flick::NollieTreFlip: return {-360, 360, .42f, 520};
        case Flick::NollieLaserFlip: return {360, -360, .42f, 520};
        case Flick::NollieHardflip360: return {-360, -360, .42f, 620};
        case Flick::NollieInwardHeelflip360: return {360, 360, .45f, 620};
        default: return {0, 0, 0, 0};
        }
    }
    const TCHAR* GrabName(ERideGrab Grab)
    {
        switch (Grab)
        {
        case ERideGrab::Indy: return TEXT("Indy");
        case ERideGrab::Melon: return TEXT("Melon");
        case ERideGrab::ChristAir: return TEXT("Christ Air");
        case ERideGrab::OneFoot: return TEXT("One Foot");
        case ERideGrab::TuckKnee: return TEXT("Tuck Knee");
        default: return TEXT("");
        }
    }
}

FRideSession::FRideSession() : Tune(FRideTuning::Get()), Native(MakeNative()) {}

void FRideSession::Activate(const FRideWorld& World, const FVector& GroundPoint, const FQuat& Rotation, const FVector& InVelocity, bool bInGoofy, const FRidePreferences& Preferences)
{
    Where = World; Tune = FRideTuning::Get();
    Configure(bInGoofy, Preferences);
    Animator.Preload();
    Animator.Attach(World.Owner);
    Animator.ResetBoardTurn();
    Names = Animator.GetNames(); Reference = Animator.GetReference();
    P = GroundPoint; V = InVelocity; Q = Rotation.GetNormalized();
    Travel = FVector::DotProduct(V, Q.GetForwardVector()) < -15.f ? -1.f : 1.f;
    TurnRate = SlideYaw = Curvature = Crouch = 0; PushTime = -1; BrakeTime = 0; PendingPop = Flick::None; TrailNum = 0;
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; Rail = INDEX_NONE; Manuals.Reset(); bHardLanding = false;
    bSwitch = false; SwitchTime = -1; FakieTime = 0;
    Line.Reset(); Holding.Reset(); HeldPoints = 0; Calm = 0; Trick.Reset(); Cues.Reset();
    // Flick-It: Native's controls, loaded on the first ride, then mounted as GameplaySession::Activate mounts them
    // (their gesture history carries on from ride to ride, as Native's does).
    if (!Flicks.HasBank())
    {
        std::string Error;
        if (!Flicks.SetBank(RideFlickBank(Error), Error))
            UE_LOG(LogTemp, Error, TEXT("SKATE ride: no native controls (%s); no trick will read"), UTF8_TO_TCHAR(Error.c_str()));
    }
    Flicks.Activate();
    ManualOut = 0; bPopFromManual = false; PendingEvent = atelier::ride::FlickEvent();
    // The clock starts a step full, so the first frame shows the start moved on by that frame's time, as every later
    // frame does. Empty, the first Step ran one tick and showed it at alpha 0 (the start again, a frame's hold), and
    // the shown board trailed real time by a tick for the whole ride.
    Accumulator = Tick60 - KINDA_SMALL_NUMBER; bCamValid = false;
    PushCount = 0; StillTime = -1; bStill = bWasStill = false; LastGrab = ERideGrab::None; SinceGrab = -1;
    // Nothing of the last ride carries into this one: its air, the spin stick's history, the lip, the climb, the line
    // it left, native's pumping and the landing it predicted.
    AirTime = SpinRate = SpinTotal = 0; SpinIn = SpinSmooth = SpinFilt = SpinClock = SpinPeak = 0;
    FMemory::Memzero(SpinHistory); SpinAt = 0;
    bPopped = bLipAir = bSelect = false; LipOut = FVector::ZeroVector; TakeoffUp = Q.GetUpVector();
    ClimbNum = ClimbAt = 0; LastRail = INDEX_NONE; RailCooldown = 0;
    ResetNative(); ResetPrediction(P);
    LandAge = -1; LandImpact = 0; bLandedFromGrab = false; Sketchy = 0; Clock = 0;
    bSteppingOff = bThroughLine = bPushFromRest = bBoxOffLine = false;
    ResetWalls();
    // Settle onto whatever is under the board. A start inside the floor (a hand-off a little low) finds the floor's top
    // from up to StartRecover above and starts on it, rather than in the air under it.
    FVector Ground, Up, Forward; bool bBlocked = false;
    bool bGround = FindGround(P, Q, 60.f, Ground, Up, Forward, bBlocked);
    if (!bGround && bBlocked)
    {
        const FVector Lift = Q.GetUpVector();
        const float R = Tune.WheelRadius;
        FHitResult Top;
        if (Sweep(P + Lift * (Tune.StartRecover + R), P + Lift * R, R, Top) && !Top.bStartPenetrating && FVector::DotProduct(Top.Normal, Lift) >= Tune.WallSlope)
        {
            bBlocked = false;
            bGround = FindGround(Top.Location - Lift * R, Q, 60.f, Ground, Up, Forward, bBlocked);
            if (bGround) UE_LOG(LogTemp, Display, TEXT("SKATE ride start inside the floor: %.0f cm up onto it"), float(FVector::DotProduct(Ground - P, Lift)));
        }
    }
    if (bGround) { P = Ground; Q = Frame(Up, Forward); SetMode(ERideState::Ground); }
    else { SetMode(ERideState::Air); LeaveWhy = TEXT("placed in the air"); AirTime = 0; TakeoffUp = Q.GetUpVector(); bPopped = true; bLipAir = false; bSelect = true; ResetPrediction(P); }
    ModeTime = 0;
    if (Mode == ERideState::Ground) V = FVector::VectorPlaneProject(V, Q.GetUpVector());
    Motion = PreviousMotion = CurrentMotion(); MotionTime = 0;
    Previous.P = Current.P = P; Previous.Q = Current.Q = Q; Previous.Deck = Current.Deck = DeckPose();
    Publish(1.f, 0.f, FSkateInput());
}

void FRideSession::Configure(bool bInGoofy, const FRidePreferences& Preferences)
{
    bGoofy = bInGoofy; Prefs = Preferences;
    // Native's physics mode, from the setting GameplaySession::Configure reads (an unknown name stays normal).
    const FString& Level = GetDefault<USkateSettings>()->Difficulty;
    Difficulty = Level.Equals(TEXT("easy"), ESearchCase::IgnoreCase) ? 0 : Level.Equals(TEXT("hardcore"), ESearchCase::IgnoreCase) ? 2 : 1;
}

void FRideSession::Launch(const FVector& InVelocity)
{
    V = InVelocity;
    if (Mode == ERideState::Ground || Mode == ERideState::Manual || Mode == ERideState::Powerslide)
    {
        // A launch that rises off the ground takes off. A level one keeps to it at its own speed: off a slope's normal
        // it would only be the slope falling away below it (native's board stays on the ground and gravity follows).
        const FVector Up = Q.GetUpVector();
        if (V.Z > 50.f && FVector::DotProduct(V, Up) > 50.f) { LeaveWhy = TEXT("launch"); TakeOff(0.f); }
        else
        {
            V = FVector::VectorPlaneProject(V, Up).GetSafeNormal() * V.Size();
            const float Along = FVector::DotProduct(V, Q.GetForwardVector());
            if (FMath::Abs(Along) > 1.f) Travel = Along < 0 ? -1.f : 1.f;
        }
    }
}

void FRideSession::Step(float Dt, const FSkateInput& Input, const atelier::skate::XboxState& Pad, const FRideWorld& World)
{
    Where = World;
    Tune = FRideTuning::Get();
    Cues.Reset();
    Accumulator = FMath::Min(Accumulator + FMath::Max(Dt, 0.f), 6 * Tick60);
    const double Start = FPlatformTime::Seconds();
    int32 Count = 0;
    while (Accumulator >= Tick60)
    {
        Previous = Current;
        const int32 Asked = BoardQueries;
        const double TickStart = FPlatformTime::Seconds();
        Tick(Input, Pad);
        CostMax = FMath::Max(CostMax, (FPlatformTime::Seconds() - TickStart) * 1000.);
        QuerySum += BoardQueries - Asked; QueryMax = FMath::Max(QueryMax, BoardQueries - Asked);
        Current.P = P; Current.Q = Q; Current.Deck = DeckPose();
        Accumulator -= Tick60; ++Count;
    }
    if (Count > 0)
    {
        const double Cost = (FPlatformTime::Seconds() - Start) * 1000. / Count;
        CostSum += Cost * Count; CostCount += Count;
        CostClock += Count * Tick60;
        if (CostClock >= 1.)
        {
            CostMean = float(CostSum / FMath::Max(1, CostCount)); CostWorst = float(CostMax);
            QueriesMean = float(QuerySum) / float(FMath::Max(1, CostCount)); QueriesWorst = QueryMax;
            CostSum = CostMax = CostClock = 0; CostCount = 0; QuerySum = 0; QueryMax = 0;
        }
    }
    Publish(Accumulator / Tick60, Dt, Input);
}

void FRideSession::SetMode(ERideState NewMode)
{
    if (Mode == NewMode) return;
    Mode = NewMode; ModeTime = 0;
    if (NewMode != ERideState::Air) bSteppingOff = bThroughLine = bBoxOffLine = false;
    // Every air starts its deadline afresh (TickAir), from where it left.
    else { AirLaunchVz = FMath::Max(0.f, float(V.Z)); AirStartP = P; AirGlance = 0; }
    // Every air picks its flight (TickAir); native's pumping starts afresh as the ground starts or ends.
    if (NewMode == ERideState::Air) bSelect = true;
    ResetPump();
}

void FRideSession::Tick(const FSkateInput& In, const atelier::skate::XboxState& Pad)
{
    // Flick-It reads the canonical pad with Native's own controls (RideFlick.h) every tick in every mode, so a
    // gesture's history runs on through a manual or a pop. The stance in effect picks the trick's mapping (Native
    // mirrors it for a regular rider); a flick out of a tail or nose grind maps from that end.
    using atelier::skate::GestureGroup;
    const GestureGroup Group = Mode != ERideState::Grind ? GestureGroup::Square : GrindKind == ERideGrind::FiveO ? GestureGroup::Tail :
        GrindKind == ERideGrind::Nosegrind || GrindKind == ERideGrind::Crooked ? GestureGroup::Nose : GestureGroup::Square;
    const Flick F = Flicks.Update(Pad, GoofyNow(), Group, Difficulty);
    // The manual's intentions run on the action graph, on the board in every mode (RideManual.h); off it they stop.
    if (Mode == ERideState::Bail || Mode == ERideState::GetUp) Manuals.Reset();
    else Manuals.ReadIntents(Flicks.Intents(), Mode == ERideState::Ground || Mode == ERideState::Powerslide || Mode == ERideState::Manual, Tick60);
    ModeTime += Tick60; Clock += Tick60;
    TickSlide = SlideYaw;
    if (TrickTime >= 0) TrickTime += Tick60;
    if (LandAge >= 0) LandAge += Tick60;
    RailCooldown = FMath::Max(0.f, RailCooldown - Tick60);
    if (In.bBail && Mode != ERideState::Bail && Mode != ERideState::GetUp) StartBail(TEXT("thrown off"));
    ReadSpinStick(In);
    switch (Mode)
    {
    case ERideState::Ground: case ERideState::Powerslide: case ERideState::Manual: TickGround(In, F); break;
    case ERideState::Air: TickAir(In, F); break;
    case ERideState::Grind: TickGrind(In, F); break;
    case ERideState::Bail: case ERideState::GetUp: TickBail(); break;
    }
    // The curvature's trail starts afresh on every return to the ground (and a manual's end is forgotten off it).
    if (Mode != ERideState::Ground && Mode != ERideState::Powerslide && Mode != ERideState::Manual) { TrailNum = 0; ManualOut = 0; }
    // Off the plain ground (a manual, a powerslide, the air, a bail) a turn round stops where it is.
    if (Mode != ERideState::Ground) { SwitchTime = -1; FakieTime = 0; }
    // The faces just climbed, for the lip test (TickAir reads them on its first ticks).
    if (Mode == ERideState::Ground || Mode == ERideState::Powerslide || Mode == ERideState::Manual)
    {
        ClimbUp[ClimbAt] = V.Z > 0 ? Q.GetUpVector() : FVector::UpVector;
        ClimbAt = (ClimbAt + 1) % ClimbTicks; ClimbNum = FMath::Min(ClimbNum + 1, ClimbTicks);
    }
    else if (Mode != ERideState::Air || AirTime > Tick60 * 2.f) ClimbNum = 0;
    // A line ends after a calm second on the ground.
    const bool bQuiet = Mode == ERideState::Ground && PendingPop == Flick::None;
    Calm = bQuiet ? Calm + Tick60 : 0.f;
    if (Calm > 1.f && (Line.Num() > 0 || !Holding.IsEmpty())) BankLine();
    TrackMotion();
    // Where this tick left the board: the next move's start.
    SafeP = P; SafeQ = Q; SafeDeck = DeckWorld(P, Q); bSafeDeck = true;
    ++Ticks;
}

ERideMotion FRideSession::CurrentMotion() const
{
    switch (Mode)
    {
    case ERideState::Ground:
        if (PendingPop != Flick::None) return ERideMotion::Pop;
        if (SwitchTime >= 0) return ERideMotion::Switch;
        if (PushTime >= 0) return ERideMotion::Push;
        if (BrakeTime > 0 || StillTime >= 0) return ERideMotion::Brake;
        if (Flicks.Loaded()) return ERideMotion::Load;
        if (LandAge >= 0 && LandAge < LandHold) return ERideMotion::Land;
        return ERideMotion::Roll;
    case ERideState::Powerslide: return ERideMotion::Powerslide;
    case ERideState::Manual:
        if (PendingPop != Flick::None) return ERideMotion::Pop;
        return bNoseManual ? ERideMotion::NoseManual : ERideMotion::Manual;
    case ERideState::Air: return ERideMotion::Air;
    case ERideState::Grind: return ERideMotion::Grind;
    case ERideState::Bail: return ERideMotion::Bail;
    case ERideState::GetUp: return ERideMotion::GetUp;
    }
    return ERideMotion::Roll;
}

void FRideSession::TrackMotion()
{
    const ERideMotion Now = CurrentMotion();
    if (Now == Motion) MotionTime += Tick60;
    else
    {
        bWasStill = Motion == ERideMotion::Brake && bStill;
        PreviousMotion = Motion; Motion = Now; MotionTime = 0;
    }
    bStill = StillTime >= 0;
}

float FRideSession::CatchTime(Flick F) const
{
    return Animator.CatchTime(F, FlipInfo(F).Time);
}

// ---------------------------------------------------------------------------------------------------------------
// Collision queries

bool FRideSession::Sweep(const FVector& From, const FVector& To, float Radius, FHitResult& Hit) const
{
    if (!Where.World) return false;
    FCollisionQueryParams Params(TEXT("RideSweep"), false, Where.Ignore);
    ++BoardQueries;
    return Where.World->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(Radius), Params);
}

bool FRideSession::Trace(const FVector& From, const FVector& To, FHitResult& Hit) const
{
    if (!Where.World) return false;
    FCollisionQueryParams Params(TEXT("RideTrace"), false, Where.Ignore);
    ++BoardQueries;
    return Where.World->LineTraceSingleByChannel(Hit, From, To, ECC_Pawn, Params);
}

bool FRideSession::IsLandable(const FHitResult& Hit) const
{
    const FVector N = Hit.ImpactNormal;
    if (Hit.bStartPenetrating || N.IsNearlyZero() || N.Z < -.1f) return false;
    if (N.Z >= Tune.WallSlope) return true;
    // A lip air comes back down onto the wall it left: a face turned the lip's way, near the lip's plane (not another
    // wall facing the same way elsewhere).
    if (bLipAir && FVector::DotProduct(N, LipOut) > .3f)
    {
        const float Out = FVector::DotProduct(FVector(Hit.ImpactPoint) - AirStartP, LipOut);
        if (Out > -LipBack && Out < LipBand) return true;
    }
    // A steeper face is a transition when the surface below the hit turns up from it, as a ramp's curve does; a wall,
    // a box's face or a rail's side goes on straight, ends or has nothing under it.
    const FVector Down = FVector::VectorPlaneProject(FVector(0, 0, -1), N).GetSafeNormal();
    if (Down.IsNearlyZero()) return false;
    for (const float Below : BendProbes)
    {
        const FVector At = FVector(Hit.ImpactPoint) + Down * Below;
        FHitResult Under;
        if (!Trace(At + N * 40.f, At - N * 20.f, Under) || Under.bStartPenetrating) return false;
        // The same face (a vert section above the curve): look further down.
        const FVector M = Under.ImpactNormal;
        const float Bend = AngleBetween(M, N);
        if (Bend < MinBend) continue;
        return Bend <= MaxBend && M.Z > N.Z;
    }
    return false;
}

void FRideSession::ResetWalls()
{
    ShownClip = FTransform::Identity; bSafeDeck = false;
    TickSlide = SlideYaw; StuckTime = 0; AirLaunchVz = 0; AirGlance = 0; AirStartP = P;
}

FTransform FRideSession::DeckWorld(const FVector& At, const FQuat& Frame) const
{
    const FTransform Deck = ShownClip * DeckPose() * FTransform(Frame, At + Frame.GetUpVector() * Tune.DeckHeight);
    // The shown board grows about its wheels' contact (USkateComponent::BoardGrowth): its pivot rises with it.
    const float Scale = FMath::Max(.25f, Where.BoardScale);
    const FQuat Rotation = Deck.GetRotation().GetNormalized();
    return FTransform(Rotation, Deck.GetLocation() + Rotation.GetUpVector() * Tune.DeckHeight * (Scale - 1.f));
}

FTransform FRideSession::DeckBox(const FTransform& Deck, float Clearance, FVector& Extent) const
{
    const float Scale = FMath::Max(.25f, Where.BoardScale);
    const float Bottom = -Tune.DeckHeight * Scale + Clearance, Top = DeckKick * Scale;
    Extent = FVector(DeckHalfLength * Scale, DeckHalfWidth * Scale, FMath::Max(.5f, (Top - Bottom) * .5f));
    return FTransform(Deck.GetRotation(), Deck.GetLocation() + Deck.GetRotation().GetUpVector() * ((Bottom + Top) * .5f));
}

bool FRideSession::SweepBox(const UWorld& World, const FTransform& From, const FTransform& To, const FVector& Extent, ECollisionChannel Channel,
    const FCollisionQueryParams& Params, const FCollisionResponseParams& Response, FHitResult& Hit, FTransform* Reached)
{
    const FCollisionShape Box = FCollisionShape::MakeBox(Extent);
    const FQuat R0 = From.GetRotation().GetNormalized(), R1 = To.GetRotation().GetNormalized();
    const float Turn = float(R0.AngularDistance(R1)) * float(Extent.Size());
    const int32 Steps = FMath::Clamp(FMath::CeilToInt(Turn / CornerStep), 1, RotationSteps);
    FVector A = From.GetLocation();
    for (int32 I = 1; I <= Steps; ++I)
    {
        const float T = float(I) / float(Steps);
        const FQuat R = Steps == 1 ? R1 : FQuat::Slerp(R0, R1, T).GetNormalized();
        const FVector B = FMath::Lerp(From.GetLocation(), To.GetLocation(), double(T));
        // A box standing still sweeps a hair, so one that starts (or turns) inside something still reports it.
        const FVector End = FVector::DistSquared(A, B) > 1e-4 ? B : A + FVector(0, 0, .01f);
        ++BoardQueries;
        if (World.SweepSingleByChannel(Hit, A, End, R, Channel, Box, Params, Response))
        {
            Hit.Time = (float(I - 1) + (Hit.bStartPenetrating ? 0.f : Hit.Time)) / float(Steps);
            if (Reached) *Reached = FTransform(R, Hit.bStartPenetrating ? A : FVector(Hit.Location));
            return true;
        }
        A = B;
    }
    return false;
}

FRideSession::EBoardHit FRideSession::SweepBoard(const FTransform& From, const FTransform& To, const FVector& Extent, const FVector& Up, bool bStopOnSupport, FHitResult& Hit) const
{
    if (!Where.World) return EBoardHit::Clear;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoard), false, Where.Ignore);
    // A face the board rolls on, by the steeper of the contact's normal and the face's.
    auto Rolls = [&](const FHitResult& H)
    {
        return FMath::Min(FVector::DotProduct(H.Normal, Up), FVector::DotProduct(H.ImpactNormal, Up)) >= Tune.WallSlope;
    };
    FTransform A = From, B = To;
    float Done = 0.f;   // the fraction of the whole move behind A
    for (int32 Pass = 0; Pass <= SupportSlides; ++Pass)
    {
        FHitResult H; FTransform At;
        if (!SweepBox(*Where.World, A, B, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, H, &At)) return EBoardHit::Clear;
        H.Time = Done + (1.f - Done) * H.Time;
        if (H.bStartPenetrating)
        {
            // In a wall: the caller's to leave. On (or tilted into) a face it rolls on: on from just off that face, so a
            // wall behind it still counts.
            if (H.Normal.IsNearlyZero() || !Rolls(H)) { Hit = H; return EBoardHit::Inside; }
            const FVector Off = H.Normal * (H.PenetrationDepth + .1f);
            A = FTransform(At.GetRotation(), At.GetLocation() + Off); B.AddToTranslation(Off);
            Done = H.Time;
            continue;
        }
        Hit = H;
        if (!Rolls(H)) return EBoardHit::Wall;
        if (bStopOnSupport) return EBoardHit::Support;
        // A face it rolls on (a ramp rising ahead): on along it for the rest of the move.
        const FVector Rest = FVector::VectorPlaneProject(B.GetLocation() - FVector(H.Location), H.Normal);
        A = FTransform(At.GetRotation(), FVector(H.Location) + H.Normal * .1f);
        B = FTransform(B.GetRotation(), A.GetLocation() + Rest);
        Done = H.Time;
    }
    return EBoardHit::Clear;
}

bool FRideSession::WallOverlap(const FTransform& Box, const FVector& Extent, const FVector& Up, FVector& Push, FVector& Normal) const
{
    Push = Normal = FVector::ZeroVector;
    if (!Where.World) return false;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardOverlap), false, Where.Ignore);
    const FCollisionShape Shape = FCollisionShape::MakeBox(Extent);
    TArray<FOverlapResult> Overlaps;
    Where.World->OverlapMultiByChannel(Overlaps, Box.GetLocation(), Box.GetRotation(), ECC_Pawn, Shape, Params);
    ++BoardQueries;
    bool bAny = false;
    float Deepest = -1.f;
    for (const FOverlapResult& Overlap : Overlaps)
    {
        UPrimitiveComponent* Other = Overlap.GetComponent();
        if (!Other || !Overlap.bBlockingHit) continue;
        // Each component's (or instance's) own way out; faces the board rolls on are the ground's.
        FMTDResult Out;
        const FBodyInstance* Body = Other->GetBodyInstance(NAME_None, true, Overlap.ItemIndex);
        ++BoardQueries;
        if (!Body || !Body->OverlapTest(Box.GetLocation(), Box.GetRotation(), Shape, &Out)) continue;
        if (FVector::DotProduct(Out.Direction, Up) >= Tune.WallSlope) continue;
        bAny = true;
        Push += Out.Direction * Out.Distance;
        if (Out.Distance > Deepest) { Deepest = Out.Distance; Normal = Out.Direction; }
    }
    return bAny;
}

bool FRideSession::LeaveWall(const FTransform& From, FVector& ToP, const FQuat& ToQ, float Clearance, bool bOnPlane, FHitResult& Wall) const
{
    const FVector Up = ToQ.GetUpVector();
    FVector At = ToP, Extent;
    for (int32 Try = 0; Try < 3; ++Try)
    {
        const FTransform Box = DeckBox(DeckWorld(At, ToQ), Clearance, Extent);
        FVector Push, Normal;
        if (!WallOverlap(Box, Extent, Up, Push, Normal))
        {
            // Free of walls. Not pushed at all: the move went through a wall rather than ending in one. Pushed: the box's
            // centre must get here from where the move started without crossing anything (the way out of a thin wall
            // can lead to its far side).
            FHitResult Between;
            if (Try == 0 || Trace(From.GetLocation(), Box.GetLocation(), Between)) return false;
            ToP = At;
            return true;
        }
        if (bOnPlane) Push = FVector::VectorPlaneProject(Push, Up);
        if (Push.IsNearlyZero()) return false;
        At += Push + Push.GetSafeNormal() * .2f;
        if (FVector::Dist(At, ToP) > MaxPush) return false;
        Wall = FHitResult(); Wall.bBlockingHit = true; Wall.Normal = Wall.ImpactNormal = Normal;
    }
    return false;
}

FRideSession::EBoardMove FRideSession::MoveBoardPose(FVector& ToP, FQuat& ToQ, float Clearance, FHitResult& Wall) const
{
    // From where the last tick left the board, unless a placement has moved it since.
    const bool bFromSafe = bSafeDeck && FVector::DistSquared(SafeP, ToP) < FMath::Square(SafeReach);
    const FVector BaseP = bFromSafe ? SafeP : P;
    const FQuat BaseQ = bFromSafe ? SafeQ : Q;
    FVector Extent;
    const FTransform From = DeckBox(bFromSafe ? SafeDeck : DeckWorld(P, Q), Clearance, Extent);
    const FTransform To = DeckBox(DeckWorld(ToP, ToQ), Clearance, Extent);
    const EBoardHit Got = SweepBoard(From, To, Extent, ToQ.GetUpVector(), false, Wall);
    if (Got == EBoardHit::Clear) return EBoardMove::Clear;
    const float Length = float(FVector::Dist(From.GetLocation(), To.GetLocation()));
    auto StopAt = [&](float T)
    {
        ToP = FMath::Lerp(BaseP, ToP, double(T)); ToQ = FQuat::Slerp(BaseQ, ToQ, T).GetNormalized();
    };
    if (Got == EBoardHit::Wall)
    {
        // Up to the face, a hair short of it.
        StopAt(FMath::Max(0.f, Wall.Time - .1f / FMath::Max(Length, .1f)));
        return EBoardMove::Corrected;
    }
    // Inside: the box would turn or be set into a wall. Out of it where the move ends, if a free pose is near; else as
    // far as the box went clear; else nowhere.
    const FHitResult Inside = Wall;
    if (LeaveWall(From, ToP, ToQ, Clearance, Mode != ERideState::Air, Wall)) return EBoardMove::Corrected;
    Wall = Inside;
    if (Inside.Time > 0.f) { StopAt(Inside.Time); return EBoardMove::Corrected; }
    ToP = BaseP; ToQ = BaseQ;
    return EBoardMove::Unresolved;
}

bool FRideSession::Probe(const FVector& Base, const FVector& Up, float Above, float Below, FVector& Point, FVector& Normal, bool& bBlocked, FVector* Block, const FVector& Toward) const
{
    const float R = Tune.WheelRadius;
    FHitResult Hit;
    if (!Sweep(Base + Up * (Above + R), Base - Up * (Below - R), R, Hit)) return false;
    // Started inside ground: look again from higher. A face there that rises against the travel (a tight concave
    // transition, a bank's foot) is ground to follow; a raised face level with the deck stays a step too high.
    if (Hit.bStartPenetrating && FVector::DotProduct(Hit.Normal, Up) >= Tune.WallSlope && !Toward.IsNearlyZero())
    {
        FHitResult Higher;
        const float Over = Above + Tune.StepUp + 2.f * R;
        if (Sweep(Base + Up * (Over + R), Base - Up * (Below - R), R, Higher) && !Higher.bStartPenetrating &&
            FVector::DotProduct(Higher.Normal, Toward.GetSafeNormal()) < -.08f)
            Hit = Higher;
    }
    Normal = Hit.Normal;
    // A face too steep for the deck (or one the wheel starts inside) is a wall or a curb, not ground.
    if (Hit.bStartPenetrating || FVector::DotProduct(Normal, Up) < Tune.WallSlope)
    {
        bBlocked = true;
        if (Block && (Block->IsZero() || FVector::DotProduct(Toward, Normal) < FVector::DotProduct(Toward, *Block))) *Block = Normal;
        return false;
    }
    Point = Hit.Location - Up * R;
    return true;
}

bool FRideSession::FindGround(const FVector& At, const FQuat& InFrame, float Below, FVector& OutP, FVector& OutUp, FVector& OutForward, bool& bBlocked, FVector* Block, const FVector& Toward) const
{
    const FVector Up = InFrame.GetUpVector(), Forward = InFrame.GetForwardVector();
    FVector FrontP, FrontN, BackP, BackN;
    const bool bFront = Probe(At + Forward * Tune.AxleX, Up, Tune.StepUp, Below, FrontP, FrontN, bBlocked, Block, Toward);
    const bool bBack = Probe(At - Forward * Tune.AxleX, Up, Tune.StepUp, Below, BackP, BackN, bBlocked, Block, Toward);
    if (bFront && bBack)
    {
        OutUp = (FrontN + BackN).GetSafeNormal();
        OutForward = FVector::VectorPlaneProject(FrontP - BackP, OutUp).GetSafeNormal();
        if (OutForward.IsNearlyZero()) OutForward = FVector::VectorPlaneProject(Forward, OutUp).GetSafeNormal();
        // The deck's centre rides on the line between the axles' contacts.
        OutP = (FrontP + BackP) * .5f;
        return true;
    }
    if (bFront || bBack)
    {
        // One axle down: keep the deck on that axle's face (a crest or an edge is passing under the board).
        const FVector N = bFront ? FrontN : BackN, C = bFront ? FrontP : BackP;
        OutUp = N; OutForward = FVector::VectorPlaneProject(Forward, N).GetSafeNormal();
        OutP = C - OutForward * (bFront ? Tune.AxleX : -Tune.AxleX);
        return true;
    }
    // A narrow crest between the axles.
    FVector CP, CN;
    if (Probe(At, Up, Tune.StepUp, Below, CP, CN, bBlocked, Block, Toward))
    {
        OutUp = CN; OutForward = FVector::VectorPlaneProject(Forward, CN).GetSafeNormal(); OutP = CP;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------------------------------------------
// Ground: rolling, pushing, steering, braking, powerslides, pumping, manuals and pops.

void FRideSession::TickGround(const FSkateInput& In, Flick F)
{
    const FVector Up = Q.GetUpVector();
    FVector Forward = Q.GetForwardVector();
    float Speed = FVector::DotProduct(V, Forward) * Travel;
    if (Speed < 0) { Travel = -Travel; Speed = -Speed; }
    const FVector Dir = Forward * Travel;
    const bool bFlat = Up.Z > .8f;
    const float StickX = FMath::Abs(In.Left.X) > .06f ? float(In.Left.X) : 0.f;

    // Pops, timed as Native's motion graph times them until its events drive Ride: the recognised trick starts its
    // ground clip (TakeOff) on the tick it is recognised; when that clip is about to end the air clip takes over
    // (LeftGround), and the board leaves on the tick after the ground clip's last. Out of a manual, or within
    // ManualOutTime of one (TakeOff.FromManual), the ground clip jumps in at its MANUALINTO point, two thirds through.
    const bool bWasManual = Mode == ERideState::Manual;
    if (F != Flick::None && PendingPop == Flick::None && Mode != ERideState::Powerslide)
    {
        PendingPop = F; PendingEvent = Flicks.Event(); PendingLoad = Flicks.PopLoad(); Cues.Add(ERideCue::Flick);
        PopWait = Animator.PopDelay(F, Tune.PopDelay);
        bPopFromManual = bWasManual || ManualOut > 0.f;
        PopTimer = bPopFromManual ? PopWait * ManualInto : 0.f;
    }
    if (PendingPop != Flick::None)
    {
        PopTimer += Tick60;
        if (PopTimer > PopWait + Tick60 * .5f)
        {
            const Flick Pop = PendingPop; PendingPop = Flick::None; bPopFromManual = false;
            if (Mode == ERideState::Manual) { EndHold(); SetMode(ERideState::Ground); }
            StartTrick(Pop);
            LeaveWhy = TEXT("pop");
            TakeOff(PopSpeed(PendingLoad) * (IsNollie(Pop) ? Tune.NollieScale : 1.f));
            return;
        }
    }

    // Manuals, as Native's motion graph runs them (RideManual.h): one starts from plain ground once the Manual
    // intention has been held 0.2 s, takes its side from the intention's sign (switching with it), and ends when the
    // intention goes; a pop already under way finishes first. Native's controller tips the deck (no rig: the deck
    // shown; with one the clips' own tilt) and never throws the rider off. Riding.Brake, which the brake button starts,
    // keeps Idle, and with it a manual, waiting until it has played out.
    TryManual();
    Manuals.Riding(Mode == ERideState::Ground && PendingPop == Flick::None, Tick60);
    if (Mode == ERideState::Manual)
    {
        const atelier::ride::ManualSide Side = Manuals.Side();
        if (Side == atelier::ride::ManualSide::None && PendingPop == Flick::None) { EndHold(); SetMode(ERideState::Ground); Manuals.End(); }
        else
        {
            // A pop under way has left the manual in Native's graph (TakeOff.FromManual): its side stays as it was.
            if (Side != atelier::ride::ManualSide::None && PendingPop == Flick::None) bNoseManual = Side == atelier::ride::ManualSide::Nose;
            Hold(bNoseManual ? TEXT("Nose Manual") : TEXT("Manual"), 150.f, Tick60);
            if (PendingPop == Flick::None) Manuals.Hold(Tick60);
            if (const atelier::ride::FlickBank* Bank = Flicks.GetBank())
                Manuals.StepDeck(Bank->Manual, Difficulty, atelier::ride::ManualDeck{Tune.ManualDeckGain, Tune.ManualDeckDamping, Tune.ManualDeckWeight}, Speed / 100.f, Tick60);
        }
    }
    // The manual's out timer: set as it ends, counted down on the ground after.
    ManualOut = Mode == ERideState::Manual ? 0.f : bWasManual ? ManualOutTime : FMath::Max(0.f, ManualOut - Tick60);

    // Powerslides: the deck turns across the travel and scrubs speed. The powerslide key holds one; on a pad the left
    // stick's rear diagonal does, as native's slide intents read it: pushing the stick out past 0.9 into the 52
    // degrees either side of straight back starts one on that side, and it lasts while the stick stays out past 0.9
    // between the other side's sideways line and 115 degrees round its own side.
    const float Reach = In.Left.Size();
    const float StickAngle = Reach > 0 ? FMath::Atan2(float(In.Left.X), float(-In.Left.Y)) : 0.f;   // from straight back, + right
    const bool bSector = Reach > .9f && StickAngle != 0 && FMath::Abs(StickAngle) < .91f;
    if (Mode != ERideState::Ground && Mode != ERideState::Powerslide) StickSlide = 0;
    else if (bSector && !bStickSector) StickSlide = StickAngle > 0 ? 1 : -1;
    else if (StickSlide != 0 && !(Reach > .9f && StickSlide * StickAngle > -UE_HALF_PI && StickSlide * StickAngle < 2.f)) StickSlide = 0;
    bStickSector = bSector;
    const bool bSlideHeld = In.bPowerslide || StickSlide != 0;
    if (Mode == ERideState::Ground && bSlideHeld && Speed > Tune.SlideMinSpeed && PendingPop == Flick::None)
        SetMode(ERideState::Powerslide);
    float Decel = 0;
    if (Mode == ERideState::Powerslide)
    {
        const float Side = StickSlide != 0 ? float(StickSlide) : In.Left.X < 0 ? -1.f : 1.f;
        SlideYaw = FMath::FixedTurn(SlideYaw, Side * Tune.SlideAngle, Tune.SlideTurnRate * Tick60);
        Decel += Curve(SlideCurve, Speed) * Tune.SlideDecel * FMath::Abs(FMath::Sin(FMath::DegreesToRadians(SlideYaw)));
        if (!bSlideHeld || Speed < 40.f) SetMode(ERideState::Ground);
    }
    else SlideYaw = FMath::FixedTurn(SlideYaw, 0.f, Tune.SlideTurnRate * Tick60);

    // Steering: the native stick curve at riding speed, a kick turn at rest; sideways gravity on a slope turns the
    // board downhill.
    float Target = 0;
    if (Mode != ERideState::Powerslide)
    {
        const float Riding = FMath::Sign(StickX) * Curve(SteerCurve, FMath::Abs(StickX)) / .835f * (Tune.MaxYawRate + Tune.YawRatePerSpeed * Speed);
        const float Pivot = StickX * Tune.PivotRate;
        Target = FMath::Lerp(Pivot, Riding, FMath::Clamp(Speed / Tune.PivotSpeed, 0.f, 1.f));
        if (Mode == ERideState::Manual) Target *= .6f;
    }
    TurnRate += (Target - TurnRate) * Damp(Tune.SteerResponse, Tick60);
    const FVector Gravity(0, 0, -G);
    FVector Slope = FVector::VectorPlaneProject(Gravity, Up);
    if (Slope.Size() > Tune.GravityLimit) Slope = Slope.GetSafeNormal() * Tune.GravityLimit;
    float FallTurn = 0;
    if (Speed > 30.f && Mode != ERideState::Powerslide)
        FallTurn = FMath::RadiansToDegrees(FVector::DotProduct(Slope, FVector::CrossProduct(Up, Dir)) / FMath::Max(Speed, 150.f)) * Tune.FallLineSteer;
    Q = (Turn(Up, (TurnRate + FallTurn) * Tick60) * Q).GetNormalized();
    Forward = Q.GetForwardVector();

    // Speed along the travel: slope, friction, push, brake.
    Speed += FVector::DotProduct(Slope, Forward * Travel) * Tick60;
    if (Speed < 0) { Travel = -Travel; Speed = -Speed; }
    Decel += Tune.RollingResistance + Curve(FrictionCurve, Speed);
    // In a manual Native's speed model adds its manual friction (FrictionVsSpeed_Manual, m/s^2 at m/s).
    if (Mode == ERideState::Manual)
        if (const atelier::ride::FlickBank* Bank = Flicks.GetBank()) Decel += Bank->Manual.Friction.Evaluate(Speed / 100.f) * 100.f;

    // Pushing, in time with the push cycle; a tap gives one weak push.
    const bool bCanPush = Mode == ERideState::Ground && bFlat && PendingPop == Flick::None && !In.bBrake;
    // Fakie, the rider turns round on the board first (native's PushFromFakie and Turning.Switch): a push turns the
    // switch clip at SwitchPushRate and starts SwitchPushLead before its end; rolling fakie on flat ground for
    // FakieSwitchTime, or at once riding switch (turning back to the rider's own stance), it plays at its own rate and
    // the roll follows from its end (not over a landing's give). A crawl is not fakie: slower than PushFromRest a push
    // goes nose first (StartPush), and the rider only turns round by himself from SwitchMinSpeed.
    if (SwitchTime >= 0)
    {
        if (!bCanPush || RiderTravel() > 0 || Flicks.Loaded() || Flicks.ManualIntent()) SwitchTime = -1;
        else
        {
            SwitchTime += Tick60;
            // A push asked during a turn by itself starts as the turn ends.
            if (In.bPush && !bSwitchPush) { bSwitchPush = true; FlipAt = FMath::Max(SwitchTime, FMath::Min(FlipAt, Animator.SwitchLength() - SwitchQueueLead)); }
        }
    }
    FakieTime = Mode == ERideState::Ground && bFlat && RiderTravel() < 0 && Speed >= Tune.SwitchMinSpeed ? FakieTime + Tick60 : 0.f;
    const bool bLanding = LandAge >= 0 && LandAge < LandHold;
    const bool bTurnByItself = !bLanding && Speed >= Tune.SwitchMinSpeed && (bSwitch || FakieTime > Tune.FakieSwitchTime);
    if (SwitchTime < 0 && PushTime < 0 && bCanPush && RiderTravel() < 0 && Animator.SwitchLength() > 0 && !Flicks.Loaded() &&
        !Flicks.ManualIntent() && ((In.bPush && Speed >= Tune.PushFromRest) || bTurnByItself))
        StartSwitch(In.bPush);
    if (SwitchTime >= 0 && SwitchTime >= FlipAt - KINDA_SMALL_NUMBER)
    {
        // The turn's end: the rider stands the other way round on the board, the other foot forward. Only the stance
        // in effect and the rider's frame change; the board, its travel and its velocity go on as they were.
        bSwitch = !bSwitch; ++Turns;
        SwitchTime = -1; FakieTime = 0;
        if (bSwitchPush) StartPush(true, Speed);
    }
    else if (SwitchTime < 0 && bCanPush && In.bPush && PushTime < 0) StartPush(true, Speed);
    if (PushTime >= 0)
    {
        if (!bCanPush) PushTime = -1;
        else
        {
            PushTime += Tick60;
            // From rest the push goes nose-first, and the board stands on the planted foot through the wind-up: it
            // neither creeps back down a slope nor leaves tail-first.
            if (bPushFromRest && PushTime < PushLead + PushContact)
            {
                if (RiderTravel() < 0) { Travel = -Travel; Speed = -Speed; }
                if (PushTime < PushLead) Speed = FMath::Max(Speed, 0.f);
            }
            if (!In.bPush && PushTime < PushLead) bPushStrong = false;
            const bool bContact = PushTime >= PushLead && PushTime < PushLead + PushContact;
            if (bContact && !bPushed) { bPushed = true; Cues.Add(ERideCue::Push); }
            if (bContact)
            {
                const float Top = Tune.PushTopSpeed * Prefs.PushSpeed;
                const float Aim = bPushStrong ? (Tune.PushTarget + Tune.PushTargetSlope * LastSpeed) * Prefs.PushSpeed
                                              : LastSpeed + FMath::Max(115.f, Tune.PushTapTarget - .1f * LastSpeed);
                const float Goal = FMath::Min(Aim, Top);
                // Native's push: a velocity change each tick of the contact, PushDvStart from rest easing to PushDvEnd
                // at PushFastFrom, never past the goal (the fast push's shorter contact gives less).
                const float Dv = FMath::Lerp(Tune.PushDvStart, Tune.PushDvEnd, FMath::Clamp(Speed / FMath::Max(1.f, Tune.PushFastFrom), 0.f, 1.f)) * Prefs.PushPower;
                if (Speed < Goal) Speed = FMath::Min(Goal, Speed + Dv);
            }
            else if (!bPushed) LastSpeed = Speed;
            if (PushTime >= PushLead + PushContact + PushRecover)
            {
                if (In.bPush) { StartPush(false, Speed); LastSpeed = Speed; }
                else PushTime = -1;
            }
        }
    }
    if (PushTime < 0) LastSpeed = Speed;

    // Braking: the foot reaches the ground, then scrubs.
    BrakeTime = In.bBrake && Mode == ERideState::Ground ? BrakeTime + Tick60 : 0.f;
    if (BrakeTime > Tune.BrakeDelay) Decel += Tune.BrakeDecel;
    Speed = FMath::Max(0.f, Speed - Decel * Tick60);
    if (BrakeTime > Tune.BrakeDelay && Speed < 12.f) Speed = 0;
    // Standing after braking to a stop, until the board rolls again.
    if (BrakeTime > Tune.BrakeDelay && Speed <= 0) StillTime = StillTime < 0 ? 0.f : StillTime + Tick60;
    else if (StillTime >= 0 && Speed < 20.f && PushTime < 0 && Mode == ERideState::Ground) StillTime += Tick60;
    else StillTime = -1;

    // Pumping, native's own (Pump, RideNative.cpp; RIDE.md "Pumping"): the triggers crouch the rider (the deeper of the
    // two, a held trigger button a full pull, as native reads the pad), and the ground's angle crouches him at least
    // MinCrouchVsGroundAngle (a coasting rider sinks into a transition and rises out of it). Native's pumping reads his
    // centre of mass over the deck rising as he stands up while the ground turns under him.
    const float Trigger = FMath::Max(In.LeftPull(), In.RightPull());
    const float Steepness = FMath::Acos(FMath::Clamp(float(Up.Z), -1.f, 1.f)) / HALF_PI;
    const float Load = FMath::Max(Trigger, Curve(MinCrouchCurve, Steepness));
    const float CrouchTarget = PendingPop != Flick::None || Flicks.Loaded() ? 1.f : .25f + .75f * Load;
    Crouch += (CrouchTarget - Crouch) * Damp(Tune.CrouchRate, Tick60);
    Pump(Speed, Trigger > 0);

    V = Forward * Travel * Speed;
    WheelSpin = FMath::Fmod(WheelSpin + FVector::DotProduct(V, Forward) * Tick60 / (2 * PI * Tune.WheelRadius) * 360.f, 360.f);

    // Move in steps of at most GroundStep, so the probes and the crest test follow the surface at any speed (a fast
    // board probing a whole tick ahead would start inside a tight transition).
    const int32 Steps = FMath::Clamp(FMath::CeilToInt(Speed * Tick60 / FMath::Max(1.f, Tune.GroundStep)), 1, 8);
    for (int32 I = 0; I < Steps; ++I)
        if (!MoveOnGround(Tick60 / Steps, Speed)) return;
    // Upside down on a wall at a crawl: fall off.
    if (Q.GetUpVector().Z < -.2f && Speed < 150.f) { StartBail(TEXT("stall on the wall")); return; }
    if (Mode == ERideState::Ground && Holding.IsEmpty() == false && Holding.Contains(TEXT("Manual"))) EndHold();
}

void FRideSession::Deflect(const FVector& Normal, float& Speed)
{
    const float Into = -FVector::DotProduct(V, Normal);
    if (Into <= 0) return;
    const FVector Up = Q.GetUpVector();
    V += Normal * Into * (1.f + Tune.WallRestitution);
    const FVector Along = FVector::VectorPlaneProject(V, Up);
    // Turn the board along the face, keeping the nose or tail that was leading.
    if (Along.Size() > 20.f) Q = Frame(Up, Along.GetSafeNormal() * Travel);
    Speed = V.Size(); TurnRate = 0;
}

void FRideSession::AddTrail(float At, const FVector& Up)
{
    if (TrailNum > 0 && At - TrailAt[TrailNum - 1] < 10.f) return;
    if (TrailNum == TrailMax)
    {
        for (int32 I = 1; I < TrailMax; ++I) { TrailAt[I - 1] = TrailAt[I]; TrailUp[I - 1] = TrailUp[I]; }
        --TrailNum;
    }
    TrailAt[TrailNum] = At; TrailUp[TrailNum] = Up; ++TrailNum;
    // Keep the odometer small.
    if (TrailAt[0] > 1e5f)
    {
        const float Base = TrailAt[0];
        for (int32 I = 0; I < TrailNum; ++I) TrailAt[I] -= Base;
        Odometer -= Base;
    }
}

bool FRideSession::MoveOnGround(float Dt, float& Speed)
{
    const FVector Up = Q.GetUpVector();
    const FVector Dir = Q.GetForwardVector() * Travel;
    if (TrailNum == 0) AddTrail(Odometer, Up);

    // Move, stopping at walls: the board's whole box (the deck shown, from a step's height up to its kicks) from where
    // the last tick left it, its turn included (MoveBoardPose).
    const float Clearance = Tune.StepUp + BoxClearance;
    FVector Next = P + V * Dt;
    FQuat NextQ = Q;
    FHitResult Wall;
    const EBoardMove Moved = MoveBoardPose(Next, NextQ, Clearance, Wall);
    if (Moved == EBoardMove::Unresolved)
    {
        // Inside a wall it cannot leave: the board stays where it is (its velocity into the wall goes), and stuck that
        // way for StuckLimit the rider falls.
        StuckTime += Dt;
        if (StuckTime > StuckLimit) { LogStuck(TEXT("on the ground"), Wall); StartBail(TEXT("stuck in a wall")); return false; }
        const FVector N = FVector::VectorPlaneProject(Wall.Normal, Up).GetSafeNormal();
        if (!N.IsNearlyZero()) Deflect(N, Speed);
        return false;
    }
    StuckTime = 0;
    if (Moved == EBoardMove::Corrected)
    {
        FVector N = FVector::VectorPlaneProject(Wall.ImpactNormal, Up).GetSafeNormal();
        if (FVector::DotProduct(Wall.ImpactNormal, Up) >= Tune.WallSlope || N.IsNearlyZero()) N = FVector::VectorPlaneProject(Wall.Normal, Up).GetSafeNormal();
        if (!N.IsNearlyZero())
        {
            if (-FVector::DotProduct(V, N) > Tune.WallBailSpeed) { StartBail(TEXT("wall")); return false; }
            Deflect(N, Speed);
        }
        Q = NextQ;
    }

    // Follow the surface; leave it when it falls away faster than the board can follow.
    FVector Ground, NewUp, NewForward, Block = FVector::ZeroVector; bool bBlocked = false;
    const float Below = Tune.StickGap + Tune.StickPerSpeed * Speed * Dt;
    if (!FindGround(Next, Q, Below, Ground, NewUp, NewForward, bBlocked, &Block, V))
    {
        if (!bBlocked) { P = Next; LeaveWhy = TEXT("no ground below"); TakeOff(0.f); return false; }
        // A face too steep to roll onto (a curb, a step) under a wheel. As in the native runtime, the board's closing
        // velocity along the face's normal throws the rider when it is fast across the deck (CurbBail) or along its
        // normal (CurbImpact); otherwise the board stops against the face, turned along it.
        const FVector Closing = Block * FMath::Max(0.f, float(-FVector::DotProduct(V, Block)));
        const float AlongUp = FVector::DotProduct(Closing, Up);
        if ((Closing - Up * AlongUp).Size() > Tune.CurbBail || FMath::Abs(AlongUp) > Tune.CurbImpact) { StartBail(TEXT("curb")); return false; }
        const FVector Face = FVector::VectorPlaneProject(Block, Up).GetSafeNormal();
        if (Face.IsNearlyZero()) { V = FVector::ZeroVector; Speed = 0; }
        else Deflect(Face, Speed);
        return false;
    }
    // Curvature along the travel, over at least CrestWindow of it (the wheelbase and more, so a transition built of
    // flat facets reads as the curve it approximates): the normal's turn per cm. A convex crest launches the board when
    // following it would take more than LaunchFactor g, beyond the CrestReach the rider's legs absorb.
    const float At = Odometer + float(FVector::Dist(P, Ground));
    int32 Base = 0;
    for (int32 I = TrailNum - 1; I >= 0; --I)
        if (At - TrailAt[I] >= Tune.CrestWindow) { Base = I; break; }
    const float Window = FMath::Max(At - TrailAt[Base], Tune.CrestWindow);
    const float Turned = FMath::DegreesToRadians(AngleBetween(TrailUp[Base], NewUp));
    const float Sign = FVector::DotProduct(NewUp - TrailUp[Base], Dir) > 0 ? -1.f : 1.f;   // convex crests tilt the normal forward
    Curvature = Sign * Turned / Window;
    const float Hold = FMath::Max(0.f, float(-FVector::DotProduct(FVector(0, 0, -G), Up)));
    const float Absorbed = 2.f * Tune.CrestReach / (Window * Window);
    if (Sign < 0 && Turned > FMath::DegreesToRadians(2.f) && Speed * Speed * (Turned / Window - Absorbed) > Tune.LaunchFactor * FMath::Max(Hold, 1.f))
    {
        P = Next; LeaveWhy = TEXT("crest"); TakeOff(0.f); return false;
    }
    // Keep the board's heading (nose or tail leading) in the new plane. The fit turns the whole box too: checked from
    // where the last tick left it, kept as far as it is free.
    const FVector Heading = FVector::VectorPlaneProject(Q.GetForwardVector(), NewUp).GetSafeNormal();
    FVector Fit = Ground;
    FQuat FitQ = Frame(NewUp, Heading.IsNearlyZero() ? NewForward : Heading);
    if (MoveBoardPose(Fit, FitQ, Clearance, Wall) == EBoardMove::Unresolved) { Fit = Next; FitQ = Q; }
    P = Fit; Q = FitQ; Odometer = At;
    AddTrail(At, NewUp);
    V = Q.GetForwardVector() * Travel * Speed;
    return true;
}

void FRideSession::StartSwitch(bool bPush)
{
    const float Length = Animator.SwitchLength();
    SwitchTime = 0; bSwitchPush = bPush; FakieTime = 0;
    SwitchRate = bPush ? FMath::Max(.1f, Tune.SwitchPushRate) : 1.f;
    FlipAt = bPush ? FMath::Max(0.f, Length / SwitchRate - Tune.SwitchPushLead) : FMath::Max(0.f, Length - SwitchEndLead);
}

void FRideSession::StartPush(bool bFirstPush, float Speed)
{
    PushTime = 0; bPushStrong = true; bPushed = false;
    bPushFromRest = bFirstPush && Speed < Tune.PushFromRest;
    PushCount = bFirstPush ? 0 : PushCount + 1;
    // The push clips' blend, as native's push target picks it: by the speed between the slow push's (from rest) and the
    // fast one's (8.5 m/s), weighed by their contact lengths (VelocityBlend).
    PushStrong = FMath::Clamp((Speed - 450.f) / 700.f, 0.f, 1.f);
    float Lead, Recover, Slow, Fast;
    if (Animator.PushTiming(false, 0.f, Lead, Slow, Recover) && Animator.PushTiming(false, 1.f, Lead, Fast, Recover))
    {
        const float At = FMath::Clamp(Speed / 100.f, 0.f, 8.5f), Low = Slow * At, High = Fast * (8.5f - At);
        PushStrong = Low + High > 0 ? FMath::Clamp(Low / (Low + High), 0.f, 1.f) : 0.f;
    }
    if (!Animator.PushTiming(bFirstPush, PushStrong, PushLead, PushContact, PushRecover))
    {
        PushLead = Tune.PushContact; PushContact = Tune.PushContactLength;
        PushRecover = FMath::Max(.05f, Tune.PushCycle - PushLead - PushContact);
    }
}

float FRideSession::PopSpeed(float Load) const
{
    // The rise from the load (RideTuning.h, "Pop"), then the take-off speed that reaches it under air gravity.
    const float Charge = 1.f - FMath::Exp(-FMath::Max(0.f, Load - 4.f / 60.f) / FMath::Max(.01f, Tune.PopLoadTime));
    const float Height = FMath::Lerp(Tune.PopHeightQuick, Tune.PopHeight, Charge) * FMath::Pow(FMath::Max(.5f, Prefs.Pop), 1.6f);
    return FMath::Sqrt(2.f * Tune.AirGravity * Height);
}

void FRideSession::StartTrick(Flick F)
{
    Trick_ = F; TrickTime = 0; bTrickFakie = RiderTravel() < 0; bTrickSwitch = bSwitch;
}

void FRideSession::TakeOff(float Pop)
{
    const FVector Up = Q.GetUpVector();
    V += Up * Pop;
    bPopped = Pop > 0;
    // Vert assist and transfers are applied on the first air tick (TickAir), where the transfer input is read.
    SetMode(ERideState::Air);
    AirTime = 0; TakeoffUp = Up; SpinTotal = 0; bLipAir = false;
    // A carve carries a little turn into the air (the spin's controller takes it from there).
    SpinRate = FMath::Clamp(TurnRate * Tune.SpinCarry, -Tune.SpinCarryMax, Tune.SpinCarryMax);
    TurnRate = 0; SlideYaw = 0; PushTime = -1; BrakeTime = 0; StillTime = -1; Manuals.End(); EndHold();
    LastGrab = ERideGrab::None; SinceGrab = -1;
    ResetPrediction(P + Up * 12.f);
}

void FRideSession::ResetPrediction(const FVector& From)
{
    PredictFrom = From; PredictVelocity = V; PredictTime = 0; PredictStart = AirTime; LandTime = -1; PredictEnd = -1; LandNormal = FVector::UpVector;
}

// ---------------------------------------------------------------------------------------------------------------
// Air: ballistic flight, spins, the flip, grabs, grinds, landing.

void FRideSession::AdvancePrediction(int32 Segments)
{
    // A prediction the flight has overtaken (the board flew past its landing, or past the face that ended the trace:
    // it glanced off it or missed it) starts again from where the board is.
    const float Flown = AirTime - PredictStart;
    if ((LandTime >= 0 && Flown > LandTime + 2.f * Tick60) || (PredictEnd >= 0 && Flown > PredictEnd + 2.f * Tick60))
        ResetPrediction(P + Q.GetUpVector() * 12.f);
    // Trace the path of the deck's centre a tenth of a second at a time, up to 3 s ahead, to the first face the board
    // can land on (IsLandable). The path is the flight's own (each tick's gravity reaches the velocity before it moves:
    // half a tick's fall more a second than the parabola). A face it cannot land on (a wall, the underside of a deck)
    // ends the trace without a landing, and so does a start inside something: the deck never levels to either.
    if (LandTime >= 0 || PredictEnd >= 0) return;
    for (int32 I = 0; I < Segments; ++I)
    {
        const float Dt = .1f;
        const FVector From = PredictFrom, To = From + PredictVelocity * Dt + FVector(0, 0, -.5f * Gravity() * (Dt * Dt + Dt * Tick60));
        FHitResult Hit;
        if (Sweep(From, To, 10.f, Hit))
        {
            PredictEnd = Hit.bStartPenetrating ? PredictTime : PredictTime + Dt * Hit.Time;
            if (!Hit.bStartPenetrating && IsLandable(Hit)) { LandTime = PredictEnd; LandNormal = Hit.Normal; }
            return;
        }
        PredictFrom = To; PredictVelocity.Z -= Gravity() * Dt; PredictTime += Dt;
        if (PredictTime > 3.f) { PredictEnd = PredictTime; return; }
    }
}

float FRideSession::Gravity() const
{
    return bLipAir ? Tune.VertGravity : Tune.AirGravity;
}

void FRideSession::ChooseLanding()
{
    // A lip air's flight (bLipAir), by native's cone (AirTrajectoryLaunch): the velocity and six around it, 10 degrees
    // across its level heading and 40 along it at a cone speed of 2 to 4 m/s, none faster than the velocity. Each flies
    // under the lip's gravity for up to 3 s; a miss or a landing within .25 s does not count. The score is native's
    // transition term: the landing face's normal along the lip's (the face it left scores most, steepest highest, the
    // deck behind the coping nothing), scaled by the take-off face's steepness, less 500 for coming down within .15 s
    // of the apex; then the smallest change (a tenth of a point per cm/s). Any other air keeps its take-off. The
    // landing prediction starts again from the board.
    const double Start = FPlatformTime::Seconds();
    SelectQueries = 0;
    const bool bLog = CVarRideSelectLog.GetValueOnGameThread() != 0;
    if (bLog)
        UE_LOG(LogTemp, Display, TEXT("SKATE ride select: %s (%s) at (%.0f, %.0f, %.0f) v (%.0f, %.0f, %.0f), take-off up (%.2f, %.2f, %.2f)"),
            bLipAir ? TEXT("lip air") : TEXT("air"), LeaveWhy, P.X, P.Y, P.Z, V.X, V.Y, V.Z, TakeoffUp.X, TakeoffUp.Y, TakeoffUp.Z);
    const FVector From = P + Q.GetUpVector() * 12.f;
    const float Speed = V.Size();
    if (bLipAir && Speed > 1.f)
    {
        FVector Right = FVector::CrossProduct(FVector::UpVector, V).GetSafeNormal();
        if (Right.IsNearlyZero()) Right = FVector::CrossProduct(FVector::UpVector, LipOut).GetSafeNormal();
        const FVector Ahead = FVector::CrossProduct(Right, FVector::UpVector);
        const float Cone = FMath::Clamp(Speed, 200.f, 400.f), Fall = Gravity(), Steep = 1.f - FMath::Abs(float(TakeoffUp.Z));
        const float Along = FMath::Sin(FMath::DegreesToRadians(40.f)) * Cone, Across = FMath::Sin(FMath::DegreesToRadians(10.f)) * Cone;
        FVector Best = V;
        float BestRank = -TNumericLimits<float>::Max();
        for (int32 I = 0; I < 7; ++I)
        {
            FVector C = V;
            if (I > 0)
            {
                const float A = FMath::DegreesToRadians(60.f * float(I - 1));
                C = (V + Ahead * (Along * FMath::Cos(A)) + Right * (Across * FMath::Sin(A))).GetClampedToMaxSize(Speed);
            }
            FVector At = From, Vel = C, Normal = FVector::UpVector;
            float T = 0, Land = -1;
            while (T < 3.f)
            {
                const float Dt = .1f;
                const FVector To = At + Vel * Dt + FVector(0, 0, -.5f * Fall * Dt * Dt);
                FHitResult Hit;
                ++SelectQueries;
                if (Sweep(At, To, 10.f, Hit) && !Hit.bStartPenetrating) { Land = T + Dt * Hit.Time; Normal = Hit.Normal; At = Hit.Location; break; }
                At = To; Vel.Z -= Fall * Dt; T += Dt;
            }
            const float Apex = C.Z > 0 ? float(C.Z) / Fall : 0.f;
            const float Rank = 500.f * float(FVector::DotProduct(Normal, LipOut)) * Steep - (FMath::Abs(Land - Apex) < .15f ? 500.f : 0.f)
                - .1f * float((C - V).Size());
            if (bLog)
                UE_LOG(LogTemp, Display, TEXT("SKATE ride select:  #%d v (%.0f, %.0f, %.0f) t %.2f at (%.0f, %.0f, %.0f) face (%.2f, %.2f, %.2f) rank %.0f%s"),
                    I, C.X, C.Y, C.Z, Land, At.X, At.Y, At.Z, Normal.X, Normal.Y, Normal.Z, Rank, Land < .25f ? TEXT(" (too soon or a miss)") : TEXT(""));
            if (Land < .25f) continue;
            if (Rank > BestRank) { BestRank = Rank; Best = C; }
        }
        V = Best;
    }
    if (bLog) UE_LOG(LogTemp, Display, TEXT("SKATE ride select: flies (%.0f, %.0f, %.0f)"), V.X, V.Y, V.Z);
    ResetPrediction(From);
    SelectCost = float((FPlatformTime::Seconds() - Start) * 1000.);
}

void FRideSession::ReadSpinStick(const FSkateInput& In)
{
    // Native's UpdateInput: the stick, its change (x1.5) kept while it moves outward (the snap), the last SpinTicks of
    // that change; on the ground the air's clock waits and the stick is smoothed (a held stick carries into the air).
    const float X = SpinStickX(In.Left);
    const float Change = 1.5f * (X - SpinIn);
    SpinIn = X;
    SpinFilt = FMath::Clamp(Change * X > .1f ? Change : 0.f, -1.f, 1.f);
    SpinHistory[SpinAt] = SpinFilt; SpinAt = (SpinAt + 1) % SpinTicks;
    if (Mode != ERideState::Air) { SpinClock = 0; SpinSmooth = .8f * SpinSmooth + .2f * X; }
}

void FRideSession::TickSpin(const FSkateInput& In)
{
    // Native's PhysicalBodySpin (normal mode), in its terms: rates in rad/s, turning against the stick (Ride's
    // SpinRate turns with it, in degrees/s). The rate follows the stick x PropBodySpinVsTime x SetSpinScale
    // (AirSpinScale), weighed by the snap (.4 for a stick held before the take-off, up to 1 for one pushed as the board
    // leaves), its change each tick at most MaxDeltaVsTime x the scale (and .2 x the scale back against the turn).
    const float Scale = Prefs.Spin;
    if (SpinClock == 0)
    {
        // The take-off: the snap is the stick's sharpest push in the last half second, weighed by its age.
        SpinPeak = 0;
        for (int32 I = 1; I < SpinTicks; ++I)
        {
            const float C = Curve(SpinSnapCurve, -float(I) * Tick60) * SpinHistory[(SpinAt - I + SpinTicks) % SpinTicks];
            if (FMath::Abs(C) > FMath::Abs(SpinPeak)) SpinPeak = C;
        }
    }
    float Accel = Curve(SpinMaxDeltaCurve, SpinClock) * Scale;
    const float AutoAccel = Curve(SpinAutoCurve, SpinClock);
    const float Snap = Curve(SpinSnapCurve, SpinClock) * SpinFilt;
    if (FMath::Abs(Snap) > FMath::Abs(SpinPeak)) SpinPeak = Snap;
    SpinClock += Tick60;
    // A released stick fades out (its smoothed value, 4% a tick), so the turn eases off.
    if (FMath::Abs(SpinIn) < 1.5e-5f) { SpinSmooth *= .96f; SpinIn = SpinSmooth; }
    else SpinSmooth = .8f * SpinSmooth + .2f * SpinIn;
    const float Prop = Curve(SpinPropCurve, SpinClock) * Scale * SpinIn;
    if (Prop * SpinPeak < 0) SpinPeak = 0;
    float Target = -(FMath::Abs(SpinPeak) * .6f + .4f) * Prop;
    const float Old = -FMath::DegreesToRadians(SpinRate);
    // In a lip air with the stick released, the board turns to the nearer of forward and fakie on the landing's line
    // by touch-down: the angle left over the time left (at least 2 ticks), times 1.2, at most 2 rad/s (native's known
    // air alignment), when the spin turns that way already or barely turns.
    const float ToLand = LandTime >= 0 ? LandTime - (AirTime - PredictStart) : -1.f;
    if (bLipAir && SpinStickX(In.Left) == 0.f && ToLand > 0)
    {
        const FVector Axis = Q.GetUpVector();
        const FVector Facing = FVector::VectorPlaneProject(Q.GetForwardVector(), Axis).GetSafeNormal();
        const FVector Path = FVector::VectorPlaneProject(V + FVector(0, 0, -Gravity() * ToLand), Axis).GetSafeNormal();
        if (!Facing.IsNearlyZero() && !Path.IsNearlyZero())
        {
            float Angle = FMath::RadiansToDegrees(FMath::Atan2(float(FVector::DotProduct(Axis, FVector::CrossProduct(Facing, Path))), float(FVector::DotProduct(Facing, Path))));
            if (Angle > 90.f) Angle -= 180.f;
            else if (Angle < -90.f) Angle += 180.f;
            const float Auto = -FMath::Clamp(FMath::DegreesToRadians(Angle / FMath::Max(ToLand, 2.f * Tick60) * 1.2f), -2.f, 2.f);
            if (FMath::Abs(Auto) > 1.5e-5f && (Old * Auto > 0 || FMath::Abs(Old) < .02f)) { Accel = AutoAccel; Target = Auto; }
        }
    }
    const float Limit = FMath::Min(.2f * Scale, Accel);
    const float Lo = Old > 0 ? -Limit : -Accel, Hi = Old > 0 ? Accel : Limit;
    SpinRate = -FMath::RadiansToDegrees(Old + FMath::Clamp(Target - Old, Lo, Hi));
}

void FRideSession::TickAir(const FSkateInput& In, Flick F)
{
    AirTime += Tick60;
    // The lip (native's vert test): off a face steeper than the vert reach (VertSteepness at VertAssist 1, 75 degrees
    // at 0), climbing steeply, the velocity that would carry the rider over the coping is lost and the climb is set
    // upright, leaning back into the ramp, at its own speed (the part along the coping is kept): Ride's own (VertClimb,
    // VertLean), or with VertNative 1 native's departure and launch adjustment (NativeLipLaunch). The flight then picks
    // its landing back in (ChooseLanding) and falls under VertGravity. Holding transfer carries the rider over instead.
    if (AirTime <= Tick60 * 1.5f)
    {
        // The steepest face climbed in the last ClimbTicks (0.13 s), or the take-off's own.
        FVector Up = TakeoffUp;
        for (int32 I = 0; I < ClimbNum; ++I)
            if (ClimbUp[I].Z < Up.Z) Up = ClimbUp[I];
        const FVector Out = FVector(Up.X, Up.Y, 0).GetSafeNormal();
        const float Reach = .25f + (FMath::Cos(FMath::DegreesToRadians(Tune.VertSteepness)) - .25f) * FMath::Clamp(Prefs.VertAssist, 0.f, 1.f);
        if (Up.Z < Reach && V.Z > 0 && !Out.IsNearlyZero())
        {
            const float Into = FMath::Max(0.f, float(-FVector::DotProduct(V, Out)));   // toward the deck behind the coping
            if (In.bTransfer) { V -= Out * Tune.TransferPush; bSelect = true; }
            else
            {
                bool bAligned = false;
                if (Tune.VertNative <= 0 || !NativeLipLaunch(Up, bAligned))
                    if (V.Z >= Tune.VertClimb * FMath::Sqrt(FMath::Square(float(V.Z)) + Into * Into))
                    {
                        V += Out * Into;
                        const FVector Coping = FVector::CrossProduct(FVector::UpVector, Out);
                        const float Side = FVector::DotProduct(V, Coping);
                        const float Lean = FMath::DegreesToRadians(Tune.VertLean);
                        V = (FVector(0, 0, FMath::Cos(Lean)) + Out * FMath::Sin(Lean)) * (V - Coping * Side).Size() + Coping * Side;
                        bAligned = true;
                    }
                if (bAligned) { bLipAir = true; LipOut = Out; bSelect = true; }
            }
        }
    }
    // A flick just after leaving a lip still pops (the rider timed it at the coping); later flicks flip the board
    // without lift (a late flip).
    if (F != Flick::None && (TrickTime < 0 || TrickTime > CatchTime(Trick_) + .05f))
    {
        Cues.Add(ERideCue::Flick);
        if (!bPopped && AirTime < Tune.LateFlickWindow)
        {
            bPopped = true;
            // Off a lip the pop is straight up, as high as on the ground (along the face's normal it would throw the
            // rider off the wall), and the landing is chosen again.
            if (bLipAir) V.Z += PopSpeed() * .8f * FMath::Sqrt(Gravity() / Tune.AirGravity);
            else V += TakeoffUp * PopSpeed() * .8f;
            bSelect = true;
        }
        StartTrick(F);
    }
    // Every air starts its flight (ChooseLanding: a lip air's landing back in, any air's prediction) where it leaves,
    // and again whenever that start changes (the lip, a transfer, a late pop), at most once a tick.
    if (bSelect) { bSelect = false; ChooseLanding(); }
    // Spin: the left stick turns the rider about the body's axis (TickSpin).
    TickSpin(In);
    const float SpinStep = SpinRate * Tick60;
    SpinTotal += SpinStep;
    Q = (Turn(Q.GetUpVector(), SpinStep) * Q).GetNormalized();
    // Level toward the predicted landing face, finishing LevelLead before touch-down.
    AdvancePrediction(2);
    if (LandTime >= 0)
    {
        const float Left = LandTime - (AirTime - PredictStart) - Tune.LevelLead;
        Q = TiltToward(Q, LandNormal, Left <= Tick60 ? 1.f : Tick60 / Left);
    }
    else if (!bLipAir && AirTime > .25f)
    {
        // No landing in sight: the board turns back toward upright rather than holding a tilt it could not land in.
        const float Off = AngleBetween(Q.GetUpVector(), FVector::UpVector);
        if (Off > .5f) Q = TiltToward(Q, FVector::UpVector, RightRate * Tick60 / Off);
    }
    // Grabs: the triggers, with B (Christ air), A (one foot) or the left stick down (tuck knee).
    ERideGrab Want = ERideGrab::None;
    if (In.bGrabLeft || In.bGrabRight)
    {
        if (In.bGrabLeft && In.bBrake) Want = ERideGrab::ChristAir;
        else if (In.bPush) Want = ERideGrab::OneFoot;
        else if (In.Left.Y < -.6f) Want = ERideGrab::TuckKnee;
        else Want = In.bGrabRight ? ERideGrab::Indy : ERideGrab::Melon;
    }
    if (SinceGrab >= 0) SinceGrab += Tick60;
    if (Want != Grab)
    {
        if (Grab != ERideGrab::None) { EndHold(); LastGrab = Grab; SinceGrab = 0; }
        Grab = Want; GrabTime = 0;
    }
    if (Grab != ERideGrab::None)
    {
        GrabTime += Tick60;
        if (GrabTime > .12f) Hold(GrabName(Grab), 300.f, Tick60);
    }
    GrabWeight = FMath::FInterpConstantTo(GrabWeight, Grab != ERideGrab::None ? 1.f : 0.f, Tick60, 7.f);

    // Grinds: a rail under the trucks while coming down onto it.
    if (TryGrind(In)) return;

    // Fly.
    // The air's safety deadline (AirDrop): from where it started and the climb of its pop window (a late pop is part of
    // the take-off), not whatever later contacts gave it.
    if (AirTime <= Tune.LateFlickWindow + Tick60) AirLaunchVz = FMath::Max(AirLaunchVz, float(V.Z));
    const float Fall = FMath::Max(1.f, FMath::Min(Tune.AirGravity, Tune.VertGravity));
    if (ModeTime > (AirLaunchVz + FMath::Sqrt(AirLaunchVz * AirLaunchVz + 2.f * Fall * AirDrop)) / Fall) { StartBail(TEXT("air past its deadline")); return; }
    V.Z -= Gravity() * Tick60;
    // The flight sphere (the deck's middle: the landing's contact) and the board's whole box (the deck shown, its nose
    // and tail past the sphere, turned as this tick turned it) along the tick's move: the earlier contact is resolved,
    // and what is left of the move goes on from there, a few times at most.
    const float Clearance = Tune.StepUp + BoxClearance;
    float Left = 1.f;
    bool bGlanced = false;
    for (int32 Pass = 0; Pass < 3 && Left > 1e-3f && Mode == ERideState::Air; ++Pass)
    {
        const FVector Move = V * (Tick60 * Left);
        const FVector From = P + Q.GetUpVector() * 12.f;
        FHitResult Hit;
        bool bHit = Sweep(From, From + Move, 10.f, Hit);
        if (bThroughLine)
        {
            // Stepping off a stalled grind: the line just left is no contact until the sphere is clear of it, near where
            // it left the line and for a moment only (the box, which starts on the line, waits as long).
            auto FromLine = [this](const FVector& X) { return float(FVector::VectorPlaneProject(X - OffPoint, OffAlong).Size()); };
            if (bHit && FromLine(Hit.Location) <= OffClear && FMath::Abs(FVector::DotProduct(Hit.Location - OffPoint, OffAlong)) < 60.f) bHit = false;
            if (FromLine(From + Move) > OffClear || AirTime > .4f) bThroughLine = false;
        }
        FHitResult Side;
        EBoardHit Box = EBoardHit::Clear;
        FVector Extent;
        const FVector Start = P;
        const FQuat StartQ = Pass == 0 ? Current.Q : Q;
        FTransform BoxFrom;
        if (!bThroughLine && !bBoxOffLine)
        {
            const bool bFromSafe = Pass == 0 && bSafeDeck && FVector::DistSquared(SafeP, P) < FMath::Square(SafeReach);
            BoxFrom = DeckBox(bFromSafe ? SafeDeck : DeckWorld(P, Q), Clearance, Extent);
            Box = SweepBoard(BoxFrom, DeckBox(DeckWorld(P + Move, Q), Clearance, Extent), Extent, Q.GetUpVector(), true, Side);
        }
        if (Box == EBoardHit::Inside)
        {
            // The box turned or moved into a wall: out of it where the move ends (whole box, reached without crossing
            // anything), else as far as it went clear, else back where the tick started; stuck that way StuckLimit,
            // the rider falls. The velocity into the wall goes.
            FVector Out = P + Move;
            const FHitResult Inside = Side;
            if (LeaveWall(BoxFrom, Out, Q, Clearance, false, Side)) { P = Out; StuckTime = 0; }
            else if (Inside.Time > 0.f) { P = FMath::Lerp(Start, Start + Move, double(Inside.Time)); Q = FQuat::Slerp(StartQ, Q, Inside.Time).GetNormalized(); Side = Inside; }
            else
            {
                Side = Inside;
                P = Current.P; Q = Current.Q;
                StuckTime += Tick60;
                if (StuckTime > StuckLimit) { LogStuck(TEXT("the box in the air"), Side); StartBail(TEXT("stuck in a wall")); return; }
            }
            V -= Side.Normal * FMath::Min(0.f, float(FVector::DotProduct(V, Side.Normal)));
            bGlanced = true;
            break;
        }
        if (bHit && Hit.bStartPenetrating)
        {
            // The sphere starts inside something: out along the way out when its centre gets there from the tick's
            // start without crossing anything, else back there. Out onto a face the board can stand on, it lands
            // there; otherwise only the velocity into the face goes.
            const FVector Out = P + Hit.Normal * (FMath::Min(Hit.PenetrationDepth, MaxPush) + .1f);
            FHitResult Between;
            if (Hit.Normal.IsNearlyZero() || Trace(Current.P + Current.Q.GetUpVector() * 12.f, Out + Q.GetUpVector() * 12.f, Between))
            {
                P = Current.P; Q = Current.Q;
                StuckTime += Tick60;
                if (StuckTime > StuckLimit) { LogStuck(TEXT("the sphere in the air"), Hit); StartBail(TEXT("stuck in a wall")); }
                return;
            }
            P = Out;
            if (Hit.Normal.Z >= Tune.WallSlope && TryLand(P, Hit.Normal)) return;
            V -= Hit.Normal * FMath::Min(0.f, float(FVector::DotProduct(V, Hit.Normal)));
            return;
        }
        StuckTime = 0;
        // A face the board can land on that the box meets first is the sphere's to land on (a nose touching down on a
        // transition goes on into the landing, TryLand's frame from the sphere's contact).
        if (Box == EBoardHit::Support && IsLandable(Side)) Box = EBoardHit::Clear;
        if (Box != EBoardHit::Clear && (!bHit || Side.Time < Hit.Time))
        {
            // The box first (a nose or tail ahead of the sphere): a face it can land on is a landing there, nose or tail
            // first (TryLand judges the tilt); anything else is a wall hit. The board stops there as the box did, its
            // turn as far as the box had turned.
            const float Stop = FMath::Max(0.f, Side.Time - .1f / FMath::Max(float(Move.Size()), .1f));
            const bool bStalled = Box == EBoardHit::Wall && Side.Time * float(Move.Size()) < .5f;
            if (!bStalled) { P += Move * Stop; Q = FQuat::Slerp(StartQ, Q, Stop).GetNormalized(); }
            if (Box == EBoardHit::Support && IsLandable(Side) && TryLand(P, Side.ImpactNormal)) return;
            if (Mode != ERideState::Air || HitWallInAir(Side.Normal)) return;
            bGlanced = true;
            if (bStalled)
            {
                // Held on the face from the move's start (the deck's turn, its own or the clip's, keeps it there): the
                // turn waits, and the board goes on along the face (the velocity into it is gone) where the box goes
                // clear; else it stays, GlanceLimit at most.
                Q = StartQ;
                const FVector To = P + V * (Tick60 * Left);
                FHitResult Along;
                if (SweepBoard(BoxFrom, DeckBox(DeckWorld(To, Q), Clearance, Extent), Extent, Q.GetUpVector(), true, Along) == EBoardHit::Clear) P = To;
                Left = 0.f;
                break;
            }
            Left *= 1.f - Side.Time;
            continue;
        }
        if (bHit)
        {
            const FVector Contact = Hit.Location - Hit.Normal * 12.f;
            // Only a face the board can land on is a landing; a wall, a rail's side or a box's face is a wall hit.
            if (IsLandable(Hit) && TryLand(Contact, Hit.Normal)) return;
            if (Mode != ERideState::Air) return;
            P = Hit.Location - Q.GetUpVector() * 12.f;
            if (HitWallInAir(Hit.Normal)) return;
            Left *= 1.f - Hit.Time; bGlanced = true;
            continue;
        }
        P += Move; Left = 0.f;
    }
    if (Mode != ERideState::Air) return;
    // Sliding along faces it cannot land on for GlanceLimit (consecutive ticks) ends the air.
    AirGlance = bGlanced ? AirGlance + Tick60 : 0.f;
    if (AirGlance > GlanceLimit) { StartBail(TEXT("stuck against a wall")); return; }
    if (P.Z < -1e6) StartBail(TEXT("fell out of the world"));
}

bool FRideSession::HitWallInAir(const FVector& Normal)
{
    const float Into = -FVector::DotProduct(V, Normal);
    const float Tilt = AngleBetween(Q.GetUpVector(), Normal);
    // Coming down onto a floor on its side or upside down is a fall, whatever the speed; so is a hard wall hit.
    if (Normal.Z >= .7f && Tilt > 75.f && Into > 0) { StartBail(TEXT("landed on its side")); return true; }
    if (Into > Tune.WallBailSpeed) { StartBail(TEXT("hit a wall")); return true; }
    // Otherwise the board slides along the face: the velocity into it goes, and none comes back (a bounce off a face
    // it cannot land on would carry it up and on in the air). The landing is looked for afresh.
    if (Into > 0) V += Normal * Into;
    // Only a real change of course looks for the landing afresh: sliding down a face keeps the landing it had.
    if (Into > 50.f) ResetPrediction(P + Q.GetUpVector() * 12.f);
    return false;
}

bool FRideSession::TryLand(const FVector& Point, const FVector& Normal)
{
    const FVector BoardUp = Q.GetUpVector();
    const float Tilt = AngleBetween(BoardUp, Normal);
    // Touching something with the deck far from flat is a wall hit, not a landing; a steep hit with the deck aligned is.
    if (Tilt > 75.f)
    {
        const float Into = -FVector::DotProduct(V, Normal);
        if (Into > Tune.WallBailSpeed) { StartBail(TEXT("hit a wall")); return true; }
        return false;
    }
    const float Impact = FMath::Max(0.f, float(-FVector::DotProduct(V, Normal)));
    const float Fall = float(V.Z);
    const FVector Along = FVector::VectorPlaneProject(V, Normal);
    const float Speed = Along.Size();
    const FVector Heading = FVector::VectorPlaneProject(Q.GetForwardVector(), Normal).GetSafeNormal();
    float Yaw = Speed > 30.f ? AngleBetween(Heading, Along) : 0.f;
    const bool bFakieLanding = Yaw > 90.f;
    if (bFakieLanding) Yaw = 180.f - Yaw;
    const bool bMidFlip = TrickTime >= 0 && TrickTime < CatchTime(Trick_) - .03f && Trick_ != Flick::Ollie && Trick_ != Flick::Nollie;
    float YawLimit = 90.f;
    if (Speed > Tune.SidewaysSafeSpeed) YawLimit = FMath::GetMappedRangeValueClamped(FVector2f(Tune.SidewaysSafeSpeed, 2000.f), FVector2f(90.f, Tune.BailYawFast), Speed);
    // A grab held into the landing rides away, as native's does (its reference holds an Indy 17 ticks past the
    // touch-down); one with a foot off the board (Christ air, one foot) wipes out, as native's do.
    const bool bFootOff = (Grab == ERideGrab::ChristAir || Grab == ERideGrab::OneFoot) && GrabWeight > .6f && AirTime > .25f;
    const TCHAR* Why = Tilt > Tune.BailTilt ? TEXT("landed tilted") : Impact > Tune.BailImpact ? TEXT("landed too hard") :
        Yaw >= YawLimit && !bSteppingOff ? TEXT("landed sideways") : bMidFlip ? TEXT("landed on the board mid-flip") :
        bFootOff ? TEXT("landed with a foot off the board") : nullptr;
    P = Point;
    if (Why)
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride landing refused (%s): face %.2f,%.2f,%.2f, deck up %.2f,%.2f,%.2f (tilt %.0f, yaw %.0f, impact %.0f); landing aimed at %.2f,%.2f,%.2f (%s)"),
            Why, Normal.X, Normal.Y, Normal.Z, BoardUp.X, BoardUp.Y, BoardUp.Z, Tilt, Yaw, Impact, LandNormal.X, LandNormal.Y, LandNormal.Z, LandTime >= 0 ? TEXT("set") : TEXT("none"));
        StartBail(Why);
        return true;
    }
    // Land: the normal part of the speed is absorbed; a sideways landing keeps cos(angle) of the speed along the board.
    // Coming down a face between 46 and 65 degrees the speed along it grows by up to 15%, as much as the travel runs
    // downhill (native's RestoreVelocity, KnownAirTrajectory.cpp), so a lip air landing low on the transition keeps
    // its speed.
    const FVector Downhill = FVector::VectorPlaneProject(FVector(0, 0, -1), Normal).GetSafeNormal();
    const float Downward = Downhill.IsNearlyZero() || Speed < 1.f ? 0.f : FMath::Clamp(float(FVector::DotProduct(Downhill, Along)) / Speed, 0.f, 1.f);
    const float Restore = 1.f + (Curve(LandingCurve, float(Normal.Z)) - 1.f) * Downward;
    Travel = bFakieLanding ? -1.f : 1.f;
    Q = Frame(Normal, Heading.IsNearlyZero() ? FVector::VectorPlaneProject(Q.GetForwardVector(), Normal).GetSafeNormal() : Heading);
    const float Kept = Speed * Restore * FMath::Cos(FMath::DegreesToRadians(Yaw));
    V = Q.GetForwardVector() * Travel * Kept;
    // A stall's step-off comes down across its hop by design: neither sideways nor sketchy.
    Sketchy = bSteppingOff ? 0.f : Yaw > Tune.SketchyYaw ? 1.f : Yaw > Tune.CleanYaw ? .5f : 0.f;
    LandAge = 0; LandImpact = Impact;
    bLandedFromGrab = Grab != ERideGrab::None || (LastGrab != ERideGrab::None && SinceGrab >= 0 && SinceGrab < .3f);
    LastGrab = ERideGrab::None; SinceGrab = -1;
    // Score the air: the flip, the spin and any grab still held.
    EndHold();
    if (Trick_ != Flick::None) AddTrick(FlickName(Trick_, bTrickFakie, bTrickSwitch), FlipInfo(Trick_).Points);
    const float Spun = FMath::Abs(SpinTotal);
    if (Spun >= 150.f) AddTrick(SpinName(SpinTotal), 150.f * FMath::RoundToFloat(Spun / 180.f));
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; SpinTotal = 0; SpinRate = 0;
    TurnRate = 0; Curvature = 0; Calm = 0;
    Cues.Add(ERideCue::Catch);
    SetMode(ERideState::Ground);
    // A manual starts on the landing tick (the Manual intention counts in the air), unless Native's guard holds: down
    // faster than 8 m/s onto a face steeper than 45 degrees (the board's fall, as it came in).
    bHardLanding = Fall < -800.f && Normal.Z < UE_HALF_SQRT_2;
    TryManual(true);
    bHardLanding = false;
    return true;
}

void FRideSession::TryManual(bool bLanding)
{
    // Turning.Idle: plain ground with no pop, push or turn round under way.
    if (Mode != ERideState::Ground || PendingPop != Flick::None || PushTime >= 0 || SwitchTime >= 0) return;
    if (!Manuals.Idle(bHardLanding)) return;
    SetMode(ERideState::Manual); bNoseManual = Manuals.Side() == atelier::ride::ManualSide::Nose; PushTime = -1;
    Manuals.Start(bLanding);
}

// ---------------------------------------------------------------------------------------------------------------
// Grinds and slides on USkateRailSubsystem lines.

bool FRideSession::TryGrind(const FSkateInput& In)
{
    if (!Where.Rails || Where.Rails->Rails.IsEmpty()) return false;
    const FVector Up = Q.GetUpVector();
    // Only an upright board coming down (or level) onto a line: vert airs pass the coping untouched.
    if (Up.Z < .7f || V.Z > 60.f || AirTime < .08f) return false;
    float S = 0; FVector Point, Tangent;
    const int32 R = Where.Rails->FindNear(P, Tune.GrindCapture, -Tune.GrindBelow, Tune.GrindAbove, S, Point, Tangent);
    if (R == INDEX_NONE) return false;
    // The line just left stays released for a moment, so its end does not catch the board again.
    if (R == LastRail && RailCooldown > 0) return false;
    const FSkateRail& Line_ = Where.Rails->Rails[R];
    // Steep lines are not grindable.
    if (FMath::Abs(Tangent.Z) > .5f) return false;
    // The board must not be moving away from the line faster than it can be caught.
    const FVector Across = FVector::CrossProduct(FVector::UpVector, Tangent).GetSafeNormal();
    if (FMath::Abs(FVector::DotProduct(V, Across)) > 800.f) return false;
    // Nor crossing it more steeply than GrindCross (the native runtime locks up to about 60 degrees).
    const FVector Flat(V.X, V.Y, 0);
    if (Flat.Size() > 100.f && FMath::Abs(FVector::DotProduct(Flat, FVector(Tangent.X, Tangent.Y, 0).GetSafeNormal())) < FMath::Cos(FMath::DegreesToRadians(Tune.GrindCross)) * Flat.Size())
        return false;
    Rail = R; RailS = S;
    RailSpeed = FVector::DotProduct(V, Tangent);
    if (FMath::Abs(RailSpeed) < 40.f) { Rail = INDEX_NONE; return false; }
    // Nothing left to grind in the direction of travel.
    const float Ahead = RailSpeed > 0 ? Line_.Length() - S : S;
    if (Ahead < Tune.GrindMinAhead) { Rail = INDEX_NONE; return false; }
    // Which grind: the board's angle to the line, then the right stick at entry.
    const FVector Nose = Q.GetForwardVector();
    const float Angle = AngleBetween(FVector::VectorPlaneProject(Nose, FVector::UpVector), Tangent);
    const float Folded = Angle > 90.f ? 180.f - Angle : Angle;
    if (Folded < Tune.GrindAlign)
    {
        GrindKind = In.Right.Y > .4f ? (FMath::Abs(In.Right.X) > .5f ? ERideGrind::Crooked : ERideGrind::Nosegrind)
                  : In.Right.Y < -.4f ? ERideGrind::FiveO : ERideGrind::FiftyFifty;
        GrindNose = Angle > 90.f ? -1.f : 1.f;
    }
    else if (Folded > 90.f - Tune.GrindAlign)
    {
        GrindKind = In.Right.Y < -.4f ? ERideGrind::Lipslide : ERideGrind::Boardslide;
        // The deck turns across the line the way it already points.
        GrindNose = FVector::DotProduct(Nose, FVector::CrossProduct(FVector::UpVector, Tangent)) > 0 ? 1.f : -1.f;
    }
    else GrindKind = ERideGrind::Crooked, GrindNose = Angle > 90.f ? -1.f : 1.f;
    // Frontside when the line is on the rider's toe side.
    const FVector Toes = RiderQ().GetRightVector() * (GoofyNow() ? -1.f : 1.f);
    bGrindFront = FVector::DotProduct(Point - P, Toes) > 0;
    RailUp = FVector::CrossProduct(Tangent, FVector::CrossProduct(FVector::UpVector, Tangent)).GetSafeNormal();
    if (RailUp.Z < 0) RailUp = -RailUp;
    // The board closes onto the line over the next ticks, as fast as it was coming and no slower than GrindLockSpeed,
    // rather than jumping there (the native board touches the line before it locks).
    const bool bSlide = GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide;
    LockOffset = P - (Point - RailUp * (bSlide ? Tune.DeckHeight - 1.5f : Tune.WheelRadius + Line_.Radius));
    LockSpeed = FMath::Max(Tune.GrindLockSpeed, float(-FVector::DotProduct(V, LockOffset.GetSafeNormal())));
    // Score the air that led onto the rail.
    if (Trick_ != Flick::None) AddTrick(FlickName(Trick_, bTrickFakie, bTrickSwitch), FlipInfo(Trick_).Points);
    Trick_ = Flick::None; TrickTime = -1;
    EndHold(); Grab = ERideGrab::None; GrabWeight = 0; SpinRate = 0; SpinTotal = 0;
    Cues.Add(ERideCue::Catch);
    SetMode(ERideState::Grind);
    TickGrind(In, Flick::None);
    return true;
}

void FRideSession::TickGrind(const FSkateInput& In, Flick F)
{
    if (!Where.Rails || !Where.Rails->Rails.IsValidIndex(Rail)) { LeaveWhy = TEXT("rail lost"); TakeOff(0.f); return; }
    FVector Tangent;
    Where.Rails->Sample(Rail, RailS, Tangent);
    const bool bSlide = GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide;
    // Gravity along the line, friction against the motion.
    RailSpeed += -G * Tangent.Z * Tick60;
    const float Friction = bSlide ? Tune.SlideFriction : Tune.GrindFriction;
    RailSpeed = RailSpeed > 0 ? FMath::Max(0.f, RailSpeed - Friction * Tick60) : FMath::Min(0.f, RailSpeed + Friction * Tick60);
    // Along the line. At its end the grind carries on into a line that continues it round a shallow corner; an end or
    // a sharp corner sends the board off the way it was going.
    const FVector Was = Tangent;
    const float From = RailS;
    const int32 FromRail = Rail;
    RailS += RailSpeed * Tick60;
    bool bOff = false;
    float Corner = 0;
    if (RailS < 0 || RailS > Where.Rails->Rails[Rail].Length()) bOff = !TurnCorner();
    else if (SharpCorner(From, RailS, Corner)) { RailS = Corner; bOff = true; }
    const FSkateRail& Line_ = Where.Rails->Rails[Rail];
    FVector Point = Where.Rails->Sample(Rail, FMath::Clamp(RailS, 0.f, Line_.Length()), Tangent);
    if (bOff) Tangent = Was;
    RailUp = FVector::CrossProduct(Tangent, FVector::CrossProduct(FVector::UpVector, Tangent)).GetSafeNormal();
    if (RailUp.Z < 0) RailUp = -RailUp;
    // The board sits on the line: trucks on it for grinds, the deck's underside for slides; what is left of the lock's
    // offset closes at LockSpeed.
    const float Drop = bSlide ? Tune.DeckHeight - 1.5f : Tune.WheelRadius + Line_.Radius;
    const float Gap = LockOffset.Size();
    LockOffset = Gap > LockSpeed * Tick60 ? LockOffset * (1.f - LockSpeed * Tick60 / Gap) : FVector::ZeroVector;
    P = Point - RailUp * Drop + LockOffset;
    FVector Nose = Tangent * GrindNose;
    if (bSlide) Nose = FVector::CrossProduct(RailUp, Tangent) * GrindNose;
    if (GrindKind == ERideGrind::Crooked) Nose = (Tangent * GrindNose + FVector::CrossProduct(RailUp, Tangent) * .5f).GetSafeNormal();
    Q = Frame(RailUp, Nose);
    V = Tangent * RailSpeed;
    // Walls along the line: the board's whole box above the line (from 2 cm over its contact), moved from where the
    // last tick left it, the lock's closing offset and the line's turns included (MoveBoardPose). A grind into a wall
    // throws the rider when fast, else stops short of it and stalls.
    FVector Reached = P;
    FQuat ReachedQ = Q;
    FHitResult Wall;
    const EBoardMove Moved = MoveBoardPose(Reached, ReachedQ, Drop + 2.f, Wall);
    if (Moved != EBoardMove::Clear)
    {
        if (-FVector::DotProduct(V, Wall.Normal) > Tune.WallBailSpeed) { StartBail(TEXT("grind into a wall")); return; }
        P = Reached; Q = ReachedQ;
        if (Rail == FromRail) RailS = From;
        RailSpeed = 0; V = FVector::ZeroVector; bOff = false;
    }
    Travel = FVector::DotProduct(V, Q.GetForwardVector()) < 0 ? -1.f : 1.f;
    WheelSpin = FMath::Fmod(WheelSpin + (bSlide ? 0.f : RailSpeed * Tick60 * 2.f), 360.f);
    Hold(GrindName(), bSlide ? 250.f : 200.f, Tick60);
    // Leave: a pop (any flick, flipping out), the end of the line or a sharp corner, or a stall.
    if (F != Flick::None)
    {
        Cues.Add(ERideCue::Flick);
        LeaveGrind(Tune.GrindExitPop * Tune.PopFromGrindScale / .8f);
        if (F != Flick::Ollie && F != Flick::Nollie) StartTrick(F);
        return;
    }
    if (bOff) { LeaveGrind(60.f); return; }
    if (FMath::Abs(RailSpeed) < Tune.GrindStall && ModeTime > .5f) { LeaveGrind(Tune.GrindStallHop, true); return; }
}

bool FRideSession::TurnCorner()
{
    const TArray<FSkateRail>& Lines = Where.Rails->Rails;
    const FSkateRail& From = Lines[Rail];
    const int32 N = From.Points.Num();
    if (N < 2) return false;
    const bool bForward = RailS > From.Length();
    const FVector Joint = bForward ? From.Points.Last() : From.Points[0];
    const FVector Out = bForward ? (From.Points[N - 1] - From.Points[N - 2]).GetSafeNormal() : (From.Points[0] - From.Points[1]).GetSafeNormal();
    const float Over = bForward ? RailS - From.Length() : -RailS;
    // The line whose end meets this one's and leads on with the smallest turn, under GrindCorner.
    int32 Best = INDEX_NONE;
    bool bBestForward = true;
    float BestTurn = Tune.GrindCorner;
    for (int32 R = 0; R < Lines.Num(); ++R)
    {
        const FSkateRail& To = Lines[R];
        const int32 M = To.Points.Num();
        if (M < 2 || !To.Bounds.ExpandBy(Tune.GrindJoin).IsInsideOrOn(Joint)) continue;
        for (int32 End = 0; End < 2; ++End)
        {
            const bool bStart = End == 0;
            if (R == Rail && bStart != bForward) continue;   // the end being left
            if (FVector::Dist(bStart ? To.Points[0] : To.Points.Last(), Joint) > Tune.GrindJoin) continue;
            const FVector Away = bStart ? (To.Points[1] - To.Points[0]).GetSafeNormal() : (To.Points[M - 2] - To.Points[M - 1]).GetSafeNormal();
            if (FMath::Abs(Away.Z) > .5f) continue;
            const float Turned = AngleBetween(Out, Away);
            if (Turned < BestTurn) { BestTurn = Turned; Best = R; bBestForward = bStart; }
        }
    }
    if (Best == INDEX_NONE) return false;
    // The new line may run the other way: the speed along it and the board's nose follow.
    if (bBestForward != bForward) { RailSpeed = -RailSpeed; GrindNose = -GrindNose; }
    Rail = Best;
    const FSkateRail& To = Lines[Best];
    RailS = bBestForward ? FMath::Min(Over, To.Length()) : FMath::Max(0.f, To.Length() - Over);
    // The gap between the two ends closes like a lock.
    LockOffset += Joint - (bBestForward ? To.Points[0] : To.Points.Last());
    LockSpeed = FMath::Max(LockSpeed, Tune.GrindLockSpeed);
    return true;
}

bool FRideSession::SharpCorner(float From, float To, float& OutS) const
{
    const FSkateRail& Line_ = Where.Rails->Rails[Rail];
    const int32 N = Line_.Points.Num();
    const bool bForward = To > From;
    for (int32 K = bForward ? 1 : N - 2; K >= 1 && K <= N - 2; K += bForward ? 1 : -1)
    {
        const float S = Line_.Lengths[K];
        if (bForward ? S <= From : S >= From) continue;
        if (bForward ? S > To : S < To) break;
        const FVector In = Line_.Points[K] - Line_.Points[K - 1], Out = Line_.Points[K + 1] - Line_.Points[K];
        if (In.SizeSquared() < .25f || Out.SizeSquared() < .25f) continue;
        if (AngleBetween(In, Out) > Tune.GrindCorner) { OutS = S; return true; }
    }
    return false;
}

void FRideSession::LeaveGrind(float Up, bool bStall)
{
    EndHold();
    // Off the side the rider leans to, so the board does not catch the line again.
    FVector Tangent = V.GetSafeNormal(), LinePoint = P;
    if (Where.Rails && Where.Rails->Rails.IsValidIndex(Rail))
    {
        FVector Along;
        LinePoint = Where.Rails->Sample(Rail, FMath::Clamp(RailS, 0.f, Where.Rails->Rails[Rail].Length()), Along);
        if (Tangent.IsNearlyZero()) Tangent = Along;
    }
    FVector Side = FVector::CrossProduct(FVector::UpVector, Tangent).GetSafeNormal() * (bGrindFront ? -1.f : 1.f) * (GoofyNow() ? -1.f : 1.f);
    float Aside = 40.f;
    if (bStall && Where.Rails && Where.Rails->Rails.IsValidIndex(Rail))
    {
        // A stall steps off the line, to a ledge's open side, a coping's deck, or else the lean side unless something
        // stands there: a small hop, wide enough that the air sweep's sphere (10 cm) is clear of the line before it
        // comes back down to its height. The sweep starts inside the line, so it passes through it until then.
        const FSkateRail& Line_ = Where.Rails->Rails[Rail];
        const FVector Open = FVector(Line_.Side.X, Line_.Side.Y, 0).GetSafeNormal();
        if (!Open.IsNearlyZero()) Side = Line_.Kind == ESkateRailKind::Coping ? -Open : Open;
        else
        {
            const FVector Sphere = P + Q.GetUpVector() * 12.f;
            auto Blocked = [&](const FVector& Way) { FHitResult Hit; return Sweep(Sphere + Way * 20.f, Sphere + Way * 60.f, 10.f, Hit); };
            if (Blocked(Side) && !Blocked(-Side)) Side = -Side;
        }
        OffClear = 10.f + Line_.Radius + 4.f;
        Aside = OffClear * Tune.AirGravity / (2.f * FMath::Max(Up, 50.f));
        bSteppingOff = bThroughLine = true; OffPoint = LinePoint; OffAlong = Tangent;
    }
    else if (Where.Rails && Where.Rails->Rails.IsValidIndex(Rail))
    {
        OffClear = 10.f + Where.Rails->Rails[Rail].Radius + 4.f;
        bBoxOffLine = true; OffPoint = LinePoint; OffAlong = Tangent;
    }
    V += FVector::UpVector * Up + Side * Aside;
    // Slides turn the board back along the travel (a stall's hop keeps it as it is).
    if (!bStall && (GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide || GrindKind == ERideGrind::Crooked))
        Q = Frame(FVector::UpVector, FVector::VectorPlaneProject(V, FVector::UpVector).GetSafeNormal() * (FVector::DotProduct(Q.GetForwardVector(), V) < 0 ? -1.f : 1.f));
    LastRail = Rail; RailCooldown = Tune.GrindRelock;
    Rail = INDEX_NONE;
    TurnRate = 0;
    const FVector UpVector = Q.GetUpVector();
    SetMode(ERideState::Air); LeaveWhy = TEXT("off a rail");
    AirTime = .1f; TakeoffUp = UpVector; SpinTotal = 0; SpinRate = 0; bPopped = true; bLipAir = false;
    LastGrab = ERideGrab::None; SinceGrab = -1;
    ResetPrediction(P + UpVector * 12.f);
    P += FVector::UpVector * 2.f;
}

// ---------------------------------------------------------------------------------------------------------------
// Bails.

void FRideSession::StartBail(const TCHAR* Why)
{
    UE_LOG(LogTemp, Display, TEXT("SKATE ride bail: %s at %.0f cm/s"), Why, V.Size());
    BailLinear = V;
    BailAngular = Q.GetUpVector() * FMath::DegreesToRadians(SpinRate) + RiderQ().GetForwardVector() * FMath::DegreesToRadians(FlipInfo(Trick_).Roll) * (TrickTime >= 0 ? 1.f : 0.f);
    LoseLine();
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; PendingPop = Flick::None; Rail = INDEX_NONE;
    SpinRate = 0; TurnRate = 0; SlideYaw = 0; PushTime = -1; StillTime = -1; Manuals.End();
    LastGrab = ERideGrab::None; SinceGrab = -1;
    Cues.Add(ERideCue::Fall);
    bFollowBody = false;
    SetMode(ERideState::Bail);
}

void FRideSession::TickBail()
{
    if (Mode == ERideState::GetUp)
    {
        V = FVector::ZeroVector;
        if (ModeTime >= Tune.GetUpTime) { SetMode(ERideState::Ground); Calm = 0; }
        return;
    }
    // Without a ragdoll the rider slides to a stop on the ground and gets up by itself.
    if (!bRagdoll)
    {
        const float Speed = V.Size();
        V = Speed > 1.f ? V * FMath::Max(0.f, Speed - Tune.BailSlideDecel * Tick60) / Speed : FVector::ZeroVector;
        V.Z -= G * Tick60;
        FVector Ground, Up, Forward; bool bBlocked = false;
        // Walls stop the slide: the board's box lying level along the slide.
        FVector Move = V * Tick60;
        FHitResult Wall;
        FVector Extent;
        const FTransform Lying = DeckBox(FTransform(Frame(FVector::UpVector, Q.GetForwardVector()), P + FVector::UpVector * Tune.DeckHeight), Tune.StepUp + BoxClearance, Extent);
        if (SweepBoard(Lying, FTransform(Lying.GetRotation(), Lying.GetLocation() + Move), Extent, FVector::UpVector, false, Wall) == EBoardHit::Wall)
        {
            Move *= FMath::Max(0.f, Wall.Time - .1f / FMath::Max(float(Move.Size()), .1f));
            V -= Wall.Normal * FMath::Min(0.f, float(FVector::DotProduct(V, Wall.Normal)));
        }
        const FVector Next = P + Move;
        if (FindGround(Next, Frame(FVector::UpVector, Q.GetForwardVector()), 20.f, Ground, Up, Forward, bBlocked))
        { P = Ground; V = FVector::VectorPlaneProject(V, Up); }
        else if (!bBlocked) P = Next;
        if (ModeTime >= Tune.BailSettle) GetUp(P, RiderQ().Rotator().Yaw);
        return;
    }
    // With a ragdoll the component calls GetUp when the body has settled; the root follows the body meanwhile, and
    // a body that never settles (stuck on geometry) still gets up. It follows where the body is reached from where it
    // is, straight or up and over (a step, a ledge's edge), never through what the body went through (a floor it was
    // pressed under, a wall it tunnelled): the slide that takes over from an unstable body starts on this side.
    if (bFollowBody)
    {
        if (Reaches(BodyPoint)) P = BodyPoint;
        V = FVector::ZeroVector;
    }
    if (ModeTime >= Tune.BailSettle + 5.f) GetUp(P, RiderQ().Rotator().Yaw);
}

bool FRideSession::Reaches(const FVector& To) const
{
    FHitResult Between;
    auto Clear = [&](const FVector& A, const FVector& B) { return !Trace(A, B, Between); };
    const FVector Low(0, 0, FollowLow);
    const double Top = FMath::Max(P.Z, To.Z) + FollowHigh;
    const FVector Over(P.X, P.Y, Top), Across(To.X, To.Y, Top);
    return Clear(P + Low, To + Low) || (Clear(P + Low, Over) && Clear(Over, Across) && Clear(Across, To + Low));
}

void FRideSession::GetUp(const FVector& GroundPoint, float Yaw)
{
    const FQuat Facing(FRotator(0, Yaw, 0));
    FVector Ground, Up, Forward; bool bBlocked = false;
    P = GroundPoint; Q = Facing;
    if (FindGround(P + FVector(0, 0, 30), Facing, 80.f, Ground, Up, Forward, bBlocked)) { P = Ground; Q = Frame(Up, Forward); }
    V = FVector::ZeroVector; Travel = 1; Sketchy = 0; Crouch = .25f; LandAge = -1;
    bSwitch = false; SwitchTime = -1; FakieTime = 0;    // up in the rider's own stance
    ResetWalls();
    LeaveWallsStanding();
    Previous.P = Current.P = P; Previous.Q = Current.Q = Q; Previous.Deck = Current.Deck = DeckPose();
    SetMode(ERideState::GetUp);
}

void FRideSession::LogStuck(const TCHAR* Site, const FHitResult& Wall) const
{
    const UPrimitiveComponent* Other = Wall.GetComponent();
    const AActor* Owner = Other ? Other->GetOwner() : nullptr;
    const FVector Up = Q.GetUpVector(), Nose = Q.GetForwardVector();
    const bool bFromSafe = bSafeDeck && FVector::DistSquared(SafeP, P) < FMath::Square(SafeReach);
    UE_LOG(LogTemp, Display, TEXT("SKATE ride stuck %s (mode %d for %.2f s, stuck %.2f s of it): at (%.0f, %.0f, %.0f), up (%.2f, %.2f, %.2f), nose (%.2f, %.2f, %.2f), ")
        TEXT("%.0f cm/s (%.0f, %.0f, %.0f), the box from %s; %s %s/%s, normal (%.2f, %.2f, %.2f), impact (%.2f, %.2f, %.2f) at (%.0f, %.0f, %.0f), %.1f cm in"),
        Site, int32(Mode), ModeTime, StuckTime, P.X, P.Y, P.Z, Up.X, Up.Y, Up.Z, Nose.X, Nose.Y, Nose.Z, V.Size(), V.X, V.Y, V.Z,
        bFromSafe ? TEXT("the last free pose") : TEXT("the session's pose"), Wall.bStartPenetrating ? TEXT("inside") : TEXT("against"),
        Owner ? *Owner->GetName() : TEXT("?"), Other ? *Other->GetName() : TEXT("?"), Wall.Normal.X, Wall.Normal.Y, Wall.Normal.Z,
        Wall.ImpactNormal.X, Wall.ImpactNormal.Y, Wall.ImpactNormal.Z, Wall.ImpactPoint.X, Wall.ImpactPoint.Y, Wall.ImpactPoint.Z,
        Wall.PenetrationDepth);
}

void FRideSession::LeaveWallsStanding()
{
    // Up (or set down) beside a wall: the whole box, turned as the rider faces, out of it along the ground; else
    // turned along the wall and out. Inside a wall, the ride would start stuck (an air that cannot move, a bail at a
    // standstill, a run-out on foot).
    const float Clearance = Tune.StepUp + BoxClearance;
    const FVector Up = Q.GetUpVector();
    FVector Extent, Push, Normal;
    const FTransform Box = DeckBox(DeckWorld(P, Q), Clearance, Extent);
    if (!WallOverlap(Box, Extent, Up, Push, Normal)) return;
    FHitResult Wall;
    FVector Out = P;
    if (LeaveWall(Box, Out, Q, Clearance, true, Wall)) { UE_LOG(LogTemp, Display, TEXT("SKATE ride up beside a wall: the board %.0f cm out of it"), float(FVector::Dist(Out, P))); P = Out; return; }
    const FVector Along = FVector::CrossProduct(Up, FVector::VectorPlaneProject(Normal, Up).GetSafeNormal()).GetSafeNormal();
    if (Along.IsNearlyZero()) return;
    const FQuat Turned = Frame(Up, FVector::DotProduct(Along, Q.GetForwardVector()) < 0 ? -Along : Along);
    const FTransform TurnedBox = DeckBox(DeckWorld(P, Turned), Clearance, Extent);
    Out = P;
    if (!WallOverlap(TurnedBox, Extent, Up, Push, Normal) || LeaveWall(TurnedBox, Out, Turned, Clearance, true, Wall))
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride up beside a wall: the board turned along it, %.0f cm out"), float(FVector::Dist(Out, P)));
        P = Out; Q = Turned;
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Scoring.

void FRideSession::AddTrick(const FString& Name, float Points)
{
    Line.Add({Name, Points}); Calm = 0;
}

void FRideSession::Hold(const FString& Name, float PointsPerSecond, float Dt)
{
    if (Holding != Name) { EndHold(); Holding = Name; HeldPoints = PointsPerSecond * .5f; }
    HeldPoints += PointsPerSecond * Dt;
}

void FRideSession::EndHold()
{
    if (Holding.IsEmpty()) return;
    AddTrick(Holding, HeldPoints);
    Holding.Reset(); HeldPoints = 0;
}

void FRideSession::BankLine()
{
    EndHold();
    float Sum = 0; for (const FLineTrick& T : Line) Sum += T.Points;
    Banked += Sum * FMath::Max(1, Line.Num());
    Line.Reset();
}

void FRideSession::LoseLine()
{
    Holding.Reset(); HeldPoints = 0; Line.Reset();
}

FString FRideSession::FlickName(Flick F, bool bFakie, bool bSwitched) const
{
    const FString Base = UTF8_TO_TCHAR(atelier::ride::FlickName(F));
    if (bFakie && !IsNollie(F)) return TEXT("Fakie ") + Base;
    return bSwitched ? TEXT("Switch ") + Base : Base;
}

FString FRideSession::SpinName(float Degrees) const
{
    // A spin up to 30 degrees short still counts (a 330 is a 360).
    const int32 Half = FMath::Max(1, FMath::RoundToInt((FMath::Abs(Degrees) - 30.f) / 180.f + .0001f));
    // A regular rider faces +Y (the board's right): turning that way (negative yaw) leads with the chest, frontside.
    const float Stance = GoofyNow() ? -1.f : 1.f;
    const bool bFrontside = Degrees * Stance * RiderTravel() < 0;
    return FString::Printf(TEXT("%s %d"), bFrontside ? TEXT("FS") : TEXT("BS"), Half * 180);
}

FString FRideSession::GrindName() const
{
    const TCHAR* Side = bGrindFront ? TEXT("FS ") : TEXT("BS ");
    switch (GrindKind)
    {
    case ERideGrind::FiveO: return FString(Side) + TEXT("5-0 Grind");
    case ERideGrind::Nosegrind: return FString(Side) + TEXT("Nosegrind");
    case ERideGrind::Crooked: return FString(Side) + TEXT("Crooked Grind");
    case ERideGrind::Boardslide: return FString(Side) + TEXT("Boardslide");
    case ERideGrind::Lipslide: return FString(Side) + TEXT("Lipslide");
    default: return FString(Side) + TEXT("50-50 Grind");
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Output: the deck, the rider, the state, the camera.

FTransform FRideSession::DeckPose() const
{
    // The deck in the root's space (the root is the deck's pivot at rest, DeckHeight above P).
    FQuat Deck = FQuat::Identity;
    FVector Offset = FVector::ZeroVector;
    if (Mode == ERideState::Powerslide || !FMath::IsNearlyZero(SlideYaw)) Deck = Turn(FVector::UpVector, SlideYaw);
    // With the rider's clips the board's pops, flips and manual tilts are the clips' own.
    if (Animator.HasRig()) return FTransform(Deck, Offset);
    const float DeckAngle = Mode == ERideState::Manual ? Manuals.DeckAngle() : 0.f;
    if (DeckAngle != 0.f)
    {
        // Up on one truck: the deck pitches about the axle that stays down (the controller's deck, nose up positive).
        const float Axle = DeckAngle < 0.f ? Tune.AxleX : -Tune.AxleX;
        const FQuat Tip = Turn(FVector::RightVector, -FMath::RadiansToDegrees(DeckAngle));
        const FVector Pivot(Axle, 0, Tune.WheelRadius - Tune.DeckHeight);
        Offset = Pivot + Tip.RotateVector(-Pivot);
        Deck = Tip * Deck;
    }
    if (TrickTime >= 0 && Trick_ != Flick::None)
    {
        const FFlipInfo Flip = FlipInfo(Trick_);
        const float T = FMath::Clamp(TrickTime / FMath::Max(.05f, Flip.Time), 0.f, 1.f);
        const float Ease = 1.f - FMath::Square(1.f - T);
        const float Mirror = GoofyNow() ? -1.f : 1.f;
        const FQuat Roll = Turn(FVector::ForwardVector, Flip.Roll * Ease * Mirror);
        const FQuat Yaw = Turn(FVector::UpVector, Flip.Yaw * Ease * Mirror);
        // The ollie's pitch: nose up through the pop, level by the catch.
        const float Pitch = -40.f * FMath::Sin(PI * FMath::Clamp(TrickTime / .45f, 0.f, 1.f)) * (IsNollie(Trick_) ? -1.f : 1.f) * (bTrickFakie ? -1.f : 1.f);
        Deck = Yaw * Roll * Turn(FVector::RightVector, Pitch) * Deck;
        Offset.Z += 18.f * FMath::Sin(PI * FMath::Clamp(TrickTime / .5f, 0.f, 1.f));
    }
    return FTransform(Deck, Offset);
}

void FRideSession::Publish(float Alpha, float Dt, const FSkateInput& In)
{
    const FVector At = FMath::Lerp(Previous.P, Current.P, Alpha);
    const FQuat Frame_ = FQuat::Slerp(Previous.Q, Current.Q, Alpha).GetNormalized();
    FTransform Deck = Current.Deck;
    Deck.SetRotation(FQuat::Slerp(Previous.Deck.GetRotation(), Current.Deck.GetRotation(), Alpha).GetNormalized());
    Deck.SetLocation(FMath::Lerp(Previous.Deck.GetLocation(), Current.Deck.GetLocation(), Alpha));
    // The root is the deck's pivot at rest, as the native runtime publishes it; the camera follows the ground point.
    Root = FTransform(Frame_, At + Frame_.GetUpVector() * Tune.DeckHeight);
    Velocity = V;

    FRideBodyPose& Body = BodyPose;
    Body = FRideBodyPose();
    Body.Motion = Motion; Body.MotionTime = MotionTime; Body.PreviousMotion = PreviousMotion; Body.Clock = Clock;
    Body.Lag = (1.f - Alpha) * Tick60;
    Body.Trick = PendingPop != Flick::None ? PendingPop : Trick_;
    Body.PopTime = PendingPop != Flick::None ? PopTimer : -1.f; Body.PopDelay = PopWait;
    Body.TrickTime = TrickTime; Body.bTrickFakie = bTrickFakie;
    Body.AirTime = AirTime;
    Body.TimeToLand = Mode == ERideState::Air && LandTime >= 0 ? FMath::Max(0.f, LandTime - (AirTime - PredictStart)) : -1.f;
    Body.LandUp = float(LandNormal.Z); Body.FallTime = Mode == ERideState::Air ? FMath::Max(0.f, float(-V.Z) / FMath::Max(1.f, Gravity())) : 0.f;
    Body.Grab = Grab; Body.GrabTime = GrabTime; Body.GrabWeight = GrabWeight; Body.LastGrab = LastGrab; Body.SinceGrab = SinceGrab;
    Body.Speed = V.Size();
    const float Turning = FMath::Clamp(TurnRate / FMath::Max(1.f, Tune.MaxYawRate + Tune.YawRatePerSpeed * float(V.Size())), -1.f, 1.f);
    // Toward the rider's toes: a regular rider's toes are on the board's right (+Y).
    Body.Lean = Turning * RiderTravel() * (GoofyNow() ? -1.f : 1.f);
    Body.Crouch = Crouch;
    Body.PushTime = PushTime; Body.PushCount = PushCount; Body.PushStrong = PushStrong;
    Body.PushLead = PushLead; Body.PushContact = PushContact; Body.PushRecover = PushRecover;
    Body.StillTime = StillTime; Body.bWasStill = bWasStill;
    Body.LoadTime = Flicks.LoadTime(); Body.bNoseLoad = Flicks.NoseLoaded();
    Body.Balance = Mode == ERideState::Manual ? Manuals.Balance() : 0.f; Body.SlideAngle = SlideYaw;
    Body.bSlideFront = SlideYaw * RiderTravel() * (GoofyNow() ? -1.f : 1.f) < 0;   // the toes lead
    Body.LandAge = LandAge; Body.LandImpact = LandImpact; Body.bLandedFromGrab = bLandedFromGrab; Body.Sketchy = Sketchy;
    Body.Grind = GrindKind; Body.bGrindFront = bGrindFront;
    Body.BailTime = Mode == ERideState::Bail ? ModeTime : -1.f;
    Body.bGoofy = GoofyNow(); Body.bFakie = RiderTravel() < 0;
    Body.SwitchTime = SwitchTime; Body.SwitchRate = SwitchRate; Body.bSwitch = bSwitch; Body.Turns = Turns;
    FRideBoardPose Board;
    Board.Deck = Deck; Board.WheelSpin = WheelSpin; Board.DeckHeight = Tune.DeckHeight;
    Board.bOnWheels = Mode == ERideState::Ground || Mode == ERideState::Manual || Mode == ERideState::Powerslide;
    if (Names.Num() != Animator.GetNames().Num()) { Names = Animator.GetNames(); Reference = Animator.GetReference(); }
    const double AnimStart = FPlatformTime::Seconds();
    Animator.Evaluate(Body, Board, Dt, Bones);
    AnimCost = float((FPlatformTime::Seconds() - AnimStart) * 1000.);
    MeasurePose(Dt);
    // The clip's own motion of the deck on the session's (the animator places the deck bone on Board.Deck): with the
    // session's pose it is the board shown, and the box the next ticks collide.
    ShownClip = Bones.IsValidIndex(DeckBone) ? Bones[DeckBone] * Board.Deck.Inverse() : FTransform::Identity;
    ShownClip.SetScale3D(FVector::OneVector);
    const bool bRidingDeck = Mode != ERideState::Bail && Mode != ERideState::GetUp && ShownClip.GetLocation().SizeSquared() <= FMath::Square(ShownReach);
    if (!bRidingDeck)
    {
        if (!bShownOff && Mode != ERideState::Bail && Mode != ERideState::GetUp)
            UE_LOG(LogTemp, Display, TEXT("SKATE ride box: the shown deck is %.0f cm off the session's (not the riding deck): the box keeps the session's deck"),
                float(ShownClip.GetLocation().Size()));
        ShownClip = FTransform::Identity;
    }
    bShownOff = !bRidingDeck;

    switch (Mode)
    {
    case ERideState::Powerslide: State = TEXT("SlideGround"); break;
    case ERideState::Air: State = TEXT("PhysicsAir"); break;
    case ERideState::Bail: State = TEXT("WipeoutGround"); break;
    case ERideState::GetUp: State = TEXT("WipeoutRecover"); break;
    case ERideState::Grind:
        switch (GrindKind)
        {
        case ERideGrind::FiveO: State = TEXT("GrindFiveO"); break;
        case ERideGrind::Nosegrind: State = TEXT("GrindNosegrind"); break;
        case ERideGrind::Crooked: State = TEXT("GrindCrooked"); break;
        case ERideGrind::Boardslide: State = TEXT("GrindBoardslide"); break;
        case ERideGrind::Lipslide: State = TEXT("GrindLipslide"); break;
        default: State = TEXT("GrindFiftyFifty"); break;
        }
        break;
    default: State = TEXT("PhysicsGround"); break;
    }
    // The trick line: the last few tricks, then what is being held or flipped now.
    TArray<FString> Shown;
    for (int32 I = FMath::Max(0, Line.Num() - 3); I < Line.Num(); ++I) Shown.Add(Line[I].Name);
    if (!Holding.IsEmpty()) Shown.Add(Holding);
    else if (Mode == ERideState::Air && Trick_ != Flick::None) Shown.Add(FlickName(Trick_, bTrickFakie, bTrickSwitch));
    Trick = FString::Join(Shown, TEXT(" + "));
    float LineSum = HeldPoints; for (const FLineTrick& T : Line) LineSum += T.Points;
    Score = Banked + LineSum * FMath::Max(1, Line.Num() + (Holding.IsEmpty() ? 0 : 1));
    // Native's published balance (animation_input's): non-zero through a manual once its balance attribute is there
    // (not in a nose manual's Into), which is how the HUD tells one.
    const float Balance = Manuals.Balance();
    ManualBalance = Mode == ERideState::Manual && !Manuals.Into() ? (FMath::Abs(Balance) < .001f ? (Balance < 0 ? -.001f : .001f) : Balance) : 0.f;

    UpdateCamera(At, Frame_, Dt);
}

void FRideSession::MeasurePose(float Dt)
{
    if (BodyBone.Num() != Names.Num())
    {
        BodyBone.SetNum(Names.Num());
        for (int32 I = 0; I < Names.Num(); ++I)
        {
            const FString Name = Names[I].ToString();
            BodyBone[I] = !Name.Contains(TEXT("SKATEBOARD")) && !Name.Contains(TEXT("TRUCK")) && !Name.Contains(TEXT("WHEEL")) && !Name.Contains(TEXT("REPARENTED"));
        }
        DeckBone = Names.IndexOfByKey(FName(TEXT("SKATEBOARD_ROOT")));
        ToeBone[0] = Names.IndexOfByKey(FName(TEXT("LEFTTOEBASE")));
        ToeBone[1] = Names.IndexOfByKey(FName(TEXT("RIGHTTOEBASE")));
        LastBones.Reset();
        HipsBone = Names.IndexOfByKey(FName(TEXT("HIPS")));
        HeadBone = Names.IndexOfByKey(FName(TEXT("HEAD")));
        ChestBone = Names.IndexOfByKey(FName(TEXT("SPINE3")));
        const int32 Arm[2] = {Names.IndexOfByKey(FName(TEXT("LEFTARM"))), Names.IndexOfByKey(FName(TEXT("RIGHTARM")))};
        if (Reference.IsValidIndex(Arm[0]) && Reference.IsValidIndex(Arm[1]) && Reference.IsValidIndex(HeadBone) && Reference.IsValidIndex(ChestBone))
        {
            // Facing away from the back: up crossed with the line from the right shoulder to the left one.
            const FVector Facing = FVector::CrossProduct(FVector::UpVector, Reference[Arm[0]].GetLocation() - Reference[Arm[1]].GetLocation()).GetSafeNormal();
            HeadAxis = Reference[HeadBone].GetRotation().UnrotateVector(Facing);
            ChestAxis = Reference[ChestBone].GetRotation().UnrotateVector(Facing);
        }
    }
    PoseNaN = 0;
    for (const FTransform& Bone : Bones) if (Bone.ContainsNaN()) ++PoseNaN;
    // The fastest body bone. The bones are in the root's space, so the ride's own travel and turning do not count.
    PoseStep = 0; PoseStepBone = INDEX_NONE; PoseDt = Dt;
    const bool bStep = LastBones.Num() == Bones.Num() && Dt > 1e-4f;
    LastBones.SetNum(Bones.Num(), EAllowShrinking::No);
    for (int32 I = 0; I < Bones.Num(); ++I)
    {
        const FVector Local = Bones[I].GetLocation();
        const float Step = bStep && BodyBone[I] ? float(FVector::Dist(Local, LastBones[I])) / Dt : 0.f;
        if (Step > PoseStep) { PoseStep = Step; PoseStepBone = I; }
        LastBones[I] = Local;
    }
    FeetOff = 0;
    if (Bones.IsValidIndex(DeckBone))
        for (int32 F = 0; F < 2; ++F)
        {
            if (!Bones.IsValidIndex(ToeBone[F])) continue;
            const FVector Local = Bones[DeckBone].InverseTransformPosition(Bones[ToeBone[F]].GetLocation());
            // Along the travel: the deck's own length runs against it on a board left end for end.
            FootHeight[F] = float(Local.Z); FootAlong[F] = float(Local.X) * Travel * (Animator.IsBoardReversed() ? -1.f : 1.f);
            // Off the deck: beyond its outline or clear of its grip.
            if (FMath::Abs(Local.X) > 42.f || FMath::Abs(Local.Y) > 14.f || Local.Z > 16.f || Local.Z < -4.f) ++FeetOff;
        }
    HipBoard = Bones.IsValidIndex(HipsBone) && Bones.IsValidIndex(DeckBone) ? float(Bones[HipsBone].GetLocation().Z - Bones[DeckBone].GetLocation().Z) : 0.f;
    auto FromTravel = [this](int32 Bone, const FVector& Axis)
    {
        if (!Bones.IsValidIndex(Bone)) return 0.f;
        const FVector Facing = Bones[Bone].GetRotation().RotateVector(Axis);
        return FMath::RadiansToDegrees(FMath::Atan2(FMath::Abs(float(Facing.Y)), float(Facing.X) * Travel));
    };
    HeadYaw = FromTravel(HeadBone, HeadAxis); ChestYaw = FromTravel(ChestBone, ChestAxis);
}

FString FRideSession::DescribePose() const
{
    return FString::Printf(TEXT("clip=%s ct=%.3f lock=%.2f lift=%.1f step=%.0f stepbone=%s dt=%.1f feet=%.1f,%.1f feetoff=%d nan=%d anim=%.3f hipboard=%.1f headyaw=%.1f chestyaw=%.1f fakiech=%.2f torso=%.2f feetalong=%.1f,%.1f turns=%u swt=%.3f mirror=%d reversed=%d camyaw=%.1f wheel=%.1f queries=%.1f/%d"),
        *Animator.GetMainClip().ToString(), Animator.GetMainTime(), Animator.GetLock(), Animator.GetLift(), PoseStep,
        Names.IsValidIndex(PoseStepBone) ? *Names[PoseStepBone].ToString() : TEXT("none"), PoseDt * 1000.f,
        FootHeight[0], FootHeight[1], FeetOff, PoseNaN, AnimCost, HipBoard, HeadYaw, ChestYaw, Animator.GetFakieWeight(), Animator.GetTorso(),
        FootAlong[0], FootAlong[1], Turns, SwitchTime, Animator.GetMirror(), Animator.IsBoardReversed(), Camera.Rotator().Yaw, WheelSpin, QueriesMean, QueriesWorst)
        + DescribeFlick();
}

FString FRideSession::DescribeFlick() const
{
    // The last recognised trick: serial, Native's trick, the gesture's set and pattern, GestureSpeed, the group
    // (0 square, 1 nose, 2 tail) and whether the mapping was mirrored (a regular stance).
    const atelier::ride::FlickEvent& E = Flicks.Event();
    return FString::Printf(TEXT(" gesture=%u,%s,%d,%d,%.3f,%d,%d"), E.Serial, E.NativeTrick.empty() ? TEXT("-") : UTF8_TO_TCHAR(E.NativeTrick.c_str()),
        int32(E.Gesture.Set), int32(E.Gesture.Pattern), E.Strength, int32(E.Group), E.bMirrored ? 1 : 0);
}

void FRideSession::StepOffBoard(float Dt, const FTransform& TrajectoryWorld)
{
    Cues.Reset();
    Root = TrajectoryWorld;
    if (Names.Num() != Animator.GetNames().Num()) { Names = Animator.GetNames(); Reference = Animator.GetReference(); }
    Animator.EvaluateFree(Dt, Bones);
}

void FRideSession::UpdateCamera(const FVector& At, const FQuat& Frame_, float Dt)
{
    // A follow camera behind the travel: it turns with the horizontal velocity on level ground and holds its heading
    // on walls and in the air, so a vert air or a bowl carve does not swing it around.
    const FVector Flat(V.X, V.Y, 0);
    const bool bSteady = (Mode == ERideState::Ground || Mode == ERideState::Manual || Mode == ERideState::Powerslide || Mode == ERideState::Grind) && Frame_.GetUpVector().Z > .75f;
    if (!bCamValid)
    {
        const FVector Facing = Flat.Size() > 50.f ? Flat.GetSafeNormal() : FVector(Frame_.GetForwardVector().X, Frame_.GetForwardVector().Y, 0).GetSafeNormal() * Travel;
        CamHeading = Facing.IsNearlyZero() ? FVector::ForwardVector : Facing;
    }
    else if (bSteady && Flat.Size() > 120.f)
    {
        const FVector Want = Flat.GetSafeNormal();
        const float Rate = FMath::Clamp(Flat.Size() / 400.f, .3f, 1.f) * Tune.CameraTurnRate;
        CamHeading = FMath::Lerp(CamHeading, Want, Damp(Rate, Dt)).GetSafeNormal();
        if (CamHeading.IsNearlyZero()) CamHeading = Want;
    }
    const FVector Body = At + FVector(0, 0, Tune.CameraLookHeight);
    FVector Wanted = At + FVector(0, 0, Tune.CameraHeight) - CamHeading * Tune.CameraDistance;
    if (!bCamValid) CamPos = Wanted;
    else
    {
        const float A = Damp(Tune.CameraFollow, Dt), B = Damp(Tune.CameraFollowZ, Dt);
        CamPos.X = FMath::Lerp(CamPos.X, Wanted.X, A); CamPos.Y = FMath::Lerp(CamPos.Y, Wanted.Y, A); CamPos.Z = FMath::Lerp(CamPos.Z, Wanted.Z, B);
        // Never fall behind by much more than the set distance (fast drops, long airs).
        const FVector Off = CamPos - Body;
        if (Off.Size() > Tune.CameraDistance * 1.6f) CamPos = Body + Off.GetSafeNormal() * Tune.CameraDistance * 1.6f;
    }
    bCamValid = true;
    // Pull in before walls.
    FVector Eye = CamPos;
    FHitResult Hit;
    if (Sweep(Body, CamPos, 12.f, Hit) && !Hit.bStartPenetrating) Eye = Hit.Location;
    const FVector Look = Body + CamHeading * Tune.CameraLookAhead;
    Camera = FTransform(FRotationMatrix::MakeFromX(Look - Eye).ToQuat(), Eye);
    CameraFOV = Tune.CameraFOV + Tune.CameraSpeedFOV * FMath::Clamp(float(V.Size()) / Tune.CameraFOVSpeed, 0.f, 1.f);
}
