// The checker supplies exact, hashed prefixes from the existing facade probe
// and its explicit-publication helper. No production method is substituted.
#include "skater_animation_facade_helpers.h"
struct CompleteInput : Input {
  using Input::Input;
  bool Bool() { return Boolean(); }
  Vec3 Vector3() { return {Float(), Float(), Float()}; }
};
#define Input CompleteInput
#include "motion_graph_complete_publication.h"
#undef Input
namespace {
void CompleteSnapshot(Output &out, SkaterAnimation &actor,
                      const AnimationAdditionalResetFields &reset,
                      const std::vector<std::string> &names) {
  out.Snapshot(actor, reset, names);
  const auto &host = actor.complete_motion;
  out.Word(std::uint32_t(host.operations.size()));
  for (std::size_t id = 0; id < host.operations.size(); ++id) {
    const auto &operation = actor.motion.operations[id];
    using K = MotionGraphOperation::Kind;
    bool registered = operation.kind != K::Unsupported &&
                      operation.kind != K::Unported &&
                      !(operation.kind == K::Condition &&
                        (operation.condition.kind ==
                             GraphMotionCondition::Kind::Unsupported ||
                         operation.condition.kind ==
                             GraphMotionCondition::Kind::Unported));
    if (!std::holds_alternative<std::monostate>(host.operations[id]))
      registered = true;
    out.Word(registered);
  }
  out.Word(std::uint32_t(actor.motion.instances.size()));
  const auto &control = host.wipeout_controls;
  out.Word(control.seed_from_air_tweak);
  out.Word(control.gestures_enabled);
  for (auto value : control.gesture)
    out.Float(value);
  const auto &p = host.physical;
  std::uint32_t mask = 0;
  if (actor.animation.tree.skater_animation_flags)
    mask |= 1;
  if (actor.motion.playback_context.is_mirrored)
    mask |= 2;
  if (actor.motion.playback_context.board_available)
    mask |= 4;
  if (actor.motion.physical.gameplay)
    mask |= 8;
  if (actor.motion.physical.conditions.physical_state)
    mask |= 16;
  if (p.bump_acceleration)
    mask |= 32;
  if (p.offboard_cadence_phase)
    mask |= 64;
  if (p.runout)
    mask |= 128;
  if (p.air_leg)
    mask |= 256;
  if (actor.motion.prelanding_inputs)
    mask |= 512;
  if (p.landing_velocity)
    mask |= 1024;
  if (actor.motion.landing_inputs)
    mask |= 2048;
  if (p.grind)
    mask |= 4096;
  if (p.toggle_board)
    mask |= 8192;
  if (actor.motion.wipeout_condition_inputs)
    mask |= 16384;
  out.Word(mask);
  const auto &pending = actor.animation.tree.settable.Entries();
  out.Word(std::uint32_t(pending.size()));
  for (const auto &value : pending) {
    for (auto word : value.name)
      out.Word(word);
    out.Float(value.value);
    out.Word(value.normalized);
    out.Word(std::uint32_t(value.sequence_id));
  }
  for (const auto *name :
       {"fakie", "AirBodyTweak", "RetrieveBoard", "IA_BODYSPIN_OLLIE_FS_0_N",
        "IA_BODYSPIN_OLLIE_BS_0_N"}) {
    out.Word(actor.animation.channels.Has(name));
    out.Float(actor.animation.channels.Elapsed(name));
    out.Float(actor.animation.channels.Remaining(name));
    out.Word(actor.animation.channels.InTransition(name));
  }
}
AnimationAdditionalResetFields ResetFields() {
  AnimationAdditionalResetFields reset;
  reset.compression = .137f;
  reset.foot_ik_influence = {.317f, .731f};
  reset.next_step_position_valid = true;
  reset.actor_flag_1904_bit23 = true;
  reset.actor_flag_1908_bit2 = true;
  reset.external_impulse_active = true;
  reset.external_physics_input_active = true;
  reset.externally_controlled = true;
  reset.prevent_manual_respawn = true;
  reset.ignore_respawn_reset_button = 255;
  reset.force_braking = true;
  reset.truck_tightness = .113f;
  reset.wheel_hardness = .719f;
  for (auto &value : reset.auxiliary_vectors)
    value = {.137f, .317f, .731f, .113f};
  reset.requested_physics_mode = 0xdeadbeef;
  return reset;
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 6)
    return 2;
  const std::filesystem::path samples(argv[1]), metadata(argv[2]),
      fixtures(argv[3]), assets(argv[5]);
  const std::vector<std::uint8_t> bytes{
      std::istreambuf_iterator<char>(std::cin), {}};
  if (bytes.size() < 8 ||
      std::string(bytes.begin(), bytes.begin() + 8) != "ATASKTR4")
    return 2;
  CompleteInput input(bytes);
  Output out;
  out.extended = out.interactions = true;
  std::string error;
  auto source = std::make_shared<AnimationSource>();
  AnimationMetadata other;
  AnimationPoseFrames frames;
  SettingsDatabase settings;
  if (!source->metadata.Load(File(metadata / "bank-0.skate"), error) ||
      !other.Load(File(metadata / "bank-1.skate"), error) ||
      !source->metadata.Merge(other, error) ||
      !frames.rig.Load(File(samples / "rig.skate"), error) ||
      !settings.Load(File(argv[4]), error)) {
    std::cerr << error;
    return 2;
  }
  const auto clip_count = input.Word();
  for (std::uint32_t i = 0; i < clip_count; ++i) {
    const auto name = input.String();
    auto clip = std::make_shared<AnimationClipSamples>();
    if (!clip->Load(File(samples / "clips" / (name + ".skate")), error) ||
        !frames.RegisterClip(clip, error)) {
      std::cerr << error;
      return 2;
    }
  }
  source->evaluator =
      std::make_shared<AnimationPoseEvaluator>(std::move(frames));
  if (!source->evaluator->LoadAuthoredClips(assets, error)) {
    std::cerr << error;
    return 2;
  }
  std::vector<std::string> names;
  for (auto count = input.Word(); count; --count)
    names.push_back(input.String());
  const auto count = input.Word();
  out.Word(count);
  for (std::uint32_t c = 0; c < count; ++c) {
    const auto id = input.Word();
    const auto pro = input.String();
    const auto graph = [&](std::uint32_t index, AnimationStockGraphs &result) {
      return LoadGraph(fixtures / ("actor-" + std::to_string(index) +
                                   ".action.simulation"),
                       result.action, error) &&
             LoadGraph(fixtures / ("actor-" + std::to_string(index) +
                                   ".motion.simulation"),
                       result.motion, error);
    };
    AnimationStockGraphs graphs;
    if (!graph(id, graphs)) {
      std::cerr << error;
      return 2;
    }
    std::unique_ptr<SkaterAnimation> actor;
    const bool constructed = SkaterAnimation::FromSource(settings, graphs, pro,
                                                         source, actor, error);
    out.Status(constructed, error);
    if (!constructed) {
      std::cerr << error;
      return 2;
    }
    auto reset = ResetFields();
    const auto steps = input.Word();
    out.Word(steps);
    CompleteSnapshot(out, *actor, reset, names);
    for (std::uint32_t step = 0; step < steps; ++step) {
      switch (input.Word()) {
      case 0: {
        const auto dt = input.Float();
        const auto map = input.Map();
        const auto physical = input.Physical();
        const bool ok = actor->Advance(graphs, dt, map, physical, reset, error);
        out.Status(ok, error);
        break;
      }
      case 1: {
        const auto natural = input.Word(), style = input.Word();
        actor->SetCustomisation(natural, style);
        out.Status(true, {});
        break;
      }
      case 2:
        actor->RequestCheckpointStance(input.Word());
        out.Status(true, {});
        break;
      case 3: {
        const auto name = input.String(), animation = input.String();
        const auto channel = input.Channel();
        bool created = false;
        const bool ok = actor->animation.NewChannel(name, animation, channel,
                                                    created, error);
        out.Status(ok, error);
        if (ok)
          out.Word(created);
        break;
      }
      case 4: {
        const auto name = input.String();
        const auto time = input.Float();
        const bool last = input.Boolean();
        actor->animation.channels.EndWith(name, time, last);
        out.Status(true, {});
        break;
      }
      case 5: {
        std::vector<Mat4> hierarchy;
        const bool ok = actor->EvaluateInitialPose(hierarchy, error);
        out.Status(ok, error);
        if (ok)
          out.Matrices(hierarchy);
        break;
      }
      case 6:
        actor->animation.tree.posture.SetProfile(input.Word());
        out.Status(true, {});
        break;
      case 7:
        actor->action_controller.EndAllBehaviors(actor->action);
        actor->motion_controller.EndAllBehaviors(actor->complete_motion);
        out.Status(true, {});
        break;
      case 8:
        input.ExtraPhysical(actor->motion);
        out.Status(true, {});
        break;
      case 9:
        input.InteractionPhysical(actor->motion);
        out.Status(true, {});
        break;
      case 10:
        Physical(input, actor->complete_motion);
        out.Status(true, {});
        break;
      case 11: {
        const auto replacement = input.Word(), settings_id = input.Word();
        AnimationStockGraphs replacement_graphs;
        if (!graph(replacement, replacement_graphs)) {
          std::cerr << error;
          return 2;
        }
        SettingsDatabase alternate;
        const SettingsDatabase *data = &settings;
        if (settings_id != 0xffffffffu) {
          if (!alternate.Load(
                  File(fixtures /
                       ("settings-" + std::to_string(settings_id) + ".simulation")),
                  error)) {
            std::cerr << error;
            return 2;
          }
          data = &alternate;
        }
        const bool ok = SkaterAnimation::FromSource(*data, replacement_graphs,
                                                    pro, source, actor, error);
        out.Status(ok, error);
        if (ok)
          graphs = std::move(replacement_graphs);
        break;
      }
      default:
        return 2;
      }
      CompleteSnapshot(out, *actor, reset, names);
    }
  }
  if (!input.ok || input.Remaining() != 0)
    return 2;
  std::cout.write(reinterpret_cast<const char *>(out.bytes.data()),
                  std::streamsize(out.bytes.size()));
  return std::cout ? 0 : 2;
}
