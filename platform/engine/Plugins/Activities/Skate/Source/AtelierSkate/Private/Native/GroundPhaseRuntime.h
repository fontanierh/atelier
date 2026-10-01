// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirReckoning.h"
#include "AirTrajectoryRuntime.h"
#include "GroundStateRuntime.h"
#include "Handplant.h"
#include "OffboardGrabCache.h"
#include "PlayerInputTypes.h"
#include "SkeletonAirRuntime.h"
#include "SkeletonController.h"
#include "SkeletonWobble.h"
namespace atelier::skate
{
struct GroundPhaseEdge
{
    std::uint32_t flags;
    Vec4 point;
    Vec3 start,end;
};
// Shared lifecycle fields: teleport and the player state coordinator borrow
// this same record, rather than constructing a second Ground history.
struct GroundPhaseLifecycle
{
    SkeletonControllerState skeleton_controller;
    bool skeleton_elapsed_16505=false;
    std::uint8_t board_animated_290=0;
    float manual_drag_2724=0;
    std::optional<GroundPhaseEdge> edge;
    std::optional<GroundLaunchInfo> pending_wall_jump;
};
struct GroundPhaseOwners
{
    PhysicalSimulationRuntime& physical;
    // Borrow the canonical PlayerInputRuntime fields without copying its state.
    ProcessedPhysicsInput& processed;
    const std::optional<BoardToolkit>& toolkit;
    GroundStateRuntime& ground;
    GroundRuntime& runtime;
    GroundPhaseLifecycle& life;
    AnimatedSkeleton& animated;
    FootIk& ik;
    PhysicsAnimationInput& animation_input;
    AirReckoning& air_reckoning;
    SkeletonWobble& wobble;
    OffboardGrabCache& grab;
    WipeoutRequests& wipeout;
    Handplant& handplant;
    const PlayerGrindStaticProvider& grind_world;
    AirTrajectoryRuntime& trajectory;
    const AirStateSettings& air_settings;
};
void ResetGroundBoardState(GroundStateRuntime&,GroundRuntime&,GroundPhaseLifecycle&,
    bool& board_wiping_out);
bool EnterGroundPhase(GroundPhaseOwners,std::string& error);
std::optional<GroundBoardOutcome> AdvanceGroundPhase(GroundPhaseOwners,
    const GroundSettings&,std::string& error);
// Called by the frame coordinator after AdvanceGroundPhase and the real
// Handplant GroundUpdate. Captures the same error later consumed by Air.
bool UpdateGroundSkeletonInput(GroundPhaseOwners,SkeletonInputRuntime&,SkeletonAir&,
    const std::vector<Mat4>& actual_globals,std::string& error);
}
