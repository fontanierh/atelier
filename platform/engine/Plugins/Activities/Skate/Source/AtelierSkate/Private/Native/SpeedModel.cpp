// SPDX-License-Identifier: Apache-2.0
#include "SpeedModel.h"
#include <algorithm>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) { float value; std::memcpy(&value, &word, 4); return value; }
float Clamp(float value, float low, float high)
{
    const float v = low - value >= 0.0f ? low : value;
    return high - v >= 0.0f ? v : high;
}
Vec4 SafeNormal(Vec4 vector, Vec4 threshold)
{
    const float squared = Dot3(vector, vector), inverse = InverseLengthSquared(squared, 2);
    const float length = squared == 0.0f ? 0.0f : squared * inverse;
    for (std::size_t i = 0; i < 4; ++i) vector[i] = length > threshold[i] ? vector[i] * inverse : 0.0f;
    return vector;
}
}
std::array<float, 8> UpdateSpeedModel(SpeedModelState& state, const SpeedModelSettings& settings,
    const SpeedModelInput& input)
{
    const float speed = std::abs(input.signed_speed), dt = input.timestep, bound = settings.speed_error_bound;
    const float low = speed - bound, lower = -low >= 0.0f ? 0.0f : low;
    float target;
    if (state.flags_1360 & 0x80000000u) { state.flags_1360 &= 0x7fffffffu; target = speed; }
    else target = Clamp(state.target_speed, lower, bound + speed);
    const float coffin = input.flags_2476 & 0x40000000u ? settings.coffin_acceleration * dt : 0.0f;
    const float projection = Dot3(input.velocity_416, input.effective_forward);
    Vec4 projected; for (std::size_t i = 0; i < 4; ++i) projected[i] = input.effective_forward[i] * projection;
    const float normal_speed = Dot3(projected, input.normal_464);
    Vec4 delta; for (std::size_t i = 0; i < 4; ++i) delta[i] = projected[i] - input.normal_464[i] * normal_speed;
    const auto tangent = SafeNormal(delta, settings.normal_threshold);
    const float gravity = Clamp(-tangent[1] * settings.gravity,
        -settings.maximum_gravity_acceleration, settings.maximum_gravity_acceleration) * dt;
    if (input.frames_2580 < 30)
    {
        const float active = input.manual_state_276 == 0.0f ? 0.0f : 1.0f;
        float direction = input.balance > 0.0f ? 1.0f : -1.0f;
        if (0.0f > Dot3(input.vector_352, tangent)) direction *= -1.0f;
        const float angle = std::abs(input.angle_2652);
        const float within = angle > settings.manual_angle_limit ? 0.0f : 1.0f;
        const float negative = angle > settings.negative_manual_angle_limit ? 0.0f : 1.0f;
        float acceleration = ((((input.turn_2672 * input.turn_2672) * settings.manual_acceleration) * within) * direction) * active;
        if (acceleration < 0.0f) acceleration *= negative;
        target = acceleration + target;
    }
    const float friction = -settings.surface_friction.Evaluate(input.surface_speed) * dt;
    const float surface_delta = gravity > 0.0f ? friction + gravity : friction - gravity >= 0.0f ? gravity : friction;
    target = (surface_delta + coffin) + target;
    if (input.elapsed_without_input > settings.no_input_delay)
        target = -std::fma(settings.no_input_friction.Evaluate(input.surface_speed), dt, -target);
    if (input.balance != 0.0f) target = -std::fma(settings.manual_friction.Evaluate(input.surface_speed), dt, -target);
    state.target_speed = target >= 0.0f ? target : 0.0f;
    float error = Clamp(state.target_speed - speed, -bound, bound);
    if (settings.override_enabled && (input.flags_2476 & 0x00400000u) && input.normal_464[1] > .65f)
    {
        float goal = settings.override_speed * Float(0x3e8e38e4);
        const float along = Dot3(input.velocity_416, input.vector_160);
        if (std::all_of(settings.override_direction_threshold.begin(), settings.override_direction_threshold.end(),
            [&](float threshold) { return threshold > along; }) && 1.0f > input.surface_speed) goal *= -1.0f;
        error = Clamp(goal - speed, -.4f, .4f);
    }
    const bool enabled = !(input.flags_2468 & 0x62010000u) && !(input.flags_2476 & 0x08000000u) && input.wheel_contact_count >= 2;
    const float gain = !enabled ? 0.0f : error < 0.0f ? settings.negative_gain : settings.positive_gain;
    const float scalar = ((input.mass * gain) * error) / dt;
    const bool forward = Dot3(input.effective_forward, tangent) > 0.0f;
    std::array<float, 8> output{};
    for (std::size_t i = 0; i < 4; ++i) output[i] = (forward ? input.effective_forward[i] : -input.effective_forward[i]) * scalar;
    return output;
}
}
