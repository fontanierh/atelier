#include "Push.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
PushAcceleration CalculatePushAcceleration(PushInput input, PushLimits limits)
{
    if (!(input.flags_2468 & 0x02000000u)) return {};
    if (input.flags_2472 & 0x200u) return {{}, {}, true};
    const float gap = input.target_speed - input.current_speed;
    float change = gap > 0.0f ? gap : 0.0f;
    const float ratio = input.current_speed / limits.maximum_pushable_speed;
    const float low = -ratio >= 0.0f ? 0.0f : ratio;
    const float fraction = 1.0f - low >= 0.0f ? low : 1.0f;
    const float limit = std::fma(1.0f - fraction, limits.low_speed_change, fraction * limits.high_speed_change);
    const bool below = change < -limit;
    if (change > limit) change = limit;
    if (below) change = -limit;
    if (input.absolute_body_speed + change > limits.maximum_pushable_speed)
    {
        const float remaining = limits.maximum_pushable_speed - input.absolute_body_speed;
        change = remaining >= 0.0f ? remaining : 0.0f;
    }
    const float force = (input.scale * change) / input.delta_seconds;
    return {Scale(input.direction, force), {}, false};
}
PushAcceleration EnqueuePush(PushInput input, PushLimits limits,
    const std::vector<float>& inverse_masses, BoardForceQueue& queue)
{
    input.scale = TotalBodyMass(inverse_masses);
    const auto result = CalculatePushAcceleration(input, limits);
    queue.Append({3, result.vector, result.local_point}); return result;
}
}
