#pragma once
#include "PlayerStateCoordinator.h"
#include "AirPhaseRuntime.h"
#include "BipedAirRuntime.h"
#include "BonelessRuntime.h"
#include "GroundAnimationRuntime.h"
#include "KnownAirRuntime.h"
#include "LandingOnDeckRuntime.h"
#include "RespawnRuntime.h"
#include "RevertRuntime.h"
#include "SlidePhaseRuntime.h"
#include "WipeoutPhysicalRuntime.h"
#include "GrindRuntime.h"
namespace atelier::skate
{
// Call-local views of the single frame owner's physical, input and pose state.
// Phase runtimes below retain only their own original state histories.
struct PlayerStatePhaseOwners
{
    PlayerStateCoordinatorOwners player;
    GroundPhaseOwners ground;
    AirPhaseOwners air;
    GroundAnimationOwners ground_animation;
    BipedRuntimeOwners biped;
    LandingOnDeckOwners landing;
    GrindRuntimeOwners grind;
    WipeoutPhysicalOwners wipeout;
    SlidePhaseOwners slide;
    const GroundSettings& ground_settings;
    const GroundAnimationSettings& ground_animation_settings;
    SkaterAnimation& animation;
    RespawnRuntime& respawn;
    TeleportStateRuntime& teleport;
    RevertRuntime& revert;
    AirPhaseRuntime& physics_air;
    KnownAirRuntime& known_air;
    BonelessRuntime& boneless;
    GroundAnimationRuntime& animation_ground;
    BipedGroundRuntime& biped_ground;
    BipedAirRuntime& biped_air;
    LandingOnDeckRuntime& landing_on_deck;
    GrindRuntime& grinding;
    WipeoutPhysicalRuntime& ragdoll;
    SlidePhaseRuntime& sliding;
};
class PlayerStatePhases final:public PlayerStatePhaseDispatch
{
public:
    explicit PlayerStatePhases(PlayerStatePhaseOwners);
    bool Exit(PhysicalStateId previous,PhysicalStateId requested,std::string& error) override;
    bool Enter(PhysicalStateId requested,std::string& error) override;
    // Complete selected-state portion of physics/frame.rs, including real
    // Ground reckoning and the two later Biped query submissions.
    bool Update(PhysicalStateId current,std::string& error);
    bool EnterAfterTeleport(std::string& error);
    bool ApplyVehicleEjection(bool& applied,std::string& error);
    bool ResumeAfterClimb(std::string& error);
private:
    PlayerStatePhaseOwners owners_;
};
}
