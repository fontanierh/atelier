#pragma once
#include "SkeletonBoardOffset.h"
#include "SkeletonRoot.h"
#include <limits>
namespace atelier::skate
{
struct LandingSettings
{
    PointGraph<4> manual_blend,grind_blend,coffin_height;
    float minimum_height,maximum_velocity,manual_damping,manual_spring,ground_minimum_compression_time,ground_damping,ground_spring;
    float grind_animation_target_time,grind_damping,grind_spring,grind_target_delta,desired_com_height;
    float coffin_time,coffin_maximum_velocity,coffin_blend_frames,coffin_base_height;
};
struct LandingInput
{
    std::uint32_t filtered_state,flags_2468,flags_2472,flags_2476;
    float balance,physical_com_velocity_along_up,physical_com_height,animation_com_height;
};
struct LandingAdjustment
{
    bool active=false;
    std::uint32_t kind=0;
    float time=0,position=0,velocity=0,previous_com_velocity=0,previous_animation_height=std::numeric_limits<float>::max();
    std::uint32_t previous_filtered_state=0;
    float desired_grind_com=0;
    void Update(LandingInput,const LandingSettings&,SkateboardOffset&);
};
struct LandingOnBoardSettings{float root_y_offset,capsule_radius,capsule_length;};
Mat4 LandingOnBoardSkateRoot(Mat4 old,Vec4 physical_com,std::uint32_t flags_2480,float ground_y,LandingOnBoardSettings);
void UpdateLandingOnBoardRoot(SkeletonRootFrames&,Vec4 com,Vec4 local_com,float spin,std::optional<std::uint32_t> revert_frames,bool reversed);
std::optional<Mat4> LandingOnBoardPoseAdjustment(const Mat4& world_to_animation,const Mat4& actual_board,const Mat4& mapped_board,Vec4 ik_offset,float com_velocity_y,std::uint32_t flags_2480,float time,const PointGraph<8>& blend);
}
