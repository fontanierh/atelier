// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerPostPhysicsPhase.h"
#include "PlayerInputHostPhase.h"
#include "PlayerStatePublication.h"
#include "PlayerStatePostInputRuntime.h"
#include "PlayerControls.h"
#include "AnimationPhaseRuntime.h"
#include "ClimbingRuntime.h"
#include "CameraOutputRuntime.h"
#include "ScoringRuntime.h"
#include "SimulationClock.h"
namespace atelier::skate
{
// Call-local views into the single game/skater ownership tree. Every phase
// borrows the same physical, input, pose, controller and state records. These
// views hold no substitute publications or independently advancing histories.
struct GameplayFrameOwners
{
    PlayerPostPhysicsOwners post;
    PlayerInputHostPhaseOwners input;
    PlayerStatePublicationOwners publication;
    AnimationPhaseOwners animation;
    AnimationFeedbackOwners feedback;
    const GroundProfiles& ground_profiles;
    GroundSettings& ground_settings;
    const OffboardGrabRegistry& grab_registry;
    ClimbingRuntime& climbing;
    ClimbingFrame climbing_frame;
    PlayerControls& controls;
    const AnimationStockGraphs& graphs;
    const AnimationProfile& animation_profile;
    camera::CameraRuntime& camera;
    SimulationClock& clock;
    bool network_active;
    ScoringRuntime& scoring;
    CentreOfMassFilter& centre_of_mass_filter;
    CentreOfMassOutput& centre_of_mass_output;
};
// Entire actual physics/frame.rs schedule. Controls are sampled once before
// this function, and its original packet is borrowed through simulation actions.
// Failure retains the exact preceding writes and consumes only reached queues.
bool AdvanceGameplayFrame(GameplayFrameOwners,ActionMap& original_actions,
    bool input_available,std::string& error);
camera::CameraPublicationFrame BindGameplayCameraFrame(GameplayFrameOwners);
}
