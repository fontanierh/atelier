// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GroundState.h"
#include <optional>
namespace atelier::skate
{
struct GroundOutputFrame
{
    Vec4 axis_464,velocity_608;
    float absolute_body_speed_2616,deck_speed_2652,state_timer_2664,scalar_2720;
    std::uint32_t flags_2476,flags_2484;
    bool selected_mode_flag_109;
};
struct GroundOutputSettings
{
    std::array<float,2> pushable_speed_terms_4_8;
    float mode_speed_threshold_0;
};
struct GroundSkateboardMotionOutput {bool is_push_accelerating,is_at_pushable_speed;};
struct GroundVelocityProjectionOutput {Vec4 velocity_without_axis_component;bool active;};
struct GroundRecordOutput
{
    bool wall_ride_exit,anti_flip_nudge_present,is_pinning;
    Vec4 anti_flip_torque;
    float time_to_skitch,skitch_spline_height,processed_scalar_2720;
    bool processed_flag_2484_bit_13;
};
struct GroundStateRecordOutput
{
    std::uint32_t grab_spline_type,grab_spline_object_id;
    bool flag_84,has_world_grab_intent_without_object;
    std::optional<bool> manual_correction_write_78;
};
struct GroundIntentRecordOutput {bool has_world_grab_intent,selected_mode_below_speed_threshold_58;};
struct PhysicsGroundOutput
{
    GroundSkateboardMotionOutput skateboard_motion_4;
    std::optional<GroundVelocityProjectionOutput> velocity_projection_36;
    GroundRecordOutput ground_32;
    GroundStateRecordOutput state_28;
    GroundIntentRecordOutput intents_52;
    bool is_grabbing_object_72_304,manual_opposition_56_168,push_suppressed_20_596;
};
PhysicsGroundOutput FillGroundPhysicsOutput(const PhysicsGroundState&,GroundOutputFrame,GroundOutputSettings);
}
