// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimatedSkeleton.h"
#include "PlayerInputTypes.h"
namespace atelier::skate
{
std::size_t OffboardSelectedHand(std::uint32_t flags_2476);
Mat4 OffboardHandAdjustment(const Mat4& actual,const Mat4& reparented);
bool UpdateOffboardPoseAdjustment(AnimatedSkeleton&,const std::vector<Mat4>& actual_globals,
    std::array<std::size_t,2> reparented_hands,const ProcessedPhysicsInput&,std::string& error);
}
