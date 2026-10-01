// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct SkeletonMotion
{
    Mat4 trajectory=SkeletonIdentity,inverse_trajectory=SkeletonIdentity,next_trajectory=SkeletonIdentity;
    Vec4 velocity_world{};
    float previous_board_at_y=0;
    void ResetBoardOrientationHistory(){previous_board_at_y=0.0f;}
    void ProcessTrajectory(const Mat4&,const Mat4& animation_to_world,float dt);
    static void PublishUnadjustedBoard(const Mat4&,std::uint32_t& flags_2472);
    float PublishAdjustedBoard(const Mat4&,std::uint32_t& flags_2468);
};
}
