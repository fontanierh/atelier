// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonRoot.h"
namespace atelier::skate
{
struct SkeletonBoardFrames
{
    Mat4 physical_board=SkeletonIdentity,skate_root=SkeletonIdentity,animation_target=SkeletonIdentity;
    Mat4 com_frame=SkeletonIdentity,lifted_com_frame=SkeletonIdentity;
    Vec4 centre_of_mass{},previous_centre_of_mass{},com_velocity{},local_centre_of_mass{},local_board_position{};
    float lift_height=0.0f;
    void Reset(Mat4 spawn);
    void PublishLocalObservations(const SkeletonRootFrames& roots,const Mat4& actual_board);
    void PublishCentreOfMass(Vec4 com,float dt,std::uint32_t flags_2472);
    Mat4 PrepareGround(const SkeletonRootFrames& roots,const Mat4& mapped_board,Mat4 actual_board,std::uint32_t& flags_2468);
    Mat4 PrepareTeleport(const SkeletonRootFrames& roots,const Mat4& mapped_board,Mat4 actual_board,std::uint32_t& flags_2468);
    void UpdateComLift(const Mat4& animation_to_world,Vec4 position,float requested_height);
};
}
