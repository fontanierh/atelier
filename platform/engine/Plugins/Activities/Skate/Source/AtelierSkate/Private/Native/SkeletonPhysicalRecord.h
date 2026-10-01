// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct SkeletonPhysicalRecord
{
    std::array<Mat4,SkeletonPartCount> pose;
    std::array<Vec4,SkeletonPartCount> positions{},velocities{},velocity_changes{};
    Vec4 centre_of_mass{},centre_of_mass_velocity{};
    float timestep=0;
    SkeletonPhysicalRecord();
    void Reset(const std::array<Mat4,SkeletonPartCount>& parts);
    void Update(const std::array<Mat4,SkeletonPartCount>& parts,Mat4 board_frame,
        const std::array<float,SkeletonAnimationPartCount>& fractional);
};
}
