// SPDX-License-Identifier: Apache-2.0
#include "GroundPropulsion.h"
namespace atelier::skate
{
GroundPropulsion CalculateGroundPropulsion(GroundPropulsionInput input, GroundPropulsionSettings settings,
    std::uint8_t& suppressed)
{
    const auto braking = CalculateBraking({input.flags_2468, input.brake_input, input.signed_speed,
        input.absolute_body_speed, input.surface_braking_factor, input.brake_direction}, settings.braking);
    const auto push = CalculatePushAcceleration({input.flags_2468, input.flags_2472, input.target_speed,
        input.signed_speed, input.absolute_body_speed, input.scalar_2660, input.timestep, input.push_direction},
        {settings.maximum_pushable_speed, settings.mode_speed_changes[0], settings.mode_speed_changes[1]});
    suppressed = std::uint8_t(push.suppressed); return {braking, push};
}
PropulsionSubmission GroundPropulsion::Submit(const ManualEffect& manual, BoardForceQueue& queue) const
{
    const auto force = manual.corrective_force_world, point = manual.corrective_point_body;
    if (manual.correction_active)
        return {true, {{queue.Append({7, {force[0], force[1], force[2]}, {point[0], point[1], point[2]}}), false}}};
    const bool brake = queue.Append(braking);
    const bool pushed = queue.Append({3, push.vector, push.local_point});
    return {false, {{brake, pushed}}};
}
}
