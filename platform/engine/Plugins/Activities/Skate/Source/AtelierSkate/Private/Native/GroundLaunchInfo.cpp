// SPDX-License-Identifier: Apache-2.0
#include "GroundLaunchInfo.h"
namespace atelier::skate
{
AirLaunchInfo GroundLaunchInfo::SelectorLaunch() const
{
    AirLaunchInfo info;
    info.reckoning_transform=system;
    info.reckoning_inverse=inverse_system;
    info.start_velocity=velocity;
    info.com_velocity=angular_velocity;
    info.skeleton_vector_160=skeleton_vector_16208;
    info.skeleton_vector_176=skeleton_vector_16240;
    info.board_position=board_position;
    info.animation_com_position=physical_center_of_mass;
    info.start_position_override=vector_224;
    info.board_position_override=vector_240;
    info.cone_angle_x=cone_angle_x;
    info.cone_angle_z=cone_angle_z;
    info.timestep=time_step;
    info.player_jumped=wall_jump;
    info.use_position_override=flag_269;
    info.trajectory_count=flags_270;
    return info;
}
void GroundLaunchInfo::Fill(const GroundLaunchPhysical& p,float cone_x,float cone_z)
{
    board_position=p.board_position;
    physical_center_of_mass=p.physical_center_of_mass;
    skeleton_vector_16208=p.skeleton_vector_16208;
    skeleton_vector_16240=p.skeleton_vector_16240;
    system=p.reckoning.system;
    inverse_system=p.reckoning.inverse_system;
    velocity=p.velocity;
    angular_velocity=p.angular_velocity;
    time_step=p.time_step;
    flags_270=(p.flags_2468&0x2000)!=0?7:1;
    cone_angle_x=cone_x;
    cone_angle_z=cone_z;
}
void GroundLaunchInfo::WallJump(Vec4 value)
{
    velocity=value;
    angular_velocity=value;
    wall_jump=true;
}
}
