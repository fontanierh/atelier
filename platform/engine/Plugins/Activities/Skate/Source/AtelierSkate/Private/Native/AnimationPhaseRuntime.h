// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirReckoning.h"
#include "AnimationFeedbackRuntime.h"
#include "AnimationPhaseInput.h"
#include "AnimationStatePublication.h"
#include "CentreOfMassFilter.h"
#include "GraphActionPhysicalConditions.h"
#include "Handplant.h"
#include "OffboardController.h"
#include "PlayerInputRuntime.h"
#include "PlayerStateConditioning.h"
#include "SkaterAnimation.h"
#include "TeleportStateRuntime.h"
#include "TrainerTuning.h"
namespace atelier::skate {
// Already sampled controls, including their actual gesture publications.
// The phase adds only the source's grind/offboard projections.
struct AnimationPhaseControls {
  const IntentMap &action_intents;
  const DerivedControllerInput &controller;
  std::uint32_t actor_flags;
};
struct AnimationPhaseOwners {
  const PhysicalSimulationRuntime &physics;
  const PlayerInputRuntime &input;
  const PlayerStateConditioning &conditioning;
  const std::array<bool, 36> &state_flags;
  const FootIk &ik;
  const Handplant &handplant;
  const AirReckoning &air_reckoning;
  const CentreOfMassOutput &centre_of_mass;
  const OffboardController &biped_controller;
  const TrainerTuning &trainer;
  const AnimationPhysicalFeedback &feedback;
  const AnimationFeedbackRuntime &feedback_owner;
  SkaterAnimation &animation;
  TeleportStateRuntime &teleport;
};
// Exact physics/animation_phase.rs::advance. Caller supplies the actual source
// GamePhysics simulation.time_step; the actor packet is borrowed from
// animation. Earlier host/graph/pose writes survive failures. Output and reset
// reply do not. The six physical ActionCondition leaves read the same live
// actor.action.physical_inputs record written by this phase.
bool AdvanceAnimationPhase(AnimationPhaseOwners, AnimationPhaseControls,
                           const AnimationStockGraphs &,
                           const AnimationProfile &, float simulation_time_step,
                           AnimationPhaseOutput &output, std::string &error);
struct AnimationFeedbackOwners {
  const PhysicalSimulationRuntime &physics;
  PlayerInputRuntime &input;
  const GroundStateRuntime &ground;
  const PhysicsAnimationInput &animation_input;
  const SkaterAnimation &animation;
  PlayerStateConditioning &conditioning;
  const AirReckoning &air_reckoning;
  AnimationFeedbackRuntime &conditioner;
  AnimationPhysicalFeedback &publication;
};
// Once after completed physical output and before CameraOutput. The same stored
// publication is read by the next AdvanceAnimationPhase.
void PublishAnimationPhaseFeedback(AnimationFeedbackOwners);
} // namespace atelier::skate
