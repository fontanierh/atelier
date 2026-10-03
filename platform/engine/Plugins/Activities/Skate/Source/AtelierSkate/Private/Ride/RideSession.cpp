#include "RideSession.h"
#include "SkateRails.h"
#include "Engine/World.h"
#include "Engine/HitResult.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "HAL/PlatformTime.h"

using atelier::ride::Flick;

namespace
{
    constexpr float Tick60 = 1.f / 60.f;
    constexpr float G = 980.f;
    // The landing's give plays for this long after a touch-down (RideAnimator).
    constexpr float LandHold = 1.f;

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
    // The native PumpVsVel: a pump's share by speed (cm/s), from 7 m/s up (below it native's share rises past 1; the
    // coasting pump keeps the deliberate pump's 1 there).
    const float PumpCurve[][2] = {{0, 1}, {701, 1}, {881, .964f}, {1068, .571f}, {1220, .157f}, {1420, .007f}};
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

FRideSession::FRideSession() : Tune(FRideTuning::Get()) {}

void FRideSession::Activate(const FRideWorld& World, const FVector& GroundPoint, const FQuat& Rotation, const FVector& InVelocity, bool bInGoofy, const FRidePreferences& Preferences)
{
    Where = World; Tune = FRideTuning::Get();
    Configure(bInGoofy, Preferences);
    Animator.Preload();
    Animator.Attach(World.Owner);
    Names = Animator.GetNames(); Reference = Animator.GetReference();
    P = GroundPoint; V = InVelocity; Q = Rotation.GetNormalized();
    Travel = FVector::DotProduct(V, Q.GetForwardVector()) < -15.f ? -1.f : 1.f;
    TurnRate = SlideYaw = Curvature = Crouch = 0; PushTime = -1; BrakeTime = 0; PendingPop = Flick::None; TrailNum = 0;
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; Rail = INDEX_NONE; Balance = 0;
    Line.Reset(); Holding.Reset(); HeldPoints = 0; Calm = 0; Trick.Reset(); Flicks.Reset(); Cues.Reset();
    // The clock starts a step full, so the first frame shows the start moved on by that frame's time, as every later
    // frame does. Empty, the first Step ran one tick and showed it at alpha 0 (the start again, a frame's hold), and
    // the shown board trailed real time by a tick for the whole ride.
    Accumulator = Tick60 - KINDA_SMALL_NUMBER; bCamValid = false;
    PushCount = 0; StillTime = -1; bStill = bWasStill = false; LastGrab = ERideGrab::None; SinceGrab = -1;
    LandAge = -1; LandImpact = 0; bLandedFromGrab = false; Sketchy = 0; Clock = 0;
    bSteppingOff = bThroughLine = bPushFromRest = false;
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
    else { SetMode(ERideState::Air); AirTime = 0; TakeoffUp = Q.GetUpVector(); bPopped = true; bLipAir = false; ResetPrediction(P); }
    if (Mode == ERideState::Ground) V = FVector::VectorPlaneProject(V, Q.GetUpVector());
    Motion = PreviousMotion = CurrentMotion(); MotionTime = 0;
    Previous.P = Current.P = P; Previous.Q = Current.Q = Q; Previous.Deck = Current.Deck = DeckPose();
    Publish(1.f, 0.f, FSkateInput());
}

void FRideSession::Configure(bool bInGoofy, const FRidePreferences& Preferences)
{
    bGoofy = bInGoofy; Prefs = Preferences;
}

void FRideSession::Launch(const FVector& InVelocity)
{
    V = InVelocity;
    if (Mode == ERideState::Ground || Mode == ERideState::Manual || Mode == ERideState::Powerslide)
    {
        const FVector Up = Q.GetUpVector();
        if (FVector::DotProduct(V, Up) > 50.f) TakeOff(0.f);
        else
        {
            V = FVector::VectorPlaneProject(V, Up);
            const float Along = FVector::DotProduct(V, Q.GetForwardVector());
            if (FMath::Abs(Along) > 1.f) Travel = Along < 0 ? -1.f : 1.f;
        }
    }
}

float FRideSession::Random()
{
    Noise ^= Noise << 13; Noise ^= Noise >> 17; Noise ^= Noise << 5;
    return float(Noise & 0xFFFFFF) / float(0xFFFFFF) * 2.f - 1.f;
}

void FRideSession::Step(float Dt, const FSkateInput& Input, const FRideWorld& World)
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
        Tick(Input);
        Current.P = P; Current.Q = Q; Current.Deck = DeckPose();
        Accumulator -= Tick60; ++Count;
    }
    if (Count > 0)
    {
        const double Cost = (FPlatformTime::Seconds() - Start) * 1000. / Count;
        CostSum += Cost * Count; CostCount += Count; CostMax = FMath::Max(CostMax, Cost);
        CostClock += Count * Tick60;
        if (CostClock >= 1.)
        {
            CostMean = float(CostSum / FMath::Max(1, CostCount)); CostWorst = float(CostMax);
            CostSum = CostMax = CostClock = 0; CostCount = 0;
        }
    }
    Publish(Accumulator / Tick60, Dt, Input);
}

void FRideSession::SetMode(ERideState NewMode)
{
    if (Mode == NewMode) return;
    Mode = NewMode; ModeTime = 0;
    if (NewMode != ERideState::Air) bSteppingOff = bThroughLine = false;
}

void FRideSession::Tick(const FSkateInput& In)
{
    // The reader works in regular stance: a goofy rider's stick is mirrored, so the same gesture does the same trick
    // with the other foot.
    const Flick F = Flicks.Update(bGoofy ? -float(In.Right.X) : float(In.Right.X), float(In.Right.Y), Tick60);
    ModeTime += Tick60; Clock += Tick60;
    if (TrickTime >= 0) TrickTime += Tick60;
    if (LandAge >= 0) LandAge += Tick60;
    RailCooldown = FMath::Max(0.f, RailCooldown - Tick60);
    if (In.bBail && Mode != ERideState::Bail && Mode != ERideState::GetUp) StartBail(TEXT("thrown off"));
    switch (Mode)
    {
    case ERideState::Ground: case ERideState::Powerslide: case ERideState::Manual: TickGround(In, F); break;
    case ERideState::Air: TickAir(In, F); break;
    case ERideState::Grind: TickGrind(In, F); break;
    case ERideState::Bail: case ERideState::GetUp: TickBail(); break;
    }
    // The curvature's trail starts afresh on every return to the ground.
    if (Mode != ERideState::Ground && Mode != ERideState::Powerslide && Mode != ERideState::Manual) TrailNum = 0;
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
    ++Ticks;
}

ERideMotion FRideSession::CurrentMotion() const
{
    switch (Mode)
    {
    case ERideState::Ground:
        if (PendingPop != Flick::None) return ERideMotion::Pop;
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
    return Where.World->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(Radius), Params);
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

    // Pops: a flick starts the pop clip and the board leaves when its ground part ends.
    if (F != Flick::None && PendingPop == Flick::None && Mode != ERideState::Powerslide)
    {
        PendingPop = F; PendingLoad = Flicks.PopLoad(); PopTimer = 0; Cues.Add(ERideCue::Flick);
        // The board leaves when the pop clip's ground part ends.
        PopWait = Animator.PopDelay(F, Tune.PopDelay);
        // A manual's flick leaves sooner: the board is already up on one truck.
        if (Mode == ERideState::Manual) PopTimer = PopWait * .5f;
    }
    if (PendingPop != Flick::None)
    {
        PopTimer += Tick60;
        if (PopTimer >= PopWait)
        {
            const Flick Pop = PendingPop; PendingPop = Flick::None;
            if (Mode == ERideState::Manual) { EndHold(); SetMode(ERideState::Ground); }
            StartTrick(Pop);
            TakeOff(PopSpeed(PendingLoad) * (Pop == Flick::Nollie ? Tune.NollieScale : 1.f));
            return;
        }
    }

    // Manuals: the right stick part-way down (tail) or up (nose).
    const int32 Band = Flicks.ManualBand();
    if (Mode == ERideState::Ground && Band != 0 && PendingPop == Flick::None && Speed > 60.f)
    {
        SetMode(ERideState::Manual); bNoseManual = Band > 0; Balance = .08f * (Random() >= 0 ? 1.f : -1.f);
        PushTime = -1;
    }
    if (Mode == ERideState::Manual)
    {
        if (Band == 0 && PendingPop == Flick::None) { EndHold(); SetMode(ERideState::Ground); }
        else
        {
            const float Wobble = Random() * Tune.ManualWobble * FMath::Clamp(Speed / 785.f, .29f, 1.f);
            Balance += (Tune.ManualInstability * Balance + Wobble - Tune.ManualControl * Flicks.BandOffset()) * Tick60;
            Hold(bNoseManual ? TEXT("Nose Manual") : TEXT("Manual"), 150.f, Tick60);
            if (FMath::Abs(Balance) >= 1.f) { EndHold(); SetMode(ERideState::Ground); Balance = 0; }
        }
    }

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
    if (Mode == ERideState::Manual) Decel += Tune.ManualFriction;

    // Pushing, in time with the push cycle; a tap gives one weak push.
    const bool bCanPush = Mode == ERideState::Ground && bFlat && PendingPop == Flick::None && !In.bBrake;
    if (bCanPush && In.bPush && PushTime < 0) StartPush(true, Speed);
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
                if (Travel < 0) { Travel = 1.f; Speed = -Speed; }
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
                // The same push per contact whatever its length (the fast push's contact is shorter).
                const float Accel = Tune.PushAccel * Prefs.PushPower * Tune.PushContactLength / FMath::Max(.02f, PushContact);
                if (Speed < Goal) Speed = FMath::Min(Goal, Speed + Accel * Tick60);
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

    // Pumping: extending through a concave transition gains speed (the rider crouches on flats and crests). Holding
    // push pumps; coasting through a steep transition pumps by itself, AutoPump as much and less with speed (the
    // native runtime's unintentional pump, its PumpVsVel), so a rider going back and forth keeps up speed.
    const bool bAutoPump = !In.bPush && !In.bBrake && !bFlat && Mode == ERideState::Ground && Tune.AutoPump > 0;
    const float CrouchTarget = PendingPop != Flick::None || Flicks.Loaded() ? 1.f : ((In.bPush || bAutoPump) && !bFlat) ? (Curvature > 1e-4f ? 0.f : 1.f) : .25f;
    const float OldCrouch = Crouch;
    Crouch += (CrouchTarget - Crouch) * Damp(Tune.CrouchRate, Tick60);
    const float PumpShare = In.bPush ? 1.f : bAutoPump ? Tune.AutoPump * Curve(PumpCurve, Speed) : 0.f;
    if (Curvature > 0 && Crouch < OldCrouch) Speed *= FMath::Exp(Curvature * (OldCrouch - Crouch) * Tune.PumpExtension * PumpShare);

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

    // Move, stopping at walls.
    FVector Move = V * Dt;
    const float Lift = Tune.WheelRadius + 8.f;
    FHitResult Wall;
    if (!Move.IsNearlyZero() && Sweep(P + Up * Lift, P + Up * Lift + Move, 7.f, Wall) && !Wall.bStartPenetrating &&
        FVector::DotProduct(Wall.ImpactNormal, Up) < Tune.WallSlope)
    {
        const FVector N = FVector::VectorPlaneProject(Wall.ImpactNormal, Up).GetSafeNormal();
        if (-FVector::DotProduct(V, N) > Tune.WallBailSpeed) { StartBail(TEXT("wall")); return false; }
        Move *= Wall.Time;
        Deflect(N, Speed);
    }
    const FVector Next = P + Move;

    // Follow the surface; leave it when it falls away faster than the board can follow.
    FVector Ground, NewUp, NewForward, Block = FVector::ZeroVector; bool bBlocked = false;
    const float Below = Tune.StickGap + Tune.StickPerSpeed * Speed * Dt;
    if (!FindGround(Next, Q, Below, Ground, NewUp, NewForward, bBlocked, &Block, V))
    {
        if (!bBlocked) { P = Next; TakeOff(0.f); return false; }
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
        P = Next; TakeOff(0.f); return false;
    }
    P = Ground; Odometer = At;
    AddTrail(At, NewUp);
    // Keep the board's heading (nose or tail leading) in the new plane.
    const FVector Heading = FVector::VectorPlaneProject(Q.GetForwardVector(), NewUp).GetSafeNormal();
    Q = Frame(NewUp, Heading.IsNearlyZero() ? NewForward : Heading);
    V = Q.GetForwardVector() * Travel * Speed;
    return true;
}

void FRideSession::StartPush(bool bFirstPush, float Speed)
{
    PushTime = 0; bPushStrong = true; bPushed = false;
    bPushFromRest = bFirstPush && Speed < Tune.PushFromRest;
    PushCount = bFirstPush ? 0 : PushCount + 1;
    PushStrong = FMath::Clamp((Speed - 450.f) / 700.f, 0.f, 1.f);
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
    Trick_ = F; TrickTime = 0; bTrickFakie = Travel < 0;
}

void FRideSession::TakeOff(float Pop)
{
    const FVector Up = Q.GetUpVector();
    V += Up * Pop;
    bPopped = Pop > 0;
    // Vert assist and transfers are applied on the first air tick (TickAir), where the transfer input is read.
    SetMode(ERideState::Air);
    AirTime = 0; TakeoffUp = Up; SpinTotal = 0; bLipAir = false;
    SpinRate = TurnRate * Tune.SpinCarry;
    TurnRate = 0; SlideYaw = 0; PushTime = -1; BrakeTime = 0; StillTime = -1; Balance = 0; EndHold();
    LastGrab = ERideGrab::None; SinceGrab = -1;
    ResetPrediction(P + Up * 12.f);
    AdvancePrediction(4);
}

void FRideSession::ResetPrediction(const FVector& From)
{
    PredictFrom = From; PredictVelocity = V; PredictTime = 0; PredictStart = AirTime; LandTime = -1; LandNormal = FVector::UpVector;
}

// ---------------------------------------------------------------------------------------------------------------
// Air: ballistic flight, spins, the flip, grabs, grinds, landing.

void FRideSession::AdvancePrediction(int32 Segments)
{
    // Trace the ballistic path of the deck's centre a tenth of a second at a time, up to 3 s ahead.
    if (LandTime >= 0 || PredictTime > 3.f) return;
    for (int32 I = 0; I < Segments; ++I)
    {
        const float Dt = .1f;
        const FVector From = PredictFrom, To = From + PredictVelocity * Dt + FVector(0, 0, -.5f * Gravity() * Dt * Dt);
        FHitResult Hit;
        if (Sweep(From, To, 10.f, Hit) && !Hit.bStartPenetrating)
        {
            LandTime = PredictTime + Dt * Hit.Time; LandNormal = Hit.Normal;
            return;
        }
        PredictFrom = To; PredictVelocity.Z -= Gravity() * Dt; PredictTime += Dt;
        if (PredictTime > 3.f) return;
    }
}

float FRideSession::Gravity() const
{
    return bLipAir ? Tune.VertGravity : Tune.AirGravity;
}

void FRideSession::ChooseLanding(const FVector& From)
{
    // Native's cone (AirTrajectoryLaunch): the velocity and six around it, 10 degrees across its level heading and 40
    // along it at a cone speed of 2 to 4 m/s, none faster than the velocity. Each flies under the lip's gravity for up
    // to 3 s; a miss or a landing within .25 s does not count. The score is native's transition term: the landing
    // face's normal along the lip's (the face it left scores most, steepest highest, the deck behind the coping
    // nothing), scaled by the take-off face's steepness, less 500 for coming down within .15 s of the apex; then the
    // smallest change (a tenth of a point per cm/s).
    const float Speed = V.Size();
    if (Speed > 1.f)
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
                if (Sweep(At, To, 10.f, Hit) && !Hit.bStartPenetrating) { Land = T + Dt * Hit.Time; Normal = Hit.Normal; break; }
                At = To; Vel.Z -= Fall * Dt; T += Dt;
            }
            if (Land < .25f) continue;
            const float Apex = C.Z > 0 ? float(C.Z) / Fall : 0.f;
            const float Rank = 500.f * float(FVector::DotProduct(Normal, LipOut)) * Steep - (FMath::Abs(Land - Apex) < .15f ? 500.f : 0.f)
                - .1f * float((C - V).Size());
            if (Rank > BestRank) { BestRank = Rank; Best = C; }
        }
        V = Best;
    }
    ResetPrediction(From);
}

void FRideSession::TickAir(const FSkateInput& In, Flick F)
{
    AirTime += Tick60;
    // The lip (native's vert test): off a face steeper than the vert reach (VertSteepness at VertAssist 1, 75 degrees
    // at 0), climbing at least VertClimb steeply, the velocity that would carry the rider over the coping is lost and
    // the climb is turned to VertLean from vertical, back into the ramp, at its own speed (the part along the coping
    // is kept). The flight then picks its landing back in (ChooseLanding) and falls under VertGravity. Holding
    // transfer carries the rider over instead.
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
            if (In.bTransfer) V -= Out * Tune.TransferPush;
            else if (V.Z >= Tune.VertClimb * FMath::Sqrt(FMath::Square(float(V.Z)) + Into * Into))
            {
                V += Out * Into;
                const FVector Coping = FVector::CrossProduct(FVector::UpVector, Out);
                const float Side = FVector::DotProduct(V, Coping);
                const float Lean = FMath::DegreesToRadians(Tune.VertLean);
                V = (FVector(0, 0, FMath::Cos(Lean)) + Out * FMath::Sin(Lean)) * (V - Coping * Side).Size() + Coping * Side;
                bLipAir = true; LipOut = Out;
                ChooseLanding(P + Up * 12.f);
            }
            ResetPrediction(P + Up * 12.f);
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
            if (bLipAir) { V.Z += PopSpeed() * .8f * FMath::Sqrt(Gravity() / Tune.AirGravity); ChooseLanding(P + Q.GetUpVector() * 12.f); }
            else { V += TakeoffUp * PopSpeed() * .8f; ResetPrediction(P + Q.GetUpVector() * 12.f); }
        }
        StartTrick(F);
    }
    // Spin: the left stick turns the rider about the body's axis (the take-off normal).
    // Off flat ground the body turns slower than off a lip (the reference: about 290 degrees in an ollie).
    const float FullSpin = TakeoffUp.Z > .9f ? Tune.FlatSpinRate : Tune.SpinRate;
    float SpinTarget = FMath::Abs(In.Left.X) > .25f ? float(In.Left.X) * FullSpin * Prefs.Spin : (SpinRate > 0 ? FMath::Min(SpinRate, 115.f) : FMath::Max(SpinRate, -115.f));
    // In a lip air with the stick released, the board turns to the nearer of forward and fakie on the landing's line
    // by touch-down, at native's rate: the angle left over the time left (at least 2 ticks), times 1.2.
    const float ToLand = LandTime >= 0 ? LandTime - (AirTime - PredictStart) : -1.f;
    if (bLipAir && FMath::Abs(In.Left.X) <= .25f && ToLand > 0)
    {
        const FVector Axis = Q.GetUpVector();
        const FVector Facing = FVector::VectorPlaneProject(Q.GetForwardVector(), Axis).GetSafeNormal();
        const FVector Path = FVector::VectorPlaneProject(V + FVector(0, 0, -Gravity() * ToLand), Axis).GetSafeNormal();
        if (!Facing.IsNearlyZero() && !Path.IsNearlyZero())
        {
            float Angle = FMath::RadiansToDegrees(FMath::Atan2(float(FVector::DotProduct(Axis, FVector::CrossProduct(Facing, Path))), float(FVector::DotProduct(Facing, Path))));
            if (Angle > 90.f) Angle -= 180.f;
            else if (Angle < -90.f) Angle += 180.f;
            SpinTarget = FMath::Clamp(Angle / FMath::Max(ToLand, 2.f * Tick60) * 1.2f, -FullSpin, FullSpin);
        }
    }
    SpinRate += (SpinTarget - SpinRate) * Damp(Tune.SpinResponse, Tick60);
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
    const FVector From = P + Q.GetUpVector() * 12.f;
    V.Z -= Gravity() * Tick60;
    const FVector Move = V * Tick60;
    FHitResult Hit;
    bool bHit = Sweep(From, From + Move, 10.f, Hit);
    if (bThroughLine)
    {
        // Stepping off a stalled grind: the line just left is no contact until the sphere is clear of it.
        auto FromLine = [this](const FVector& X) { return float(FVector::VectorPlaneProject(X - OffPoint, OffAlong).Size()); };
        if (bHit && FromLine(Hit.Location) <= OffClear) bHit = false;
        if (FromLine(From + Move) > OffClear || AirTime > .5f) bThroughLine = false;
    }
    if (bHit)
    {
        if (Hit.bStartPenetrating) { P += Hit.Normal * (Hit.PenetrationDepth + .1f); V = FVector::VectorPlaneProject(V, Hit.Normal); return; }
        const FVector Contact = Hit.Location - Hit.Normal * 12.f;
        if (TryLand(Contact, Hit.Normal)) return;
        if (Mode != ERideState::Air) return;
        // A glancing hit (a wall beside the flight): slide along it.
        P = Hit.Location - Q.GetUpVector() * 12.f;
        V = FVector::VectorPlaneProject(V, Hit.Normal) + Hit.Normal * FMath::Max(0.f, float(-FVector::DotProduct(V, Hit.Normal))) * Tune.WallRestitution;
        return;
    }
    P += Move;
    if (P.Z < -1e6) StartBail(TEXT("fell out of the world"));
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
    const FVector Along = FVector::VectorPlaneProject(V, Normal);
    const float Speed = Along.Size();
    const FVector Heading = FVector::VectorPlaneProject(Q.GetForwardVector(), Normal).GetSafeNormal();
    float Yaw = Speed > 30.f ? AngleBetween(Heading, Along) : 0.f;
    const bool bFakieLanding = Yaw > 90.f;
    if (bFakieLanding) Yaw = 180.f - Yaw;
    const bool bMidFlip = TrickTime >= 0 && TrickTime < CatchTime(Trick_) - .03f && Trick_ != Flick::Ollie && Trick_ != Flick::Nollie;
    float YawLimit = 90.f;
    if (Speed > Tune.SidewaysSafeSpeed) YawLimit = FMath::GetMappedRangeValueClamped(FVector2f(Tune.SidewaysSafeSpeed, 2000.f), FVector2f(90.f, Tune.BailYawFast), Speed);
    const TCHAR* Why = Tilt > Tune.BailTilt ? TEXT("landed tilted") : Impact > Tune.BailImpact ? TEXT("landed too hard") :
        Yaw >= YawLimit && !bSteppingOff ? TEXT("landed sideways") : bMidFlip ? TEXT("landed on the board mid-flip") :
        (Grab != ERideGrab::None && GrabWeight > .6f && AirTime > .25f) ? TEXT("landed holding the grab") : nullptr;
    P = Point;
    if (Why) { StartBail(Why); return true; }
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
    if (Trick_ != Flick::None) AddTrick(FlickName(Trick_, bTrickFakie), FlipInfo(Trick_).Points);
    const float Spun = FMath::Abs(SpinTotal);
    if (Spun >= 150.f) AddTrick(SpinName(SpinTotal), 150.f * FMath::RoundToFloat(Spun / 180.f));
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; SpinTotal = 0; SpinRate = 0;
    TurnRate = 0; Curvature = 0; Calm = 0;
    Cues.Add(ERideCue::Catch);
    SetMode(ERideState::Ground);
    return true;
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
    const FVector Toes = Q.GetRightVector() * (bGoofy ? -1.f : 1.f);
    bGrindFront = FVector::DotProduct(Point - P, Toes) > 0;
    RailUp = FVector::CrossProduct(Tangent, FVector::CrossProduct(FVector::UpVector, Tangent)).GetSafeNormal();
    if (RailUp.Z < 0) RailUp = -RailUp;
    // The board closes onto the line over the next ticks, as fast as it was coming and no slower than GrindLockSpeed,
    // rather than jumping there (the native board touches the line before it locks).
    const bool bSlide = GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide;
    LockOffset = P - (Point - RailUp * (bSlide ? Tune.DeckHeight - 1.5f : Tune.WheelRadius + Line_.Radius));
    LockSpeed = FMath::Max(Tune.GrindLockSpeed, float(-FVector::DotProduct(V, LockOffset.GetSafeNormal())));
    // Score the air that led onto the rail.
    if (Trick_ != Flick::None) AddTrick(FlickName(Trick_, bTrickFakie), FlipInfo(Trick_).Points);
    Trick_ = Flick::None; TrickTime = -1;
    EndHold(); Grab = ERideGrab::None; GrabWeight = 0; SpinRate = 0; SpinTotal = 0;
    Cues.Add(ERideCue::Catch);
    SetMode(ERideState::Grind);
    TickGrind(In, Flick::None);
    return true;
}

void FRideSession::TickGrind(const FSkateInput& In, Flick F)
{
    if (!Where.Rails || !Where.Rails->Rails.IsValidIndex(Rail)) { TakeOff(0.f); return; }
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
    FVector Side = FVector::CrossProduct(FVector::UpVector, Tangent).GetSafeNormal() * (bGrindFront ? -1.f : 1.f) * (bGoofy ? -1.f : 1.f);
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
    V += FVector::UpVector * Up + Side * Aside;
    // Slides turn the board back along the travel (a stall's hop keeps it as it is).
    if (!bStall && (GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide || GrindKind == ERideGrind::Crooked))
        Q = Frame(FVector::UpVector, FVector::VectorPlaneProject(V, FVector::UpVector).GetSafeNormal() * (FVector::DotProduct(Q.GetForwardVector(), V) < 0 ? -1.f : 1.f));
    LastRail = Rail; RailCooldown = Tune.GrindRelock;
    Rail = INDEX_NONE;
    TurnRate = 0;
    const FVector UpVector = Q.GetUpVector();
    SetMode(ERideState::Air);
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
    BailAngular = Q.GetUpVector() * FMath::DegreesToRadians(SpinRate) + Q.GetForwardVector() * FMath::DegreesToRadians(FlipInfo(Trick_).Roll) * (TrickTime >= 0 ? 1.f : 0.f);
    LoseLine();
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; PendingPop = Flick::None; Rail = INDEX_NONE;
    SpinRate = 0; TurnRate = 0; SlideYaw = 0; PushTime = -1; StillTime = -1; Balance = 0;
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
        const FVector Next = P + V * Tick60;
        if (FindGround(Next, Frame(FVector::UpVector, Q.GetForwardVector()), 20.f, Ground, Up, Forward, bBlocked))
        { P = Ground; V = FVector::VectorPlaneProject(V, Up); }
        else if (!bBlocked) P = Next;
        if (ModeTime >= Tune.BailSettle) GetUp(P, Q.Rotator().Yaw);
        return;
    }
    // With a ragdoll the component calls GetUp when the body has settled; the root follows the body meanwhile, and
    // a body that never settles (stuck on geometry) still gets up.
    if (bFollowBody) { P = BodyPoint; V = FVector::ZeroVector; }
    if (ModeTime >= Tune.BailSettle + 5.f) GetUp(P, Q.Rotator().Yaw);
}

void FRideSession::GetUp(const FVector& GroundPoint, float Yaw)
{
    const FQuat Facing(FRotator(0, Yaw, 0));
    FVector Ground, Up, Forward; bool bBlocked = false;
    P = GroundPoint; Q = Facing;
    if (FindGround(P + FVector(0, 0, 30), Facing, 80.f, Ground, Up, Forward, bBlocked)) { P = Ground; Q = Frame(Up, Forward); }
    V = FVector::ZeroVector; Travel = 1; Sketchy = 0; Crouch = .25f; LandAge = -1;
    Previous.P = Current.P = P; Previous.Q = Current.Q = Q; Previous.Deck = Current.Deck = DeckPose();
    SetMode(ERideState::GetUp);
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

FString FRideSession::FlickName(Flick F, bool bFakie) const
{
    const FString Base = UTF8_TO_TCHAR(atelier::ride::FlickName(F));
    return bFakie && F != Flick::Nollie ? TEXT("Fakie ") + Base : Base;
}

FString FRideSession::SpinName(float Degrees) const
{
    // A spin up to 30 degrees short still counts (a 330 is a 360).
    const int32 Half = FMath::Max(1, FMath::RoundToInt((FMath::Abs(Degrees) - 30.f) / 180.f + .0001f));
    // A regular rider faces +Y (the board's right): turning that way (negative yaw) leads with the chest, frontside.
    const float Stance = bGoofy ? -1.f : 1.f;
    const bool bFrontside = Degrees * Stance * Travel < 0;
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
    if (Mode == ERideState::Manual)
    {
        // Up on one truck: the deck pitches about the axle that stays down.
        const float Pitch = Tune.ManualPitch * (.6f + .4f * FMath::Clamp(FMath::Abs(Balance), 0.f, 1.f));
        const float Axle = bNoseManual ? Tune.AxleX : -Tune.AxleX;
        const FQuat Tip = Turn(FVector::RightVector, bNoseManual ? Pitch : -Pitch);
        const FVector Pivot(Axle, 0, Tune.WheelRadius - Tune.DeckHeight);
        Offset = Pivot + Tip.RotateVector(-Pivot);
        Deck = Tip * Deck;
    }
    if (TrickTime >= 0 && Trick_ != Flick::None)
    {
        const FFlipInfo Flip = FlipInfo(Trick_);
        const float T = FMath::Clamp(TrickTime / FMath::Max(.05f, Flip.Time), 0.f, 1.f);
        const float Ease = 1.f - FMath::Square(1.f - T);
        const float Mirror = bGoofy ? -1.f : 1.f;
        const FQuat Roll = Turn(FVector::ForwardVector, Flip.Roll * Ease * Mirror);
        const FQuat Yaw = Turn(FVector::UpVector, Flip.Yaw * Ease * Mirror);
        // The ollie's pitch: nose up through the pop, level by the catch.
        const float Pitch = -40.f * FMath::Sin(PI * FMath::Clamp(TrickTime / .45f, 0.f, 1.f)) * (Trick_ == Flick::Nollie ? -1.f : 1.f) * (bTrickFakie ? -1.f : 1.f);
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
    Body.Lean = Turning * Travel * (bGoofy ? -1.f : 1.f);
    Body.Crouch = Crouch;
    Body.PushTime = PushTime; Body.PushCount = PushCount; Body.PushStrong = PushStrong;
    Body.PushLead = PushLead; Body.PushContact = PushContact; Body.PushRecover = PushRecover;
    Body.StillTime = StillTime; Body.bWasStill = bWasStill;
    Body.LoadTime = Flicks.LoadTime(); Body.bNoseLoad = Flicks.NoseLoaded();
    Body.Balance = Balance; Body.SlideAngle = SlideYaw;
    Body.bSlideFront = SlideYaw * Travel * (bGoofy ? -1.f : 1.f) < 0;   // the toes lead
    Body.LandAge = LandAge; Body.LandImpact = LandImpact; Body.bLandedFromGrab = bLandedFromGrab; Body.Sketchy = Sketchy;
    Body.Grind = GrindKind; Body.bGrindFront = bGrindFront;
    Body.BailTime = Mode == ERideState::Bail ? ModeTime : -1.f;
    Body.bGoofy = bGoofy; Body.bFakie = Travel < 0;
    FRideBoardPose Board;
    Board.Deck = Deck; Board.WheelSpin = WheelSpin; Board.DeckHeight = Tune.DeckHeight;
    Board.bOnWheels = Mode == ERideState::Ground || Mode == ERideState::Manual || Mode == ERideState::Powerslide;
    if (Names.Num() != Animator.GetNames().Num()) { Names = Animator.GetNames(); Reference = Animator.GetReference(); }
    const double AnimStart = FPlatformTime::Seconds();
    Animator.Evaluate(Body, Board, Dt, Bones);
    AnimCost = float((FPlatformTime::Seconds() - AnimStart) * 1000.);
    MeasurePose(Dt);

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
    else if (Mode == ERideState::Air && Trick_ != Flick::None) Shown.Add(FlickName(Trick_, bTrickFakie));
    Trick = FString::Join(Shown, TEXT(" + "));
    float LineSum = HeldPoints; for (const FLineTrick& T : Line) LineSum += T.Points;
    Score = Banked + LineSum * FMath::Max(1, Line.Num() + (Holding.IsEmpty() ? 0 : 1));
    ManualBalance = Mode == ERideState::Manual ? (FMath::Abs(Balance) < .001f ? (Balance < 0 ? -.001f : .001f) : FMath::Clamp(Balance, -1.f, 1.f)) : 0.f;

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
            FootHeight[F] = float(Local.Z); FootAlong[F] = float(Local.X) * Travel;
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
    return FString::Printf(TEXT("clip=%s ct=%.3f lock=%.2f lift=%.1f step=%.0f stepbone=%s dt=%.1f feet=%.1f,%.1f feetoff=%d nan=%d anim=%.3f hipboard=%.1f headyaw=%.1f chestyaw=%.1f fakiech=%.2f torso=%.2f feetalong=%.1f,%.1f"),
        *Animator.GetMainClip().ToString(), Animator.GetMainTime(), Animator.GetLock(), Animator.GetLift(), PoseStep,
        Names.IsValidIndex(PoseStepBone) ? *Names[PoseStepBone].ToString() : TEXT("none"), PoseDt * 1000.f,
        FootHeight[0], FootHeight[1], FeetOff, PoseNaN, AnimCost, HipBoard, HeadYaw, ChestYaw, Animator.GetFakieWeight(), Animator.GetTorso(),
        FootAlong[0], FootAlong[1]);
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
