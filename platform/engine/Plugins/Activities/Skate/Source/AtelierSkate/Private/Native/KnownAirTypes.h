// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct KnownAirTrajectory
{
    Vec4 position{};
    Vec4 velocity{};
    Vec4 acceleration{};
    float scalar_48{};
    std::uint32_t word_52{};
    std::uint32_t word_56{};
    std::uint32_t word_60{};
};
struct KnownAirPrediction
{
    KnownAirTrajectory trajectory{};
    float collision_time_48{};
    std::int32_t collision_frame_128{};
};
struct KnownAirState
{
    Vec4 landing_normal_64{};
    Vec4 landing_heading_80{};
    Vec4 trajectory_apex_96{};
    Vec4 collision_position_112{};
    Vec4 selector_vector_128{};
    Vec4 trajectory_follow_offset_144{};
    Vec4 target_com_position_160{};
    float collision_normal_speed_176{};
    float time_in_state_180{};
    float start_y_184{};
    float max_y_188{};
    float com_max_y_192{};
    float collision_time_196{};
    float time_to_apex_200{};
    float body_flip_target_speed_204{};
    bool reached_apex_208{};
    bool landing_heading_valid_209{};
    bool start_flipped_210{};
    bool body_flipping_211{};
    bool grind_air_adjust_activated_212{};
    bool targeting_grind_213{};
    std::int32_t trajectory_index_216{};
};
struct KnownAirFrame
{
    Vec4 start_flip_reference_96{};
    Vec4 alternate_head_target_112{};
    Vec4 velocity_400{};
    Vec4 ground_normal_464{};
    float start_height_484{};
    Vec4 skater_up_544{};
    std::uint32_t flags_2468{};
    std::uint32_t flags_2472{};
    std::uint32_t flags_2476{};
    std::uint32_t flags_2480{};
    std::uint32_t flags_2484{};
    std::uint32_t flags_2488{};
    std::int32_t next_physics_state_2500{};
    float delta_time_2604{};
    float forward_speed_2612{};
    float body_spin_input_2640{};
    Vec4 selector_landing_normal_2656{};
};
struct KnownAirSettings
{
    PointGraph<8> max_heading_adjust_vs_up_y_160{};
    PointGraph<8> landing_speed_scalar_vs_ground_normal_y_240{};
    PointGraph<8> flip_start_collision_time_vs_normal_y{};
    float trajectory_error_blend_away_time_384{};
    float min_target_heading_velocity_420{};
    float min_auto_body_speed_424{};
    float max_spin_speed_428{};
    float frames_for_grind_air_assist_436{};
    float body_flip_min_grab_time_fraction_456{};
    float flip_scalar{};
};
struct KnownAirModeSettings
{
    bool upside_down_falling_wipeout_enabled_2{};
    bool perfect_body_flips_28{};
    float body_spin_speed_limit_56{};
};
struct KnownAirWipeoutSettings
{
    float air_falling_min_up_y_260{};
    float air_falling_max_angle_264{};
};
struct KnownAirReckoningFields
{
    Vec4 landing_normal_1152{};
    Vec4 heading_axis_1200{};
    float body_spin_angle_1568{};
    float body_spin_speed_1572{};
};
struct KnownAirWipeoutRequest
{
    bool requested_35{};
    float scalar_116{};
    std::uint32_t counter_200{};
};
struct RestoreVelocityGeometry
{
    Vec4 tangential_velocity{};
    float landing_speed_curve_input{};
    float landing_speed_blend_source{};
};
struct KnownAirOutput
{
    Vec4 trajectory_apex_0{};
    Vec4 collision_position_16{};
    Vec4 landing_normal_32{};
    Vec4 selector_vector_48{};
    Vec4 trajectory_position_64{};
    Vec4 landing_heading_80{};
    Vec4 selector_com_position_96{};
    Vec4 landing_normal_copy_144{};
    Vec4 locked_trajectory_velocity_160{};
    float time_in_state_176{};
    float collision_time_180{};
    float time_until_collision_184{};
    float collision_normal_speed_188{};
    float time_to_apex_196{};
    float jump_height_200{};
    std::int32_t trajectory_index_220{};
    KnownAirTrajectory selected_trajectory_240{};
    std::array<float,25> trajectory_plane_samples_336{};
    bool reached_apex_436{};
    bool known_air_valid_437{};
    bool locked_trajectory_velocity_valid_452{};
};
}
