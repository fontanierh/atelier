#pragma once
// Flick-It for the Ride backend: reads the right stick one simulation tick at a time and recognises the trick
// gestures of skate. (RIDE.md, "Tricks"). Plain C++ with no engine types, so Tests/test_ride_flick.py can compile it
// on its own and play the scripted gesture paths through it.
#include <cmath>
#include <cstdint>

namespace atelier::ride
{
    enum class Flick : std::uint8_t
    {
        None, Ollie, Nollie, Kickflip, Heelflip, ShoveIt, FsShoveIt, Shove360, FsShove360,
        VarialKickflip, VarialHeelflip, Hardflip, InwardHeelflip, TreFlip, LaserFlip, Hardflip360, InwardHeelflip360
    };

    inline const char* FlickName(Flick F)
    {
        switch (F)
        {
        case Flick::Ollie: return "Ollie";
        case Flick::Nollie: return "Nollie";
        case Flick::Kickflip: return "Kickflip";
        case Flick::Heelflip: return "Heelflip";
        case Flick::ShoveIt: return "Pop Shove-it";
        case Flick::FsShoveIt: return "FS Pop Shove-it";
        case Flick::Shove360: return "360 Shove-it";
        case Flick::FsShove360: return "FS 360 Shove-it";
        case Flick::VarialKickflip: return "Varial Kickflip";
        case Flick::VarialHeelflip: return "Varial Heelflip";
        case Flick::Hardflip: return "Hardflip";
        case Flick::InwardHeelflip: return "Inward Heelflip";
        case Flick::TreFlip: return "360 Flip";
        case Flick::LaserFlip: return "Laser Flip";
        case Flick::Hardflip360: return "360 Hardflip";
        case Flick::InwardHeelflip360: return "360 Inward Heelflip";
        default: return "";
        }
    }

    /** Right-stick gestures in regular stance (x right, y away from the player); the caller mirrors x for goofy. */
    class FlickReader
    {
    public:
        // The rim: a stick this far out is on it, and leaves it below RimLeave.
        static constexpr float RimEnter = .7f, RimLeave = .55f;
        // A chord between two stick positions that passes this close to the centre goes through it: a flick.
        static constexpr float Through = .75f;
        // After leaving the rim, the stick must reach the far side within this time to count as one flick (s).
        static constexpr float Window = .22f;
        // Manual band: stick between these radii, held for ManualHold seconds.
        static constexpr float BandInner = .22f, BandOuter = .8f, ManualHold = .1f;

        void Reset() { *this = FlickReader(); }

        /** One tick. Returns the gesture completed this tick, if any. */
        Flick Update(float X, float Y, float Dt)
        {
            Time += Dt;
            const float M = std::sqrt(X * X + Y * Y);
            const bool Rim = OnRim ? M > RimLeave : M > RimEnter;
            Flick Result = Flick::None;
            if (Rim)
            {
                if (!OnRim)
                {
                    // Back on the rim: the far end of a flick through the centre, or a new gesture.
                    if (Armed && Time - LeftAt <= Window) Result = Pop(LastX, LastY, X, Y);
                    if (Result == Flick::None && !Consumed) Start(X, Y);
                }
                else if (Count > 0)
                {
                    const float PX = PathX[Count - 1], PY = PathY[Count - 1];
                    // A flick that stays on the rim: the load is the time on it so far.
                    if (ChordDistance(PX, PY, X, Y) < Through) { Result = Pop(PX, PY, X, Y); Load = RimTime; }
                    else Add(X, Y);
                }
                if (Result != Flick::None) { Count = 0; Armed = false; Consumed = true; }
                RimTime += Dt;
            }
            else
            {
                if (OnRim)
                {
                    LeftAt = Time; Armed = !Consumed && Count > 0;
                    Load = Armed ? RimTime : 0.f;
                    if (Armed) { LastX = PathX[Count - 1]; LastY = PathY[Count - 1]; }
                    // A sweep along the lower rim that ends level with the centre, then lets go: a shove-it.
                    if (Armed) Result = Shove();
                    if (Result != Flick::None) Armed = false;
                }
                if (M < BandInner) Consumed = false;
                RimTime = 0;
            }
            OnRim = Rim;
            // Manual band: part-way out, not on the rim.
            const int Band = !Rim && M >= BandInner && M < BandOuter && std::fabs(Y) > .2f ? (Y < 0 ? -1 : 1) : 0;
            BandTime = Band != 0 && Band == BandSide ? BandTime + Dt : 0;
            BandSide = Band; BandY = Y;
            StickY = Y; StickX = X; Radius = M;
            return Result;
        }

        /** Crouch for a pop: the stick held on the lower rim (an ollie's load) or upper rim (a nollie's). */
        bool Loaded() const { return OnRim && !Consumed && (StickY < .05f || StickY > .5f); }
        bool NoseLoaded() const { return OnRim && !Consumed && StickY > .5f; }
        float LoadTime() const { return Loaded() ? RimTime : 0.f; }
        /** How long the stick rested on the rim where the last pop's gesture started (s). */
        float PopLoad() const { return Load; }
        /** -1 tail manual (stick part-way down), +1 nose manual (part-way up), 0 none; after a short hold. */
        int ManualBand() const { return BandTime >= ManualHold ? BandSide : 0; }
        /** Stick height within the manual band: 0 at the band's middle, +-1 at its edges (positive towards the centre). */
        float BandOffset() const
        {
            const float Middle = .5f, Half = .3f;
            return BandSide < 0 ? (BandY + Middle) / Half : BandSide > 0 ? (Middle - BandY) / Half : 0.f;
        }
        float X() const { return StickX; }
        float Y() const { return StickY; }

    private:
        static constexpr int MaxPath = 24;
        float PathX[MaxPath] = {}, PathY[MaxPath] = {};
        int Count = 0;
        bool OnRim = false, Armed = false, Consumed = false;
        float Time = 0, LeftAt = -1, LastX = 0, LastY = 0, RimTime = 0, Load = 0;
        int BandSide = 0; float BandTime = 0, BandY = 0;
        float StickX = 0, StickY = 0, Radius = 0;

        static float Angle(float X, float Y) { return std::atan2(Y, X) * 57.29578f; }
        static float ChordDistance(float AX, float AY, float BX, float BY)
        {
            const float DX = BX - AX, DY = BY - AY, L = std::sqrt(DX * DX + DY * DY);
            if (L < 1e-4f) return std::sqrt(AX * AX + AY * AY);
            // Distance from the centre to the segment.
            float T = -(AX * DX + AY * DY) / (L * L);
            T = T < 0 ? 0 : T > 1 ? 1 : T;
            const float CX = AX + DX * T, CY = AY + DY * T;
            return std::sqrt(CX * CX + CY * CY);
        }
        void Start(float X, float Y) { Count = 0; Add(X, Y); }
        void Add(float X, float Y)
        {
            if (Count > 0)
            {
                float D = Angle(X, Y) - Angle(PathX[Count - 1], PathY[Count - 1]);
                while (D > 180) D -= 360;
                while (D < -180) D += 360;
                if (std::fabs(D) < 4.f) return;    // the same spot
            }
            if (Count == MaxPath) { for (int I = 1; I < MaxPath; ++I) { PathX[I - 1] = PathX[I]; PathY[I - 1] = PathY[I]; } --Count; }
            PathX[Count] = X; PathY[Count] = Y; ++Count;
        }
        // Where a gesture started on the rim: 0 right, 1 down-right, 2 down, 3 down-left, 4 left, 5 up, 6 other.
        int StartZone() const
        {
            const float A = Angle(PathX[0], PathY[0]);
            if (A >= 60 && A <= 120) return 5;
            if (A > 150 || A < -150) return 4;
            if (A > 120) return 6;
            if (A > -30) return 0;
            if (A > -70) return 1;
            if (A >= -110) return 2;
            return 3;
        }
        // Total angle swept along the rim path (degrees, signed: positive anticlockwise).
        float Sweep() const
        {
            float Total = 0;
            for (int I = 1; I < Count; ++I)
            {
                float D = Angle(PathX[I], PathY[I]) - Angle(PathX[I - 1], PathY[I - 1]);
                while (D > 180) D -= 360;
                while (D < -180) D += 360;
                Total += D;
            }
            return Total;
        }
        Flick Pop(float, float, float EX, float EY)
        {
            if (Count == 0) return Flick::None;
            const int Zone = StartZone();
            const float M = std::sqrt(EX * EX + EY * EY);
            if (M < .6f) return Flick::None;
            if (Zone == 5) return EY < -.2f ? Flick::Nollie : Flick::None;
            if (EY < .2f) return Flick::None;
            const float A = Angle(EX, EY);
            const int Exit = A > 115 || A < -90 ? 1 : A < 65 ? 2 : 0;   // 0 up, 1 up-left, 2 up-right
            switch (Zone)
            {
            case 2: return Exit == 1 ? Flick::Kickflip : Exit == 2 ? Flick::Heelflip : Flick::Ollie;
            case 1: return Exit == 1 ? Flick::VarialKickflip : Exit == 2 ? Flick::InwardHeelflip : Flick::Ollie;
            case 0: return Exit == 1 ? Flick::TreFlip : Exit == 2 ? Flick::InwardHeelflip360 : Flick::Ollie;
            case 3: return Exit == 1 ? Flick::Hardflip : Exit == 2 ? Flick::VarialHeelflip : Flick::Ollie;
            case 4: return Exit == 2 ? Flick::LaserFlip : Exit == 1 ? Flick::Hardflip360 : Flick::Ollie;
            default: return Flick::Ollie;
            }
        }
        Flick Shove() const
        {
            if (Count < 2) return Flick::None;
            const float EX = PathX[Count - 1], EY = PathY[Count - 1];
            const float Level = std::fabs(Angle(std::fabs(EX), EY));   // degrees from level
            const float Swept = std::fabs(Sweep());
            if (Level > 35 || Swept < 50) return Flick::None;
            const int Zone = StartZone();
            const bool EndLeft = EX < 0;
            if (Zone == 2) return EndLeft ? Flick::ShoveIt : Flick::FsShoveIt;
            if ((Zone == 0 || Zone == 1) && EndLeft) return Flick::Shove360;
            if ((Zone == 3 || Zone == 4) && !EndLeft) return Flick::FsShove360;
            return Flick::None;
        }
    };
}
