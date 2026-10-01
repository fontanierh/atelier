// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GroundRuntime.h"
#include "PhysicalSimulationRuntime.h"
#include "PhysicsAnimationInput.h"
#include "PlayerInputTypes.h"
namespace atelier::skate
{
// Completed outputs of separate producers, consumed directly by Ground.
struct GroundInputObservations
{
    float manual_drag_2724;
    std::uint32_t trajectory_state_bits,edge_flags;
    Vec4 edge_point;
};
BoardToolkit PrepareGroundToolkit(GroundRuntime&,const BoardRuntime&,const ProcessedPhysicsInput&);
GroundContactFrame GroundWallContactFrame(const PhysicalBoardProbes&,float time2752,float time2756);
GroundBoardInput PrepareGroundBoardInput(const GroundSettings&,const BoardToolkit&,
    const ProcessedPhysicsInput&,const ScalarAttributeInputs&,const ContactEventState&,
    const PumpingState&,float unintentional_pump_scalar,const PhysicalRidingOutputs&,
    float actual_board_at_y_delta,const std::array<AffineTransform,2>& base_trucks,
    GroundInputObservations);
}
