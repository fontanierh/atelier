#pragma once
#include "ForceQueue.h"
namespace atelier::skate
{
struct WallRideSettings
{
    PointGraph<8> anti_gravity_vs_time;
    float max_dot_floor_wall, foot_force_time, auto_jump_height, max_time;
    float velocity_time_to_consider, auto_jump_y_down_scalar, auto_jump_force;
};
struct WallRidePhysical
{
    Vec4 board_normal, up, velocity;
    float board_mass, gravity, speed;
    std::int32_t contact_count;
};
struct GroundContactFrame
{
    Vec4 vector_8032{}, vector_8048{}, vector_8064{};
    std::uint32_t word_8080 = 0;
    bool flag_8084 = false;
    float scalar_2752 = 0, scalar_2756 = 0;
};
struct GroundContactResponse
{
    bool active_2731 = false;
    QueuedPointForce tag_16_force{16, {}, {}};
    Vec4 vector_2688{};
    float scalar_2704 = 0;
    bool animated_board_2708 = false;
};
GroundContactResponse CalculateWallRideResponse(const WallRideSettings&, WallRidePhysical,
    GroundContactFrame, Vec4 previous_velocity);
}
