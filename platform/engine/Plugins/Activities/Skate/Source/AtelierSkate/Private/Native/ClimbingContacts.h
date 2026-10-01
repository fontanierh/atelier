// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ClimbingClips.h"
#include "ClimbingTypes.h"
namespace atelier::skate {
Vec3 ClimbingContactClearance(const ClimbingClip&,const std::vector<Mat4>&);
std::pair<Vec3,Quat> ClimbingWrist(ClimbingLedge,std::size_t side);
bool ApplyClimbingHands(const ClimbingClip&,std::vector<climbing_math::Transform>&,
                       const Mat4& root,ClimbingLedge,float weight,std::string& error);
} // namespace atelier::skate
