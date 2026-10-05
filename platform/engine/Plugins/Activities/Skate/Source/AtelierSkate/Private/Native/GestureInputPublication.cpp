// SPDX-License-Identifier: Apache-2.0
#include "GestureInputPublication.h"
#include <algorithm>
#include <cmath>

namespace atelier::skate
{
namespace
{
bool AsciiEqual(std::string_view first,std::string_view second)
{
    if (first.size() != second.size()) return false;
    const auto lower = [](unsigned char c) { return c >= 'A' && c <= 'Z' ? static_cast<unsigned char>(c+32) : c; };
    for (std::size_t i = 0; i < first.size(); ++i)
        if (lower(static_cast<unsigned char>(first[i])) != lower(static_cast<unsigned char>(second[i]))) return false;
    return true;
}
}
bool GestureEventPermitted(std::string_view name,std::uint32_t flags,std::uint32_t state,const IntentMap& action)
{
    const auto bit = [&](unsigned index) { return (flags&(std::uint32_t{1}<<index)) != 0; };
    const auto member = [&](std::initializer_list<std::string_view> names)
    { return std::any_of(names.begin(),names.end(),[&](auto candidate) { return AsciiEqual(name,candidate); }); };
    if (bit(5) && member({"FingerFlip","FS_Varial","BS_Varial"})) return false;
    if (bit(4) && ((state == 200 || state == 201) || member({"L_F_Kickflip","L_B_Kickflip","L_F_Heelflip","L_B_Heelflip","L_FS_Shuvit","L_BS_Shuvit"}))) return false;
    if (member({"FrontFlip","BackFlip"}) &&
        (!(action.Contains("RightAirGrab") || action.Contains("LeftAirGrab")) || action.Contains("LeftPush") || action.Contains("RightPush") || bit(3))) return false;
    if (bit(8) && member({"SlideFs180","SlideBs180"})) return false;
    if (bit(12) && !member({"Ollie","Kickflip","Heelflip","Hardflip","InwardHeelflip","VarialKickflip","VarialHeelflip","PopShuvit","FSPopShuvit","360PopShuvit","FS360PopShuvit"})) return false;
    return true;
}
bool GestureInputPublication::Load(const SettingsDatabase& data,std::vector<GestureSet> bank,std::string& error)
{
    std::array<std::uint8_t,2> misses{};
    for (std::size_t stick = 0; stick < 2; ++stick)
    {
        const auto key = stick == 0 ? "left_stick" : "right_stick";
        const auto field = data.Field("recognizer",key,"NumTicksPatternNotInRangeBeforeCulling");
        if (!field) { error = "Missing recognizer culling field for "+std::string(key); return false; }
        if (field->type != "EA::Reflection::UInt8") { error = "Recognizer culling field must be UInt8"; return false; }
        // The original u8 hexadecimal reader accepts arbitrarily padded zeroes;
        // width alone must not reject a representable numeric UInt8 value.
        if (field->is_text || field->byte_count == 0 || field->words.empty() || field->words.back() > 255 ||
            std::any_of(field->words.begin(),field->words.end()-1,[](auto value) { return value != 0; }))
        { error = "Invalid recognizer UInt8 culling field for "+std::string(key); return false; }
        misses[stick] = static_cast<std::uint8_t>(field->words.back());
    }
    constexpr std::array<std::string_view,7> names{"main","rotated90","rotated_minus90","air","fingerflip","left","step"};
    constexpr std::array<std::uint32_t,7> sticks{1,1,1,1,1,0,0};
    if (bank.size() != names.size()) { error = "Gesture input requires all seven authored gesture sets"; return false; }
    std::vector<std::pair<std::uint32_t,GestureRecognizer>> recognizers;
    for (std::size_t i = 0; i < names.size(); ++i)
    {
        if (bank[i].name != names[i] || bank[i].stick != sticks[i] || !ValidGesturePatterns(bank[i].patterns))
        { error = "Invalid authored gesture set "+std::string(names[i]); return false; }
        recognizers.emplace_back(sticks[i],GestureRecognizer(std::move(bank[i].patterns)));
    }
    recognizers_ = std::move(recognizers); maximum_misses_ = authored_misses_ = misses; pace_ = 1.f;
    held_pattern_.reset(); trace_.clear(); return true;
}
void GestureInputPublication::Tune(float radius,float window,float pace)
{
    for (auto& entry : recognizers_) entry.second.ScaleRadius(radius);
    // A node's miss count wraps at 64, so the window stays below it.
    for (std::size_t i = 0; i < 2; ++i)
        maximum_misses_[i] = window == 1.f ? authored_misses_[i]
            : static_cast<std::uint8_t>(std::clamp(std::lround(authored_misses_[i] * window), 1l, 60l));
    pace_ = pace;
}
bool GestureInputPublication::Publish(std::array<StickPoint,2> axes,std::uint32_t difficulty,std::uint32_t flags,
    std::uint32_t state,IntentMap& action,std::string& error)
{
    if (recognizers_.size() != 7) { error = "Gesture input requires initialized authored recognizers"; return false; }
    for (auto& sample : axes)
    {
        sample[1] = -sample[1];
        for (auto& value : sample) if (std::abs(value) < 0.1f) value = 0;
    }
    bool held = false; std::vector<std::pair<std::string,float>> events; trace_.clear();
    for (const auto stick : {1u,0u})
    {
        // Every Held query on this stick precedes every Sample query.
        for (auto& entry : recognizers_) if (entry.first == stick)
            if (const auto pattern = entry.second.Held(axes[stick]))
                if (held_pattern_ && AsciiEqual(*held_pattern_,entry.second.Patterns()[*pattern].name)) held = true;
        for (auto& entry : recognizers_) if (entry.first == stick)
            if (const auto match = entry.second.Sample(axes[stick],{maximum_misses_[stick],difficulty,pace_}))
            {
                const auto& name = entry.second.Patterns()[match->pattern].name;
                if (name == "Kickflip" || name == "Heelflip" || name == "N_Kickflip" || name == "N_Heelflip") held_pattern_ = name;
                events.emplace_back(name,match->strength);
                trace_.push_back({static_cast<std::uint8_t>(&entry-recognizers_.data()),name,*match,false});
            }
    }
    if (held) action.Insert("HoldPattern",1);
    for (std::size_t i = 0; i < events.size(); ++i) if (GestureEventPermitted(events[i].first,flags,state,action))
    {
        action.Insert("Trick",1); action.Insert(events[i].first,1); action.Insert("GestureSpeed",events[i].second);
        trace_[i].permitted = true;
    }
    return true;
}
}
