// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "InputIntentions.h"
#include "MotionFrame.h"
namespace atelier::skate
{
struct AnimationCrouchingPhysical
{
    float body_84,body_164,body_188,force_516,ground_force_520;
    float minimum_crouch_528,deck_angle_532,animation_height_72;
};
struct AnimationBodyTiltPhysical {float lateral_tilt,body_spin_speed;std::uint32_t filtered_category;};
struct AnimationFakiePhysical
{
    std::uint32_t category,grind_state;
    bool doing_trick;
    Vec4 board_axis,deck_velocity,external_velocity;
    float ground_projected_speed;
};
struct AnimationPhysicalFeedback
{
    SetTurningPhysical turning;
    AnimationCrouchingPhysical crouching;
    float pumping_acceleration;
    Vec4 ground_acceleration;
    bool bumped;
    std::array<float,8> conditioned_turn;
};
// These are preceding completed simulation publications. There is no neutral
// constructor: callers provide the actual producer record and its absence.
struct AnimationPhysical
{
    GraphConditionInputs conditions;
    AnimationPhysicalFeedback feedback;
    AnimationBodyTiltPhysical body_tilt;
    AnimationFakiePhysical fakie;
    std::pair<bool,bool> physical_stance;
    MotionGraphFootFrame foot_frame;
    bool board_present,physical_28_byte75;
    float time_since_teleport;
};
}
