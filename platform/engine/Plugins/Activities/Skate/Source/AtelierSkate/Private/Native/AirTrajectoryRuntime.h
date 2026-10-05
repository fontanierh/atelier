// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirTrajectoryQuery.h"
#include "AirTrajectoryGrindRuntime.h"
#include "AirTrajectorySelector.h"
#include "PlantTrajectoryQueries.h"
#include <memory>
#include <utility>
namespace atelier::skate {
// One shared original query plus the real host's retained selector, synchronous
// submission/next-update completion, authored grind provider and nearby cache.
class AirTrajectoryRuntime : public HandplantTrajectoryQueries {
public:
  AirTrajectorySelector selector;
  AirTrajectorySelectorSettings settings{};
  // Host preference: zero retains the original near-vertical band.
  float vert_assist=0.0f;
  bool Load(const SettingsDatabase &, std::string &);
  bool Launch(AirLaunchInfo, AirSelectorInput, const WorldGeometry &,
              bool &launched, std::string &);
  void BindGrindWorld(std::shared_ptr<const PlayerGrindStaticProvider>);
  bool Update(AirSelectorInput, const WorldGeometry &, AirTrajectoryGrindContext,
              bool &valid, std::string &);
  static bool Query(const WorldGeometry &, AirTrajectoryQueryRequest,
                    AirTrajectoryQueryResult &, std::string &);
  bool Query(const WorldGeometry &, const AirTrajectory &, float radius,
             float start_error, float end_error, PlantTrajectoryQueryResult &,
             std::string &) override;
  const std::optional<std::vector<AirTrajectoryQueryResult>> &PendingResults() const {
    return pending_results_;
  }
  const AirTrajectoryGrindRuntime &GrindSettings() const { return grind_settings_; }
  AirTrajectoryGrindRuntime &MutableGrindSettings() { return grind_settings_; }
  const std::vector<std::size_t> &NearbyGrinds() const { return nearby_grinds_; }
  const std::shared_ptr<const PlayerGrindStaticProvider> &GrindWorld() const {
    return grind_world_;
  }
private:
  std::optional<std::vector<AirTrajectoryQueryResult>> pending_results_;
  AirTrajectoryGrindRuntime grind_settings_;
  std::shared_ptr<const PlayerGrindStaticProvider> grind_world_;
  std::vector<std::size_t> nearby_grinds_;
  bool Submit(const WorldGeometry &, std::string &);
};
std::pair<Vec4,Vec4> AirTrajectoryVertDeparture(Vec4 normal, Vec4 velocity,
                                               float direction, float assist);
Vec4 AirTrajectoryVertDepartureNormal(Vec4 normal, Vec4 velocity, float direction);
} // namespace atelier::skate
