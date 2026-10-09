#pragma once
#include "PlayerStateCoordinator.h"
#include "PlayerTeleportRuntime.h"
#include "OffboardContactToolkit.h"
#include "OffboardAirSelector.h"
#include "LandingDeck.h"
#include "AirTrajectoryRuntime.h"
#include "AnimationPublication.h"
namespace atelier::skate
{
struct PlayerInputHostPhaseOwners
{
    PlayerStateCoordinatorOwners player;
    PlayerInputOwners input;
    OffboardContactToolkit& contact;
    OffboardAirSelector& selector;
    LandingDeck& landing_deck;
    AirTrajectoryRuntime& trajectory;
    PlayerTeleportRuntime& teleport;
    const PlayerGrindStaticProvider& grind_world;
};
struct PlayerInputHostPhaseFrame
{
    const AnimationInputPacket& packet;
    const PhysicsPosePacket& pose;
    const std::vector<AnimationAttribute>& attributes;
    ActionMap& actions;
    bool input_available;
};
// The full input_phase.rs host: preceding contact completion, actual shared
// landing latch, possession resets, and both halves of the sole input owner.
// ResetPlayer refreshes the same collision snapshot used by the second half.
bool AdvancePlayerInputHostPhase(PlayerInputHostPhaseOwners,PlayerInputHostPhaseFrame,
    bool& teleported,std::string& error);
SkeletonInputCollision BindSkeletonInputCollision(const PhysicalSimulationRuntime&);
}
