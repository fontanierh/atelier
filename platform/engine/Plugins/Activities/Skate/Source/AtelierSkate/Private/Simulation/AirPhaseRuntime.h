#pragma once
#include "GroundPhaseRuntime.h"
#include "FootplantRuntime.h"
#include "WipeoutRuntime.h"
namespace atelier::skate
{
// Required source PlayerState::post packet, borrowed rather than reconstructed
// from current body rates. Its producer is the player lifecycle coordinator.
struct AirPhaseJumpInput
{
    const RawVector& jump_reference;
    const std::uint32_t& jump_fix_frames;
};
struct AirPhaseOwners
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
    FootplantRuntime& footplant;
    WipeoutRuntime& wipeout;
    const PlayerGrindStaticProvider& grind_world;
    AirTrajectoryRuntime& trajectory;
    const AirStateSettings& settings;
    AirPhaseJumpInput post;
    const PhysicsPosePacket& packet;
    SkeletonInputOwners SkeletonOwners() const
    {return {physical,animated,ik,animation_input};}
};
AirStateBindingInput BindAirPhaseInput(AirPhaseOwners);
SkeletonInputCollision AirPhaseCollisionInput(const PhysicalSimulationRuntime&);
WipeoutObservations AirPhaseWipeoutObservations(AirPhaseOwners);
class AirPhaseRuntime
{
public:
    PhysicsAirState state;
    bool Enter(AirPhaseOwners,std::string& error);
    void Exit(AirReckoning&);
    bool Advance(AirPhaseOwners,std::string& error);
    void UpdateApex(const BoardRuntime&);
    // The common source postphysics coordinator calls CheckAir(false) after
    // this state's apex update and completed physical-feedback publication.
    bool PostPhysics(AirPhaseOwners,std::string& error);
    void Fill(AirOutputFields&) const;
};
}
