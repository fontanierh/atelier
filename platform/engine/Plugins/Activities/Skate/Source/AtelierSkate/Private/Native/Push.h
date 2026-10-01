// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ForceQueue.h"
namespace atelier::skate
{
struct PushInput
{
    std::uint32_t flags_2468, flags_2472;
    float target_speed, current_speed, absolute_body_speed, scale, delta_seconds;
    Vec3 direction;
};
struct PushLimits { float maximum_pushable_speed, low_speed_change, high_speed_change; };
struct PushAcceleration { Vec3 vector{}, local_point{}; bool suppressed = false; };
PushAcceleration CalculatePushAcceleration(PushInput, PushLimits);
PushAcceleration EnqueuePush(PushInput, PushLimits, const std::vector<float>& inverse_masses, BoardForceQueue&);
}
