// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirState.h"
#include "HandplantContact.h"
#include "HandplantRotation.h"
#include "PhysicalSimulationRuntime.h"
#include "PlantTrajectoryQueries.h"
#include "PlayerInputTypes.h"
namespace atelier::skate {
class AnimatedSkeleton;
class FootIk;
struct PlantSkeletonFrame;
struct HandplantPending {
  HandplantCandidate candidate;
  Vec4 com, velocity, normal, heading;
};
struct HandplantValues {
  Vec4 com, up, heading;
};
class Handplant {
public:
  HandplantSettings settings;
  std::uint32_t flags = 0;
  float phase;
  Vec4 anchor{}, previous_candidate_point{};
  std::optional<HandplantPending> pending;
  std::optional<HandplantCandidate> candidate;
  AirTrajectory initial, entry;
  std::array<AirTrajectory, 2> outgoing;
  std::array<Vec4, 4> curve{};
  std::array<Mat4, 4> rotations;
  Vec4 direction{};
  float travel_sign = 0, elapsed = -1, warped = -1, apex = -1,
        estimated_phase = -1, out_duration = 0;
  bool continuation = true;
  std::int32_t direction_hint = 0, direction_count = 0;
  float ik_blend = 0, ik_distance = -1;
  bool ik_released = false, ik_latched = false;
  Handplant();
  bool Load(const SettingsDatabase &, std::string &);
  std::array<float, 3> AnimationThresholds() const {
    return settings.animation;
  }
  void Reset();
  void FullReset();
  void ResetIk();
  void EstimateApex();
  // Complete Ground82D38430 submission; no synthetic world lookup. Cap40 and
  // authored ordering are applied inside the unchanged position selector.
  void GroundQuery(const ProcessedPhysicsInput &,
                   const PlayerGrindStaticProvider &);
  void GroundQuery(const ProcessedPhysicsInput &,
                   const std::vector<PlayerGrindPrimitive> &);
  bool GroundUpdate(PhysicalSimulationRuntime &, const ProcessedPhysicsInput &,
                    const AnimatedSkeleton &, FootIk &, std::string &);
  bool Enter(PhysicalSimulationRuntime &, const ProcessedPhysicsInput &,
             std::uint8_t &board_animated_290, HandplantTrajectoryQueries &,
             std::string &);
  bool Update(PlantSkeletonFrame, HandplantAirReckoning &, std::string &);
  void Launch(HandplantCandidate, Vec4 com, Vec4 velocity, Vec4 normal,
              Vec4 body_heading, Vec4 reckoning_heading);
  bool SelectOutgoing(const WorldGeometry &, HandplantTrajectoryQueries &,
                      std::string &);
  void BuildCurve();
  HandplantValues Values(const std::array<Mat4, 24> &world_pose,
                         Vec4 physical_com);
  void UpdateIk(const ProcessedPhysicsInput &, const AnimatedSkeleton &,
                const SkeletonRootFrames &, const SkeletonAnimationRecord &,
                FootIk &, bool ground);
};
float HandplantApexTime(const AirTrajectory &);
Vec4 PlantTrajectoryPosition(const AirTrajectory &, float time);
Vec4 PlantTrajectoryVelocity(const AirTrajectory &, float time);
} // namespace atelier::skate
