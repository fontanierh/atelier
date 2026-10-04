#pragma once
// Native's manual for the Ride backend (RIDE.md, "Manuals"). No engine types, so the offline replay test
// (Tests/Native/ride_input_replay_probe.cpp) runs this same code.
//  - The action graph (OnBoard, every tick, in the air too): Native's Manual and ManualBrake intentions as
//    PlayerControls produces them (RideFlick), and ManualEngageTime, how long Manual has been held
//    (CreateMGTimeIntentFromAGIntent). On the ground its Antic state starts when AnticMag passes 0.9 and lasts while
//    the conditioned right stick is out of its dead zone.
//  - The motion graph (Riding.Turning): from Idle a manual starts once ManualEngageTime passes 0.2 s, unless a
//    landing came down faster than 8 m/s on a face steeper than 45 degrees; a rider already anticipating a pop
//    (Turning.Anticipation, entered from Idle with the Antic state) has no way into one, and neither has one in
//    Riding.Brake, which the Brake intention starts and Idle waits for. The side is Manual's sign (TailManual below 0,
//    NoseManual above), the brake lasts while ManualBrake is published, and the manual ends when Manual goes. A nose
//    manual started on the ground (from Idle, or from the tail) first plays NoseManual.Holding.Into, which carries no
//    balance; one landed from the air goes straight to its Cycle (InAirStatic's transition).
//  - The physics: CalculateManual (Native/Manual.cpp) as GroundBoard calls it, on Native's settings
//    (physics_manual/default, physics_mode/<difficulty>). Its target is (0.25 + 0.75 |balance|) of MaxTiltAngle (24
//    degrees; BrakeTiltAngle, 30, braking) with a 1.5 Hz procedural wobble scaled by NoiseVsSpeed, and it has no fail
//    angle. Ride's board is kinematic, so the controller's angular displacement drives a deck with one axis: the
//    pitch about the axle that stays down, weighed down by a fitted weight (ManualDeck).
#include "Native/Manual.h"
#include "Native/NativeMath.h"
#include <cstdint>
#include <optional>
#include <string>

namespace atelier::skate { class IntentMap; class SettingsDatabase; }

namespace atelier::ride
{
    /** Native's data for the manual, decoded once with Native's loaders. */
    struct ManualBank
    {
        skate::ManualSettings Settings{};
        skate::ManualMode Modes[3]{};            // physics_mode easy, normal, hardcore
        skate::PointGraph<8> Friction{};         // physics_friction FrictionVsSpeed_Manual (m/s to m/s^2)
        static bool Load(const skate::SettingsDatabase& Data, ManualBank& Out, std::string& Error);
    };

    /** Ride's one-axis deck under the controller (fitted to Native's deck over carpark-1's two manuals). */
    struct ManualDeck
    {
        float Gain = .8f;          // share of the controller's displacement that turns the deck about the axle
        float Damping = 50.f;      // 1/s
        float Weight = 120.f;      // rad/s^2 pulling the raised end down
    };

    enum class ManualSide : std::int8_t { Tail = -1, None = 0, Nose = 1 };

    class ManualControl
    {
    public:
        /** A mount: nothing held, the deck flat. */
        void Reset() { *this = ManualControl(); }

        /** The action graph, every tick and in every mode, on this tick's intentions (FlickReader::Intents). bGround:
         *  on the wheels (the Antic state is OnGround's). */
        void ReadIntents(const skate::IntentMap& Intents, bool bGround, float Dt);

        /** Riding.Brake, every tick (one graph step a tick). bRiding: rolling on the ground with no manual, pop or
         *  powerslide under way; anything else leaves it. The Brake intention (the brake button) starts it; its Into
         *  (B_BRAKE_INTO, 0.2 s) plays out whatever the button does, Cyc lasts while the brake is held, and Out
         *  (B_BRAKE_OUT, 0.5 s) hands back to Turning 0.1 s before its end, where Idle takes over the tick after. Each
         *  waits for its 0.2 s blend in, so Into lasts 14 ticks. */
        void Riding(bool bRiding, float Dt);
        /** Riding.Brake is playing, so Turning.Idle is not. */
        bool BrakePlaying() const { return Brake != BrakeStep::None; }

        /** Turning.Idle on the ground with nothing else playing (no pop, push, turn round, powerslide or brake): true
         *  when a manual starts. bHardLanding: Native's guard, a landing this tick faster than 8 m/s down onto a face
         *  steeper than 45 degrees. Otherwise the Antic state starts the anticipation. */
        bool Idle(bool bHardLanding);
        /** Starts the manual (Idle said so): the controller and the deck start again. bLanding: the tick's landing
         *  started it (from the air), so a nose manual skips its Into. */
        void Start(bool bLanding);
        /** A manual's tick, before its deck: the graph's side, and NoseManual.Holding.Into's clock. */
        void Hold(float Dt);
        /** The side the intentions hold in a manual (None: Manual has gone, which ends it). */
        ManualSide Side() const { return !Manual ? ManualSide::None : *Manual < 0.f ? ManualSide::Tail : ManualSide::Nose; }
        /** NoseManual.Holding.Into is playing: no balance attribute yet. */
        bool Into() const { return IntoTime >= 0.f; }
        /** The manual's brake (TailManual.Brake, NoseManual.Holding.Brake): ManualBrake published. */
        bool Braking() const { return ManualBrake.has_value(); }
        /** The physics' balance in a manual: the balance attribute (Manual, or -1 / +1 braking on the tail / nose)
         *  negated, positive on the tail; 0 in the nose manual's Into. */
        float Balance() const;
        /** One physics tick of a manual: CalculateManual on the deck. Speed is the board's (m/s), Difficulty Native's
         *  physics mode (0 easy, 1 normal, 2 hardcore). */
        void StepDeck(const ManualBank& Bank, std::uint32_t Difficulty, const ManualDeck& Deck, float Speed, float Dt);
        /** The manual's end: the deck goes flat. */
        void End() { Angle = Spin = 0; State.Reset(); Time = 0; IntoTime = -1; Graph = ManualSide::None; }

        std::optional<float> ManualIntent() const { return Manual; }
        float EngageTime() const { return Engage; }
        bool Antic() const { return bAntic; }
        bool Anticipating() const { return bAnticipating; }
        /** The deck's pitch (rad): positive with the nose up (a tail manual), negative with the tail up. */
        float DeckAngle() const { return Angle; }
        /** The controller's target this tick (rad, same sign). */
        float Target() const { return State.target_angle; }

    private:
        enum class BrakeStep : std::uint8_t { None, Into, Cyc, Out };
        std::optional<float> Manual, ManualBrake;
        float Engage = 0, AnticMag = 0;
        bool bAntic = false, bAnticipating = false, bBrake = false;
        BrakeStep Brake = BrakeStep::None;
        float BrakeTime = 0;                      // the brake clip's clock (s), and its blend's
        bool bBrakeBlended = false;               // the brake clip's blend has been dropped
        ManualSide Graph = ManualSide::None;      // the manual state the graph is in
        float IntoTime = -1;                      // NoseManual.Holding.Into's clock (s), -1 outside it
        skate::ManualState State;
        float Angle = 0, Spin = 0, Time = 0;
    };
}
