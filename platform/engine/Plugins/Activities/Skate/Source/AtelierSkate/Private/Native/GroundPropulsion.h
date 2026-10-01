// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Braking.h"
#include "Push.h"
#include "Manual.h"
namespace atelier::skate
{
struct GroundPropulsionInput
{
    std::uint32_t flags_2468, flags_2472;
    float target_speed, signed_speed, absolute_body_speed, scalar_2660, timestep, brake_input;
    Vec3 push_direction, brake_direction;
    float surface_braking_factor;
};
struct GroundPropulsionSettings
{
    BrakeSettings braking;
    float maximum_pushable_speed;
    std::array<float, 2> mode_speed_changes;
};
struct PropulsionSubmission
{
    bool manual_correction;
    std::array<bool, 2> appended;
};
struct GroundPropulsion
{
    QueuedPointForce braking;
    PushAcceleration push;
    PropulsionSubmission Submit(const ManualEffect&, BoardForceQueue&) const;
};
GroundPropulsion CalculateGroundPropulsion(GroundPropulsionInput, GroundPropulsionSettings,
    std::uint8_t& push_suppressed_2730);
}
