// SPDX-License-Identifier: Apache-2.0
// A recorded ride's pad, replayed offline through Ride's controls adapter (Private/Ride/RideFlick.cpp) and, beside it,
// through Native's own input owners scheduled as GameplaySession does, then compared tick by tick and bit for bit.
//
// usage: ride_input_replay_probe settings.skate gestures.skate rows.txt
//        ride_input_replay_probe settings.skate gestures.skate script.txt
//
// rows.txt (the test writes it from a recording's frames.jsonl; floats are their binary32 bits in hex):
//   prefix <neutral ticks between the mount's activation and row 0>
//   then one line per row:
//   k ax0..ax5 b dt ground_before has_pad pad_buttons pad_lt pad_rt pad_lx pad_ly pad_rx pad_ry [ground push speed]
// ax are the six axes the engine reported (LX, LY, RX, RY, LT, RT, after its per-axis dead zone), b the recorder's
// button-index mask, dt the frame's step, ground_before whether the ride was rolling before the frame, and pad the
// packet the Native backend sent that frame when it was recorded. The optional last three are Native's own after the
// frame: rolling (0/1), pushing (0/1) and the speed's bits (cm/s); with them Ride's manual (Private/Ride/RideManual.cpp)
// runs on the goofy reader's intentions over Native's ground, as RideSession runs it.
//
// Each row is turned into FSkateInput the way USkateComponent::ReadInput does it (the recorded keys only: no mouse,
// no arrow keys), then packed with the host's own packer (Private/SkatePad.h). The adapter gets that packet; Native's
// owners get the recorded packet where there is one (the packet itself is compared first), so the comparison covers
// the host contract as well as the adapter's schedule. Output, one record per line:
//   pad k buttons lt rt lx ly rx ry recorded(0/1) same(0/1)
//   rec k set pattern name strength distance elapsed permitted        (the core's recognizer trace)
//   trick k speed unmirrored mirrored goofy regular serial_goofy serial_regular
//   manual k side                                                     (Ride's manual started, switched or ended)
//   deck k angle target                                               (a manual tick's deck, degrees, nose up +)
//   flag k on                                                         (the published balance turned non-zero / 0)
//   brake k on                                                        (Riding.Brake started / played out)
//   diff k field detail                                               (the first differences, if any)
//   summary key=value ...
//
// script.txt (scripted input, as a scenario's skate.input drives the board: FSkateInput as given, no controller keys):
//   script
//   then one line per item: "mount" (a mount's activation), or one tick's input
//   tick lx ly rx ry flags group goofy
// lx..ry are FSkateInput's sticks (doubles), flags its bits (1 push, 2 brake, 4 transfer, 8 powerslide, 16 grab left,
// 32 grab right) plus 64 when the board is rolling, group the gesture group (GraphGestureOperations) and goofy the stance
// in effect. The adapter reads each tick's packed pad beside Native's owners (compared as above); output:
//   rec k set pattern name strength distance elapsed permitted        (the adapter's recognizer trace)
//   flick k native_trick ride_trick speed set pattern serial          (a recognised trick)
//   manual k side                                                     (Ride's manual: -1 tail, 1 nose, 0 ended)
//   deck k angle target                                               (a manual tick's deck, degrees, nose up +)
//   flag k on, brake k on                                             (as above)
// The manual runs as RideSession runs it on plain ground (no pop, push or turn round), at a speed of 5 m/s.
//   diff ... and summary ticks= tricks= words= ... as above
#include "Ride/RideFlick.h"
#include "Ride/RideManual.h"
#include "SkatePad.h"
#include "Native/BoardPhysicsSettings.h"
#include "Native/ControllerInputRuntime.h"
#include "Native/GraphGestureOperations.h"
#include "Native/PlayerControls.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

using namespace atelier;
using skate::XboxState;

namespace
{
std::uint32_t Bits(float Value) { std::uint32_t Out; std::memcpy(&Out, &Value, 4); return Out; }
float FromBits(std::uint32_t Value) { float Out; std::memcpy(&Out, &Value, 4); return Out; }

std::vector<std::uint8_t> File(const char* Path)
{
    std::ifstream In(Path, std::ios::binary);
    return {std::istreambuf_iterator<char>(In), {}};
}

// The recorder's button indices (games' ride_session.py BUTTONS): the gamepad's, then the keyboard's and the mouse's.
enum : int { FaceBottom = 0, FaceRight = 1, FaceLeft = 2, LeftShoulder = 4, RightShoulder = 5, LeftThumb = 6,
    RightThumb = 7, KeyW = 14, KeyA = 15, KeyS = 16, KeyD = 17, Space = 18, KeyQ = 19, KeyE = 20, KeyC = 21,
    LeftShift = 24, LeftMouse = 25 };

struct Row
{
    long K = 0;
    std::array<float, 6> Ax{};
    std::uint32_t B = 0;
    float Dt = 0;
    bool bGroundBefore = false, bHasPad = false;
    XboxState Pad;
    bool bNative = false, bGround = false, bPush = false;   // Native's own state after the frame, when given
    float Speed = 0;
};

// RideSession's manual (TryManual and TickGround's manual block) on one tick: the action graph's intentions every
// tick, then on plain ground Turning.Idle and Riding.Brake, a manual's side and its deck. Prints a line when the side,
// the published balance or the brake state changes.
struct ManualRun
{
    ride::ManualControl Control;
    int Side = 0;
    bool bIn = false, bFlag = false, bBraking = false;

    void Tick(long K, const ride::FlickReader& Reader, bool bGroundBefore, bool bGround, bool bIdle, bool bPop, float Speed,
        float Dt)
    {
        Control.ReadIntents(Reader.Intents(), bGroundBefore, Dt);
        // In the air, or popping (TakeOff.FromManual), no manual.
        if (!bGround || bPop) { if (bIn) End(K); Control.Riding(false, Dt); Report(K); return; }
        // A landing this tick starts one straight into its cycle.
        if (!bIn && bIdle && Control.Idle(false)) { bIn = true; Control.Start(!bGroundBefore); }
        Control.Riding(!bIn, Dt);
        if (bIn)
        {
            const int Now = int(Control.Side());
            if (Now == 0) End(K);
            else
            {
                if (Now != Side) { Side = Now; std::printf("manual %ld %d\n", K, Side); }
                Control.Hold(Dt);
                Control.StepDeck(Reader.GetBank()->Manual, 1, ride::ManualDeck{}, Speed, Dt);
                std::printf("deck %ld %.4f %.4f\n", K, Control.DeckAngle() * 57.29578f, Control.Target() * 57.29578f);
            }
        }
        Report(K);
    }
    void End(long K) { bIn = false; Side = 0; Control.End(); std::printf("manual %ld 0\n", K); }
    void Report(long K)
    {
        // RideSession's ManualBalance is non-zero (SkateRuntime's manual flag) in a manual past the nose's Into.
        const bool bNow = bIn && !Control.Into();
        if (bNow != bFlag) { bFlag = bNow; std::printf("flag %ld %d\n", K, bFlag ? 1 : 0); }
        if (Control.BrakePlaying() != bBraking) { bBraking = !bBraking; std::printf("brake %ld %d\n", K, bBraking ? 1 : 0); }
    }
};

// USkateComponent::ReadInput on recorded keys: the left stick with D and A, the dead zone undone, the right stick
// with y up, Space's load and pop on the right stick (held: down; released: up for .05 s), the largest of them kept.
struct HostReader
{
    float SpaceHeld = -1.f, SpaceRelease = -1.f;

    skate_pad::HostPad Read(const Row& R)
    {
        const auto Down = [&](int Index) { return (R.B >> Index & 1u) != 0; };
        skate_pad::HostPad P;
        const float LeftX = std::clamp(R.Ax[0] + (Down(KeyD) ? 1.f : 0.f) - (Down(KeyA) ? 1.f : 0.f), -1.f, 1.f);
        P.LeftX = skate_pad::Unsqueeze(LeftX);
        P.LeftY = skate_pad::Unsqueeze(R.Ax[1]);
        double RightX = skate_pad::Unsqueeze(R.Ax[2]), RightY = -skate_pad::Unsqueeze(R.Ax[3]);
        double KeysX = 0, KeysY = 0;
        if (Down(Space)) { SpaceHeld = std::max(0.f, SpaceHeld) + R.Dt; SpaceRelease = -1.f; KeysY = -1; }
        else if (SpaceHeld >= 0.f) { SpaceHeld = -1.f; SpaceRelease = 0.f; }
        if (SpaceRelease >= 0.f)
        {
            SpaceRelease += R.Dt;
            KeysY = SpaceRelease < .05f ? 1. : 0.;
            if (SpaceRelease >= .05f) SpaceRelease = -1.f;
        }
        if (std::sqrt(KeysX * KeysX + KeysY * KeysY) > std::sqrt(RightX * RightX + RightY * RightY))
        { RightX = KeysX; RightY = KeysY; }
        P.RightX = RightX; P.RightY = RightY;
        P.bPush = Down(KeyW) || Down(FaceBottom) || Down(FaceLeft);
        P.bBrake = Down(KeyS) || Down(FaceRight);
        P.bPowerslide = Down(KeyC);
        P.bGrabLeft = Down(KeyQ) || R.Ax[4] > .35f;
        P.bGrabRight = Down(KeyE) || R.Ax[5] > .35f;
        P.bTransfer = Down(LeftShift) || (P.LeftY > .7f && std::fabs(P.LeftX) < P.LeftY);
        P.bGround = R.bGroundBefore;
        // The player's own controller drove the recording.
        P.bController = true;
        P.bFaceLeft = Down(FaceLeft); P.bFaceBottom = Down(FaceBottom); P.bW = Down(KeyW);
        P.bLeftShoulder = Down(LeftShoulder); P.bRightShoulder = Down(RightShoulder);
        P.bLeftThumb = Down(LeftThumb); P.bRightThumb = Down(RightThumb);
        P.bQ = Down(KeyQ); P.bE = Down(KeyE);
        P.LeftTrigger = R.Ax[4]; P.RightTrigger = R.Ax[5];
        return P;
    }
};

// Native's owners, scheduled as GameplaySession and GameplayRuntime schedule them, written out here independently of
// the adapter: Tick strips the transfer bit and samples the pad; GameplayRuntime::Advance runs PlayerControls::Sample
// (UpdateForPhysics on board: no offboard remap, the board's step and held-stick threshold, then the gestures in the
// profile's physics mode). Ride has no physics, so the scoring capabilities and the physical state are 0 on both sides.
struct NativeCore
{
    skate::ControllerInputRuntime Input;
    skate::PlayerControls Controls;
    skate::BoardPhysicsSettings Board;
    std::uint64_t PhysicalTicks = 0;
    std::uint32_t PhysicsMode = 1;

    bool Tick(XboxState State, std::string& Error)
    {
        State.buttons = static_cast<std::uint16_t>(State.buttons & ~skate_pad::ButtonTransfer);
        Input.Sample(State);
        auto Packet = Input.PublishedInput();
        auto Actions = Packet.Actions();
        skate::PlayerSimulationActions Simulation(Actions, std::nullopt);
        Controls.Update(Simulation, Board.step.simulation.time_step, Board.input_magnitude_threshold, 0);
        if (!Controls.PublishGestures(PhysicsMode, 0, Error)) return false;
        ++PhysicalTicks;
        return true;
    }
    bool Activate(std::string& Error)
    {
        Input = skate::ControllerInputRuntime{};
        if (PhysicalTicks == 0 && !Tick({}, Error)) return false;
        for (int I = 0; I < 4; ++I) if (!Tick({}, Error)) return false;
        Input = skate::ControllerInputRuntime{};
        return true;
    }
};

struct Counts
{
    long Ticks = 0, Words = 0, Conditioned = 0, PreIntents = 0, Trace = 0, Intents = 0, Speed = 0, Held = 0,
        Mapping = 0, Stance = 0, Diffs = 0;
};

void Diff(Counts& C, long K, const char* Field, const std::string& Detail)
{
    if (C.Diffs++ < 20) std::printf("diff %ld %s %s\n", K, Field, Detail.c_str());
}

std::string Hex(std::uint32_t Value) { char B[16]; std::snprintf(B, sizeof B, "%08x", Value); return B; }

bool SameIntents(const std::vector<skate::ControllerIntent>& A, const std::vector<skate::ControllerIntent>& B)
{
    if (A.size() != B.size()) return false;
    for (std::size_t I = 0; I < A.size(); ++I)
        if (A[I].name != B[I].name || Bits(A[I].value) != Bits(B[I].value)) return false;
    return true;
}

bool SameMap(const skate::IntentMap& A, const skate::IntentMap& B)
{
    if (A.Size() != B.Size()) return false;
    auto I = A.Entries().begin(); auto J = B.Entries().begin();
    for (; I != A.Entries().end(); ++I, ++J)
        if (I->first != J->first || Bits(I->second) != Bits(J->second)) return false;
    return true;
}

bool SameTrace(const std::vector<ride::FlickRecognition>& A, const std::vector<skate::GestureEventTrace>& B)
{
    if (A.size() != B.size()) return false;
    for (std::size_t I = 0; I < A.size(); ++I)
        if (A[I].Set != B[I].set || A[I].Pattern != B[I].recognition.pattern || A[I].Name != B[I].name
            || Bits(A[I].Strength) != Bits(B[I].recognition.strength) || Bits(A[I].Distance) != Bits(B[I].recognition.distance)
            || Bits(A[I].Elapsed) != Bits(B[I].recognition.elapsed) || A[I].bPermitted != B[I].permitted) return false;
    return true;
}

// The adapter (pinned to a stance) against Native's owners after the same tick.
void Compare(Counts& C, long K, const ride::FlickReader& A, const NativeCore& N)
{
    const auto& Words = N.Controls.controller.Words();
    if (A.Words() != Words)
    {
        ++C.Words;
        for (int I = 0; I < 26; ++I)
            if (A.Words()[I] != Words[I])
            { Diff(C, K, "words", std::to_string(I) + " " + Hex(A.Words()[I]) + " " + Hex(Words[I])); break; }
    }
    if (Bits(A.ConditionedX()) != Words[9] || Bits(A.ConditionedY()) != Words[10])
    { ++C.Conditioned; Diff(C, K, "conditioned", Hex(Bits(A.ConditionedX())) + "," + Hex(Bits(A.ConditionedY()))); }
    if (!SameIntents(A.PreGestureIntents(), N.Controls.intents))
    { ++C.PreIntents; Diff(C, K, "pre_intents", std::to_string(A.PreGestureIntents().size()) + " " + std::to_string(N.Controls.intents.size())); }
    static const std::vector<skate::GestureEventTrace> None;
    const auto* Gestures = N.Controls.Gestures();
    if (!SameTrace(A.Recognitions(), Gestures ? Gestures->LastEvents() : None))
    { ++C.Trace; Diff(C, K, "trace", std::to_string(A.Recognitions().size())); }
    if (!SameMap(A.Intents(), N.Controls.action_intents))
    { ++C.Intents; Diff(C, K, "intents", std::to_string(A.Intents().Size()) + " " + std::to_string(N.Controls.action_intents.Size())); }
    const float* Speed = N.Controls.action_intents.Get("GestureSpeed");
    const auto Mine = A.GestureSpeed();
    if (Mine.has_value() != (Speed != nullptr) || (Mine && Bits(*Mine) != Bits(*Speed)))
    { ++C.Speed; Diff(C, K, "speed", Mine ? Hex(Bits(*Mine)) : "-"); }
    const auto Held = A.HeldPattern(); const auto Theirs = N.Controls.HeldPattern();
    if (Held.has_value() != Theirs.has_value() || (Held && *Held != *Theirs))
    { ++C.Held; Diff(C, K, "held", Held ? std::string(*Held) : "-"); }
}

// The two pinned stances sample the same pad: everything but the mapping must agree.
void CompareStances(Counts& C, long K, const ride::FlickReader& Goofy, const ride::FlickReader& Regular)
{
    if (Goofy.Words() != Regular.Words() || !SameIntents(Goofy.PreGestureIntents(), Regular.PreGestureIntents())
        || !SameMap(Goofy.Intents(), Regular.Intents()))
    { ++C.Stance; Diff(C, K, "stance", "sampling differs between the pinned stances"); }
}

bool ReadRows(const char* Path, long& Prefix, std::vector<Row>& Rows)
{
    std::ifstream In(Path);
    std::string Word;
    if (!(In >> Word >> Prefix) || Word != "prefix") return false;
    std::string Line;
    std::getline(In, Line);
    while (std::getline(In, Line))
    {
        if (Line.empty()) continue;
        std::istringstream S(Line);
        Row R; std::uint32_t Ax[6], Dt; int Ground, HasPad; unsigned Buttons; int Pad[6];
        if (!(S >> R.K)) return false;
        for (auto& A : Ax) if (!(S >> std::hex >> A)) return false;
        if (!(S >> std::dec >> R.B >> std::hex >> Dt >> std::dec >> Ground >> HasPad >> std::hex >> Buttons >> std::dec)) return false;
        for (auto& P : Pad) if (!(S >> P)) return false;
        int NativeGround = 0, NativePush = 0; std::uint32_t Speed = 0;
        if (S >> NativeGround >> NativePush >> std::hex >> Speed >> std::dec)
        { R.bNative = true; R.bGround = NativeGround != 0; R.bPush = NativePush != 0; R.Speed = FromBits(Speed); }
        for (int I = 0; I < 6; ++I) R.Ax[I] = FromBits(Ax[I]);
        R.Dt = FromBits(Dt); R.bGroundBefore = Ground != 0; R.bHasPad = HasPad != 0;
        R.Pad.buttons = static_cast<std::uint16_t>(Buttons);
        R.Pad.triggers = {static_cast<std::uint8_t>(Pad[0]), static_cast<std::uint8_t>(Pad[1])};
        R.Pad.left = {static_cast<std::int16_t>(Pad[2]), static_cast<std::int16_t>(Pad[3])};
        R.Pad.right = {static_cast<std::int16_t>(Pad[4]), static_cast<std::int16_t>(Pad[5])};
        Rows.push_back(R);
    }
    return true;
}

bool SamePad(const XboxState& A, const XboxState& B)
{
    return A.buttons == B.buttons && A.triggers == B.triggers && A.left == B.left && A.right == B.right;
}

int RunScript(std::ifstream& In, const std::shared_ptr<const ride::FlickBank>& Bank, NativeCore& Core)
{
    std::string Error;
    ride::FlickReader Reader;
    if (!Reader.SetBank(Bank, Error)) { std::fprintf(stderr, "adapter: %s\n", Error.c_str()); return 2; }
    Counts C; long K = 0, Tricks = 0;
    ManualRun Manual;
    int WasGround = -1;   // the previous tick's rolling flag (-1: none since the mount)
    std::string Line;
    while (std::getline(In, Line))
    {
        std::istringstream S(Line);
        std::string Kind;
        if (!(S >> Kind)) continue;
        if (Kind == "mount")
        {
            Reader.Activate(); Manual = ManualRun(); WasGround = -1;
            if (!Core.Activate(Error)) { std::fprintf(stderr, "native activation: %s\n", Error.c_str()); return 2; }
            Compare(C, K, Reader, Core);
            continue;
        }
        if (Kind != "tick") { std::fprintf(stderr, "unreadable script line: %s\n", Line.c_str()); return 2; }
        std::string Words[4]; unsigned Flags = 0, Group = 0; int Goofy = 0;
        if (!(S >> Words[0] >> Words[1] >> Words[2] >> Words[3] >> Flags >> Group >> Goofy) || Group > 6)
        { std::fprintf(stderr, "unreadable tick: %s\n", Line.c_str()); return 2; }
        skate_pad::HostPad P;
        P.LeftX = std::strtod(Words[0].c_str(), nullptr); P.LeftY = std::strtod(Words[1].c_str(), nullptr);
        P.RightX = std::strtod(Words[2].c_str(), nullptr); P.RightY = std::strtod(Words[3].c_str(), nullptr);
        P.bPush = Flags & 1; P.bBrake = Flags & 2; P.bTransfer = Flags & 4; P.bPowerslide = Flags & 8;
        P.bGrabLeft = Flags & 16; P.bGrabRight = Flags & 32; P.bGround = Flags & 64;
        const XboxState Pad = skate_pad::Pack(P);
        const auto Trick = Reader.Update(Pad, Goofy != 0, static_cast<skate::GestureGroup>(Group));
        if (!Core.Tick(Pad, Error)) { std::fprintf(stderr, "native tick %ld: %s\n", K, Error.c_str()); return 2; }
        ++C.Ticks;
        Compare(C, K, Reader, Core);
        for (const auto& R : Reader.Recognitions())
            std::printf("rec %ld %u %u %s %08x %08x %08x %d\n", K, unsigned(R.Set), unsigned(R.Pattern), R.Name.c_str(),
                Bits(R.Strength), Bits(R.Distance), Bits(R.Elapsed), R.bPermitted ? 1 : 0);
        const bool bGround = (Flags & 64) != 0, bGroundBefore = WasGround < 0 ? bGround : WasGround != 0;
        WasGround = bGround ? 1 : 0;
        Manual.Tick(K, Reader, bGroundBefore, bGround, (Flags & 1) == 0, Trick != ride::Flick::None, 5.f, Reader.StepTime());
        if (Trick != ride::Flick::None)
        {
            const auto& E = Reader.Event();
            std::printf("flick %ld %s %s %08x %u %u %u\n", K, E.NativeTrick.c_str(), ride::FlickName(Trick), Bits(E.Strength),
                unsigned(E.Gesture.Set), unsigned(E.Gesture.Pattern), E.Serial);
            ++Tricks;
        }
        ++K;
    }
    std::printf("summary ticks=%ld tricks=%ld words=%ld conditioned=%ld pre_intents=%ld trace=%ld intents=%ld speed=%ld "
        "held=%ld\n", C.Ticks, Tricks, C.Words, C.Conditioned, C.PreIntents, C.Trace, C.Intents, C.Speed, C.Held);
    return 0;
}
}

int main(int argc, char** argv)
{
    if (argc < 4) { std::fprintf(stderr, "usage: %s settings.skate gestures.skate rows.txt\n", argv[0]); return 2; }
    std::string Error;
    const auto SettingsBytes = File(argv[1]), GestureBytes = File(argv[2]);
    long Prefix = 0; std::vector<Row> Rows;
    std::ifstream Script(argv[3]);
    std::string First;
    const bool bScript = (Script >> First) && First == "script";
    if (!bScript && !ReadRows(argv[3], Prefix, Rows)) { std::fprintf(stderr, "unreadable rows\n"); return 2; }

    // The adapter, as Ride makes it: one bank, one reader per ride, a mount's activation. Two readers pin the stance
    // either way (goofy maps unmirrored, regular mirrored).
    const auto Bank = ride::FlickBank::Load(SettingsBytes, GestureBytes, Error);
    if (!Bank) { std::fprintf(stderr, "adapter bank: %s\n", Error.c_str()); return 2; }
    ride::FlickReader Goofy, Regular;
    if (!Goofy.SetBank(Bank, Error) || !Regular.SetBank(Bank, Error))
    { std::fprintf(stderr, "adapter: %s\n", Error.c_str()); return 2; }

    // Native's owners from Native's loaders, independently of the adapter's bank.
    skate::SettingsDatabase Settings;
    std::vector<skate::GestureSet> Sets;
    if (!Settings.Load(SettingsBytes, Error) || !skate::LoadGestureData(GestureBytes, Sets, Error))
    { std::fprintf(stderr, "native data: %s\n", Error.c_str()); return 2; }
    auto Board = skate::BoardPhysicsSettings::Load(Settings, Error);
    auto Controls = skate::PlayerControls::Load(Settings, Sets, Error);
    if (!Board || !Controls) { std::fprintf(stderr, "native owners: %s\n", Error.c_str()); return 2; }
    NativeCore Core{skate::ControllerInputRuntime{}, std::move(*Controls), *Board};
    if (bScript) return RunScript(Script, Bank, Core);

    Counts C;
    // The mount, then the neutral settle before row 0 (the capture boundary).
    Goofy.Activate(); Regular.Activate();
    if (!Core.Activate(Error)) { std::fprintf(stderr, "native activation: %s\n", Error.c_str()); return 2; }
    Compare(C, -1, Goofy, Core);
    const auto Group = skate::GestureGroup::Square;
    for (long I = 0; I < Prefix; ++I)
    {
        Goofy.Update({}, true, Group); Regular.Update({}, false, Group);
        if (!Core.Tick({}, Error)) { std::fprintf(stderr, "native tick: %s\n", Error.c_str()); return 2; }
        Compare(C, -1, Goofy, Core); CompareStances(C, -1, Goofy, Regular); ++C.Ticks;
    }

    HostReader Host;
    ManualRun Manual;
    long PadRows = 0, PadSame = 0, FirstPadDiff = -1, Tricks = 0;
    for (const Row& R : Rows)
    {
        const XboxState Pad = skate_pad::Pack(Host.Read(R));
        const bool bSame = R.bHasPad && SamePad(Pad, R.Pad);
        if (R.bHasPad) { ++PadRows; if (bSame) ++PadSame; else if (FirstPadDiff < 0) FirstPadDiff = R.K; }
        std::printf("pad %ld %x %d %d %d %d %d %d %d %d\n", R.K, Pad.buttons, Pad.triggers[0], Pad.triggers[1], Pad.left[0],
            Pad.left[1], Pad.right[0], Pad.right[1], R.bHasPad ? 1 : 0, bSame ? 1 : 0);

        const auto TrickGoofy = Goofy.Update(Pad, true, Group);
        const auto TrickRegular = Regular.Update(Pad, false, Group);
        if (!Core.Tick(R.bHasPad ? R.Pad : Pad, Error)) { std::fprintf(stderr, "native tick %ld: %s\n", R.K, Error.c_str()); return 2; }
        ++C.Ticks;
        Compare(C, R.K, Goofy, Core);
        CompareStances(C, R.K, Goofy, Regular);

        if (R.bNative)
            Manual.Tick(R.K, Goofy, R.bGroundBefore, R.bGround, !R.bPush, TrickGoofy != ride::Flick::None, R.Speed / 100.f,
                Goofy.StepTime());
        if (const auto* Gestures = Core.Controls.Gestures())
            for (const auto& E : Gestures->LastEvents())
                std::printf("rec %ld %u %zu %s %08x %08x %08x %d\n", R.K, unsigned(E.set), E.recognition.pattern,
                    E.name.c_str(), Bits(E.recognition.strength), Bits(E.recognition.distance), Bits(E.recognition.elapsed),
                    E.permitted ? 1 : 0);

        // The mapping under a pinned stance, against GraphGestureOperations on Native's own intents.
        const float* Speed = Core.Controls.action_intents.Get("GestureSpeed");
        if (Speed)
        {
            const auto Unmirrored = skate::SelectGestureTrick(Group, Core.Controls.action_intents, false);
            const auto Mirrored = skate::SelectGestureTrick(Group, Core.Controls.action_intents, true);
            const auto Expect = [](std::optional<std::string_view> Name)
            { return Name ? ride::FlickFromNative(*Name) : ride::Flick::None; };
            const std::string G = TrickGoofy != ride::Flick::None ? Goofy.Event().NativeTrick : "-";
            const std::string Rg = TrickRegular != ride::Flick::None ? Regular.Event().NativeTrick : "-";
            const bool bGoofyOk = TrickGoofy == Expect(Unmirrored) && (TrickGoofy == ride::Flick::None || G == *Unmirrored);
            const bool bRegularOk = TrickRegular == Expect(Mirrored) && (TrickRegular == ride::Flick::None || Rg == *Mirrored);
            if (!bGoofyOk || !bRegularOk) { ++C.Mapping; Diff(C, R.K, "mapping", G + " " + Rg); }
            if (TrickGoofy != ride::Flick::None) ++Tricks;
            std::printf("trick %ld %08x %s %s %s %s %u %u\n", R.K, Bits(*Speed),
                Unmirrored ? std::string(*Unmirrored).c_str() : "-", Mirrored ? std::string(*Mirrored).c_str() : "-",
                G.c_str(), Rg.c_str(), Goofy.Event().Serial, Regular.Event().Serial);
        }
        else if (TrickGoofy != ride::Flick::None || TrickRegular != ride::Flick::None)
        { ++C.Mapping; Diff(C, R.K, "mapping", "a trick without a gesture"); }
    }
    std::printf("summary rows=%zu prefix=%ld ticks=%ld pad_rows=%ld pad_same=%ld first_pad_diff=%ld tricks=%ld "
        "words=%ld conditioned=%ld pre_intents=%ld trace=%ld intents=%ld speed=%ld held=%ld mapping=%ld stance=%ld "
        "step=%08x threshold=%08x\n", Rows.size(), Prefix, C.Ticks, PadRows, PadSame, FirstPadDiff, Tricks, C.Words,
        C.Conditioned, C.PreIntents, C.Trace, C.Intents, C.Speed, C.Held, C.Mapping, C.Stance,
        Bits(Core.Board.step.simulation.time_step), Bits(Core.Board.input_magnitude_threshold));
    return 0;
}
