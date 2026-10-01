// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "MotionGraphContinuationSettings.h"
#include "MotionGraphHost.h"
namespace atelier::skate {
// Independently absent, actual upstream producer records. Shared landing,
// wipeout, category, stance, gameplay and hands remain on the borrowed host.
struct MotionGraphContinuationInputs {
  std::optional<Vec4> bump_acceleration;
  std::optional<float> offboard_cadence_phase;
  std::optional<MotionGraphRunoutObservation> runout;
  std::optional<AnimationAirLegPhysical> air_leg;
  std::optional<MotionGraphLandingVelocityPublication> landing_velocity;
  std::optional<MotionGraphGrindPhysical> grind;
  std::optional<MotionGraphToggleBoardPhysical> toggle_board;
};
// One accepted host owns every shared mutable value and allocation counter.
// This registration layer supplies the remaining original instance variants;
// it is driven by the same controller and the same behavior IDs.
class MotionGraphContinuationHost final : public graph::Host {
public:
  explicit MotionGraphContinuationHost(MotionGraphHost &owner) : base(owner) {}
  MotionGraphHost &base;
  MotionGraphContinuationInputs physical;
  MotionGraphWipeoutControlState wipeout_controls;
  std::optional<MotionGraphContinuationSettings> settings;
  std::vector<MotionGraphContinuationOperation> operations;
  std::vector<MotionGraphContinuationInstance> instances;
  bool FromGraph(const Graph &, const GraphBinding &, const CompiledGraph &,
                 const SettingsDatabase &, std::string &error);
  graph::Context GetContext() const override { return base.GetContext(); }
  std::uint32_t ConditionActivation(graph::Id, const graph::Frame &) override;
  std::uint32_t Allocate(graph::Id, const graph::Frame &) override;
  void Begin(graph::Id, graph::Context, const graph::Frame &) override;
  void Update(graph::Id, graph::Context, const graph::Frame &) override;
  void End(graph::Id, graph::Context, const graph::Frame &) override;
  void Hook(graph::Id, const graph::Frame &) override;
  void Release(std::uint32_t instance) override { base.Release(instance); }

private:
  GraphOperationRemap remap_;
  bool Extra(graph::Id) const;
  void Run(graph::Id, graph::Context, const graph::Frame &, std::uint8_t);
  bool Execute(graph::Id, const graph::Frame &, std::uint8_t, std::string &);
  void AddError(std::string);
};
} // namespace atelier::skate
