#pragma once
#include "ForceQueue.h"
namespace atelier::skate
{
struct BrakeSettings { float input_force, override_force, minimum_speed; };
struct BrakeInput
{
    std::uint32_t flags_2468;
    float input_2728, signed_speed, absolute_body_speed, surface_factor;
    Vec3 direction;
};
QueuedPointForce CalculateBraking(BrakeInput, BrakeSettings);
struct LinearDragSettings { float brake_speed, balance_speed, comparison_threshold, balance_drag; };
struct LinearDragInput
{
    std::uint32_t flags_2468;
    float absolute_body_speed, balance_2720, scalar_2724, comparison_scalar;
};
float CalculateLinearDrag(LinearDragInput, LinearDragSettings);
}
