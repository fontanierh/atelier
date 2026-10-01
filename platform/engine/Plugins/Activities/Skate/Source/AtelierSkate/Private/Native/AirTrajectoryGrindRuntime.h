// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirTrajectoryGrind.h"
#include "PlayerInputTypes.h"
namespace atelier::skate {
struct AirTrajectoryGrindContext {
  Vec4 board_position, body_position;
  std::array<std::uint32_t, 2> actor;
  static AirTrajectoryGrindContext FromProcessed(const ProcessedPhysicsInput &,
                                                 Vec4 board_position);
};
// Source host settings and real geometry/provider admission. The retained
// nearby indices belong to AirTrajectoryRuntime and survive non-acquisition
// candidates, just as they do in the original host.
struct AirTrajectoryGrindRuntime {
  AirTrajectoryGrindAssistLimits limits{};
  PointGraph<8> height{};
  float padding = 0, maximum_adjust = 0, velocity_scalar = 0, max_angle = 0;
  float score = 0, truck_distance = 0, penalty_domain = 0;
  bool Load(const SettingsDatabase &, std::string &);
  bool Evaluate(AirTrajectoryPrediction &, bool acquire, const WorldGeometry &,
                const PlayerGrindStaticProvider &, std::vector<std::size_t> &nearby,
                float lock_distance, AirTrajectoryGrindContext,
                AirTrajectoryGrindEvaluation &, std::string &) const;
};
} // namespace atelier::skate
