// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerStateCoordinator.h"
#include "KnownAirRuntime.h"
#include "BipedAirRuntime.h"
#include "LandingOnDeckRuntime.h"
#include "WipeoutPhysicalRuntime.h"
#include "RevertRuntime.h"
#include "SlideState.h"
#include "Handplant.h"
#include "GroundAnimationRuntime.h"
#include "TeleportStateRuntime.h"
namespace atelier::skate
{
// Passed views borrow the same canonical owners. The frame supplies actual
// retained phase states and completed physical/animation/query histories;
// there is no publication manager or replacement Fill-result cache here.
struct PlayerStatePublicationOwners
{
    PlayerStateCoordinatorOwners shared;
    AirPhaseOwners air;
    BipedRuntimeOwners biped;
    LandingOnDeckOwners landing;
    GrindRuntimeOwners grind;
    WipeoutPhysicalOwners wipeout;
    AirPhaseRuntime& air_runtime;
    KnownAirRuntime& known_air;
    BipedGroundRuntime& biped_ground;
    BipedAirRuntime& biped_air;
    LandingOnDeckRuntime& landing_on_deck;
    GrindRuntime& grind_runtime;
    WipeoutPhysicalRuntime& wipeout_runtime;
    RevertRuntime& revert;
    // Bind the sole SlidePhaseRuntime.state, not a separate Slide history.
    const SlideState& slide;
    Handplant& handplant;
    GroundAnimationRuntime& ground_animation;
    TeleportStateRuntime& teleport;
};
// Complete actual player_state/publication.rs sequence. Earlier physical,
// phase, flag and dismount writes remain visible after a later failure.
bool PublishPlayerPhysicalState(PlayerStatePublicationOwners,std::string& error);
// Source late Wipeout300 FillPhysOut, kept separate from phase scheduling.
void PublishWipeoutPlayerState(PlayerStatePublicationOwners);
}
