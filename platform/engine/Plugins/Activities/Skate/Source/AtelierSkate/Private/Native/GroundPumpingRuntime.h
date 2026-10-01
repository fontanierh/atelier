// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PhysicalSimulationRuntime.h"
#include "PlayerInputTypes.h"
#include "Pumping.h"
namespace atelier::skate
{
void UpdatePhysicalGroundPumping(PumpingState&,const PumpingConfiguration&,GroundPumpingMode,
    const BoardToolkit&,const PhysicalRidingOutputs&,const SkeletonAnimationRecord&,
    const SkeletonBoardFrames&,std::uint32_t flags_2476);
bool UpdatePhysicalRevertPumping(PumpingState&,const PumpingConfiguration&,const BoardToolkit&,
    const PhysicalRidingOutputs&,const SkeletonAnimationRecord&,const ProcessedPhysicsInput&,
    float balance,std::string& error);
}
