#pragma once
#include "BoardContactFeedback.h"
#include "BoardGroundAngle.h"
#include "BoardRuntime.h"
#include <optional>
namespace atelier::skate
{
inline constexpr float WheelLineLength=0.2f;
struct WheelLine {Vec3 start,end;};
std::array<WheelLine,4> WheelLines(const BoardRuntime&,Vec3 reckoning_up);
struct WheelLineHit {float fraction;Vec3 normal;std::uint32_t surface_tag;};
struct WheelLineState
{
    std::array<Vec3,4> normals{{{0,1,0},{0,1,0},{0,1,0},{0,1,0}}};
    std::array<float,4> distances{};
    std::array<std::uint32_t,4> physics_surfaces{};
    // The low 7 bits of each hit's packed surface: the game's sound surface (0 none).
    std::array<std::uint32_t,4> sound_surfaces{};
    float minimum_distance=0;
    void Publish(const std::array<std::optional<WheelLineHit>,4>&);
};
struct PartGroundContact
{
    bool in_contact=false;
    Vec3 normal{0,1,0},point{},relative_velocity{};
};
struct BoardGroundState
{
    std::array<PartGroundContact,BoardBodyCount> parts{};
    std::array<Vec3,BoardBodyCount> previous_velocities{},accelerations{};
    Vec3 closing_velocity{};
    float maximum_closing_speed=0,opposing_contact=0,surface_twelve_height=0;
    std::uint32_t collision_flags=0;
    Vec3 overall_normal{0,1,0},wheel_normal{0,1,0};
    std::array<bool,4> valid_wheel_normals{};
    std::uint8_t part_contact_count=0,wheel_contact_count=0;
    float time_without_wheel_contact=0;
    std::array<float,4> wheel_angular_drag{};
    void SampleAccelerations(const std::array<Vec3,BoardBodyCount>&,float time_step);
    void AdvanceContactTime(float time_step);
    void Update(const std::vector<BoardContactReport>&,const WheelLineState&,Vec3 reckoning_up,
        float maximum_ground_angle_degrees,bool board_wiping_out);
};
}
