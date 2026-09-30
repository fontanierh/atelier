#pragma once
// C++ adaptation of skate-core at 7842b9e: see NATIVE_PORT.md.
// SI units, radians, Z up. Scalar controllers retain the original 60 Hz update order;
// vector normalization/trigonometry use the host standard library, not Xenon intrinsics.
#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace SkateNative
{
constexpr float Step = 1.f / 60.f, Pi = 3.14159265358979323846f;
inline float Clamp(float V, float A, float B) { return std::clamp(V, A, B); }
inline float Unit(float V) { return Clamp(V, 0.f, 1.f); }
inline float Lerp(float A, float B, float T) { return std::fma(B - A, T, A); }
struct FixedClock
{
    double Remainder=0;
    int Advance(double Dt)
    {
        constexpr double H=1./60.;
        Remainder+=std::clamp(Dt,0.,.1);
        const int Count=int((Remainder+1e-8)/H);
        Remainder-=Count*H;
        return Count;
    }
};
struct Vec
{
    float X = 0, Y = 0, Z = 0;
    Vec operator+(Vec B) const { return {X+B.X,Y+B.Y,Z+B.Z}; }
    Vec operator-(Vec B) const { return {X-B.X,Y-B.Y,Z-B.Z}; }
    Vec operator*(float S) const { return {X*S,Y*S,Z*S}; }
    float Dot(Vec B) const { return X*B.X+Y*B.Y+Z*B.Z; }
    Vec Cross(Vec B) const { return {Y*B.Z-Z*B.Y,Z*B.X-X*B.Z,X*B.Y-Y*B.X}; }
    float Length() const { return std::sqrt(Dot(*this)); }
    Vec UnitVector() const { float L=Length(); return L>1e-6f ? *this*(1.f/L) : Vec{}; }
    Vec Planar(Vec N) const { return *this-N*Dot(N); }
};
struct Curve
{
    std::array<float,16> X{}, Y{};
    int Count = 2;
    Curve(float From=1, float To=1, float End=1) { X[1]=End; Y[0]=From; Y[1]=To; }
    float At(float V) const
    {
        if (V<X[0]) return Y[0];
        if (!(V<X[Count-1])) return Y[Count-1];
        for (int I=1; I<Count; ++I) if (V<X[I])
        {
            float Width=X[I]-X[I-1];
            return Width<=0 ? Y[I] : std::fma((Y[I]-Y[I-1])/Width,V-X[I-1],Y[I-1]);
        }
        return Y[Count-1];
    }
};
// These simple fallback curves are authored for the host game. RetailSettings overrides
// them with the committed original point graphs, including schema defaults.
struct Settings
{
    float HardTurnIncrease=1, Damping=.7f, SpeedGraphMax=50, PushIncrement=.05f, PushDecrement=.015f;
    float PushSteerMin=.5f, ManualSteer=.6f, GeneralSteer=.6f, TightTrucks=.7f, TiltBlend=.2f;
    Curve SteerSpeed{1,.27f}, SteerInput{0,.83f};
    float MaxPushSpeed=8.5f, PushDVStart=.6f, PushDVEnd=.5f, PushHoldingMax=4;
    Curve PushTimeMax{.23f,.25f,8.5f}, PushStrengthCurve{.75f,4.5f};
    float Gravity=9.8f, JumpMin=1.33f, JumpMax=1.71f;
    Curve PumpSpeed{3,0,15}, PumpTime{1,.1f}, MinCrouch{0,.8f}, Compression{0,1}, DeckCompression{0,1};
    float PumpDamping=.1f, PumpMinChange=.004f, PumpMaxChange=.006f, AngularDamping=.2f;
    float CompressionGround=-8, CompressionDeck=-8, PumpAcceleration=18, PumpAbsorption=1;
    float PumpMaxAcceleration=10, PumpMaxAbsorption=0, UnintentionalPump=.7f;
    float ManualP=.05f, ManualI=.03f, ManualD=-.8f, ManualMaxAngle=24, ManualMaxError=.1f;
    float ManualDerivativeLimit=.04f, ManualStartTorque=0, ManualNoise=.05f, ManualFrequency=1.5f;
    float ManualBleed=.96f, ManualNoContact=0;
    Curve ManualNoiseSpeed{.3f,1,10}, LandingSpin{0,1}, LandingSide{0,1};
    Curve CoastDrag{.13f,.5f,8}, ManualDrag{.13f,.5f,8}, SurfaceDrag{0,1.2f,27.7f};
    float NoInputTime=3;
    float GrindLockDistance=.9f, GrindMaxDown=7, GrindMaxRail=64, GrindMaxLedge=36, GrindAdjustAngle=25;
    float GrindMaxOffset=.2f, GrindMaxDelta=.03f;
    Curve JumpLowSpeed{1,1}, JumpHighSpeed{1,.46f}, JumpVertical{1,1}, JumpYScalar{1,1};
    float JumpResponseSpeed=27.8f, JumpAbsoluteMin=.95f, JumpMinimumScalar=.1f, JumpYBonus=1.5f;
};
struct Steering
{
    float PushScalar=1, DampedTurn=0, DeckTilt=0;
    std::array<float,2> Targets{}, ContactTime{};
    float Update(const Settings& S, float Turn, float HardTurn, float Speed, float Flip,
                 bool Manual, float Tightness, bool Pushing, bool Front=true, bool Back=true)
    {
        const float HardScalar=std::fma(std::abs(HardTurn),S.HardTurnIncrease,1.f);
        if (HardTurn!=0) Turn=Turn>=0 ? 1.f : -1.f;
        DampedTurn=std::fma(1-S.Damping,DampedTurn,S.Damping*Turn);
        PushScalar=Clamp(PushScalar+(Pushing?-S.PushDecrement:S.PushIncrement),S.PushSteerMin,1);
        const float Tight=std::fma(S.TightTrucks,Tightness,1.f)-Tightness;
        const float Target=Flip*S.GeneralSteer*(Manual?S.ManualSteer:1)*Tight*PushScalar*
            S.SteerInput.At(std::abs(DampedTurn))*S.SteerSpeed.At(Unit(Speed/S.SpeedGraphMax))*HardScalar*DampedTurn;
        DeckTilt=std::fma(1-S.TiltBlend,DeckTilt,S.TiltBlend*Target);
        bool Active[2]={Front,Back};
        for (int I=0;I<2;++I)
        {
            if (Active[I])
            {
                if (ContactTime[I]<=.16500001f)
                {
                    ContactTime[I]+=Step;
                    const float F=Unit(ContactTime[I]*6.060606f);
                    Targets[I]=std::fma(1-F,Targets[I],F*DeckTilt);
                }
                else Targets[I]=DeckTilt;
            }
            else { if (ContactTime[I]==0) Targets[I]*=.983f; ContactTime[I]=0; }
        }
        return DeckTilt;
    }
};
// TU3 push_animation::strength (the result is a target DV, not the per-tick force cap).
inline float PushStrength(const Settings& S, float Held, float Speed)
{ return S.PushStrengthCurve.At(Unit(Held/S.PushTimeMax.At(Speed))); }
// TU3 CalcPushForce: returns the velocity increment; mass and dt cancel when applied.
inline float PushDelta(const Settings& S, float Target, float Current, float Absolute)
{
    float Limit=Lerp(S.PushDVStart,S.PushDVEnd,Unit(Current/S.MaxPushSpeed));
    float DV=Clamp(std::max(Target-Current,0.f),-Limit,Limit);
    return Absolute+DV>S.MaxPushSpeed ? std::max(S.MaxPushSpeed-Absolute,0.f) : DV;
}
// Ordinary GroundJump launch: authored COM height, speed graphs and surface response.
// the host game supplies its own rider COM and prepared velocity (there is no EA animation graph).
inline Vec GroundJump(const Settings& S, Vec Prepared, Vec Normal, float Speed, float Strength, float COMHeight)
{
    const float Fraction=Unit(Speed/S.JumpResponseSpeed);
    const float Low=std::fma(S.JumpLowSpeed.At(Fraction),S.JumpMin-S.JumpAbsoluteMin,S.JumpAbsoluteMin);
    const float High=std::fma(S.JumpHighSpeed.At(Fraction),S.JumpMax-S.JumpAbsoluteMin,S.JumpAbsoluteMin);
    const float Height=std::fma(Low,1-Strength,High*Strength);
    const float Launch=std::sqrt(std::max(Height-COMHeight,0.f)*S.Gravity*2);
    const float Angle=Unit(std::acos(Clamp(Normal.Z,-1,1))*2/Pi);
    Vec Velocity=Prepared.Planar(Normal)+Normal*(Launch*std::max(S.JumpVertical.At(Angle),S.JumpMinimumScalar));
    Velocity.Z+=Clamp((S.JumpYScalar.At(Normal.Z)-1)*Velocity.Z,0,S.JumpYBonus);
    return Velocity;
}
struct Pumping
{
    Vec PreviousPosition{}, PreviousNormal{0,0,1};
    float PreviousHeight=0, SmoothedChange=0, Time=0, AngularSpeed=0, Absorption=0, MinimumCrouch=0, CompressionAmount=0;
    bool Valid=false;
    float Update(const Settings& S, Vec Position, Vec Normal, float Height, float DeckAngle, bool Intentional)
    {
        float DV=0;
        if (Valid)
        {
            const float Rising=std::max(Height-PreviousHeight,0.f);
            SmoothedChange=std::fma(Rising,S.PumpDamping,(1-S.PumpDamping)*SmoothedChange);
            float Effect=SmoothedChange<S.PumpMinChange?0:SmoothedChange;
            Time=Effect>0?Time+Step:0;
            Effect=std::min(Effect,S.PumpMaxChange)*S.PumpTime.At(Time);
            const Vec Delta=Position-PreviousPosition;
            const float Speed=Delta.Length()/Step;
            float Angular=PreviousNormal.Cross(Normal).Dot(Delta.Cross(Normal).UnitVector())/Step;
            AngularSpeed=std::fma(1-S.AngularDamping,AngularSpeed,Angular*S.AngularDamping);
            Absorption=-Speed*AngularSpeed;
            float Angle=std::acos(Unit(PreviousNormal.Z))*2/Pi;
            MinimumCrouch=S.MinCrouch.At(Unit(Angle));
            CompressionAmount=S.Compression.At(Unit(Angle))*S.CompressionGround;
            float Deck=S.DeckCompression.At(DeckAngle*2/Pi)*S.CompressionDeck;
            if (Deck*Deck>CompressionAmount*CompressionAmount) CompressionAmount=Deck;
            float Pump=AngularSpeed*S.PumpSpeed.At(Speed);
            const float Raw=Pump*(Pump*Effect>0?S.PumpAcceleration:S.PumpAbsorption)*Effect;
            DV=Clamp(Raw,-S.PumpMaxAbsorption*Step,S.PumpMaxAcceleration*Step);
            if (!Intentional) DV*=S.UnintentionalPump;
        }
        PreviousPosition=Position; PreviousNormal=Normal; PreviousHeight=Height; Valid=true;
        return DV;
    }
};
// CalcManualEffect's pitch controller. The adapter applies its angular displacement
// to the deck; the two contact flags refer to support at the selected axle.
struct Manual
{
    float Elapsed=0, Correction=0, Measured=0, FilteredError=0, Target=0;
    float Update(const Settings& S, float Balance, float Pitch, float Speed, float Clock, bool Positive, bool Negative)
    {
        if (Balance==0) { *this={}; return 0; }
        const float Signed=(std::abs(Balance)*.75f+.25f)*(Balance>0?1:-1);
        Target=S.ManualMaxAngle*Signed*Pi/180 + S.ManualNoiseSpeed.At(Speed)*std::sin(Clock*S.ManualFrequency*2*Pi)*S.ManualNoise;
        if (Elapsed==0) Correction=S.ManualStartTorque*Target;
        float Change=Pitch-Measured; Measured=Pitch;
        float Error=Clamp(Target-Pitch,-S.ManualMaxError,S.ManualMaxError);
        FilteredError=std::fma(.95f,FilteredError,.05f*Error);
        float Derivative=Clamp(Change*(Elapsed==0?0:1)*S.ManualD,-S.ManualDerivativeLimit,S.ManualDerivativeLimit);
        float WheelScale=Positive!=Negative?.5f:1;
        float OutputScale=1;
        if ((!Positive&&Balance>0)||(!Negative&&Balance<0))
        { Correction=S.ManualBleed*Correction*WheelScale; OutputScale=S.ManualNoContact*WheelScale; }
        else Correction=((Correction+Derivative)+FilteredError*S.ManualI)+Error*S.ManualP;
        Elapsed+=Step;
        return Correction*OutputScale;
    }
};
struct Landing
{
    int Kind=0;
    float Adjust=0, SideSpeed=0, ForwardSpeed=0;
};
inline Landing LandingQuality(const Settings& S, Vec Normal, Vec Velocity, Vec Forward, float AirSpin, bool Flipped)
{
    Landing Out;
    const Vec V=Velocity.Planar(Normal), F=Forward.Planar(Normal);
    const float Speed=V.Length();
    if (F.Length()*Speed<1e-5f) return Out;
    Out.ForwardSpeed=std::abs(V.Dot(F)); Out.SideSpeed=std::abs(F.Cross(Normal).Dot(Velocity));
    float Orientation=F.UnitVector().Cross(V.UnitVector()).Z*(Flipped?-1:1);
    float Angular=-AirSpin;
    float Spin=S.LandingSpin.At(std::min((std::abs(Angular)-.1f)*.14492753f,1.f));
    float Side=S.LandingSide.At(std::min((Out.SideSpeed-.1f)*.1010101f,1.f));
    if (Speed>=2)
    {
        bool Toward=(F.UnitVector()*(Flipped?-1.f:1.f)).Dot(V.UnitVector())>=0;
        if (std::abs(Angular)<=.1f) { Out.Kind=1; Out.Adjust=Side; }
        else { Out.Kind=((Toward&&Angular*Orientation<=0)||(!Toward&&Angular*Orientation>0))?2:1; Out.Adjust=std::max(Spin,Side); }
        Out.Adjust*=Angular>=0?1:-1;
        if (std::abs(Orientation)<.2f&&(Out.Kind!=2||std::abs(Out.Adjust)<=.3f))
        { Out.Kind=std::abs(Orientation)>=.05f?3:0; Out.Adjust=0; }
    }
    return Out;
}
// TU3 grind lateral pin: caller supplies the board/rail offset and support-relative velocity.
inline float GrindPin(float Offset, float SideVelocity, float Strength=800, float Slope=1)
{
    const float Force=Offset*Strength;
    return Force==0?0:(Force-Strength*.133f*SideVelocity)*Slope;
}
inline float GrindFriction(float Support, float Strength, float Material, bool Flagged=false)
{ return std::max(Support,0.f)*Strength*Material*(Flagged?1.9f:1.f)*.48f; }

struct Point { float X=0,Y=0; };
struct Pattern { std::string Name; std::vector<Point> Points; float ToleranceSquared=.16f; };
struct GestureNode
{
    bool Active=false,Complete=false;
    unsigned Next=0,Elapsed=0,Misses=0;
    float Distance=0;
    void Update(const Pattern& P,Point Stick,unsigned MaxMisses)
    {
        auto DistanceTo=[&](Point B){float X=Stick.X-B.X,Y=Stick.Y-B.Y;return X*X+Y*Y;};
        if (!Active)
        {
            float D=DistanceTo(P.Points[0]);
            if (D<=P.ToleranceSquared) { Active=true; Next=1; Elapsed=1; Distance=D; }
            return;
        }
        float D=DistanceTo(P.Points[Next]);
        if (D<=P.ToleranceSquared)
        {
            Distance+=D; Elapsed=(Elapsed+1)&0x3ff; Misses=0;
            if (++Next==P.Points.size()) Complete=true;
        }
        else if (Next!=1||DistanceTo(P.Points[0])>P.ToleranceSquared)
        {
            Elapsed=(Elapsed+1)&0x3ff; Misses=(Misses+1)&0x3f;
            if (Misses>MaxMisses) *this={};
        }
    }
    float Score(unsigned Count) const
    {
        float N=float(Count);
        return N*N*N*N/(std::min(std::max(Distance,.15f)/N,.15f)*std::max(Elapsed,1u));
    }
};
struct GestureResult { int Index=-1; float Strength=0; };
struct Gestures
{
    std::vector<Pattern> Patterns;
    std::vector<GestureNode> Nodes;
    bool Primed=false,Refractory=false;
    void Reset() { Nodes.assign(Patterns.size(),{}); Primed=false; Refractory=false; }
    GestureResult Update(Point Stick, bool Hardcore=false, unsigned MaxMisses=10)
    {
        if (Nodes.size()!=Patterns.size()) Reset();
        if (!Primed||Refractory) { Primed=true; Refractory=false; Nodes.assign(Patterns.size(),{}); return {}; }
        GestureResult Result; float Best=0;
        for (unsigned I=0;I<Patterns.size();++I)
        {
            const auto& P=Patterns[I]; if (P.Points.size()<2||P.Points.size()>15) continue;
            auto& N=Nodes[I]; N.Update(P,Stick,MaxMisses);
            if (N.Complete&&N.Score(unsigned(P.Points.size()))>Best)
            {
                Best=N.Score(unsigned(P.Points.size())); Result.Index=int(I);
                float Ratio=float(N.Elapsed)/P.Points.size();
                float Lower=Hardcore?1.5f:1.75f,Upper=Hardcore?3.f:4.4f;
                Result.Strength=1-Unit((Ratio-Lower)/(Upper-Lower));
            }
        }
        if (Result.Index>=0) { Refractory=true; Nodes.assign(Patterns.size(),{}); }
        return Result;
    }
};
}
