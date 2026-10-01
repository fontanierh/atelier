// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SlideStateRuntime.h"
#include "GroundPhaseRuntime.h"
#include "WipeoutRuntime.h"
namespace atelier::skate
{
// These are the source SkaterRuntime/GamePhysics owners. Slide retains no
// second processed packet, skeleton, controller, material or query history.
struct SlidePhaseOwners
{
    PhysicalSimulationRuntime& physical;
    ProcessedPhysicsInput& processed;
    const std::optional<BoardToolkit>& toolkit;
    GroundStateRuntime& ground;
    GroundRuntime& ground_runtime;
    GroundPhaseLifecycle& life;
    AnimatedSkeleton& animated;
    FootIk& ik;
    PhysicsAnimationInput& animation_input;
    SkeletonInputRuntime& skeleton_input;
    SkeletonAir& skeleton_air;
    AirReckoning& air_reckoning;
    WipeoutRuntime& wipeout;
    AirTrajectoryRuntime& trajectory;
    const AirStateSettings& air_settings;
    const GroundSettings& ground_settings;
    const PhysicsPosePacket& packet;
    const std::uint32_t& jump_fix_frames;
};
class SlidePhaseRuntime
{
public:
    SlideState state;
    SlideStateSettings settings;
    bool Load(const SettingsDatabase&,std::string& error);
    void Enter(SlidePhaseOwners);
    void Exit(SlidePhaseOwners);
    bool Advance(SlidePhaseOwners,std::string& error);
    // The shared postphysics coordinator invokes the same Ground check once,
    // after the actual solved collision/riding records have been published.
    bool PostPhysics(SlidePhaseOwners,std::string& error);
};
// Complete original air_phase::input launch/selector transport, bound to the
// same owners; jump-reference fields are not consumed by Slide's launch path.
AirStateBindingInput BindSlidePhaseTrajectoryInput(SlidePhaseOwners);
WipeoutObservations SlidePhaseWipeoutObservations(SlidePhaseOwners);
bool AdvanceSlidePhase(SlideState&,const SlideStateSettings&,SlidePhaseOwners,std::string& error);
}
