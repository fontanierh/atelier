#pragma once
#include "ReckoningFrames.h"
#include "AirStateSettings.h"
namespace atelier::skate
{
// The retained wall-jump/animated-ground packet, before selector consumption.
struct GroundLaunchPhysical
{
    const ReckoningFrames& reckoning;
    Vec4 skeleton_vector_16208, skeleton_vector_16240;
    Vec4 board_position, physical_center_of_mass, velocity, angular_velocity;
    std::uint32_t flags_2468;
    float time_step;
};
struct GroundLaunchInfo
{
    Mat4 system=SkeletonIdentity, inverse_system=SkeletonIdentity;
    Vec4 velocity{}, angular_velocity{}, skeleton_vector_16208{}, skeleton_vector_16240{};
    Vec4 board_position{}, physical_center_of_mass{}, vector_224{}, vector_240{};
    float cone_angle_x=0, cone_angle_z=0, time_step=0;
    bool flag_269=false, wall_jump=false;
    std::uint16_t flags_270=0;
    AirLaunchInfo SelectorLaunch() const;
    void Fill(const GroundLaunchPhysical&,float cone_x,float cone_z);
    void WallJump(Vec4);
};
}
