#include "RideManual.h"
#include "Native/GroundControlSettings.h"
#include "Native/Intents.h"
#include <cmath>

// Native's float order: no contraction (Native's files disable it too).
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(_MSC_VER)
#pragma fp_contract(off)
#endif

namespace atelier::ride
{
namespace
{
using namespace atelier::skate;

// The deck's one angle, as the controller measures it (BoardServices::AngleBetween on the deck and the ground frame).
struct DeckMeasurement final : ManualAngleMeasurement
{
    float Angle = 0;
    bool AngleBetween(Vec4, Vec4, Vec4, float& Output, std::string&) override { Output = Angle; return true; }
};

// A wheel pair is down within this of the deck lying flat (rad).
constexpr float Flat = 1e-4f;

// The clips the graph's expiries count against (s, at the clips' 30 frames a second): B_BRAKE_INTO and B_BRAKE_OUT
// (R_BRAKE_N_N_0_INTO, _OUT); B_NOSE_MANUAL_INTO (M_NOSEIDLE_N_0_INTO, 14 frames).
constexpr float BrakeInto = .2f, BrakeOut = .5f, NoseInto = 14.f / 30.f;
// The brake's clips blend in over 0.2 s (PlayAnimation's time). WillExpire waits for the blend (waitForTransitions), and
// the tree only drops a blend at the start of the advance after its clock has passed it (AnimationTreeOwner::Advance,
// TransitionComplete): B_BRAKE_INTO's expiry comes on its 14th tick, not its 12th.
constexpr float BrakeBlend = .2f;
// Float slack for those clocks, which count whole steps.
constexpr float Slack = 1e-4f;
}

bool ManualBank::Load(const SettingsDatabase& Data, ManualBank& Out, std::string& Error)
{
    ManualBank Bank;
    if (!LoadGroundManualSettings(Data, Bank.Settings, Error)) return false;
    const char* Names[] = {"easy", "normal", "hardcore"};
    for (int I = 0; I < 3; ++I) if (!LoadGroundManualMode(Data, Names[I], Bank.Modes[I], Error)) return false;
    // The speed model's manual friction is the same in every mode and on every surface.
    SpeedModelSettings Speed;
    if (!LoadGroundSpeedModelSettings(Data, "normal", "smooth", Speed, Error)) return false;
    Bank.Friction = Speed.manual_friction;
    Out = Bank; Error.clear();
    return true;
}

void ManualControl::ReadIntents(const IntentMap& Intents, bool bGround, float Dt)
{
    const float* M = Intents.Get("Manual");
    const float* B = Intents.Get("ManualBrake");
    const float* A = Intents.Get("AnticMag");
    Manual = M ? std::optional<float>(*M) : std::nullopt;
    ManualBrake = B ? std::optional<float>(*B) : std::nullopt;
    AnticMag = A ? *A : 0.f;
    bBrake = Intents.Contains("Brake");
    // Riding.Brake is the ground's.
    if (!bGround) { Brake = BrakeStep::None; BrakeTime = 0; }
    // TimeMgIntentState: the time counts while the intent is there, this tick's included, and is 0 without it.
    Engage = M ? Engage + Dt : 0.f;
    // The Antic state: its precondition AnticMag > 0.9, then held while AnticMag is published, on the ground only.
    bAntic = bGround && A && (bAntic || *A > .9f);
    // Turning.Anticipation lasts while its anticipation intents do.
    if (!bAntic) bAnticipating = false;
}

void ManualControl::Riding(bool bRiding, float Dt)
{
    if (!bRiding) { Brake = BrakeStep::None; BrakeTime = 0; bBrakeBlended = false; return; }
    // One step a tick, each on the clip's clock before this tick's advance; the step out of Out leaves Idle current,
    // and Idle's transitions run on the next tick (RideSession checks for a manual before this). WillExpire as Native
    // reckons it: no blend under way, and no more than InTime left of the clip.
    const auto WillExpire = [&](float Length, float InTime) { return bBrakeBlended && !(Length - BrakeTime > InTime); };
    switch (Brake)
    {
    case BrakeStep::None: if (bBrake) { Brake = BrakeStep::Into; BrakeTime = 0; } break;
    case BrakeStep::Into: if (WillExpire(BrakeInto, .01f)) { Brake = BrakeStep::Cyc; BrakeTime = 0; } break;
    case BrakeStep::Cyc: if (!bBrake) { Brake = BrakeStep::Out; BrakeTime = 0; } break;
    case BrakeStep::Out: if (WillExpire(BrakeOut, .1f)) Brake = BrakeStep::None; break;
    }
    // The advance: a blend past its time is dropped first, then the clip and its blend move on.
    bBrakeBlended = BrakeTime > BrakeBlend;
    BrakeTime += Dt;
}

bool ManualControl::Idle(bool bHardLanding)
{
    // Riding.Brake playing: Idle is not current.
    if (BrakePlaying()) return false;
    // Idle's transitions in order: Manual (its precondition), then Anticipation.
    if (!bAnticipating && Manual && Engage > .2f && !bHardLanding) return true;
    if (bAntic) bAnticipating = true;
    return false;
}

void ManualControl::Start(bool bLanding)
{
    State.Reset(); Angle = Spin = Time = 0;
    Graph = Side();
    IntoTime = !bLanding && Graph == ManualSide::Nose ? 0.f : -1.f;
}

void ManualControl::Hold(float Dt)
{
    const ManualSide Now = Side();
    // Leaving TailManual for the nose starts NoseManual.Holding again, at its Into.
    if (Now == ManualSide::Nose && Graph == ManualSide::Tail) IntoTime = 0.f;
    if (Now != ManualSide::Nose) IntoTime = -1.f;
    else if (IntoTime >= 0.f)
    {
        // Into hands over on WillExpire: to Cycle 0.05 s before the clip's end, to Brake 0.1 s before it with
        // ManualBrake held.
        if (IntoTime >= NoseInto - (ManualBrake ? .1f : .05f) - Slack) IntoTime = -1.f;
        else IntoTime += Dt;
    }
    Graph = Now;
}

float ManualControl::Balance() const
{
    if (!Manual || IntoTime >= 0.f) return 0.f;
    const float Attribute = ManualBrake ? (*Manual < 0.f ? -1.f : 1.f) : *Manual;
    return -Attribute;
}

void ManualControl::StepDeck(const ManualBank& Bank, std::uint32_t Difficulty, const ManualDeck& Deck, float Speed, float Dt)
{
    // GroundInput's binding, on the deck: the balance, no stance flip (the side is the graph's), the manual's own clock
    // for the procedural noise, the speed, no animation noise, the step; the wheels down by the deck's angle (the
    // tail's with the nose up). The ground frame is the deck's own axis, so the displacement's first lane is the
    // correction about it.
    ManualInput In{};
    In.balance = Balance(); In.flipped_controls = 1.f; In.procedural_noise_time = Time; In.absolute_speed = Speed;
    In.animation_noise = 0.f; In.timestep = Dt;
    In.powersliding = false; In.braking = Braking();
    In.positive_balance_contact = Angle >= -Flat; In.negative_balance_contact = Angle <= Flat;
    In.reversed_point_selection = false;
    In.reference_x = {1.f, 0.f, 0.f, 0.f}; In.reference_z = {0.f, 0.f, 1.f, 0.f}; In.deck_z = In.reference_z;
    DeckMeasurement Measure; Measure.Angle = Angle;
    ManualError Error;
    const auto Effect = CalculateManual(State, Bank.Settings, Bank.Modes[Difficulty < 3 ? Difficulty : 1], In, Measure, Error);
    const float Correction = Effect ? -Effect->angular_displacement[0] : 0.f;
    // ApplyDeckAngularDisplacement: the displacement over a step is the spin it adds (Deck.Gain of it about the axle);
    // the raised end's weight and the damping work against it. Back on both axles the deck stops flat.
    const float Down = Angle > 0.f ? 1.f : Angle < 0.f ? -1.f : 0.f;
    Spin += Deck.Gain * Correction / Dt - Deck.Weight * Down * Dt - Deck.Damping * Spin * Dt;
    const float Next = Angle + Spin * Dt;
    if (Angle != 0.f && Next * Angle < 0.f) { Angle = 0.f; Spin = 0.f; }
    else Angle = Next;
    Time += Dt;
}
}
