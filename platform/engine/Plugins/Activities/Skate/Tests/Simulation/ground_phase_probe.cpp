// This fixture borrows actual owners and invokes the complete production phase.
#include "GroundPhaseRuntime.h"
#include "PlayerInputPhase.h"
#include "ground_phase_helpers.inc"
struct GroundInputReader {
  Input &source;
  std::uint32_t Word() { return source.Word(); }
  float Float() { return source.Float(); }
  template <std::size_t N> std::array<float, N> Floats() {
    return source.Floats<N>();
  }
  template <std::size_t N> std::array<std::uint32_t, N> Words() {
    std::array<std::uint32_t, N> value;
    for (auto &v : value)
      v = Word();
    return value;
  }
  Vec3 Three() { return {Float(), Float(), Float()}; }
  Mat4 Matrix() { return source.Matrix(); }
  template <std::size_t N> PointGraph<N> Curve() {
    return {Floats<N>(), Floats<N>()};
  }
};
struct GroundOutputWriter : Output {
  void Value(std::uint32_t v) { Word(v); }
  void Value(float v) { Float(v); }
  void Value(Vec3 v) {
    Float(v.x);
    Float(v.y);
    Float(v.z);
  }
  template <class T, std::size_t N> void Value(const std::array<T, N> &v) {
    for (const auto &x : v)
      Value(x);
  }
  template <std::size_t N> void Curve(const PointGraph<N> &c) {
    Value(c.x);
    Value(c.y);
  }
};
// GENERATED_GROUND_PROTOCOL
namespace {
// GENERATED_TRANSPORT_HELPERS
void PhaseSnapshot(
    Output &o, const GroundStateRuntime &g, const GroundRuntime &r,
    const GroundSettings &settings, const GroundPhaseLifecycle &life,
    const SkeletonWobble &wobble, const OffboardGrabCache &grab,
    const FootplantRuntime &foot, const Handplant &hand,
    const AirReckoning &air, const SkeletonAir &sair,
    const PhysicalSimulationRuntime &p, const AnimatedSkeleton &animated,
    const FootIk &ik, const SkeletonInputRuntime &input,
    const PhysicsAnimationInput &anim, const ProcessedPhysicsInput &processed,
    const WipeoutRequests &wipeout, const AirTrajectoryRuntime &trajectory) {
  o.Word(8);
  Block(o, [&] {
    GroundOutputWriter row;
    Observe(row, g.state);
    Observe(row, g.pumping);
    row.Value(g.wobble.words);
    Observe(row, g.steering);
    Observe(row, g.speed);
    Observe(row, g.manual);
    row.Float(g.heading_previous);
    row.Word(g.entered);
    row.Value(g.output_settings.pushable_speed_terms_4_8);
    row.Float(g.output_settings.mode_speed_threshold_0);
    for (bool b : g.auto_push_enabled)
      row.Word(b);
    row.Value(std::array<float, 4>{
        g.entry_settings.deck_angular_drag, g.entry_settings.powerslide_exit,
        g.entry_settings.landing_strength, g.entry_settings.landing_offset});
    Observe(row, g.pumping_settings.settings);
    for (const auto &m : g.pumping_settings.modes) {
      Observe(row, m.controller);
      row.Float(m.unintentional_scalar);
    }
    o.words.insert(o.words.end(), row.words.begin(), row.words.end());
  });
  Block(o, [&] {
    o.Floats(r.retained_board_normal);
    const auto &c = r.contact;
    o.Word(c.active_2731);
    o.Word(c.tag_16_force.tag);
    VectorOut(o, c.tag_16_force.force_world);
    VectorOut(o, c.tag_16_force.point_body);
    o.Floats(c.vector_2688);
    o.Float(c.scalar_2704);
    o.Word(c.animated_board_2708);
    o.Word(bool(r.collision_force));
    if (r.collision_force) {
      o.Floats(r.collision_force->force_2528);
      o.Floats(r.collision_force->point_2544);
      o.Floats(r.collision_force->vector_2592);
    }
  });
  Block(o, [&] {
    const auto &c = life.skeleton_controller;
    for (auto v : {c.effective, c.requested, std::uint32_t(c.has_request),
                   std::uint32_t(c.override_enabled), std::uint32_t(c.flag_18),
                   std::uint32_t(life.skeleton_elapsed_16505),
                   std::uint32_t(life.board_animated_290)})
      o.Word(v);
    o.Float(life.manual_drag_2724);
    o.Word(bool(life.edge));
    if (life.edge) {
      o.Word(life.edge->flags);
      o.Floats(life.edge->point);
      VectorOut(o, life.edge->start);
      VectorOut(o, life.edge->end);
    }
    o.Word(bool(life.pending_wall_jump));
    if (life.pending_wall_jump) {
      GroundOutputWriter row;
      Observe(row, *life.pending_wall_jump);
      o.words.insert(o.words.end(), row.words.begin(), row.words.end());
    }
    o.Word(wobble.active);
    o.Word(wobble.landing);
    o.Floats(
        std::array<float, 3>{wobble.time, wobble.amplitude, wobble.direction});
  });
  Block(o, [&] {
    const auto &g = p.possession_live;
    o.Word(p.board_wiping_out);
    o.Word(p.board.CollisionGroup());
    o.Word(g.volumes.deck);
    o.Word(g.volumes.trucks);
    o.Word(g.volumes.wheels);
    o.Word(std::uint32_t(g.volumes.deck_children.size()));
    for (bool v : g.volumes.deck_children)
      o.Word(v);
    for (auto m : {p.settings.board.collision.wheel_material,
                   p.settings.board.standard_wheel_material,
                   p.settings.board.collision.truck_material,
                   p.settings.board.collision.deck_material})
      o.Floats(std::array<float, 3>{m.static_friction, m.dynamic_friction,
                                    m.restitution});
    for (const auto &b : p.board.Bodies())
      o.Floats(
          std::array<float, 2>{b.inertia.linear_drag, b.inertia.angular_drag});
    const auto &q = p.board.Forces();
    o.Word(std::uint32_t(q.Count()));
    for (std::size_t k = 0; k < q.Count(); ++k) {
      const auto &v = q.Entries()[k];
      o.Word(v.tag);
      VectorOut(o, v.force_world);
      VectorOut(o, v.point_body);
    }
  });
  Block(o, [&] {
    GroundOutputWriter row;
    OutGroundGrab(row, grab);
    o.words.insert(o.words.end(), row.words.begin(), row.words.end());
  });
  Block(o, [&] {
    for (const auto &vector : processed.vectors_400_416)
      for (auto v : vector)
        o.Word(v);
    for (auto v : {processed.flags_2468, processed.flags_2472,
                   processed.flags_2476, processed.state_variant_index_2528,
                   processed.actor_query_2948, processed.actor_query_2952})
      o.Word(v);
  });
  Block(o, [&] {
    GroundOutputWriter row;
    Observe(row, settings);
    o.words.insert(o.words.end(), row.words.begin(), row.words.end());
  });
  Block(o, [&] {
    const auto &probes = p.riding.probes;
    auto state = [&](const BoardProbeState &s) {
      VectorOut(o, s.start);
      VectorOut(o, s.point);
      VectorOut(o, s.normal);
      o.Word(s.surface_tag);
      o.Word(s.hit);
    };
    auto hit = [&](const std::optional<BoardProbeHit> &h) {
      o.Word(bool(h));
      if (h) {
        VectorOut(o, h->point);
        VectorOut(o, h->normal);
        o.Word(h->surface_tag);
      }
    };
    state(probes.deck);
    state(probes.wall);
    o.Word(bool(probes.wall_line));
    if (probes.wall_line) {
      VectorOut(o, probes.wall_line->start);
      VectorOut(o, probes.wall_line->end);
    }
    o.Word(bool(probes.pending));
    if (probes.pending) {
      hit(probes.pending->deck);
      o.Word(bool(probes.pending->wall));
      if (probes.pending->wall)
        hit(*probes.pending->wall);
    }
  });
  FootSnapshot(o, foot, trajectory, AirOutputFields{}, wipeout,
               p.skeleton_collision);
  Snapshot(o, hand, air, sair, p, animated, ik, input, anim, processed,
           life.board_animated_290);
}
void PhaseOutcome(Output &o, const GroundBoardOutcome &s) {
  o.Word(std::uint32_t(s.kind));
  o.Word(s.tag_15_queued);
  o.Word(s.ordinary.manual_correction);
  o.Word(s.ordinary.terminal_force_tag);
  o.Word(s.ordinary.terminal_force_queued);
  o.Word(s.ordinary.speed_model_reset);
}
} // namespace
int main(int argc, char **argv) {
  // The unchanged shared lifecycle prefix includes this old wire adapter.
  // Retain its body for provenance; this phase uses GroundPublish instead.
  (void)&Publish;
  if (argc != 7)
    return 2;
  SettingsDatabase data;
  PhysicsSkeletons skeletons;
  AnimationPoseFrames frames;
  std::string error;
  if (!data.Load(File(argv[1]), error) ||
      !skeletons.Load(File(argv[2]), argv[4], error) ||
      !frames.rig.Load(File(argv[3]), error))
    return 2;
  const auto *definition = skeletons.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  AnimationPoseEvaluator evaluator(std::move(frames));
  if (!evaluator.LoadAuthoredClips(argv[5], error))
    return 2;
  const auto settings = PhysicalSimulationSettings::Load(
      data, *definition, evaluator.frames.rig, error);
  const auto asettings = AnimatedSkeletonSettings::Load(
      data, *definition, evaluator.frames.rig, false, error);
  GroundProfiles profiles;
  if (!settings || !asettings || !profiles.Load(data, error))
    return 2;
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    auto world = AuthoredQueryWorld(i);
    auto pvalue = PhysicalSimulationRuntime::Initialize(
        *settings, data, evaluator, std::move(world),
        settings->Spawn({0, -.035f, 0}), error);
    if (!pvalue)
      return 2;
    auto &p = *pvalue;
    AnimatedSkeleton animated(*asettings);
    auto ik = FootIk::Load(data, evaluator.frames.rig, animated, error);
    auto input = SkeletonInputRuntime::Load(data, error);
    auto sair = SkeletonAir::Load(data, error);
    PhysicsAnimationInput anim;
    Handplant hand;
    FootplantRuntime foot;
    AirReckoning air;
    GroundStateRuntime ground;
    GroundRuntime runtime;
    SkeletonWobble wobble;
    OffboardGrabCache grab;
    AirStateSettings air_settings;
    AirTrajectoryRuntime trajectory;
    GroundPhaseLifecycle life;
    TrainerTuning trainer;
    WipeoutRequests wipeout;
    wipeout.InitializePlayer();
    if (!ik || !input || !sair ||
        !anim.Load(data, evaluator.frames.rig, "normal", error) ||
        !hand.Load(data, error) || !foot.Load(data, error) ||
        !air.Load(data, error) || !ground.Load(data, true, error) ||
        !runtime.Load(data, error) || !air_settings.Load(data, error) ||
        !trajectory.Load(data, error))
      return 2;
    auto provider = ReadProvider(i);
    trajectory.BindGrindWorld(
        std::make_shared<PlayerGrindStaticProvider>(provider));
    auto selected = profiles.Select(1, 1, error);
    if (!selected)
      return 2;
    auto active = selected->Tuned(trainer);
    ProcessedPhysicsInput processed{};
    ResetProcessedPhysicsInput(processed);
    std::optional<BoardToolkit> toolkit;
    PhysicsPosePacket packet;
    const auto rows = i.Word();
    o.Word(rows);
    auto snapshot = [&] {
      PhaseSnapshot(o, ground, runtime, active, life, wobble, grab, foot, hand,
                    air, *sair, p, animated, *ik, *input, anim, processed,
                    wipeout, trajectory);
    };
    snapshot();
    for (unsigned row = 0; row < rows; ++row) {
      const auto op = i.Word();
      o.Word(op);
      bool okay = true;
      Output extra;
      error.clear();
      const GroundPhaseOwners owners{
          p,        processed, toolkit,  ground,     runtime,     life,
          animated, *ik,       anim,     air,        wobble,      grab,
          wipeout,  hand,      provider, trajectory, air_settings};
      switch (op) {
      case 0:
        GroundPublish(i, processed, anim, life, trainer);
        processed.category_2516 = i.Word();
        processed.frames_since_teleport_2584 = i.Word();
        processed.time_since_last_input_2748 = i.Float();
        processed.time_on_ground_2752 = i.Float();
        processed.signed_ground_time_2756 = i.Float();
        processed.truck_tightness_2760 = i.Float();
        processed.crouch_2776 = i.Float();
        processed.crouch_delta_2780 = i.Float();
        processed.spin_input_2672 = i.Float();
        processed.actor_query_2948 = i.Word();
        processed.actor_query_2952 = i.Word();
        processed.vectors_720_784_800_816_832_864[0] = Raw(i.Floats<4>());
        anim.fields.turn = i.Float();
        anim.fields.hard_turn = i.Float();
        break;
      case 1: {
        const auto kind = i.Word();
        packet.hierarchy.clear();
        if (kind != 4) {
          static const char *names[] = {"RIG_TPOSE", "POSTURE_STIFF_POSE",
                                        "POSTURE_SLOUCH_POSE",
                                        "POSTURE_BUFF_POSE"};
          PoseCommand command;
          command.kind = PoseCommand::Kind::Pose;
          command.name = names[kind == 5 ? 0 : kind];
          std::vector<Sqt> pose;
          if (!evaluator.Evaluate({command}, pose, error) ||
              !evaluator.Hierarchy(pose, packet.hierarchy, error))
            return 2;
          if (kind == 5)
            packet.hierarchy.resize(1);
        }
        const auto deck = p.DeckFrame();
        const LandingInput landing{0,
                                   processed.flags_2468,
                                   processed.flags_2472,
                                   processed.flags_2476,
                                   0,
                                   p.skeleton.record.centre_of_mass_velocity[1],
                                   p.skeleton.record.centre_of_mass[1] -
                                       deck[3][1],
                                   0};
        okay = animated.ProcessPose(
            {p.animation_record, p.roots, p.board_frames}, packet.hierarchy,
            landing, processed.timestep_2604, processed.flags_2468,
            processed.flags_2472, std::nullopt, error);
        break;
      }
      case 2:
        if (i.Word())
          toolkit = BoardToolkit::FromBoard(
              p.board, processed.flags_2468, processed.scalar_2612,
              Decode(processed.vectors_464_480_496_512_528[0]),
              Decode(processed.vectors_544_560_592_608[0]));
        else
          toolkit.reset();
        break;
      case 3:
        okay = EnterGroundPhase(owners, error);
        break;
      case 4: {
        auto result = AdvanceGroundPhase(owners, active, error);
        okay = bool(result);
        if (result)
          PhaseOutcome(extra, *result);
        break;
      }
      case 5:
        ResetGroundBoardState(ground, runtime, life, p.board_wiping_out);
        break;
      case 6:
        okay = hand.GroundUpdate(p, processed, animated, *ik, error);
        break;
      case 7:
        okay = UpdateGroundSkeletonInput(owners, *input, *sair,
                                         packet.hierarchy, error);
        break;
      case 8:
        p.board.ForcesMut().Clear();
        break;
      case 9: {
        const auto tag = i.Word();
        p.board.ForcesMut().Append({tag,
                                    {i.Float(), i.Float(), i.Float()},
                                    {i.Float(), i.Float(), i.Float()}});
        break;
      }
      case 10: {
        GroundInputReader reader{i};
        ground.state = ReadPhysicsGroundState(reader);
        ground.pumping = ReadPumpingState(reader);
        ground.entered = i.Word() != 0;
        break;
      }
      case 11: {
        auto &c = life.skeleton_controller;
        c.effective = i.Word();
        c.requested = i.Word();
        c.has_request = i.Word() != 0;
        c.override_enabled = i.Word() != 0;
        c.flag_18 = i.Word() != 0;
        life.skeleton_elapsed_16505 = i.Word() != 0;
        life.board_animated_290 = std::uint8_t(i.Word());
        air.state.spin_angle = i.Float();
        air.state.spin_speed = i.Float();
        wipeout.mode = i.Word();
        wipeout.balance = i.Float();
        p.board_wiping_out = i.Word() != 0;
        break;
      }
      case 12: {
        const auto seed = i.Word();
        const auto flags = i.Word();
        SeedGroundGrab(grab, seed, std::uint8_t(flags));
        break;
      }
      case 13:
        if (i.Word()) {
          const auto flags = i.Word();
          const auto point = i.Floats<4>();
          const Vec3 start{i.Float(), i.Float(), i.Float()},
              end{i.Float(), i.Float(), i.Float()};
          life.edge = GroundPhaseEdge{flags, point, start, end};
        } else
          life.edge.reset();
        break;
      case 14:
        if (i.Word()) {
          GroundInputReader reader{i};
          life.pending_wall_jump = ReadGroundLaunchInfo(reader);
        } else
          life.pending_wall_jump.reset();
        break;
      case 15: {
        const auto mode = i.Word(), surface = i.Word();
        selected = profiles.Select(mode, surface, error);
        okay = bool(selected);
        if (selected)
          active = selected->Tuned(trainer);
        break;
      }
      case 16:
        okay = trajectory.Load(data, error);
        break;
      case 17:
        trajectory.BindGrindWorld(
            std::make_shared<PlayerGrindStaticProvider>(provider));
        break;
      case 18: {
        const auto normal = Decode(processed.vectors_464_480_496_512_528[0]),
                   up = Decode(processed.vectors_464_480_496_512_528[4]);
        const auto com = p.animation_record.ComToDeck();
        p.riding.UpdateGroundReckoning(
            p.board, {com, anim.extra.physical_body_spin}, processed.flags_2468,
            anim.fields.balance, false,
            {{normal[0], normal[1], normal[2]},
             {up[0], up[1], up[2]},
             processed.scalar_2652,
             processed.scalar_2616,
             std::int32_t(processed.wheel_count_2556)});
        break;
      }
      case 19:
        extra.Word(p.collision_feedback.flags.compliant);
        extra.Word(p.collision_feedback.flags.has_impulse);
        extra.Word(p.skeleton_collision.partial_ragdoll);
        extra.Floats(p.collision_pose_error);
        extra.Float(p.collision_feedback.drive_weight);
        break;
      case 20: {
        const auto normal = Decode(processed.vectors_464_480_496_512_528[0]),
                   up = Decode(processed.vectors_544_560_592_608[0]);
        if (!toolkit)
          return 2;
        const auto position = toolkit->deck[3];
        p.riding.probes.PrepareWall({processed.state_2508,
                                     {normal[0], normal[1], normal[2]},
                                     {up[0], up[1], up[2]},
                                     {position[0], position[1], position[2]},
                                     processed.time_on_ground_2752});
        okay = p.riding.probes.Start(p.board, p.world, error) &&
               p.riding.probes.Publish(error);
        break;
      }
      case 21:
        okay = p.riding.probes.Start(p.board, p.world, error);
        break;
      case 22:
        okay = p.riding.probes.Publish(error);
        break;
      case 23:
        p.riding.probes.ResetResults();
        break;
      default:
        return 2;
      }
      o.Status(okay, error);
      o.Word(std::uint32_t(extra.words.size()));
      for (auto v : extra.words)
        o.Word(v);
      snapshot();
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto v : o.words)
    for (unsigned k = 0; k < 4; ++k)
      std::cout.put(char(v >> (8 * k)));
  return std::cout ? 0 : 2;
}
