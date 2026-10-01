// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationPhysical.h"
#include "CameraRuntime.h"
#include "CentreOfMassFilter.h"
#include "GroundStateRuntime.h"
#include "PhysicalPhase.h"
#include "PhysicalSimulationRuntime.h"
#include "PlayerInputTypes.h"
#include "SkaterAnimation.h"

namespace atelier::skate::camera {
// Borrow the canonical completed owners. The physical state coordinator owns
// selected_state and state_flag_81; there is no second player-state owner here.
struct CameraPublicationFrame {
  const PhysicalSimulationRuntime &physics;
  const ProcessedPhysicsInput &processed;
  const PhysicalPlayerInput &physical;
  const BoardToolkit *toolkit;
  const GroundStateRuntime &ground;
  const PhysicsAnimationInput &animation_input;
  const SkaterAnimation &animation;
  const AnimationPhysicalFeedback &feedback;
  const CentreOfMassOutput &centre_of_mass;
  PhysicalStateId selected_state;
  bool state_flag_81;
};
struct CameraStateOutput {
  float height_32;
  std::uint8_t physically_pushing_55, wiping_out_59, manual_60, reset_62;
  std::uint8_t use_skeleton_root_75, flag_79, flag_81;
};
struct CameraAnimationOutput {
  std::array<float, 8> conditioned_turn;
  float input_turn_64, input_kickturn_68, time_since_input_128;
  std::uint32_t wipeout_tweak_148;
  std::uint8_t stance_155, running_out_160, skater_animation_stance;
};
struct CameraAirOutput {
  Vec4 apex_0, landing_position_16, landing_normal_32, launch_position_48,
      heading_80;
  float time_176, duration_180, apex_time_196;
  std::uint8_t flag_440;
};
struct CameraOffboardOutput {
  float duration_92, time_152, apex_time_156;
  Vec4 launch_normal_160, launch_position_176, landing_normal_192,
      landing_position_208, heading_224, apex_240;
  std::uint8_t object_held_304, hurdle_317, use_trajectory_331, dropping_in_334;
};
struct CameraGrindOutput {
  Vec4 direction_0, camera_target_96;
  std::uint8_t grinding_316;
};
struct CameraEventsOutput {
  std::uint8_t intent_51, preparing_52, dropping_in_63, trick_125,
      hippy_jump_322;
  float broken_bone_duration_200;
  std::uint32_t capabilities_204;
};
struct CameraPreferences {
  std::array<bool, 2> invert_look;
  std::uint8_t shake_variant;
  float value_32;
};
// Exact intermediate publication shape. No constructor invents producer data.
struct CameraPublicationInputs {
  std::uint64_t tick;
  CameraStateOutput state;
  CameraAnimationOutput animation;
  CameraAirOutput air;
  CameraOffboardOutput offboard;
  CameraGrindOutput grinds;
  CameraEventsOutput events;
  Vec4 damped_com_80, ground_up_80;
  float ground_scalar_288;
  std::array<float, 2> look_552_556;
  Vec4 collision_look_target_64;
  CameraPreferences preferences;
  std::uint32_t context;
};
// Whole host camera/publication.rs subject producer; output is assigned only
// after the original toolkit and finite-publication checks succeed.
bool PublishCameraSubject(const CameraPublicationFrame &,
                          const CameraPublicationInputs &,
                          CameraSubjectSnapshot &output, std::string &error);
Mat4 EffectiveCameraSkeletonRoot(Mat4 root, std::uint32_t flags_2476);
} // namespace atelier::skate::camera
