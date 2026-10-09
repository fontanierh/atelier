// Only explicit caller transport and read-only observations; every operation
// invokes the complete production owner over the canonical live objects.
#include "RenderPoseRuntime.h"
#include "render_pose_owner_helpers.inc"
namespace {
std::string Text(Input &i) {
  std::string out;
  for (auto n = i.Word(); n; --n)
    out += char(i.Word());
  return out;
}
void OutputOwner(Output &o, const SkeletonOutputRuntime &s,
                 const SkeletonWobble &w) {
  for (auto n : s.pose.bone_indices)
    o.Word(std::uint32_t(n));
  for (auto p : s.pose.geometry.parents) {
    o.Word(bool(p));
    if (p)
      o.Word(std::uint32_t(*p));
  }
  for (auto m : s.pose.geometry.inverse_part_frames)
    o.Matrix(m);
  for (auto n : s.pose.board_bones.All())
    o.Word(std::uint32_t(n));
  const auto &b = s.pose.board_settings;
  o.Floats(std::array<float, 4>{b.truck_tilt_scalar, b.truck_tilt_max_angle,
                                b.truck_tilt_wobble_scalar,
                                b.truck_displacement_max});
  o.Word(w.active);
  o.Word(w.landing);
  o.Float(w.time);
  o.Float(w.amplitude);
  o.Float(w.direction);
  o.Word(w.SelectedLandingCurves());
  const auto &v = s.deck_wobble;
  o.Word(v.sampled);
  o.Float(v.tilt);
  o.Float(v.squish);
  o.Word(v.remains_active);
  o.Float(s.compression_rest_height);
  for (const auto &g :
       {s.wobble_settings.takeoff_tilt, s.wobble_settings.landing_tilt,
        s.wobble_settings.takeoff_squish, s.wobble_settings.landing_squish}) {
    o.Floats(g.x);
    o.Floats(g.y);
  }
  o.Float(s.wobble_settings.maximum_time);
}
void FeetOwner(Output &o, const FootPhysicalOutputs &f) {
  for (auto v : f.state.previous_local_toes)
    o.Floats(v);
  o.Float(f.settings.deck_half_width);
  o.Float(f.settings.deck_total_half_length);
  o.Floats(f.settings.padding);
  for (auto v : f.output.local_velocity)
    o.Floats(v);
  for (auto v : f.output.world_velocity)
    o.Floats(v);
  for (auto v : f.output.within_deck_box)
    o.Word(v);
}
void FinalPose(Output &o, const std::vector<Mat4> &render,
               std::uint64_t generation, const SkaterAnimation &actor,
               const PhysicalPlayerInput &publication,
               const ProcessedPhysicsInput &p, const WipeoutRuntime &wipe) {
  o.Wide(generation);
  o.Word(std::uint32_t(render.size()));
  for (auto m : render)
    o.Matrix(m);
  o.Word(std::uint32_t(actor.pose.size()));
  for (auto q : actor.pose) {
    o.Floats(q.scale);
    o.Floats(q.rotation);
    o.Floats(q.translation);
  }
  o.Word(publication.skeleton.flag_597);
  o.Word(publication.skeleton.flag_600);
  o.Word(publication.skeleton.flag_601);
  for (auto v : publication.skeleton.anim_to_world_11920)
    for (auto w : v)
      o.Word(w);
  for (auto v :
       {publication.reckoning.vector_16, publication.reckoning.vector_64,
        publication.reckoning.vector_96})
    for (auto w : v)
      o.Word(w);
  o.Word(wipe.RequestsWipeout(p));
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 9)
    return 2;
  SettingsDatabase data;
  PhysicsSkeletons skeletons;
  AnimationPoseFrames frames;
  std::string error;
  if (!data.Load(File(argv[1]), error) ||
      !skeletons.Load(File(argv[2]), argv[4], error) ||
      !frames.rig.Load(File(argv[3]), error))
    return 2;
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  for (auto n = i.Word(); n; --n) {
    const auto name = Text(i);
    auto clip = std::make_shared<AnimationClipSamples>();
    if (!clip->Load(
            File(std::filesystem::path(argv[7]) / "clips" / (name + ".skate")),
            error) ||
        !frames.RegisterClip(clip, error))
      return 2;
  }
  auto source = std::make_shared<AnimationSource>();
  AnimationMetadata other;
  if (!source->metadata.Load(
          File(std::filesystem::path(argv[6]) / "bank-0.skate"), error) ||
      !other.Load(File(std::filesystem::path(argv[6]) / "bank-1.skate"),
                  error) ||
      !source->metadata.Merge(other, error))
    return 2;
  source->evaluator =
      std::make_shared<AnimationPoseEvaluator>(std::move(frames));
  auto &evaluator = *source->evaluator;
  if (!evaluator.LoadAuthoredClips(argv[5], error))
    return 2;
  const auto *definition = skeletons.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  const auto settings = PhysicalSimulationSettings::Load(
      data, *definition, evaluator.frames.rig, error);
  const auto asettings = AnimatedSkeletonSettings::Load(
      data, *definition, evaluator.frames.rig, false, error);
  if (!settings || !asettings)
    return 2;
  AnimationStockGraphs graphs;
  const auto graph = [&](std::string_view k, AnimationLoadedGraph &g) {
    if (!g.source.Load(File(std::filesystem::path(argv[8]) /
                            ("actor." + std::string(k) + ".native")),
                       error))
      return false;
    return g.binding.Bind(g.source, error) &&
           g.runtime.FromBinding(g.binding, error);
  };
  if (!graph("action", graphs.action) || !graph("motion", graphs.motion))
    return 2;
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    auto world = AuthoredQueryWorld(i);
    std::vector<PlayerGrindPrimitive> edges;
    for (auto n = i.Word(); n; --n) {
      auto start = i.Floats<4>(), end = i.Floats<4>();
      edges.push_back({start, end, i.Wide()});
    }
    (void)edges;
    auto physical = PhysicalSimulationRuntime::Initialize(
        *settings, data, evaluator, std::move(world),
        settings->Spawn({0, -.035f, 0}), error);
    if (!physical)
      return 2;
    auto &p = *physical;
    AnimatedSkeleton animated(*asettings);
    auto ik = FootIk::Load(data, evaluator.frames.rig, animated, error);
    auto input = SkeletonInputRuntime::Load(data, error);
    auto sair = SkeletonAir::Load(data, error);
    PhysicsAnimationInput anim;
    Handplant hand;
    AirReckoning air;
    WipeoutRuntime wipe;
    std::unique_ptr<SkaterAnimation> actor;
    if (!ik || !input || !sair ||
        !anim.Load(data, evaluator.frames.rig, "normal", error) ||
        !hand.Load(data, error) || !air.Load(data, error) ||
        !wipe.Load(data, error) ||
        !SkaterAnimation::FromSource(data, graphs, "", source, actor, error))
      return 2;
    std::vector<Mat4> render;
    if (!actor->EvaluateInitialPose(render, error))
      return 2;
    std::uint64_t generation = 0;
    auto output = SkeletonOutputRuntime::Load(data, evaluator.frames.rig,
                                              animated, error);
    auto feet = FootPhysicalOutputs::Load(data, error);
    if (!output || !feet)
      return 2;
    SkeletonWobble wobble;
    TruckSteeringState steering;
    ProcessedPhysicsInput processed{};
    ResetProcessedPhysicsInput(processed);
    PhysicalPlayerInput publication{};
    std::uint8_t board_animated = 0;
    const auto rows = i.Word();
    o.Word(rows);
    auto snapshot = [&] {
      const auto at = o.words.size();
      Snapshot(o, hand, air, *sair, p, animated, *ik, *input, anim, processed,
               board_animated);
      o.words[at] = 13;
      Block(o, [&] { OutputOwner(o, *output, wobble); });
      Block(o, [&] { FeetOwner(o, *feet); });
      Block(o, [&] {
        FinalPose(o, render, generation, *actor, publication, processed, wipe);
      });
    };
    snapshot();
    for (unsigned row = 0; row < rows; ++row) {
      auto op = i.Word();
      o.Word(op);
      bool okay = true;
      error.clear();
      Output extra;
      switch (op) {
      case 0:
        Publish(i, processed, p);
        break;
      case 1: {
        auto kind = i.Word();
        PoseCommand command;
        command.kind =
            kind == 4 ? PoseCommand::Kind::Clip : PoseCommand::Kind::Pose;
        if (kind == 4) {
          command.name = Text(i);
          command.time = i.Float();
        } else {
          static const char *names[] = {"RIG_TPOSE", "POSTURE_STIFF_POSE",
                                        "POSTURE_SLOUCH_POSE",
                                        "POSTURE_BUFF_POSE"};
          command.name = names[kind % 4];
        }
        okay = evaluator.Evaluate({command}, actor->pose, error);
        break;
      }
      case 2: {
        auto compression = output->AverageCompressions(p.board);
        extra.Floats(compression);
        okay = PublishRenderPose({p, animated, processed, publication, *ik,
                                  wipe, *actor, steering, wobble, *output,
                                  *feet, render, generation},
                                 compression, error);
        break;
      }
      case 3: {
        auto part = i.Word();
        p.skeleton.SetPartTransform(part, i.Matrix());
        break;
      }
      case 4:
        steering.targets = i.Floats<2>();
        break;
      case 5: {
        auto landing = i.Word() != 0, reverse = i.Word() != 0;
        output->TriggerWobble(wobble, landing, reverse);
        break;
      }
      case 6: {
        auto board = output->AdvanceWobble(wobble, p.skeleton, p.DeckFrame());
        extra.Matrix(board);
        break;
      }
      case 7: {
        const auto actual = i.Floats<4>(), predicted = i.Floats<4>();
        p.correction.ObserveBoard(actual, predicted);
        p.correction.pending = i.Word() != 0;
        break;
      }
      case 8: {
        auto dt = i.Float();
        feet->Publish(p.skeleton.record, dt);
        break;
      }
      case 9:
        feet->state.Reset();
        break;
      case 10: {
        auto part = i.Word();
        p.skeleton.record.velocities[part] = i.Floats<4>();
        break;
      }
      case 11: {
        std::vector<Mat4> globals, locals;
        okay = evaluator.Hierarchy(actor->pose, globals, error);
        for (auto q : actor->pose)
          locals.push_back(SqtToMatrix(q));
        extra.Word(std::uint32_t(globals.size()));
        for (auto m : globals)
          extra.Matrix(m);
        extra.Word(std::uint32_t(locals.size()));
        for (auto m : locals)
          extra.Matrix(m);
        if (okay)
          okay = output->Publish(
              animated, p.roots, p.skeleton, p.board,
              p.settings.board.step.base_truck_transforms, steering.targets,
              output->AverageCompressions(p.board), globals, locals, error);
        extra.Word(std::uint32_t(globals.size()));
        for (auto m : globals)
          extra.Matrix(m);
        extra.Word(std::uint32_t(locals.size()));
        for (auto m : locals)
          extra.Matrix(m);
        break;
      }
      case 12: {
        auto count = std::int32_t(i.Word()), detach = std::int32_t(i.Word());
        std::vector<std::int32_t> parents;
        for (auto n = i.Word(); n; --n)
          parents.push_back(std::int32_t(i.Word()));
        std::vector<Mat4> matrices;
        for (auto n = i.Word(); n; --n)
          matrices.push_back(i.Matrix());
        okay = ComposeRenderHierarchy(count, parents, detach, matrices, error);
        extra.Word(std::uint32_t(matrices.size()));
        for (auto m : matrices)
          extra.Matrix(m);
        break;
      }
      case 13: {
        auto fixture = i.Word(), kind = i.Word();
        SettingsDatabase loaded;
        if (!loaded.Load(File(std::filesystem::path(argv[8]) /
                              ("case-" + std::to_string(fixture)) /
                              "settings.native"),
                         error))
          return 2;
        if (kind == 0) {
          auto replacement = FootPhysicalOutputs::Load(loaded, error);
          okay = bool(replacement);
          if (replacement)
            feet = *replacement;
        } else {
          auto replacement = SkeletonOutputRuntime::Load(
              loaded, evaluator.frames.rig, animated, error);
          okay = bool(replacement);
          if (replacement) {
            output = *replacement;
            wobble = {};
            p.correction = {};
          }
        }
        break;
      }
      case 14: {
        auto n = i.Word();
        if (n > actor->pose.size())
          return 2;
        actor->pose.resize(n);
        break;
      }
      case 15: {
        auto part = i.Word();
        output->pose.bone_indices[part] = i.Word();
        break;
      }
      case 16: {
        auto part = i.Word();
        output->pose.geometry.parents[part] =
            i.Word() ? std::optional<std::size_t>(i.Word()) : std::nullopt;
        break;
      }
      case 17: {
        auto body = i.Word();
        const auto v = i.Floats<3>();
        p.board.BodiesMut()[body].rates.position = {v[0], v[1], v[2]};
        break;
      }
      case 18:
        generation = i.Wide();
        break;
      case 19: {
        const auto anchor = i.Floats<4>();
        const auto bone = i.Word();
        std::vector<Mat4> globals;
        okay = evaluator.Hierarchy(actor->pose, globals, error);
        if (okay) {
          actor->packet.hierarchy = globals;
          okay = AdvancePlantSkeleton(
              {processed, {p, animated, *ik, anim}, *input, globals, *sair},
              anchor,
              bone == UINT32_MAX ? std::nullopt
                                 : std::optional<std::size_t>(bone),
              error);
        }
        break;
      }
      case 20: {
        processed.flags_2468 = i.Word();
        processed.flags_2472 = i.Word();
        processed.flags_2476 = i.Word();
        processed.flags_2480 = i.Word();
        processed.flags_2484 = i.Word();
        processed.state_2508 = i.Word();
        processed.category_2512 = i.Word();
        processed.state_timer_2664 = i.Float();
        processed.player_state_value_2520 = i.Word();
        std::array<std::uint32_t, 4> normal;
        for (auto &word : normal)
          word = i.Word();
        processed.vectors_544_560_592_608[0] = normal;
        p.riding.ground.part_contact_count = std::uint8_t(i.Word());
        break;
      }
      default:
        return 2;
      }
      o.Status(okay, error);
      o.Word(std::uint32_t(extra.words.size()));
      for (auto w : extra.words)
        o.Word(w);
      snapshot();
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto w : o.words)
    for (unsigned lane = 0; lane < 4; ++lane)
      std::cout.put(char(w >> (lane * 8)));
  return 0;
}
