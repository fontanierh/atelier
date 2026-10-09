#pragma once
#include "PlayerStatePhases.h"
#include "RenderPoseRuntime.h"
namespace atelier::skate
{
// These views borrow the same state and physical owners used before Solve.
// Render receives those owners' actual completed records, after the selected
// post-state checks have updated the sole wipeout request history.
struct PlayerPostPhysicsOwners
{
    PlayerStatePhaseOwners states;
    RenderPoseOwners render;
};
bool FinishPlayerPostPhysics(PlayerPostPhysicsOwners,std::string& error);
bool CheckPlayerWipeoutAfterPhysics(PlayerStatePhaseOwners,std::string& error);
bool AdvancePlayerOffboardPostPhysics(PlayerStatePhaseOwners,std::string& error);
}
