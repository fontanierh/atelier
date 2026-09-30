// SPDX-License-Identifier: Apache-2.0
#include "Intents.h"
#include <cmath>
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
std::uint32_t Bits(float value) { std::uint32_t bits; std::memcpy(&bits,&value,4); return bits; }
std::int32_t SignedBits(float value) { const auto bits = Bits(value); std::int32_t out; std::memcpy(&out,&bits,4); return out; }
float LimitDelta(float value, float lower, float upper)
{
    const auto selected = lower-value >= 0 ? lower : value;
    return upper-selected >= 0 ? selected : upper;
}
float Ramp(float elapsed, float time)
{
    const std::array<float,2> keys{0,time};
    std::size_t begin = 0, count = 2;
    while (count != 0)
    {
        const auto step = count / 2, middle = begin + step;
        if (SignedBits(keys[middle]) < SignedBits(elapsed)) { begin = middle+1; count -= step+1; }
        else count = step;
    }
    if (begin == 0) return 0;
    if (begin == 2) return 1;
    return std::fma((1.0f-0.0f)/(time-0.0f),elapsed-0.0f,0.0f);
}
}
std::optional<float> IntentMap::Insert(std::string_view name, float value)
{
    const auto key = EncodeIntentKey(name);
    const auto found = values_.find(key);
    const auto previous = found == values_.end() ? std::nullopt : std::optional<float>(found->second);
    values_[key] = value;
    return previous;
}
const float* IntentMap::Get(std::string_view name) const
{
    const auto found = values_.find(EncodeIntentKey(name));
    return found == values_.end() ? nullptr : &found->second;
}
std::optional<float> IntentMap::Remove(std::string_view name)
{
    const auto found = values_.find(EncodeIntentKey(name));
    if (found == values_.end()) return std::nullopt;
    const auto value = found->second;
    values_.erase(found);
    return value;
}
bool IntentMap::Contains(std::string_view name) const { return Get(name) != nullptr; }
float ApplyIntentFilter(float value, std::uint32_t kind)
{
    const auto pi = Float(0x40490fdb), half_pi = Float(0x3fc90fdb);
    switch (kind)
    {
    case 0: return value;
    case 1: return value * -1.0f;
    case 2: return std::abs(value);
    case 3: return value >= 0 ? 1.0f-value : -1.0f-value;
    case 4: { const auto lower = -value >= 0 ? 0.0f : value; return 1.0f-lower >= 0 ? lower : 1.0f; }
    case 5: return value >= 0 ? pi-value : -pi-value;
    case 6: { const auto rotated = value-half_pi; return rotated < -pi ? rotated+Float(0x40c90fdb) : rotated; }
    default: { const auto rotated = value+half_pi; return rotated > pi ? rotated-Float(0x40c90fdb) : rotated; }
    }
}
float FilterIntentChain(float value, std::array<std::uint32_t,4> filters, std::optional<Stance> stance)
{
    if (stance)
    {
        const std::array<bool,4> enabled{true,true,stance->first,stance->second};
        for (std::size_t i = 0; i < 4; ++i)
            if (enabled[i] && filters[i] <= 7) value = ApplyIntentFilter(value,filters[i]);
    }
    return value;
}
IntentMutation CreateMgIntent::Emit(std::optional<float> action_value, std::optional<Stance> stance) const
{
    const auto found = action_value ? action_value : default_value;
    if (!found) return {IntentMutation::Kind::Remove,0};
    return {IntentMutation::Kind::Set,FilterIntentChain(scale * *found,filters,stance)};
}
IntentMutation CreateMgIntent::Enter(bool& created, std::optional<float> value, std::optional<Stance> stance) const
{
    const auto result = Emit(value,stance); created = true; return result;
}
IntentMutation CreateMgIntent::Update(bool& created, std::optional<float> value, std::optional<Stance> stance) const
{
    const auto result = on_update ? Emit(value,stance) : !created ? Exit() : IntentMutation{};
    created = false; return result;
}
void AttachIntent(std::optional<float> value, bool set_skeleton,
    const std::function<void(float)>& packet, const std::function<void(float)>& skeleton)
{
    if (value) { packet(*value); if (set_skeleton) skeleton(*value); }
}
float MotionIntentFilterState::Begin(const MotionIntentFilterSettings& settings)
{
    elapsed = 0; previous_delta = 0; value = settings.starting_value; return value;
}
float MotionIntentFilterState::Update(const MotionIntentFilterSettings& s, std::optional<float> input, float dt, Stance stance)
{
    elapsed += dt;
    const auto target = FilterIntentChain(s.scale * input.value_or(s.default_value),s.filters,stance);
    auto blend = target < value ? s.blend_falling : s.blend_rising;
    if (input) { if (s.ramp_time) blend = Ramp(elapsed,*s.ramp_time) * blend; }
    else if (s.blend_out) blend = *s.blend_out;
    const auto weighted_target = blend * target;
    const auto candidate = std::fma(1.0f-blend,value,weighted_target);
    auto delta = candidate-value;
    if (s.clamp_acceleration) delta = LimitDelta(delta,previous_delta-*s.clamp_acceleration,previous_delta+*s.clamp_acceleration);
    if (s.clamp_velocity) delta = LimitDelta(delta,-*s.clamp_velocity,*s.clamp_velocity);
    previous_delta = delta; value = delta+value; return value;
}
std::uint32_t IntentFilterKind(std::optional<std::string_view> name)
{
    const auto key = EncodeIntentKey(name.value_or("none"));
    const std::array<std::string_view,7> names{"negate","abs","oneMinus","clamp","angleFlip","angleRot90","angleRotN90"};
    for (std::size_t i = 0; i < names.size(); ++i) if (EncodeIntentKey(names[i]) == key) return std::uint32_t(i)+1;
    return 0;
}
}
