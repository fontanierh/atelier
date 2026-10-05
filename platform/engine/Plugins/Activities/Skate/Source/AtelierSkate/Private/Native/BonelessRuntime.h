// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirPhaseRuntime.h"
#include "PlantSkeleton.h"
namespace atelier::skate {
// The source state602 owns only its completed toe anchor and four stock curves.
// Every physical, plant, animation and trajectory history is borrowed below.
struct BonelessFrame {
  AirPhaseOwners owners;
  const std::vector<Mat4> &actual_globals;
};
class BonelessRuntime {
public:
  std::size_t toe = 15;
  Vec4 anchor{};
  bool right = false;
  // The player's boneless height (FeelTuning::boneless): the launch's rise is scaled so the apex moves by this factor
  // under any gravity scale. At 1 (and stock gravity) the launch is bit-exact.
  float height_scale = 1.0f;
  bool Load(const SettingsDatabase &, std::string &error);
  void Enter(PhysicalSimulationRuntime &, GroundPhaseLifecycle &,
             const ProcessedPhysicsInput &);
  bool Update(BonelessFrame, std::string &error);
  bool Launch(BonelessFrame, std::string &error);
  const std::array<PointGraph<8>, 4> &Curves() const { return curves_; }
private:
  std::array<PointGraph<8>, 4> curves_{};
};
} // namespace atelier::skate
