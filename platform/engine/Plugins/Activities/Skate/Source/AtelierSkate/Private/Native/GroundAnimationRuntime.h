// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GroundAnimationSettings.h"
#include "GroundPhaseRuntime.h"
#include "SkeletonAirRuntime.h"
namespace atelier::skate {
struct GroundAnimationOwners {
  PhysicalSimulationRuntime &physical;
  ProcessedPhysicsInput &processed;
  const std::optional<BoardToolkit> &toolkit;
  GroundStateRuntime &ground;
  GroundRuntime &ground_runtime;
  GroundPhaseLifecycle &life;
  AnimatedSkeleton &animated;
  FootIk &ik;
  PhysicsAnimationInput &animation_input;
  SkeletonInputRuntime &skeleton_input;
  SkeletonAir &skeleton_air;
  WipeoutRequests &wipeout;
  AirTrajectoryRuntime &trajectory;
  const AirStateSettings &air_settings;
  const PhysicsPosePacket &packet;
  const TrainerTuning &trainer;
  SkeletonInputOwners SkeletonOwners() const {
    return {physical, animated, ik, animation_input};
  }
};
class GroundAnimationRuntime {
public:
  GroundJump jump;
  bool launched = false;
  Vec4 launch_velocity{};
  void Fill(const ProcessedPhysicsInput &, AirOutputFields &) const;
  bool Enter(GroundAnimationOwners, std::string &error);
  bool Advance(GroundAnimationOwners, const GroundSettings &,
               const GroundAnimationSettings &, std::string &error);
  void Exit(GroundAnimationOwners);

private:
  bool AdvanceSkeleton(GroundAnimationOwners, std::string &error);
  bool AdvanceBoard(GroundAnimationOwners, const GroundSettings &,
                    const GroundAnimationSettings &, std::string &error);
};
void SetGroundAnimationDrag(BoardRuntime &, float drag);
} // namespace atelier::skate
