// SPDX-License-Identifier: Apache-2.0
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
    std::optional<std::string_view> HeldPattern() const
    { return held_pattern_ ? std::optional<std::string_view>(*held_pattern_) : std::nullopt; }
    const std::vector<GestureEventTrace>& LastEvents() const { return trace_; }
    // The player's flick feel (FeelTuning): pattern radius, the ticks a flick may stray before it is dropped, and
    // pace, each a scale on the authored values (1 restores them), and tight flicks (FeelTuning::tight_flicks).
    void Tune(float radius,float window,float pace,bool tight_flicks=false);
private:
    std::vector<std::pair<std::uint32_t,GestureRecognizer>> recognizers_;
    std::array<std::uint8_t,2> maximum_misses_{},authored_misses_{};
    float pace_=1.f;
    bool tight_flicks_=false;
    std::optional<std::string> held_pattern_;
    std::vector<GestureEventTrace> trace_;
};
}
