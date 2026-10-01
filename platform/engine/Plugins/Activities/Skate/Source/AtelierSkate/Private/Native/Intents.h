// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationName.h"
#include <array>
#include <functional>
#include <map>
#include <optional>
#include <string_view>
#include <utility>

namespace atelier::skate
{
class IntentMap
{
public:
    std::optional<float> Insert(std::string_view name, float value);
    const float* Get(std::string_view name) const;
    std::optional<float> Remove(std::string_view name);
    bool Contains(std::string_view name) const;
    void Clear() { values_.clear(); }
    std::size_t Size() const { return values_.size(); }
    bool Empty() const { return values_.empty(); }
    const std::map<IntentKey,float>& Entries() const { return values_; }
private:
    std::map<IntentKey,float> values_;
};
float ApplyIntentFilter(float value, std::uint32_t kind);
using Stance = std::pair<bool,bool>;
float FilterIntentChain(float value, std::array<std::uint32_t,4> filters, std::optional<Stance> stance);
struct IntentMutation
{
    enum class Kind { None, Remove, Set };
    Kind kind = Kind::None;
    float value = 0;
};
struct CreateMgIntent
{
    bool on_update = false;
    std::optional<float> default_value;
    float scale = 1;
    std::array<std::uint32_t,4> filters{};
    IntentMutation Emit(std::optional<float> action_value, std::optional<Stance> stance) const;
    IntentMutation Enter(bool& created_this_frame, std::optional<float> action_value, std::optional<Stance> stance) const;
    IntentMutation Update(bool& created_this_frame, std::optional<float> action_value, std::optional<Stance> stance) const;
    IntentMutation Exit() const { return {IntentMutation::Kind::Remove,0}; }
};
void AttachIntent(std::optional<float> value, bool set_skeleton,
    const std::function<void(float)>& packet, const std::function<void(float)>& skeleton);
struct MotionIntentFilterSettings
{
    float starting_value = 0, default_value = 0, scale = 1;
    std::array<std::uint32_t,4> filters{};
    std::optional<float> ramp_time;
    float blend_rising = 1, blend_falling = 1;
    std::optional<float> blend_out, clamp_velocity, clamp_acceleration;
};
struct MotionIntentFilterState
{
    float elapsed = 0, previous_delta = 0, value = 0;
    float Begin(const MotionIntentFilterSettings& settings);
    float Update(const MotionIntentFilterSettings& settings, std::optional<float> input, float dt, Stance stance);
};
// Constructor lookup uses encoded identity, including case and truncation aliases.
std::uint32_t IntentFilterKind(std::optional<std::string_view> name);
}
