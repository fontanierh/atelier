#pragma once
#include "AirTrajectoryRuntime.h"
#include "FootplantPrediction.h"
#include "FootplantSettings.h"
#include "PlantSkeleton.h"
#include "WipeoutRequests.h"
namespace atelier::skate {
// The sole FootPlantManager owner. Pending submission and its delivered result
// are distinct retained fields, including across Reset and FullReset.
class FootplantRuntime {
public:
  bool enabled = false;
  AirTrajectoryQueryResult result = AirTrajectoryQueryResult::Miss();
  FootplantSettings settings;
  std::optional<std::size_t> selected_toe;
  bool candidate = false, hit = false, perform = false, flag_627 = false;
  bool launch_valid = false, lock_valid = false, contact_active = false;
  bool requested = false;
  float contact_time = -1, scalar_596 = -1, scalar_600 = 0;
  float target_blend = 0, active_elapsed = 0, scalar_612 = 0;
  std::uint32_t surface = 0;
  Vec4 contact{}, adjusted_contact{}, current_up{}, selected_world{};
  Vec4 selected_record{}, leg_direction{};
  std::array<Vec4, 2> vectors_352_368{};
  std::array<Vec4, 4> curve{};
  Vec4 physical_com{}, animation_com{}, launch_direction{}, locked_target{};
  AirTrajectory request{}, completed_trajectory{};
  bool Load(const SettingsDatabase &, std::string &error);
  void Reset();
  void FullReset();
  void Publish(AirOutputFields &) const;
  void UpdateCandidate(const KnownAirFootplantInput &,
                       FootplantPredictionFrame);
  void UpdateLaunch(const KnownAirFootplantInput &);
  bool ConsumeAndSubmit(const KnownAirFootplantInput &,
                        FootplantPredictionFrame, FootIk &,
                        SkeletonCollisionMode &, std::string &error);
  bool GroundEnter(PhysicalSimulationRuntime &, const ProcessedPhysicsInput &,
                   std::uint8_t &board_animated_290, std::string &error);
  bool GroundUpdate(PlantSkeletonFrame, const std::optional<BoardToolkit> &,
                    const AirStateSettings &, AirTrajectoryRuntime &,
                    std::array<float, 2> body_adjust, std::string &error);
  void PostPhysics(const ProcessedPhysicsInput &, WipeoutRequests &) const;
  // Original pure/manager members are public for an exact caller-domain probe;
  // runtime scheduling invokes them through the owner methods above.
  std::uint32_t Start(Vec4 com, Vec4 velocity);
  void Adjust(float fraction, std::array<float, 2> body_adjust);
  void UpdatePose(const KnownAirFootplantInput &, const SkeletonRootFrames &,
                  FootIk &, SkeletonCollisionMode &);
  void ClearContact();
  void NearbyEdge(FootplantPredictionFrame);
};
} // namespace atelier::skate
