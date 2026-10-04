// Native's own maths in the Ride session (RIDE.md, "Pumping" and "Lip airs"): the settings database the native runtime
// reads (Content/Data/SkateNative/settings.skate), and the pure functions of its pumping and of its departure off a
// vert and launch adjustment, called directly rather than copied. Native's axes are x left, y up, z forward, in
// metres; Unreal's X forward, Y right, Z up, in cm. Native turns floating-point contraction off, and so does this file,
// so its sums round as native's do.
#include "RideSession.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Native/Settings.h"
#include "Native/Pumping.h"
#include "Native/AirTrajectoryLaunch.h"
#include "Native/AirTrajectoryRuntime.h"
#include "Native/AirTrajectorySelectorSettings.h"
#include "Native/AirTrajectorySelectorMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace N = atelier::skate;
namespace M = atelier::skate::air_trajectory_detail;

/** What the session keeps of native's state between ticks: its pumping. */
struct FRideNativeState
{
    N::PumpingState Pump;
};

namespace
{
    struct FNativeSettings
    {
        bool bValid = false;
        N::PumpingConfiguration Pumping;
        N::GroundPumpingMode PumpMode{};
        N::AirTrajectorySelectorSettings Select{};
    };

    /** Native's settings in its normal physics mode, read once; without them Ride does not pump and a lip air leaves
     *  by Ride's own departure. */
    const FNativeSettings& Settings()
    {
        static const FNativeSettings Loaded = []
        {
            FNativeSettings S;
            const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Data/SkateNative/settings.skate"));
            TArray<uint8> Bytes;
            std::string Error;
            N::SettingsDatabase Data;
            if (!FFileHelper::LoadFileToArray(Bytes, *Path)) Error = "cannot read settings.skate";
            else if (Data.Load(std::vector<std::uint8_t>(Bytes.GetData(), Bytes.GetData() + Bytes.Num()), Error)
                && S.Pumping.Load(Data, Error) && S.Pumping.Mode(1, S.PumpMode, Error)
                && N::LoadAirTrajectorySelectorSettings(Data, S.Select, Error))
                S.bValid = true;
            if (!S.bValid)
                UE_LOG(LogTemp, Error, TEXT("SKATE ride: native settings unavailable (%s): no pumping, and lip airs leave by Ride's departure"), UTF8_TO_TCHAR(Error.c_str()));
            return S;
        }();
        return Loaded;
    }

    N::Vec4 Point(const FVector& U) { return {float(-U.Y / 100.), float(U.Z / 100.), float(U.X / 100.), 0.f}; }
    N::Vec4 Dir(const FVector& U) { return {float(-U.Y), float(U.Z), float(U.X), 0.f}; }
    FVector Unreal(const N::Vec4& A) { return FVector(A[2], -A[0], A[1]) * 100.; }   // a point or a velocity, cm
}

TPimplPtr<FRideNativeState, EPimplPtrMode::DeepCopy> FRideSession::MakeNative()
{
    return MakePimpl<FRideNativeState, EPimplPtrMode::DeepCopy>();
}

void FRideSession::ResetNative()
{
    Native->Pump.Reset();
}

void FRideSession::ResetPump()
{
    Native->Pump.Reset();
}

void FRideSession::Pump(float& Speed, bool bIntentional)
{
    // Native's UpdateGroundPumping (Pumping.cpp) on the board's ground point, the ground's normal and the centre of
    // mass over the deck along it (Crouch lowers it PumpDepth / .75 cm a unit); its velocity change this tick, as
    // native's pump force (CalculatePumpForce) applies it: UnintentionalPumpScalar as much with no trigger held.
    const FNativeSettings& S = Settings();
    if (!S.bValid) return;
    const N::Vec4 Normal = Dir(Q.GetUpVector());
    const float Height = 1.f - Crouch * Tune.PumpDepth / 75.f;
    const N::PumpingSample Sample{Point(P), Normal, M::Scale(Normal, Height), 0.f, std::uint8_t(bIntentional ? 1 : 0)};
    N::UpdateGroundPumping(Native->Pump, S.Pumping.settings, S.PumpMode.controller, Sample);
    const float Scalar = bIntentional ? 1.f : S.PumpMode.unintentional_scalar * Tune.CoastPump;
    Speed = FMath::Max(0.f, Speed + 100.f * (Native->Pump.pump_acceleration * Scalar));
}

bool FRideSession::NativeLipLaunch(const FVector& Up, bool& bAligned)
{
    // Native's launch off the face Up, in its order: AirTrajectoryRuntime::Launch's AirTrajectoryVertDeparture (at the
    // player's VertAssist: off a face steeper than its reach, climbing steeply enough, the speed into the face is lost
    // and the face counts as level-normalled wall), then the selector's AdjustAirTrajectoryLaunchVelocity: off a wall
    // (normal y under VertJumpAlignMaxGroundNormalY), a steep climb is turned upright at its own speed, leaning
    // VertJumpAlignMaxAngle x (input - .25) toward the wall's normal (1.15 degrees back in with no input), the speed
    // along the coping kept; a shallower natural air keeps NaturalAirOffVertsScalar of its speed off the face.
    bAligned = false;
    const FNativeSettings& S = Settings();
    if (!S.bValid) return false;
    const auto Departure = N::AirTrajectoryVertDeparture(Dir(Up), Point(V), 0.f, FMath::Clamp(Prefs.VertAssist, 0.f, 1.f));
    N::AirLaunchInfo Info;
    Info.start_velocity = Departure.second; Info.player_jumped = bPopped;
    N::AirSelectorInput In{};
    In.ground_normal = Departure.first; In.directional_input = 0.f; In.previous_physics_state = 0;
    bAligned = N::AdjustAirTrajectoryLaunchVelocity(Info, In, S.Select);
    V = Unreal(Info.start_velocity);
    return true;
}
