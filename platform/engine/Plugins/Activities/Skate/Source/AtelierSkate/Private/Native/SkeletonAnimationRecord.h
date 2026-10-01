// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct SkeletonAnimationMasses
{
    std::array<float,SkeletonAnimationPartCount> part_weights{};
    float total=0;
    std::array<float,SkeletonAnimationPartCount> fractional{};
    static SkeletonAnimationMasses Normalize(std::array<float,SkeletonAnimationPartCount> weights);
    static SkeletonAnimationMasses FromBoneData(std::array<Vec3,SkeletonAnimationPartCount> sizes,
        std::array<std::uint32_t,SkeletonAnimationPartCount> collision_shapes,bool head_has_hat);
};
struct SkeletonAnimationRecord
{
    std::array<Mat4,SkeletonAnimationPartCount> pose;
    Vec4 centre_of_mass{},centre_of_mass_delta{},com_to_deck_world{},com_to_deck_world_delta{};
    float reset_scalar=0;
    SkeletonAnimationRecord();
    void ResetHistory();
    void Update(const std::array<Mat4,SkeletonAnimationPartCount>& input,
        const Mat4& animation_to_board,const SkeletonAnimationMasses& masses);
    Vec3 ComToDeck() const {return {com_to_deck_world[0],com_to_deck_world[1],com_to_deck_world[2]};}
};
}
