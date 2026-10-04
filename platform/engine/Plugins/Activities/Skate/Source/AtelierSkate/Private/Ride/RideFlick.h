#pragma once
// Flick-It for the Ride backend: Native's own controls, owned per ride and stepped once per simulation tick (RIDE.md,
// "Tricks"). The canonical pad (SkatePad.h, the packet the Native backend gets) goes through Native's
// ControllerInputRuntime (ConvertXbox, the pad history and action packet), PlayerControls (the derived controller
// words, the riding, manual, wipe-out, anticipation and trick intentions, and the gesture manager with its seven
// recognizers) and GraphGestureOperations' stance mapping. Nothing is re-implemented here: this file holds the owners,
// feeds them and reports what they published. No engine types, so the offline replay test
// (Tests/Native/ride_input_replay_probe.cpp) runs this same adapter.
#include "Native/Gestures.h"
#include "Native/GraphGestureOperations.h"
#include "Native/Input.h"
#include "Native/Intents.h"
#include "Native/Settings.h"
#include "RideManual.h"
#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace atelier::skate { struct ControllerIntent; }

namespace atelier::ride
{
    enum class Flick : std::uint8_t
    {
        None, Ollie, Nollie, Kickflip, Heelflip, ShoveIt, FsShoveIt, Shove360, FsShove360, VarialKickflip,
        VarialHeelflip, Hardflip, InwardHeelflip, TreFlip, LaserFlip, Hardflip360, InwardHeelflip360,
        // Native's nollie family (GraphGestureOperations' N_Kickflip ... N_360InwardHeelflip): the same tricks popped
        // off the nose.
        NollieKickflip, NollieHeelflip, NollieShoveIt, NollieFsShoveIt, NollieShove360, NollieFsShove360,
        NollieVarialKickflip, NollieVarialHeelflip, NollieHardflip, NollieInwardHeelflip, NollieTreFlip,
        NollieLaserFlip, NollieHardflip360, NollieInwardHeelflip360,
        Num
    };

    /** A trick popped off the nose: the nollie and its flips and shove-its. */
    inline bool IsNollie(Flick F) { return F == Flick::Nollie || (F >= Flick::NollieKickflip && F < Flick::Num); }

    const char* FlickName(Flick F);
    /** Native's trick name (a GraphGestureOperations mapping row's result, e.g. "N_InwardHeelflip") as Ride's trick;
     *  None for a trick Ride has no clips for (the presentation catalogue is still the small enum). */
    Flick FlickFromNative(std::string_view Name);

    /** One recognizer's match this tick (the gesture manager's trace), in manager order. */
    struct FlickRecognition
    {
        std::uint8_t Set = 0;          // 0 main, 1 rotated90, 2 rotated_minus90, 3 air, 4 fingerflip, 5 left, 6 step
        std::uint16_t Pattern = 0;     // the pattern's index in its set
        std::string Name;              // the pattern's name (the gesture intent it publishes)
        float Strength = 0, Distance = 0, Elapsed = 0;
        bool bPermitted = false;       // GestureEventPermitted: published into the action intents
    };

    /** A recognised trick: the pop request. Trick height (U53) is still Ride's own. */
    struct FlickEvent
    {
        std::uint32_t Serial = 0;                  // recognised tricks since the owners were made, from 1
        Flick Trick = Flick::None;                 // Ride's trick
        std::string NativeTrick;                   // the mapped trick, as Native names it
        skate::GestureGroup Group = skate::GestureGroup::Square;
        FlickRecognition Gesture;                  // the published gesture the mapping chose
        bool bMirrored = false;                    // Native's Mirrored(): the regular stance in effect
        float Strength = 0;                        // the GestureSpeed intent this tick (the last permitted event's)
    };

    /** Native's data for the controls, decoded once with Native's own loaders and shared by every ride. */
    struct FlickBank
    {
        skate::SettingsDatabase Settings;
        std::vector<skate::GestureSet> Sets;
        float StepTime = 0;                // the board's fixed simulation step (BoardPhysicsSettings)
        float MagnitudeThreshold = 0;      // inputlistener/default/StickMagnitudeMinToCountHeld
        ManualBank Manual;                 // the manual's controller settings and friction (RideManual.h)
        /** settings.skate and gestures.skate's bytes. */
        static std::shared_ptr<const FlickBank> Load(const std::vector<std::uint8_t>& Settings,
            const std::vector<std::uint8_t>& Gestures, std::string& Error);
    };

    class FlickReader
    {
    public:
        // Ride's own load (the crouch before a pop, until the graph port replaces it) reads the canonical right stick:
        // the rim is entered this far out and left below RimLeave; a stick back under Centre clears a pop's load.
        static constexpr float RimEnter = .7f, RimLeave = .55f, Centre = .22f;

        FlickReader();
        ~FlickReader();
        FlickReader(FlickReader&&) noexcept;
        FlickReader& operator=(FlickReader&&) noexcept;

        /** Native's session load: fresh controls (PlayerControls::Load) on this bank. Error says why it failed. */
        bool SetBank(std::shared_ptr<const FlickBank> InBank, std::string& Error);
        bool HasBank() const { return Bank != nullptr; }
        const FlickBank* GetBank() const { return Bank.get(); }
        /** A mount, as GameplaySession::Activate does it: a fresh controller-input runtime, the controls stepped on a
         *  neutral pad (five ticks the first time, four after), then a fresh runtime again. The controls and their
         *  recognizers keep their history from ride to ride, as Native's do. */
        void Activate();

        /** One simulation tick on the canonical pad (the host's transfer bit is taken off, as GameplaySession::Tick
         *  does). bGoofy is the stance in effect (Native mirrors its mapping for a regular one); Group is where a trick
         *  would start (Square on the ground and in a manual; Tail or Nose out of those grinds); Difficulty is Native's
         *  physics mode (0 easy, 1 normal, 2 hardcore). Returns the trick recognised this tick. */
        Flick Update(const skate::XboxState& Pad, bool bGoofy, skate::GestureGroup Group, std::uint32_t Difficulty = 1);

        /** Native's step, which the controls run on. */
        float StepTime() const { return Bank ? Bank->StepTime : 0.f; }
        /** The last recognised trick's pop request. */
        const FlickEvent& Event() const { return Last; }
        /** Every recognizer's match this tick, in the manager's order. */
        const std::vector<FlickRecognition>& Recognitions() const { return Tick_; }
        /** The GestureSpeed published this tick, if any gesture was. */
        std::optional<float> GestureSpeed() const { return Speed; }
        /** This tick's action intents (PlayerControls::action_intents after the gestures' publication). */
        const skate::IntentMap& Intents() const;
        /** This tick's intentions before the gestures (PlayerControls::intents). */
        const std::vector<skate::ControllerIntent>& PreGestureIntents() const;
        /** The derived controller's 26 words (PlayerControls::controller). */
        const std::array<std::uint32_t, 26>& Words() const;
        /** The held Kickflip/Heelflip pattern (GestureInputPublication). */
        std::optional<std::string_view> HeldPattern() const;
        /** Native's conditioned right stick this tick (after the radial dead zone; y up). */
        float ConditionedX() const { return CX; }
        float ConditionedY() const { return CY; }

        /** Crouch for a pop: the stick held on the lower rim (an ollie's load) or upper rim (a nollie's). */
        bool Loaded() const { return OnRim && !Consumed && (StickY < .05f || StickY > .5f); }
        bool NoseLoaded() const { return OnRim && !Consumed && StickY > .5f; }
        float LoadTime() const { return Loaded() ? RimTime : 0.f; }
        /** The anticipation behind the last pop: how long Native's conditioned right stick had been out of its dead
         *  zone before the tick the trick was recognised (s). */
        float PopLoad() const { return Load; }
        /** The last pop's GestureSpeed: 1 for a gesture done within 1.75 ticks a pattern point, 0 from 4.4. */
        float PopGesture() const { return Last.Strength; }
        /** Native's Manual intention this tick (ProduceManual): the conditioned right stick's length, negative with it
         *  down (the tail), absent with its y centred. */
        std::optional<float> ManualIntent() const;
        float X() const { return StickX; }
        float Y() const { return StickY; }

    private:
        struct Owners;
        void Step(const skate::XboxState& Pad, std::uint32_t Difficulty);

        std::shared_ptr<const FlickBank> Bank;
        std::unique_ptr<Owners> O;      // Native's per-player owners: ControllerInputRuntime and PlayerControls
        std::vector<FlickRecognition> Tick_;
        std::optional<float> Speed;
        FlickEvent Last;
        std::uint32_t Serial = 0;
        float CX = 0, CY = 0;

        // The load.
        bool OnRim = false, Consumed = false;
        float RimTime = 0, WindTime = 0, Load = 0;
        float StickX = 0, StickY = 0;
    };
}
