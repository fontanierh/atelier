#pragma once
#include "WipeoutPhysicalState.h"
#include "WipeoutDrives.h"
#include "GeometryTypes.h"
namespace atelier::skate
{
struct WipeoutControlProfile
{
    Vec4 roll_axis{},horizontal_axis{},align_euler{};
    PointGraph<8> spin_vs_time;
    float direction_follow,torque_velocity,torque_distance,spin_inertia;
    bool roll_on_ground;float ground_roll_torque,sideways_spin,forward_spin;
    bool horizontal_directed;float drift_maximum_speed,drift_forward,drift_sideways;
    bool align_with_velocity,align_ground_with_velocity;
    float ground_align_torque,tilt_degrees,drift_drag;
    static bool Load(const SettingsDatabase&,std::string_view key,WipeoutControlProfile&,std::string&);
};
struct WipeoutPhysicalSettings
{
    WipeoutRecoverySettings recovery;
    float remove_target_time,remove_drives_time,controlled_weight_step,collision_weight_step;
    float board_restitution,board_friction,deck_angular_drag,push_force;
    std::array<ContactMaterial,3> standard_materials;
    static bool Load(const SettingsDatabase&,WipeoutPhysicalSettings&,std::string&);
};
}
