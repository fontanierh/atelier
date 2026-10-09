#pragma once
#include "SimulationMath.h"
namespace atelier::skate
{
struct SpeedModelSettings
{
    float negative_gain, maximum_gravity_acceleration, gravity, positive_gain, coffin_acceleration;
    float speed_error_bound;
    PointGraph<8> surface_friction;
    float manual_acceleration, negative_manual_angle_limit, manual_angle_limit, no_input_delay;
    PointGraph<8> no_input_friction, manual_friction;
    bool override_enabled;
    float override_speed;
    Vec4 normal_threshold, override_direction_threshold;
};
struct SpeedModelState { float target_speed; std::uint32_t flags_1360; };
struct SpeedModelInput
{
    std::uint32_t flags_2468, flags_2476;
    std::int32_t wheel_contact_count, frames_2580;
    float timestep, signed_speed, angle_2652, surface_speed, turn_2672, balance;
    float elapsed_without_input, manual_state_276;
    Vec4 vector_160, vector_352, velocity_416, normal_464, effective_forward;
    float mass;
};
std::array<float, 8> UpdateSpeedModel(SpeedModelState&, const SpeedModelSettings&, const SpeedModelInput&);
}
