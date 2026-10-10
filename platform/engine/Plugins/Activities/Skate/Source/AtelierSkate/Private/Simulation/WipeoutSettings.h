#pragma once
#include "StockSettingsReader.h"
namespace atelier::skate
{
struct WipeoutFrame
{
    std::uint32_t flags_2468{};
    std::uint32_t flags_2472{};
    std::uint32_t flags_2476{};
    std::uint32_t flags_2480{};
    std::uint32_t flags_2484{};
    std::uint32_t category{};
    float timestep{};
    float time_on_ground{};
    float speed{};
    Vec4 animation_up{};
    float landing_angle{};
    Vec4 deck_velocity{};
    Vec4 com_velocity{};
    std::int32_t jump_fix_frames{};
    Mat4 deck{};
    Mat4 input_board{};
    Mat4 world_to_animation{};
    Vec4 closing_velocity{};
    std::uint32_t board_material_flags{};
    bool board_contact{};
    bool wheel_contact{};
    Vec4 board_contact_normal{};
    float opposing_contact{};
    std::array<float,8> regions_force{};
    float maximum_skater_force{};
    float vehicle_force{};
    bool group_8{};
    bool conflicting{};
    bool compliant{};
    Vec4 highest_normal{};
    Vec4 pose_error{};
    float maximum_pose_error{};
    bool flip_active{};
    float flip_requested_speed{};
    float system_up_y{};
    bool grind_selected{};
    bool grind_normal_valid{};
    Vec4 grind_normal{};
};
struct WipeoutMode
{
    bool check_squash{};
    bool check_bad_landing{};
    float ground_xz{};
    float bad_landing_scale{};
};
struct WipeoutGroundSettings
{
    float vehicle_scalar{};
    float vehicle_contact{};
    float skitch_contact{};
    float skitch_scalar{};
    float skitch_arms_scalar{};
    float skater_scalar{};
    float max_squash{};
    float max_squash_coffin{};
    float max_displacement{};
    float max_contact{};
    float max_arm_contact{};
    float max_deck_error{};
    float opposing_contact{};
    float y_acceleration{};
    float light_dmo_scalar{};
    float player_scalar{};
    float ai_scalar{};
    float skitch_acc_scalar{};
    float balance_total{};
    float balance_min_speed{};
    float balance_base{};
};
struct WipeoutAirSettings
{
    float xz_trick{};
    float y_trick{};
    float xz_acceleration{};
    float y_acceleration{};
    float max_squash{};
    float max_displacement{};
    float max_contact{};
    float max_arm_contact{};
    float body_flip_scalar{};
    float body_flip_acc_scalar{};
    float light_dmo_scalar{};
    std::int32_t ignore_danger_frames{};
    float max_landing_speed{};
    float max_stairs_speed{};
    float max_grind_speed{};
    PointGraph<8> max_landing_angle{};
};
struct WipeoutSettings
{
    WipeoutGroundSettings ground{};
    WipeoutAirSettings air{};
    float lean_contact_y{};
};
bool LoadWipeoutSettings(const SettingsDatabase&,WipeoutSettings&,std::array<WipeoutMode,5>&,std::string& error);
}
