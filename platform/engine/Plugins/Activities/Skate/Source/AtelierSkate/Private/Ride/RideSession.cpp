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
    TurnRate = SlideYaw = Curvature = Crouch = 0; PushTime = -1; BrakeTime = 0; PendingPop = Flick::None;
    Trick_ = Flick::None; TrickTime = -1; Grab = ERideGrab::None; GrabWeight = 0; Rail = INDEX_NONE; Balance = 0;
    Line.Reset(); Holding.Reset(); HeldPoints = 0; Calm = 0; Trick.Reset(); Flicks.Reset(); Cues.Reset();
    Accumulator = 0; bCamValid = false;
    PushCount = 0; StillTime = -1; bStill = bWasStill = false; LastGrab = ERideGrab::None; SinceGrab = -1;
    LandAge = -1; LandImpact = 0; bLandedFromGrab = false; Sketchy = 0; Clock = 0;
    // Settle onto whatever is under the board.
    FVector Ground, Up, Forward; bool bBlocked = false;
    if (FindGround(P, Q, 60.f, Ground, Up, Forward, bBlocked)) { P = Ground; Q = Frame(Up, Forward); SetMode(ERideState::Ground); }
    else { SetMode(ERideState::Air); AirTime = 0; TakeoffUp = Q.GetUpVector(); bPopped = true; ResetPrediction(P); }
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

bool FRideSession::Probe(const FVector& Base, const FVector& Up, float Above, float Below, FVector& Point, FVector& Normal, bool& bBlocked) const
{
    const float R = Tune.WheelRadius;
    FHitResult Hit;
    if (!Sweep(Base + Up * (Above + R), Base - Up * (Below - R), R, Hit)) return false;
    if (Hit.bStartPenetrating) { bBlocked = true; return false; }
    Normal = Hit.Normal;
    // A face too steep for the deck is a wall or a curb, not ground.
    if (FVector::DotProduct(Normal, Up) < Tune.WallSlope) { bBlocked = true; return false; }
    Point = Hit.Location - Up * R;
    return true;
}

bool FRideSession::FindGround(const FVector& At, const FQuat& InFrame, float Below, FVector& OutP, FVector& OutUp, FVector& OutForward, bool& bBlocked) const
{
    const FVector Up = InFrame.GetUpVector(), Forward = InFrame.GetForwardVector();
    FVector FrontP, FrontN, BackP, BackN;
    const bool bFront = Probe(At + Forward * Tune.AxleX, Up, Tune.StepUp, Below, FrontP, FrontN, bBlocked);
    const bool bBack = Probe(At - Forward * Tune.AxleX, Up, Tune.StepUp, Below, BackP, BackN, bBlocked);
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
    if (Probe(At, Up, Tune.StepUp, Below, CP, CN, bBlocked))
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

    // Powerslides: the deck turns across the travel and scrubs speed.
    if (Mode == ERideState::Ground && In.bPowerslide && Speed > Tune.SlideMinSpeed && PendingPop == Flick::None)
        SetMode(ERideState::Powerslide);
    float Decel = 0;
    if (Mode == ERideState::Powerslide)
    {
        const float Side = In.Left.X < 0 ? -1.f : 1.f;
        SlideYaw = FMath::FixedTurn(SlideYaw, Side * Tune.SlideAngle, Tune.SlideTurnRate * Tick60);
        Decel += Curve(SlideCurve, Speed) * Tune.SlideDecel * FMath::Abs(FMath::Sin(FMath::DegreesToRadians(SlideYaw)));
        if (!In.bPowerslide || Speed < 40.f) SetMode(ERideState::Ground);
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

    // Pumping: extending through a concave transition gains speed (the rider crouches on flats and crests).
    const float CrouchTarget = PendingPop != Flick::None || Flicks.Loaded() ? 1.f : (In.bPush && !bFlat) ? (Curvature > 1e-4f ? 0.f : 1.f) : .25f;
    const float OldCrouch = Crouch;
    Crouch += (CrouchTarget - Crouch) * Damp(Tune.CrouchRate, Tick60);
    if (Curvature > 0 && Crouch < OldCrouch) Speed *= FMath::Exp(Curvature * (OldCrouch - Crouch) * Tune.PumpExtension);

    V = Forward * Travel * Speed;
    WheelSpin = FMath::Fmod(WheelSpin + FVector::DotProduct(V, Forward) * Tick60 / (2 * PI * Tune.WheelRadius) * 360.f, 360.f);

    // Move, stopping at walls.
    FVector Move = V * Tick60;
    const float Lift = Tune.WheelRadius + 8.f;
    FHitResult Wall;
    if (!Move.IsNearlyZero() && Sweep(P + Up * Lift, P + Up * Lift + Move, 7.f, Wall) && !Wall.bStartPenetrating &&
        FVector::DotProduct(Wall.ImpactNormal, Up) < Tune.WallSlope)
    {
        const FVector N = FVector::VectorPlaneProject(Wall.ImpactNormal, Up).GetSafeNormal();
        const float Into = -FVector::DotProduct(V, N);
        if (Into > Tune.WallBailSpeed) { StartBail(TEXT("wall")); return; }
        Move *= Wall.Time;
        if (Into > 0)
        {
            V += N * Into * (1.f + Tune.WallRestitution);
            const FVector Along = FVector::VectorPlaneProject(V, Up);
            if (Along.Size() > 20.f)
            {
                // Turn the board along the wall, keeping the nose or tail that was leading.
                const FVector Lead = Along.GetSafeNormal() * Travel;
                Q = Frame(Up, Lead);
            }
            Speed = V.Size(); TurnRate = 0;
        }
    }
    const FVector Next = P + Move;

    // Follow the surface; leave it when it falls away faster than the board can follow.
    FVector Ground, NewUp, NewForward; bool bBlocked = false;
    const float Below = Tune.StickGap + Tune.StickPerSpeed * Speed * Tick60;
    if (!FindGround(Next, Q, Below, Ground, NewUp, NewForward, bBlocked))
    {
        if (bBlocked && Speed * Tick60 > 1.f && Speed > Tune.WallBailSpeed) { StartBail(TEXT("curb")); return; }
        P = Next;
        if (bBlocked) { V = FVector::ZeroVector; return; }
        TakeOff(0.f);
        return;
    }
    // Curvature along the travel: the normal's turn per cm. A crest sharper than gravity can hold launches.
    const float Turned = FMath::DegreesToRadians(AngleBetween(Up, NewUp));
    const float Dist = FMath::Max(1.f, float(FVector::Dist(P, Ground)));
    const float Sign = FVector::DotProduct(NewUp - Up, Dir) > 0 ? -1.f : 1.f;   // convex crests tilt the normal forward
    Curvature = Sign * Turned / Dist;
    const float Hold = FMath::Max(0.f, float(-FVector::DotProduct(FVector(0, 0, -G), Up)));
    if (Sign < 0 && Turned > FMath::DegreesToRadians(2.f) && Speed * Speed * Turned / Dist > Tune.LaunchFactor * FMath::Max(Hold, 1.f))
    {
        P = Next; TakeOff(0.f); return;
    }
    P = Ground;
    // Keep the board's heading (nose or tail leading) in the new plane.
    const FVector Heading = FVector::VectorPlaneProject(Forward, NewUp).GetSafeNormal();
    Q = Frame(NewUp, Heading.IsNearlyZero() ? NewForward : Heading);
    V = Q.GetForwardVector() * Travel * Speed;
    // Upside down on a wall at a crawl: fall off.
    if (NewUp.Z < -.2f && Speed < 150.f) { StartBail(TEXT("stall on the wall")); return; }
    if (Mode == ERideState::Ground && Holding.IsEmpty() == false && Holding.Contains(TEXT("Manual"))) EndHold();
}

void FRideSession::StartPush(bool bFirstPush, float Speed)
{
    PushTime = 0; bPushStrong = true; bPushed = false;
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
    AirTime = 0; TakeoffUp = Up; SpinTotal = 0;
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
        const FVector From = PredictFrom, To = From + PredictVelocity * Dt + FVector(0, 0, -.5f * Tune.AirGravity * Dt * Dt);
        FHitResult Hit;
        if (Sweep(From, To, 10.f, Hit) && !Hit.bStartPenetrating)
        {
            LandTime = PredictTime + Dt * Hit.Time; LandNormal = Hit.Normal;
            return;
        }
        PredictFrom = To; PredictVelocity.Z -= Tune.AirGravity * Dt; PredictTime += Dt;
        if (PredictTime > 3.f) return;
    }
}

void FRideSession::TickAir(const FSkateInput& In, Flick F)
{
    AirTime += Tick60;
    // The lip: off a face steeper than VertSteepness, vert assist removes the velocity that would carry the rider
    // over the coping, so a straight air comes back into the ramp; holding transfer carries the rider over instead.
    if (AirTime <= Tick60 * 1.5f)
    {
        const FVector Up = TakeoffUp;
        const float Steep = 90.f - FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(float(Up.Z), -1.f, 1.f)));
        const FVector Out = FVector(Up.X, Up.Y, 0).GetSafeNormal();
        if (Steep > Tune.VertSteepness && V.Z > 0 && !Out.IsNearlyZero())
        {
            const float Through = FVector::DotProduct(V, Out);   // negative: toward the deck behind the coping
            if (In.bTransfer) V -= Out * Tune.TransferPush;
            else if (Prefs.VertAssist > 0)
            {
                V -= Out * FMath::Min(Through, 0.f) * Prefs.VertAssist;
                V += Out * Tune.VertReturn * Prefs.VertAssist;
            }
            ResetPrediction(P + Up * 12.f);
        }
    }
    // A flick just after leaving a lip still pops (the rider timed it at the coping); later flicks flip the board
    // without lift (a late flip).
    if (F != Flick::None && (TrickTime < 0 || TrickTime > CatchTime(Trick_) + .05f))
    {
        Cues.Add(ERideCue::Flick);
        if (!bPopped && AirTime < Tune.LateFlickWindow) { V += TakeoffUp * PopSpeed() * .8f; bPopped = true; ResetPrediction(P + Q.GetUpVector() * 12.f); }
        StartTrick(F);
    }
    // Spin: the left stick turns the rider about the body's axis (the take-off normal).
    // Off flat ground the body turns slower than off a lip (the reference: about 290 degrees in an ollie).
    const float FullSpin = TakeoffUp.Z > .9f ? Tune.FlatSpinRate : Tune.SpinRate;
    const float SpinTarget = FMath::Abs(In.Left.X) > .25f ? float(In.Left.X) * FullSpin * Prefs.Spin : (SpinRate > 0 ? FMath::Min(SpinRate, 115.f) : FMath::Max(SpinRate, -115.f));
    SpinRate += (SpinTarget - SpinRate) * Damp(Tune.SpinResponse, Tick60);
    const float SpinStep = SpinRate * Tick60;
    SpinTotal += SpinStep;
    Q = (Turn(Q.GetUpVector(), SpinStep) * Q).GetNormalized();
    // Level toward the predicted landing face, finishing LevelLead before touch-down.
    AdvancePrediction(2);
    if (LandTime >= 0)
    {
        const float Left = LandTime - AirTime - Tune.LevelLead;
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
    V.Z -= Tune.AirGravity * Tick60;
    const FVector Move = V * Tick60;
    FHitResult Hit;
    if (Sweep(From, From + Move, 10.f, Hit))
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
        Yaw >= YawLimit ? TEXT("landed sideways") : bMidFlip ? TEXT("landed on the board mid-flip") :
        (Grab != ERideGrab::None && GrabWeight > .6f && AirTime > .25f) ? TEXT("landed holding the grab") : nullptr;
    P = Point;
    if (Why) { StartBail(Why); return true; }
    // Land: the normal part of the speed is absorbed; a sideways landing keeps cos(angle) of the speed along the board.
    Travel = bFakieLanding ? -1.f : 1.f;
    Q = Frame(Normal, Heading.IsNearlyZero() ? FVector::VectorPlaneProject(Q.GetForwardVector(), Normal).GetSafeNormal() : Heading);
    const float Kept = Speed * FMath::Cos(FMath::DegreesToRadians(Yaw));
    V = Q.GetForwardVector() * Travel * Kept;
    Sketchy = Yaw > Tune.SketchyYaw ? 1.f : Yaw > Tune.CleanYaw ? .5f : 0.f;
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
    const FSkateRail& Line_ = Where.Rails->Rails[Rail];
    FVector Tangent;
    Where.Rails->Sample(Rail, RailS, Tangent);
    const bool bSlide = GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide;
    // Gravity along the line, friction against the motion.
    RailSpeed += -G * Tangent.Z * Tick60;
    const float Friction = bSlide ? Tune.SlideFriction : Tune.GrindFriction;
    RailSpeed = RailSpeed > 0 ? FMath::Max(0.f, RailSpeed - Friction * Tick60) : FMath::Min(0.f, RailSpeed + Friction * Tick60);
    RailS += RailSpeed * Tick60;
    FVector Point = Where.Rails->Sample(Rail, FMath::Clamp(RailS, 0.f, Line_.Length()), Tangent);
    RailUp = FVector::CrossProduct(Tangent, FVector::CrossProduct(FVector::UpVector, Tangent)).GetSafeNormal();
    if (RailUp.Z < 0) RailUp = -RailUp;
    // The board sits on the line: trucks on it for grinds, the deck's underside for slides.
    const float Drop = bSlide ? Tune.DeckHeight - 1.5f : Tune.WheelRadius + Line_.Radius;
    P = Point - RailUp * Drop;
    FVector Nose = Tangent * GrindNose;
    if (bSlide) Nose = FVector::CrossProduct(RailUp, Tangent) * GrindNose;
    if (GrindKind == ERideGrind::Crooked) Nose = (Tangent * GrindNose + FVector::CrossProduct(RailUp, Tangent) * .5f).GetSafeNormal();
    Q = Frame(RailUp, Nose);
    V = Tangent * RailSpeed;
    Travel = FVector::DotProduct(V, Q.GetForwardVector()) < 0 ? -1.f : 1.f;
    WheelSpin = FMath::Fmod(WheelSpin + (bSlide ? 0.f : RailSpeed * Tick60 * 2.f), 360.f);
    Hold(GrindName(), bSlide ? 250.f : 200.f, Tick60);
    // Leave: a pop (any flick, flipping out), the end of the line, or a stall.
    if (F != Flick::None)
    {
        Cues.Add(ERideCue::Flick);
        LeaveGrind(Tune.GrindExitPop * Tune.PopFromGrindScale / .8f);
        if (F != Flick::Ollie && F != Flick::Nollie) StartTrick(F);
        return;
    }
    if (RailS < 0 || RailS > Line_.Length()) { LeaveGrind(60.f); return; }
    if (FMath::Abs(RailSpeed) < Tune.GrindStall && ModeTime > .5f) { LeaveGrind(30.f); return; }
}

void FRideSession::LeaveGrind(float Up)
{
    EndHold();
    // Off the side the rider leans to, so the board does not catch the line again.
    const FVector Tangent = V.GetSafeNormal();
    const FVector Side = FVector::CrossProduct(FVector::UpVector, Tangent).GetSafeNormal() * (bGrindFront ? -1.f : 1.f) * (bGoofy ? -1.f : 1.f);
    V += FVector::UpVector * Up + Side * 40.f;
    // Slides turn the board back along the travel.
    if (GrindKind == ERideGrind::Boardslide || GrindKind == ERideGrind::Lipslide || GrindKind == ERideGrind::Crooked)
        Q = Frame(FVector::UpVector, FVector::VectorPlaneProject(V, FVector::UpVector).GetSafeNormal() * (FVector::DotProduct(Q.GetForwardVector(), V) < 0 ? -1.f : 1.f));
    LastRail = Rail; RailCooldown = Tune.GrindRelock;
    Rail = INDEX_NONE;
    TurnRate = 0;
    const FVector UpVector = Q.GetUpVector();
    SetMode(ERideState::Air);
    AirTime = .1f; TakeoffUp = UpVector; SpinTotal = 0; SpinRate = 0; bPopped = true;
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
    Board.TruckLean = Mode == ERideState::Ground || Mode == ERideState::Manual ? -Turning * Travel * Tune.LeanAngle : 0.f;
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
    }
    PoseNaN = 0;
    for (const FTransform& Bone : Bones) if (Bone.ContainsNaN()) ++PoseNaN;
    // The fastest body bone in the root's frame, so the ride's own travel and turning do not count.
    PoseStep = 0;
    const bool bStep = LastBones.Num() == Bones.Num() && Dt > 1e-4f;
    LastBones.SetNum(Bones.Num(), EAllowShrinking::No);
    for (int32 I = 0; I < Bones.Num(); ++I)
    {
        const FVector Local = Root.InverseTransformPosition(Bones[I].GetLocation());
        if (bStep && BodyBone[I]) PoseStep = FMath::Max(PoseStep, float(FVector::Dist(Local, LastBones[I])) / Dt);
        LastBones[I] = Local;
    }
    FeetOff = 0;
    if (Bones.IsValidIndex(DeckBone))
        for (int32 F = 0; F < 2; ++F)
        {
            if (!Bones.IsValidIndex(ToeBone[F])) continue;
            const FVector Local = Bones[DeckBone].InverseTransformPosition(Bones[ToeBone[F]].GetLocation());
            FootHeight[F] = float(Local.Z);
            // Off the deck: beyond its outline or clear of its grip.
            if (FMath::Abs(Local.X) > 42.f || FMath::Abs(Local.Y) > 14.f || Local.Z > 16.f || Local.Z < -4.f) ++FeetOff;
        }
}

FString FRideSession::DescribePose() const
{
    return FString::Printf(TEXT("clip=%s lock=%.2f lift=%.1f step=%.0f feet=%.1f,%.1f feetoff=%d nan=%d anim=%.3f"),
        *Animator.GetMainClip().ToString(), Animator.GetLock(), Animator.GetLift(), PoseStep, FootHeight[0], FootHeight[1], FeetOff, PoseNaN, AnimCost);
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
