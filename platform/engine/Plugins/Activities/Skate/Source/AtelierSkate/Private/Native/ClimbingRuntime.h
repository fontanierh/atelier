// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ClimbingContacts.h"
#include "ClimbingLedge.h"
#include "CameraOutputRuntime.h"
#include "PlayerInputRuntime.h"
#include "PlayerStateLifecycle.h"
#include "OffboardAirSelector.h"
#include "BoardPossessionManager.h"
#include "CentreOfMassFilter.h"
#include "AnimatedSkeleton.h"
#include "FootIk.h"
namespace atelier::skate {
struct ClimbingFrame;
class ClimbingGlobalStages {
public:
  virtual ~ClimbingGlobalStages()=default;
  // The coordinator binds the real completed exchange/feedback, camera owner,
  // clock and Biped transition/query/contact owner. No default is provided.
  virtual bool AdvanceCamera(ClimbingFrame&,camera::CameraRuntime&,std::string& error)=0;
  virtual void FinishClockTick()=0;
  virtual bool ResumeAfterClimb(ClimbingFrame&,std::string& error)=0;
};
struct ClimbingFrame {
  PhysicalSimulationRuntime& physical;
  PlayerInputRuntime& player;
  AnimatedSkeleton& animated;
  FootIk& ik;
  PhysicsAnimationInput& animation_input;
  CentreOfMassFilter& centre_of_mass_filter;
  CentreOfMassOutput& centre_of_mass_output;
  std::vector<Mat4>& render_pose;
  std::uint64_t& pose_generation;
  const PhysicalPlayerStateLifecycle& selected_state;
  OffboardAirSelector& offboard_air_selector;
  BoardPossessionManager& offboard_feet;
};
struct ClimbingControls {
  const DerivedControllerInput& controller;
  const std::optional<Vec4>& offboard_direction;
};
enum class ClimbingPhase {Catch,Hang,Mantle,Settle};
struct ClimbingAttached {
  ClimbingPhase phase;
  float time;
  ClimbingLedge ledge;
  climbing_math::Transform start_root;
  std::vector<climbing_math::Transform> entry;
  std::vector<Mat4> fallback;
  Mat4 board_world,physical_board_world;
  bool carry_board;
};
struct ClimbingApproach {ClimbingLedge ledge;float weight;};
class ClimbingRuntime {
public:
  std::optional<ClimbingClips> clips;
  std::vector<std::size_t> indices;
  std::optional<ClimbingAttached> active;
  float cooldown=0;
  std::optional<ClimbingApproach> approach;
  std::vector<climbing_math::Transform> ground_entry;
  bool Load(const std::optional<ClimbingClipFile>&,
            const std::vector<std::string>& skater_names,std::string& error);
  bool Advance(ClimbingFrame,ClimbingControls,camera::CameraRuntime&,
               ClimbingGlobalStages&,bool& handled,std::string& error);
  bool Approach(ClimbingFrame,ClimbingControls,std::string& error);
  bool PublishPose(ClimbingFrame,const Mat4& root,std::vector<Mat4> pose,
                   std::string& error);
};
float ClimbingReachGain(float distance,bool airborne);
} // namespace atelier::skate
