#include "MotionGraphContinuationHost.h"
#include <algorithm>
namespace atelier::skate {
bool MotionGraphContinuationHost::FromGraph(const Graph &source,
                                            const GraphBinding &binding,
                                            const CompiledGraph &compiled,
                                            const SettingsDatabase &data,
                                            std::string &error) {
  std::vector<MotionGraphContinuationOperation> parsed;
  for (const auto &op : binding.operations) {
    const auto &element = source.elements[op.element];
    const GraphAttributes a(element.attributes);
    const auto failed_factory = [&] {
      const auto kind = op.kind == GraphOperationKind::Behavior    ? "behaviour"
                        : op.kind == GraphOperationKind::Condition ? "condition"
                                                                   : "hook";
      error = "Graph " + element.tag + " at byte " +
              std::to_string(element.source_offset) + ": " + kind + " `" +
              op.name + "`: " + error;
      return false;
    };
    MotionGraphContinuationOperation extra;
    bool recognized = false;
    if (!ParseMotionGraphContinuationOperation(op.kind, a, extra, recognized,
                                               error))
      return failed_factory();
    if (!recognized) {
      MotionGraphOperation existing;
      if (!ParseMotionGraphOperation(op.kind, a, existing, error))
        return failed_factory();
      if (existing.kind == MotionGraphOperation::Kind::Animation)
        for (auto id : op.parameters)
          if (!AddMotionAnimationParameter(
                  existing.animation,
                  GraphAttributes(source.elements[id].attributes), error))
            return failed_factory();
    }
    parsed.push_back(std::move(extra));
  }
  MotionGraphContinuationSettings loaded;
  if (!loaded.Load(data, base.animation.tree.Metadata(), error))
    return false;
  // All original factory/parameter and source-ordered settings validation is
  // complete before mutating the accepted shared owner. Its constructor
  // retains the canonical RNG, handles, hooks, flags and condition bindings.
  if (!base.FromGraph(source, binding, compiled, data, error))
    return false;
  base.pushing = loaded.pushing;
  base.feedback_settings = loaded.feedback;
  base.sliding_settings = loaded.sliding;
  base.prelanding_condition_settings = loaded.airborne.spin.prelanding;
  operations = std::move(parsed);
  remap_ = compiled.operations;
  instances.clear();
  for (auto id : remap_.behaviors) {
    instances.push_back(CreateMotionGraphContinuationInstance(operations[id]));
    if (!std::holds_alternative<std::monostate>(operations[id])) {
      auto found =
          std::find(base.capabilities.unported.begin(),
                    base.capabilities.unported.end(), base.operations[id].name);
      if (found != base.capabilities.unported.end())
        base.capabilities.unported.erase(found);
      ++base.capabilities.supported;
    } else if (base.operations[id].kind ==
               MotionGraphOperation::Kind::Unported) {
      // Raw-only simulation factories do not become registered just because
      // the generic diagnostic catalog recognizes their trimmed name.
      base.operations[id].kind = MotionGraphOperation::Kind::Unsupported;
      auto found =
          std::find(base.capabilities.unported.begin(),
                    base.capabilities.unported.end(), base.operations[id].name);
      if (found != base.capabilities.unported.end())
        base.capabilities.unported.erase(found);
      base.capabilities.source_unsupported.push_back(base.operations[id].name);
    }
  }
  settings = std::move(loaded);
  physical = {};
  wipeout_controls = {};
  error.clear();
  return true;
}
bool MotionGraphContinuationHost::Extra(graph::Id id) const {
  return id < remap_.behaviors.size() &&
         remap_.behaviors[id] < operations.size() &&
         !std::holds_alternative<std::monostate>(
             operations[remap_.behaviors[id]]);
}
std::uint32_t
MotionGraphContinuationHost::ConditionActivation(graph::Id id,
                                                 const graph::Frame &frame) {
  return base.ConditionActivation(id, frame);
}
std::uint32_t MotionGraphContinuationHost::Allocate(graph::Id id,
                                                    const graph::Frame &frame) {
  const auto handle = base.Allocate(id, frame);
  if (Extra(id))
    instances[id] =
        CreateMotionGraphContinuationInstance(operations[remap_.behaviors[id]]);
  return handle;
}
void MotionGraphContinuationHost::AddError(std::string error) {
  if (base.errors.size() < 64)
    base.errors.push_back(std::move(error));
  else
    base.diagnostics_overflowed = true;
}
void MotionGraphContinuationHost::Run(graph::Id id, graph::Context context,
                                      const graph::Frame &frame,
                                      std::uint8_t phase) {
  if (!Extra(id)) {
    if (phase == 0)
      base.Begin(id, context, frame);
    else if (phase == 1)
      base.Update(id, context, frame);
    else
      base.End(id, context, frame);
    return;
  }
  std::string error;
  if (!Execute(id, frame, phase, error))
    AddError("MotionGraph behavior " + std::to_string(id) + ": " + error);
}
void MotionGraphContinuationHost::Begin(graph::Id id, graph::Context c,
                                        const graph::Frame &f) {
  Run(id, c, f, 0);
}
void MotionGraphContinuationHost::Update(graph::Id id, graph::Context c,
                                         const graph::Frame &f) {
  Run(id, c, f, 1);
}
void MotionGraphContinuationHost::End(graph::Id id, graph::Context c,
                                      const graph::Frame &f) {
  Run(id, c, f, 2);
}
void MotionGraphContinuationHost::Hook(graph::Id id, const graph::Frame &f) {
  base.Hook(id, f);
}
bool MotionGraphContinuationHost::Execute(graph::Id id,
                                          const graph::Frame &frame,
                                          std::uint8_t phase,
                                          std::string &error) {
  if (!settings) {
    error = "MotionGraph continuation requires loaded original settings";
    return false;
  }
  const auto &op = operations[remap_.behaviors[id]];
  auto &instance = instances[id];
  auto &a = base.animation;
  const auto &s = *settings;
  const auto category =
      base.physical.conditions.physical_state
          ? std::optional<std::uint32_t>(
                base.physical.conditions.physical_state->category)
          : std::nullopt;
  if (const auto *p = std::get_if<GraphMotionAuxiliaryFeedbackOperation>(&op)) {
    return ExecuteGraphMotionAuxiliaryFeedbackOperation(
        *p, std::get<AnimationFakieHeadState>(instance), phase, a, s.bump,
        physical.bump_acceleration, base.flags.manualing, base.is_power_sliding,
        error);
  }
  if (const auto *p = std::get_if<AnimationKickturnOperation>(&op)) {
    return ExecuteAnimationKickturnOperation(
        *p, std::get<AnimationKickturnState>(instance), s.kickturn, a, frame.dt,
        phase, error);
  }
  if (const auto *p = std::get_if<GraphMotionAirborneOperation>(&op)) {
    const auto state =
        base.physical.gameplay
            ? std::optional<std::uint32_t>(base.physical.gameplay->state)
            : std::nullopt;
    return ExecuteGraphMotionAirborneOperation(
        *p, std::get<GraphMotionAirborneInstance>(instance), phase, frame.dt,
        {a, s.airborne, physical.air_leg, base.prelanding_inputs, category,
         state, base.flags.doing_trick, base.busy_hands,
         base.playback_context.is_mirrored},
        error);
  }
  if (const auto *p = std::get_if<GraphMotionOffboardTimingOperation>(&op)) {
    std::optional<MotionGraphOffboardAirTiming> air;
    if (base.physical.gameplay) {
      const auto &v = *base.physical.gameplay;
      air = MotionGraphOffboardAirTiming{v.offboard_time_to_land,
                                         v.offboard_air_scalar_92,
                                         v.offboard_air_translation};
    }
    return p->Execute(std::get<MotionGraphOffboardTimingInstance>(instance),
                      {a, base.animation_phase, physical.offboard_cadence_phase,
                       air, physical.runout},
                      phase, error);
  }
  if (const auto *p = std::get_if<GraphMotionTrickLifecycleOperation>(&op)) {
    std::optional<MotionGraphTrickPhysicalPublication> trick;
    if (base.physical.gameplay) {
      const auto &v = *base.physical.gameplay;
      trick = MotionGraphTrickPhysicalPublication{
          v.footplant_duration, v.handplant_time, v.handplant_thresholds,
          v.landing_turning};
    }
    return p->Execute(std::get<MotionGraphTrickLifecycleInstance>(instance),
                      {a, s.tricks, base.riding, trick, base.landing_inputs,
                       physical.landing_velocity, category,
                       base.playback_context, frame.dt},
                      phase, error);
  }
  if (const auto *p = std::get_if<GraphMotionGrindOperation>(&op)) {
    return p->Execute(std::get<MotionGraphGrindState>(instance), a, s.grind,
                      physical.grind, frame.dt, phase, error);
  }
  if (const auto *p = std::get_if<GraphMotionOffboardWipeoutOperation>(&op)) {
    std::optional<MotionGraphOffboardTweakPhysical> tweak;
    if (base.physical.gameplay) {
      const auto &v = *base.physical.gameplay;
      tweak = MotionGraphOffboardTweakPhysical{v.offboard_time_to_land,
                                               v.offboard_air_scalar_92};
    }
    return p->Execute(std::get<MotionGraphOffboardWipeoutInstance>(instance),
                      {a, wipeout_controls, base.action_controls.wipeout,
                       s.wipeout, tweak, base.wipeout_condition_inputs,
                       base.playback_context},
                      phase, error);
  }
  if (std::holds_alternative<MotionGraphToggleBoardOperation>(op)) {
    return ExecuteGraphMotionToggleBoard(
        std::get<MotionGraphToggleBoardState>(instance), a,
        physical.toggle_board, phase, error);
  }
  error = "Unbound MotionGraph continuation operation";
  return false;
}
} // namespace atelier::skate
