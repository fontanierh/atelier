// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Gestures.h"
#include "Intents.h"
#include "Settings.h"

namespace atelier::skate
{
bool GestureEventPermitted(std::string_view name,std::uint32_t flags,std::uint32_t physical_state,const IntentMap& action);
class GestureInputPublication
{
public:
    // The bank contains the seven native gesture sets in authored manager order.
    bool Load(const SettingsDatabase&,std::vector<GestureSet> bank,std::string& error);
    bool Publish(std::array<StickPoint,2> axes,std::uint32_t difficulty,std::uint32_t flags,
        std::uint32_t physical_state,IntentMap& action,std::string& error);
    std::optional<std::string_view> HeldPattern() const
    { return held_pattern_ ? std::optional<std::string_view>(*held_pattern_) : std::nullopt; }
private:
    std::vector<std::pair<std::uint32_t,GestureRecognizer>> recognizers_;
    std::array<std::uint8_t,2> maximum_misses_{};
    std::optional<std::string> held_pattern_;
};
}
