// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardAssembly.h"
#include "SkeletonPoseFrames.h"
#include <optional>
namespace atelier::skate
{
inline constexpr std::size_t SkeletonJointCount=22;
struct SkeletonJointBone
{
    Quat parent_orientation,joint_orientation;
    Mat4 volume_frame;
    float swing_limit,twist_limit;
};
struct SkeletonJointBoneSettings {bool ball_joint;float swing_angle,twist_angle,swing_ragdoll,twist_ragdoll;};
struct SkeletonJointSettings
{
    Vec4 displacement_limit;
    float twist_displacement_limit,swing_displacement_limit;
    bool enforce_swing_free,enforce_twist_free;
};
struct SkeletonJoint
{
    std::size_t parent,child;
    std::array<std::uint32_t,16> parameters;
    std::array<std::uint32_t,20> frames;
};
struct SkeletonJoints
{
    std::array<SkeletonJoint,SkeletonJointCount> records;
    static std::optional<SkeletonJoints> FromDefinition(
        const std::array<Mat4,SkeletonAnimationPartCount>& initial_bones,
        const std::array<std::optional<std::size_t>,SkeletonAnimationPartCount>& parents,
        const std::array<SkeletonJointBone,SkeletonAnimationPartCount>& bones,
        const std::array<SkeletonJointBoneSettings,SkeletonJointCount>& settings,
        SkeletonJointSettings global,std::string& error);
    std::vector<JointConstraint> Build(const std::array<BodySnapshot,SkeletonPartCount>& bodies,
        std::size_t reaction_base,float time_step) const;
};
}
