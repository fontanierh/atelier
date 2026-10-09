#pragma once
#include "PlayerStateRuntime.h"
#include "PlayerInputRuntime.h"
#include "GroundPhaseRuntime.h"
#include "OffboardGrabRuntime.h"
namespace atelier::skate
{
// Mandatory physical Enter/Exit dispatch supplied by the sole frame owner.
// Core lifecycle publication completes before these actual phase adapters run.
class PlayerStatePhaseDispatch
{
public:
    virtual ~PlayerStatePhaseDispatch()=default;
    virtual bool Exit(PhysicalStateId previous,PhysicalStateId requested,std::string& error)=0;
    virtual bool Enter(PhysicalStateId requested,std::string& error)=0;
};
struct PlayerStateCoordinatorOwners
{
    PhysicalSimulationRuntime& physical;
    PlayerInputRuntime& input;
    PlayerStateRuntime& state;
    GroundPhaseLifecycle& ground_lifecycle;
    SkeletonInputRuntime& skeleton_input;
    PhysicsAnimationInput& animation_input;
    FootIk& ik;
    WipeoutRequests& wipeout;
    OffboardGrabRuntime& grab;
    SimulationExchange& exchange;
};
BoardPossessionProcessed BindPlayerBoardPossession(PlayerStateCoordinatorOwners);
BoardPossessionObserveInput BindPlayerBoardPossessionObservation(PlayerStateCoordinatorOwners);
bool SetPlayerPhysicalState(PlayerStateCoordinatorOwners,PhysicalStateId,
    PlayerStatePhaseDispatch&,std::string& error);
bool InitializePlayerPhysicalState(PlayerStateCoordinatorOwners,
    PlayerStatePhaseDispatch&,std::string& error);
bool SelectPlayerPhysicalState(PlayerStateCoordinatorOwners,const ProcessedPhysicsSnapshot&,
    PlayerStatePhaseDispatch&,std::string& error);
// Takes the actual current world/registry scene, after preceding grab batches
// were completed. A failed Sync retains the preceding counter/root/IK writes.
bool AdvancePlayerPreState(PlayerStateCoordinatorOwners,const OffboardGrabScene&,std::string& error);
}
