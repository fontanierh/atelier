// Immutable wire/owner helper prefixes are staged with exact boundaries/hash.
#include "GroundAnimationRuntime.h"
#include "ground_animation_helpers.inc"
namespace {
void JumpOut(Output &o, GroundJump v) {
  o.Floats(v.velocity);
  o.Float(v.scalar_16);
  o.Word(v.active);
}
void JumpSettingsOut(Output &o, const GroundAnimationSettings &a) {
  const auto &s = a.jump;
  o.Floats(s.vertical_response.x);
  o.Floats(s.vertical_response.y);
  for (auto graph : {s.y_scalar_vs_normal_y, s.speed_scalar_vs_angle,
                     s.minimum_height_vs_speed, s.maximum_height_vs_speed}) {
    o.Floats(graph.x);
    o.Floats(graph.y);
  }
  o.Floats(std::array<float, 8>{
      s.speed_response_max_speed, s.minimum_scalar, s.maximum_y_bonus,
      s.adjust_z_factor, s.adjust_x_factor, s.absolute_minimum_height,
      s.hippy_minimum_height, s.hippy_maximum_height});
  for (auto m : a.modes)
    o.Floats(std::array<float, 3>{m.minimum_height_64, m.minimum_height_68,
                                  m.maximum_height});
}
void GroundSnapshot(
    Output &o, const GroundAnimationRuntime &g,
    const GroundAnimationSettings &a, const GroundStateRuntime &ground,
    const GroundRuntime &runtime, const GroundPhaseLifecycle &life,
    const FootplantRuntime &foot, const Handplant &hand,
    const AirReckoning &air, const SkeletonAir &sair,
    const PhysicalSimulationRuntime &p, const AnimatedSkeleton &animated,
    const FootIk &ik, const SkeletonInputRuntime &input,
    const PhysicsAnimationInput &anim, const ProcessedPhysicsInput &processed,
    const AirOutputFields &pub, const WipeoutRequests &wipeout,
    const AirTrajectoryRuntime &trajectory) {
  o.Word(6);
  Block(o, [&] {
    JumpOut(o, g.jump);
    o.Word(g.launched);
    o.Floats(g.launch_velocity);
  });
  Block(o, [&] { JumpSettingsOut(o, a); });
  Block(o, [&] {
    o.Float(ground.steering.deck_tilt);
    o.Floats(ground.steering.targets);
    o.Floats(ground.steering.activation_time);
    o.Word(life.skeleton_elapsed_16505);
    o.Word(life.board_animated_290);
    o.Float(life.manual_drag_2724);
    o.Word(wipeout.mode);
    o.Float(wipeout.balance);
    o.Word(p.correction.pending);
  });
  Block(o, [&] {
    for (auto material : {p.settings.board.collision.wheel_material,
                          p.settings.board.standard_wheel_material})
      o.Floats(std::array<float, 3>{material.static_friction,
                                    material.dynamic_friction,
                                    material.restitution});
    for (const auto &b : p.board.Bodies())
      o.Float(b.inertia.linear_drag);
    for (const auto &b : p.board.Bodies())
      VectorOut(o, b.rates.linear_velocity);
  });
  Block(o, [&] {
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
    o.Word(runtime.collision_force.has_value());
    if (runtime.collision_force)
      for (auto v : {runtime.collision_force->force_2528,
                     runtime.collision_force->point_2544,
                     runtime.collision_force->vector_2592})
        o.Floats(v);
  });
  FootSnapshot(o, foot, trajectory, pub, wipeout, p.skeleton_collision);
  Snapshot(o, hand, air, sair, p, animated, ik, input, anim, processed,
           life.board_animated_290);
}
void GroundPublish(Input &i, ProcessedPhysicsInput &p, PhysicsAnimationInput &a,
                   GroundPhaseLifecycle &life, TrainerTuning &trainer) {
  p.flags_2468 = i.Word();
  p.flags_2472 = i.Word();
  p.flags_2476 = i.Word();
  p.flags_2480 = i.Word();
  p.flags_2484 = i.Word();
  p.flags_2488 = i.Word();
  p.state_variant_index_2528 = i.Word();
  p.state_2504 = i.Word();
  p.state_2508 = i.Word();
  p.category_2512 = i.Word();
  p.external_physics_1616.flags = i.Word();
  p.wheel_count_2556 = i.Word();
  p.timestep_2604 = i.Float();
  p.gravity_2648 = i.Float();
  p.scalar_2612 = i.Float();
  p.scalar_2616 = i.Float();
  p.scalar_2652 = i.Float();
  p.scalar_2656 = i.Float();
  p.state_timer_2664 = i.Float();
  p.scalar_2764 = i.Float();
  p.transition_2636 = i.Float();
  life.manual_drag_2724 = i.Float();
  a.fields.balance = i.Float();
  a.fields.brake = i.Float();
  a.extra.physical_body_spin = i.Float();
  a.extra.jump_strength = i.Float();
  a.extra.jump_controls = i.Floats<2>();
  trainer.pop = i.Float();
  p.vectors_400_416[0] = Raw(i.Floats<4>());
  p.vectors_400_416[1] = Raw(i.Floats<4>());
  for (auto &v : p.vectors_464_480_496_512_528)
    v = Raw(i.Floats<4>());
  for (auto &v : p.vectors_544_560_592_608)
    v = Raw(i.Floats<4>());
  p.prepared_jump_704 = Raw(i.Floats<4>());
  p.animation_com_to_deck_752 = Raw(i.Floats<4>());
  p.collision_pose_error_736 = Raw(i.Floats<4>());
}
GroundJumpInput JumpInput(Input &i) {
  const auto a = i.Word(), b = i.Word(), c = i.Word(), d = i.Word();
  const auto ef = i.Floats<4>(), f = i.Floats<4>(), v = i.Floats<4>(),
             gp = i.Floats<4>(), up = i.Floats<4>(), normal = i.Floats<4>(),
             com = i.Floats<4>(), prepared = i.Floats<4>();
  const float strength = i.Float();
  const auto controls = i.Floats<2>();
  const float gravity = i.Float(), speed = i.Float();
  return {a,  b,      c,   d,        ef,       f,        v,       gp,
          up, normal, com, prepared, strength, controls, gravity, speed};
}
} // namespace
int main(int argc, char **argv) {
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
    auto world = World(i);
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
    GroundAnimationSettings ga_settings;
    GroundAnimationRuntime ga;
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
        !runtime.Load(data, error) || !ga_settings.Load(data, error) ||
        !air_settings.Load(data, error) || !trajectory.Load(data, error))
      return 2;
    auto provider = PlayerGrindStaticProvider::FromConverted({}, error);
    if (!provider)
      return 2;
    trajectory.BindGrindWorld(
        std::make_shared<PlayerGrindStaticProvider>(*provider));
    auto selected = profiles.Select(1, 1, error);
    if (!selected)
      return 2;
    auto active = selected->Tuned(trainer);
    ProcessedPhysicsInput processed{};
    ResetProcessedPhysicsInput(processed);
    std::optional<BoardToolkit> toolkit;
    PhysicsPosePacket packet;
    AirOutputFields pub{};
    const auto rows = i.Word();
    o.Word(rows);
    auto snapshot = [&] {
      GroundSnapshot(o, ga, ga_settings, ground, runtime, life, foot, hand, air,
                     *sair, p, animated, *ik, *input, anim, processed, pub,
                     wipeout, trajectory);
    };
    snapshot();
    for (unsigned row = 0; row < rows; ++row) {
      const auto op = i.Word();
      o.Word(op);
      bool okay = true;
      Output extra;
      error.clear();
      const GroundAnimationOwners owners{
          p,          processed,    toolkit, ground, runtime, life,
          animated,   *ik,          anim,    *input, *sair,   wipeout,
          trajectory, air_settings, packet,  trainer};
      switch (op) {
      case 0:
        GroundPublish(i, processed, anim, life, trainer);
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
            owners.SkeletonOwners().AnimationOwners(), packet.hierarchy,
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
        okay = ga.Enter(owners, error);
        break;
      case 4:
        okay = ga.Advance(owners, active, ga_settings, error);
        break;
      case 5:
        ga.Exit(owners);
        break;
      case 6:
        for (auto &v : pub.jump_velocity_delta_112)
          v = i.Word();
        for (auto &v : pub.launch_velocity_128)
          v = i.Word();
        pub.launched_442 = std::uint8_t(i.Word());
        ga.Fill(processed, pub);
        for (auto v : pub.jump_velocity_delta_112)
          extra.Word(v);
        for (auto v : pub.launch_velocity_128)
          extra.Word(v);
        extra.Word(pub.launched_442);
        break;
      case 7:
        p.board.ForcesMut().Clear();
        break;
      case 8: {
        const auto tag = i.Word();
        p.board.ForcesMut().Append({tag,
                                    {i.Float(), i.Float(), i.Float()},
                                    {i.Float(), i.Float(), i.Float()}});
        break;
      }
      case 9:
        ga.jump.velocity = i.Floats<4>();
        ga.jump.scalar_16 = i.Float();
        ga.jump.active = i.Word() != 0;
        ga.launched = i.Word() != 0;
        ga.launch_velocity = i.Floats<4>();
        break;
      case 10:
        SetGroundAnimationDrag(p.board, i.Float());
        break;
      case 11: {
        const auto mode = i.Word();
        const auto value = CalculateGroundJump(
            JumpInput(i), ga_settings.modes[mode], ga_settings.jump);
        JumpOut(extra, value);
        break;
      }
      case 12: {
        const auto mode = i.Word(), surface = i.Word();
        selected = profiles.Select(mode, surface, error);
        okay = bool(selected);
        if (selected)
          active = selected->Tuned(trainer);
        break;
      }
      case 13:
        okay = trajectory.Load(data, error);
        break;
      case 14:
        trajectory.BindGrindWorld(
            std::make_shared<PlayerGrindStaticProvider>(*provider));
        break;
      case 15: {
        const auto fixture = i.Word();
        SettingsDatabase test;
        if (!test.Load(File(std::string(argv[6]) + "/load-" +
                            std::to_string(fixture) + "/settings.native"),
                       error))
          return 2;
        okay = ga_settings.Load(test, error);
        break;
      }
      case 16:
        sair->CapturePhysicsError(p.board, p.board_frames.animation_target);
        break;
      case 17:
        ground.steering.deck_tilt = i.Float();
        ground.steering.targets = i.Floats<2>();
        ground.steering.activation_time = i.Floats<2>();
        wipeout.mode = i.Word();
        wipeout.balance = i.Float();
        life.skeleton_elapsed_16505 = i.Word() != 0;
        life.board_animated_290 = std::uint8_t(i.Word());
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
