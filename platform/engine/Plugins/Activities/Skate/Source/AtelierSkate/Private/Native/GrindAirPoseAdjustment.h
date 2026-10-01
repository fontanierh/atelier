// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimatedSkeleton.h"
#include "GrindAir.h"
#include "PlayerInputTypes.h"
namespace atelier::skate
{
bool UpdateGrindAirPoseAdjustment(GrindAir&,const GrindAirSettings&,Mat4 processed_deck,
    const ProcessedPhysicsInput&,AnimatedSkeleton&,AnimatedSkeletonOwners,const std::vector<Mat4>& actual_globals,
    bool& adjusted,std::string& error);
}
