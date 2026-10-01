// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonPoseFrames.h"
#include <optional>

namespace atelier::skate
{
Mat4 OrthonormalizeSkeletonFrame(Mat4 source);
struct SkeletonRootFrames
{
    Mat4 board=SkeletonIdentity,inverse_board=SkeletonIdentity;
    Vec4 previous_board_position{},predicted_board_position{};
    std::optional<Vec4> supplied_prediction;
    Mat4 animation_to_board=SkeletonIdentity,animation_to_world=SkeletonIdentity;
    Mat4 world_to_animation=SkeletonIdentity,heading_alignment=SkeletonIdentity;
    bool initialize_heading=true;
    void UpdateTeleport(Mat4 physical_board,const Mat4& animation_board,const Mat4& reckoning_frame);
    void ResetInitialAlignment(Mat4 alignment);
    void Update(Mat4 physical_board,Vec4 board_velocity,float time_step,
        const Mat4& animation_board,const Mat4& reckoning_frame);
};
}
