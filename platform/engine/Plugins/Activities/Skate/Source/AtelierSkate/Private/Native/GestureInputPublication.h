#pragma once
#include "Gestures.h"
#include "Intents.h"
#include "Settings.h"

namespace atelier::skate
{
bool GestureEventPermitted(std::string_view name,std::uint32_t flags,std::uint32_t physical_state,const IntentMap& action);
// One recognizer's match in the last Publish, in manager order (the right stick's sets, then the left's). An
// observation for hosts (Ride's pop request); Publish never reads it back.
struct GestureEventTrace
{
    std::uint8_t set=0;              // authored set: main, rotated90, rotated_minus90, air, fingerflip, left, step
    std::string name;                // the pattern's name
    GestureRecognition recognition{};
    bool permitted=false;            // GestureEventPermitted: published into the action intents
};
class GestureInputPublication
{
public:
    // The bank contains the seven native gesture sets in authored manager order.
    bool Load(const SettingsDatabase&,std::vector<GestureSet> bank,std::string& error);
    bool Publish(std::array<StickPoint,2> axes,std::uint32_t difficulty,std::uint32_t flags,
        std::uint32_t physical_state,IntentMap& action,std::string& error);
    // One tick at 120 Hz (Tune's samples_per_tick 2): the sticks half a tick ago (null without a reading between
    // frames), then now. Held queries read `now` only, before either sample, as the 60 Hz Publish reads its one
    // sample; each recognizer publishes the tick's match (GestureRecognizer::SampleTick).
    bool PublishFine(const std::array<StickPoint,2>* half,std::array<StickPoint,2> now,std::uint32_t difficulty,
        std::uint32_t flags,std::uint32_t physical_state,IntentMap& action,std::string& error);
    std::optional<std::string_view> HeldPattern() const
    { return held_pattern_ ? std::optional<std::string_view>(*held_pattern_) : std::nullopt; }
    const std::vector<GestureEventTrace>& LastEvents() const { return trace_; }
    // The player's flick feel (FeelTuning): pattern radius, the ticks a flick may stray before it is dropped, and
    // pace, each a scale on the authored values (1 restores them), tight flicks (FeelTuning::tight_flicks), and the
    // stick samples per tick (FeelTuning::flick_120hz: 1 the authored 60 Hz, 2 for 120 Hz). At 120 Hz the window
    // counts twice the samples, so a flick may stray for the same time.
    void Tune(float radius,float window,float pace,bool tight_flicks=false,std::uint8_t samples_per_tick=1);
    std::uint8_t SamplesPerTick() const { return samples_per_tick_; }
private:
    std::vector<std::pair<std::uint32_t,GestureRecognizer>> recognizers_;
    std::array<std::uint8_t,2> maximum_misses_{},authored_misses_{};
    float pace_=1.f;
    std::uint8_t samples_per_tick_=1;
    bool Publish(bool fine,const std::array<StickPoint,2>* half,std::array<StickPoint,2> now,std::uint32_t difficulty,
        std::uint32_t flags,std::uint32_t physical_state,IntentMap& action,std::string& error);
    bool tight_flicks_=false;
    std::optional<std::string> held_pattern_;
    std::vector<GestureEventTrace> trace_;
};
}
