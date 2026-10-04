#include "RideFlick.h"
#include "Native/BoardPhysicsSettings.h"
#include "Native/ControllerInputRuntime.h"
#include "Native/PlayerControls.h"
#include <cmath>
#include <cstring>

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

float Float(std::uint32_t Bits) { float Value; std::memcpy(&Value, &Bits, 4); return Value; }

// GameplaySession's host transfer bit, which it takes off before Native samples the pad.
constexpr std::uint16_t TransferButton = 0x0800;

struct FNames { std::string_view Native; Flick Ride; };
constexpr FNames Names[] = {
    {"Ollie", Flick::Ollie}, {"Nollie", Flick::Nollie}, {"Kickflip", Flick::Kickflip}, {"Heelflip", Flick::Heelflip},
    {"PopShuvit", Flick::ShoveIt}, {"FSPopShuvit", Flick::FsShoveIt}, {"360PopShuvit", Flick::Shove360},
    {"FS360PopShuvit", Flick::FsShove360}, {"VarialKickflip", Flick::VarialKickflip},
    {"VarialHeelflip", Flick::VarialHeelflip}, {"Hardflip", Flick::Hardflip}, {"InwardHeelflip", Flick::InwardHeelflip},
    {"360Flip", Flick::TreFlip}, {"Laserflip", Flick::LaserFlip}, {"360Hardflip", Flick::Hardflip360},
    {"360InwardHeelflip", Flick::InwardHeelflip360},
    {"N_Kickflip", Flick::NollieKickflip}, {"N_Heelflip", Flick::NollieHeelflip}, {"N_PopShuvit", Flick::NollieShoveIt},
    {"N_FSPopShuvit", Flick::NollieFsShoveIt}, {"N_360PopShuvit", Flick::NollieShove360},
    {"N_FS360PopShuvit", Flick::NollieFsShove360}, {"N_VarialKickflip", Flick::NollieVarialKickflip},
    {"N_VarialHeelflip", Flick::NollieVarialHeelflip}, {"N_Hardflip", Flick::NollieHardflip},
    {"N_InwardHeelflip", Flick::NollieInwardHeelflip}, {"N_360Flip", Flick::NollieTreFlip},
    {"N_Laserflip", Flick::NollieLaserFlip}, {"N_360Hardflip", Flick::NollieHardflip360},
    {"N_360InwardHeelflip", Flick::NollieInwardHeelflip360},
};

// The mapping row SelectGestureTrick chose (the present key in the lowest bucket, rows from the last), so the pop
// request can name the gesture behind the trick. The trick itself always comes from SelectGestureTrick.
std::optional<std::string_view> SelectedKey(GestureGroup Group, const IntentMap& Action)
{
    const auto Rows = GestureMappingRows(Group);
    std::optional<std::string_view> Key;
    auto Bucket = ~std::size_t(0);
    for (auto Index = Rows.size; Index > 0; --Index)
    {
        const auto& Row = Rows.data[Index - 1]; std::uint32_t Sum = 0;
        for (auto Word : EncodeIntentKey(Row.key)) Sum += Word;
        const auto Current = static_cast<std::size_t>(Sum) % 43;
        if (Current < Bucket && Action.Contains(Row.key)) { Key = Row.key; Bucket = Current; }
    }
    return Key;
}
}

struct FlickReader::Owners
{
    ControllerInputRuntime Input;
    PlayerControls Controls;
};

const char* FlickName(Flick F)
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
    case Flick::NollieKickflip: return "Nollie Kickflip";
    case Flick::NollieHeelflip: return "Nollie Heelflip";
    case Flick::NollieShoveIt: return "Nollie Pop Shove-it";
    case Flick::NollieFsShoveIt: return "Nollie FS Pop Shove-it";
    case Flick::NollieShove360: return "Nollie 360 Shove-it";
    case Flick::NollieFsShove360: return "Nollie FS 360 Shove-it";
    case Flick::NollieVarialKickflip: return "Nollie Varial Kickflip";
    case Flick::NollieVarialHeelflip: return "Nollie Varial Heelflip";
    case Flick::NollieHardflip: return "Nollie Hardflip";
    case Flick::NollieInwardHeelflip: return "Nollie Inward Heelflip";
    case Flick::NollieTreFlip: return "Nollie 360 Flip";
    case Flick::NollieLaserFlip: return "Nollie Laser Flip";
    case Flick::NollieHardflip360: return "Nollie 360 Hardflip";
    case Flick::NollieInwardHeelflip360: return "Nollie 360 Inward Heelflip";
    default: return "";
    }
}

Flick FlickFromNative(std::string_view Name)
{
    for (const auto& N : Names) if (N.Native == Name) return N.Ride;
    return Flick::None;
}

std::shared_ptr<const FlickBank> FlickBank::Load(const std::vector<std::uint8_t>& Settings,
    const std::vector<std::uint8_t>& Gestures, std::string& Error)
{
    auto Result = std::make_shared<FlickBank>();
    if (!Result->Settings.Load(Settings, Error) || !LoadGestureData(Gestures, Result->Sets, Error)) return nullptr;
    // The board's settings give the controls' step and held-stick threshold, as PlayerControls::UpdateForPhysics
    // reads them.
    const auto Board = BoardPhysicsSettings::Load(Result->Settings, Error);
    if (!Board) return nullptr;
    Result->StepTime = Board->step.simulation.time_step;
    Result->MagnitudeThreshold = Board->input_magnitude_threshold;
    // PlayerControls::Load checks the seven sets and the recognizers' culling fields.
    if (!PlayerControls::Load(Result->Settings, Result->Sets, Error)) return nullptr;
    Error.clear();
    return Result;
}

FlickReader::FlickReader() = default;
FlickReader::~FlickReader() = default;
FlickReader::FlickReader(FlickReader&&) noexcept = default;
FlickReader& FlickReader::operator=(FlickReader&&) noexcept = default;

bool FlickReader::SetBank(std::shared_ptr<const FlickBank> InBank, std::string& Error)
{
    *this = FlickReader();
    if (!InBank) { Error = "no native gesture data"; return false; }
    auto Controls = PlayerControls::Load(InBank->Settings, InBank->Sets, Error);
    if (!Controls) return false;
    O.reset(new Owners{ControllerInputRuntime{}, std::move(*Controls)});
    Bank = std::move(InBank);
    return true;
}

void FlickReader::Activate()
{
    // The rider's own state starts again; Native's controls carry on.
    auto Keep = std::move(O); auto KeepBank = std::move(Bank); const auto KeepSerial = Serial; auto KeepLast = std::move(Last);
    *this = FlickReader();
    O = std::move(Keep); Bank = std::move(KeepBank); Serial = KeepSerial; Last = std::move(KeepLast);
    if (!O) return;
    // GameplaySession::Activate: Tick({}) once on a session that never ticked, four more after the spawn, each a
    // controller sample and the controls' update; the controller-input runtime is fresh before and after.
    const bool bFirst = O->Controls.ticks == 0;
    O->Input = ControllerInputRuntime{};
    for (int I = bFirst ? 5 : 4; I > 0; --I) Step(XboxState{}, 1);
    O->Input = ControllerInputRuntime{};
}

void FlickReader::Step(const XboxState& Pad, std::uint32_t Difficulty)
{
    // GameplaySession::Tick, then PlayerControls::Sample on board (no offboard remap): the pad without the host's
    // transfer bit through ControllerInputRuntime (ConvertXbox and the pad history), the controls' update on the
    // published action packet (riding, manual, wipe-out, anticipation and trick intentions), then the gestures. The
    // physical capabilities (ProduceWipeout's only reader) are Native's physics', which Ride has none of; actor flags
    // are 0, as Native's are, so the physical state passed to the gestures is never read.
    XboxState State = Pad;
    State.buttons = static_cast<std::uint16_t>(State.buttons & ~TransferButton);
    O->Input.Sample(State);
    auto Actions = O->Input.PublishedInput().Actions();
    O->Controls.Update(Actions, Bank->StepTime, Bank->MagnitudeThreshold, 0);
    std::string Error;
    O->Controls.PublishGestures(Difficulty, 0, Error);
}

Flick FlickReader::Update(const XboxState& Pad, bool bGoofy, GestureGroup Group, std::uint32_t Difficulty)
{
    Tick_.clear(); Speed.reset();
    if (!O) return Flick::None;
    const float Dt = Bank->StepTime;

    // Ride's load and manual band, on the canonical right stick.
    {
        const float X = float(Pad.right[0]) / 32767.f, Y = float(Pad.right[1]) / 32767.f, M = std::sqrt(X * X + Y * Y);
        const bool Rim = OnRim ? M > RimLeave : M > RimEnter;
        RimTime = Rim ? RimTime + Dt : 0.f;
        if (M < BandInner) Consumed = false;
        OnRim = Rim;
        const int Band = !Rim && M >= BandInner && M < BandOuter && std::fabs(Y) > .2f ? (Y < 0 ? -1 : 1) : 0;
        BandTime = Band != 0 && Band == BandSide ? BandTime + Dt : 0;
        BandSide = Band; StickX = X; StickY = Y;
    }

    Step(Pad, Difficulty);
    const auto& W = O->Controls.controller.Words();
    CX = Float(W[9]); CY = Float(W[10]);
    // The anticipation: the conditioned right stick out of the dead zone (Native's AnticMag intent).
    const float Before = WindTime;
    WindTime = CX != 0 || CY != 0 ? WindTime + Dt : 0.f;

    if (const auto* Gestures = O->Controls.Gestures())
        for (const auto& E : Gestures->LastEvents())
            Tick_.push_back({E.set, static_cast<std::uint16_t>(E.recognition.pattern), E.name, E.recognition.strength,
                E.recognition.distance, E.recognition.elapsed, E.permitted});
    const auto& Action = O->Controls.action_intents;
    if (const float* Published = Action.Get("GestureSpeed")) Speed = *Published;
    if (!Speed) return Flick::None;

    // The action graph's trick from this group (GraphGestureOperations' SelectGestureTrick), mirrored for a regular
    // stance as Native's Mirrored() is.
    const bool bMirrored = !bGoofy;
    const auto Chosen = SelectGestureTrick(Group, Action, bMirrored);
    const Flick Trick = Chosen ? FlickFromNative(*Chosen) : Flick::None;
    if (Trick == Flick::None) return Flick::None;
    FlickEvent E;
    E.Serial = ++Serial; E.Trick = Trick; E.NativeTrick = std::string(*Chosen); E.Group = Group; E.bMirrored = bMirrored;
    E.Strength = *Speed;
    if (const auto Key = SelectedKey(Group, Action))
        for (const auto& R : Tick_) if (R.bPermitted && R.Name == *Key) { E.Gesture = R; break; }
    Last = std::move(E);
    Load = Before;
    Consumed = true;
    return Trick;
}

const IntentMap& FlickReader::Intents() const
{
    static const IntentMap Empty;
    return O ? O->Controls.action_intents : Empty;
}

const std::vector<ControllerIntent>& FlickReader::PreGestureIntents() const
{
    static const std::vector<ControllerIntent> Empty;
    return O ? O->Controls.intents : Empty;
}

const std::array<std::uint32_t, 26>& FlickReader::Words() const
{
    static const std::array<std::uint32_t, 26> Empty{};
    return O ? O->Controls.controller.Words() : Empty;
}

std::optional<std::string_view> FlickReader::HeldPattern() const
{
    return O ? O->Controls.HeldPattern() : std::nullopt;
}
}
