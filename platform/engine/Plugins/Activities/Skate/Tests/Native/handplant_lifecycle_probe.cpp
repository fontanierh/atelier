// SPDX-License-Identifier: Apache-2.0
// The checker stages the complete unchanged numeric probe for its wire helpers.
// Its renamed entry point is never invoked by this composition probe.
#define main HandplantNumericProbeEntry
#include "handplant_probe.cpp"
#undef main
#include "AirReckoning.h"
#include "AirTrajectoryRuntime.h"
namespace {
void VectorOut(Output &o, Vec3 v) {
  o.Floats(std::array<float, 3>{v.x, v.y, v.z});
}
void BodyOut(Output &o, const BodySnapshot &b) {
  o.Word(b.state_flags);
  o.Floats(b.rates.orientation);
  for (auto c : b.rates.basis.columns)
    o.Floats(c);
  for (auto c : b.rates.world_inverse_inertia.columns)
    o.Floats(c);
  for (auto v :
       {b.rates.position, b.rates.linear_velocity, b.rates.angular_velocity,
        b.rates.force_acceleration, b.rates.torque_acceleration})
    VectorOut(o, v);
  o.Float(b.rates.kinetic_energy);
  o.Word(b.rates.cool_down);
}
void DynamicsOut(Output &o, const DriveDynamics &d) {
  for (auto p : {d.linear, d.angular}) {
    o.Floats(std::array<float, 3>{p.spring_or_max_velocity, p.damping,
                                  p.max_strength});
    o.Word(std::uint32_t(p.type));
  }
}
void DriveFramesOut(Output &o, const DriveFrames &f) {
  for (auto a : {f.body_a, f.body_b}) {
    o.Floats(a.orientation);
    VectorOut(o, a.translation);
  }
}
template <class F> void Block(Output &o, F f) {
  const auto at = o.words.size();
  o.Word(0);
  f();
  o.words[at] = std::uint32_t(o.words.size() - at - 1);
}
void Snapshot(Output &o, const Handplant &h, const AirReckoning &air,
              const SkeletonAir &sair, const PhysicalSimulationRuntime &p,
              const AnimatedSkeleton &a, const FootIk &ik,
              const SkeletonInputRuntime &input,
              const PhysicsAnimationInput &anim,
              const ProcessedPhysicsInput &processed,
              std::uint8_t board_animated) {
  o.Word(10);
  Block(o, [&] {
    OwnerOut(o, h);
    EffectsOut(o, p, ik, board_animated);
  });
  Block(o, [&] {
    const auto &s = air.state;
    o.Floats(std::array<float, 6>{s.spin_angle, s.spin_speed,
                                  s.secondary_lean_angle, s.flip_angle,
                                  s.flip_speed, s.flip_requested_speed});
    o.Matrix(s.spin_transform);
    o.Floats(s.flip_axis);
    o.Word(s.flip_active);
    o.Word(s.flip_side);
    for (auto w : p.riding.body_spin)
      o.Word(w);
    const auto &g = p.riding.reckoning;
    for (auto v :
         {g.dynamic_up, g.up, g.target, g.up_velocity, g.ground_normal})
      VectorOut(o, v);
    o.Float(g.ground_blend);
    for (auto f : {g.ground_filter, g.slow_filter, g.fast_filter})
      for (auto w : f.words)
        o.Word(w);
    const auto &f = p.riding.reckoning_frames;
    for (auto m :
         {f.ground, f.system, f.unflipped, f.inverse_system, f.body_flip})
      o.Matrix(m);
    o.Floats(f.heading);
    o.Float(f.target_lean_angle);
    o.Floats(f.lateral_tilt);
  });
  Block(o, [&] {
    const auto &r = p.roots;
    for (auto m :
         {r.board, r.inverse_board, r.animation_to_board, r.animation_to_world,
          r.world_to_animation, r.heading_alignment})
      o.Matrix(m);
    o.Floats(r.previous_board_position);
    o.Floats(r.predicted_board_position);
    o.Word(r.supplied_prediction.has_value());
    if (r.supplied_prediction)
      o.Floats(*r.supplied_prediction);
    o.Word(r.initialize_heading);
    const auto &f = p.board_frames;
    for (auto m : {f.physical_board, f.skate_root, f.animation_target,
                   f.com_frame, f.lifted_com_frame})
      o.Matrix(m);
    for (auto v : {f.centre_of_mass, f.previous_centre_of_mass, f.com_velocity,
                   f.local_centre_of_mass, f.local_board_position})
      o.Floats(v);
    o.Float(f.lift_height);
  });
  Block(o, [&] {
    for (auto m : p.animation_record.pose)
      o.Matrix(m);
    for (auto v : {p.animation_record.centre_of_mass,
                   p.animation_record.centre_of_mass_delta,
                   p.animation_record.com_to_deck_world,
                   p.animation_record.com_to_deck_world_delta})
      o.Floats(v);
    o.Float(p.animation_record.reset_scalar);
    for (auto m : a.targets)
      o.Matrix(m);
    for (auto m : {a.animation_board, a.unadjusted_board, a.animation_hips,
                   a.motion.trajectory, a.motion.inverse_trajectory,
                   a.motion.next_trajectory})
      o.Matrix(m);
    o.Floats(a.motion.velocity_world);
    o.Float(a.motion.previous_board_at_y);
    o.Float(a.board_at_y_delta);
    for (auto m : p.drive_frames)
      o.Matrix(m);
  });
  Block(o, [&] {
    const auto &s = ik.state;
    o.Word(s.feet_enabled);
    for (auto l : s.limbs) {
      o.Word(std::uint32_t(l.mode));
      o.Floats(std::array<float, 3>{l.board_blend, l.external_blend,
                                    l.target_blend});
      o.Word(l.external_target_set);
      o.Word(l.local_target_set);
      o.Floats(l.external_target_local_delta);
      o.Floats(l.part_position);
    }
    for (auto f : s.frames) {
      for (auto m : {f.target, f.world, f.external_world, f.board,
                     f.parent_world, f.external_parent_world, f.parent_board})
        o.Matrix(m);
      o.Word(f.within_contact_bounds);
    }
    for (auto t : s.external_targets) {
      o.Floats(t.world_position);
      o.Floats(t.animation_position);
      o.Floats(t.normal);
      o.Word(t.normal_set);
      o.Float(t.normal_blend);
    }
    for (auto c : s.contacts.feet) {
      o.Word(c.query_state);
      o.Floats(c.position);
      o.Floats(std::array<float, 2>{c.desired_offset, c.offset});
    }
    o.Word(s.contacts.support_failed);
    o.Word(s.contacts.support_failed_this_update);
  });
  Block(o, [&] {
    o.Floats(sair.board_animation.rotation_error);
    o.Word(sair.board_animation.blending);
    for (auto w : p.board.Hook().drive.frames)
      o.Word(w);
    for (auto w : p.board.Hook().drive.dynamics)
      o.Word(w);
    BodyOut(o, p.board.Hook().body);
    for (auto b : p.board.Bodies())
      BodyOut(o, b);
    for (auto b : p.skeleton.Bodies())
      BodyOut(o, b);
    for (auto b : p.skeleton_drives.targets.bodies)
      BodyOut(o, b);
  });
  Block(o, [&] {
    for (auto m : p.skeleton.record.pose)
      o.Matrix(m);
    for (auto v : p.skeleton.record.positions)
      o.Floats(v);
    for (auto v : p.skeleton.record.velocities)
      o.Floats(v);
    for (auto v : p.skeleton.record.velocity_changes)
      o.Floats(v);
    o.Floats(p.skeleton.record.centre_of_mass);
    o.Floats(p.skeleton.record.centre_of_mass_velocity);
    o.Float(p.skeleton.record.timestep);
    for (auto v : p.pose_errors.parts)
      o.Floats(v);
    for (auto v : p.pose_errors.extra)
      o.Floats(v);
    for (auto v : p.pose_errors.targets)
      o.Floats(v);
  });
  Block(o, [&] {
    for (auto f : p.skeleton_drives.targets.frames)
      DriveFramesOut(o, f);
    for (auto d : p.skeleton_drives.targets.dynamics)
      DynamicsOut(o, d);
    for (const auto &b : p.skeleton_drives.bones) {
      o.Word(b.has_value());
      if (b) {
        for (auto n : b->parent)
          o.Word(std::uint32_t(n));
        for (auto active : b->active)
          o.Word(active);
        for (auto f : b->frames)
          DriveFramesOut(o, f);
        for (auto d : b->dynamics.channels)
          DynamicsOut(o, d);
        o.Word(b->dynamics.mode);
        o.Floats(b->dynamics.strengths);
        o.Float(b->dynamics.transition_counter);
        o.Word(b->dynamics.transition_active);
      }
    }
  });
  Block(o, [&] {
    for (auto w :
         {processed.flags_2468, processed.flags_2472, processed.flags_2476,
          processed.flags_2480, processed.flags_2484, processed.state_2508,
          processed.category_2512, anim.fields.flags2468})
      o.Word(w);
    o.Word(input.reenable_requested);
    o.Word(input.teleporting);
    o.Word(input.force_mode);
    o.Floats(p.root_velocity);
    o.Floats(p.previous_root_position);
    o.Floats(p.reset_local_hips);
    o.Word(p.invalid_target_reset);
    o.Matrix(p.animation_board_to_physics);
    for (auto v : p.extra_target_positions)
      o.Floats(v);
    o.Floats(p.correction.board_prediction_error);
    o.Word(p.correction.pending);
  });
  Block(o, [&] {
    o.Matrix(a.board_offset.transform);
    o.Floats(std::array<float, 2>{a.board_offset.orientation_frames,
                                  a.board_offset.height_frames});
    o.Word(a.board_offset.orientation_refreshed);
    o.Word(a.board_offset.height_refreshed);
    const auto &l = a.landing;
    o.Word(l.active);
    o.Word(l.kind);
    o.Floats(std::array<float, 5>{l.time, l.position, l.velocity,
                                  l.previous_com_velocity,
                                  l.previous_animation_height});
    o.Word(l.previous_filtered_state);
    o.Float(l.desired_grind_com);
  });
}
[[maybe_unused]] SkeletonInputCollision Collision(const PhysicalSimulationRuntime &p) {
  return {p.collision_feedback.flags.compliant,
          p.collision_feedback.flags.has_impulse, p.collision_pose_error,
          p.skeleton_collision.partial_ragdoll,
          p.collision_feedback.drive_weight};
}
void Publish(Input &i, ProcessedPhysicsInput &p,
             PhysicalSimulationRuntime &physical) {
  p.flags_2468 = i.Word();
  p.flags_2472 = i.Word();
  p.flags_2476 = i.Word();
  p.flags_2480 = i.Word();
  p.flags_2484 = i.Word();
  p.state_2508 = i.Word();
  p.category_2512 = i.Word();
  p.timestep_2604 = i.Float();
  p.gravity_2648 = i.Float();
  p.vectors_544_560_592_608[2] = Raw(i.Floats<4>());
  p.vectors_400_416[0] = Raw(i.Floats<4>());
  p.vectors_464_480_496_512_528[0] = Raw(i.Floats<4>());
  p.vectors_544_560_592_608[1] = Raw(i.Floats<4>());
  p.vectors_544_560_592_608[3] = Raw(i.Floats<4>());
  physical.riding.reckoning_frames.heading = i.Floats<4>();
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 6)
    return 2;
  SettingsDatabase data;
  PhysicsSkeletons skeletons;
  AnimationPoseFrames frames;
  std::string error;
  if (!data.Load(File(argv[1]), error) ||
      !skeletons.Load(File(argv[2]), argv[4], error) ||
      !frames.rig.Load(File(argv[3]), error)) {
    std::cerr << error;
    return 2;
  }
  const auto *definition = skeletons.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  AnimationPoseEvaluator evaluator(std::move(frames));
  if (!evaluator.LoadAuthoredClips(argv[5], error)) {
    std::cerr << error;
    return 2;
  }
  const auto settings = PhysicalSimulationSettings::Load(
      data, *definition, evaluator.frames.rig, error);
  const auto asettings = AnimatedSkeletonSettings::Load(
      data, *definition, evaluator.frames.rig, false, error);
  if (!settings || !asettings)
    return 2;
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    // Additive metadata-world sentinel. Every old triangle-count wire keeps
    // its original meaning; the new branch uses the shared real constructor.
    const auto world_header = i.Word();
    i.at -= 4;
    auto world = world_header == 0xffffffffu ? (i.Word(), AuthoredQueryWorld(i))
                                             : World(i);
    std::vector<PlayerGrindPrimitive> edges;
    const auto n = i.Word();
    for (unsigned e = 0; e < n; ++e) {
      const auto start = i.Floats<4>(), end = i.Floats<4>();
      const auto owner = i.Wide();
      edges.push_back({start, end, owner});
    }
    auto physical = PhysicalSimulationRuntime::Initialize(
        *settings, data, evaluator, std::move(world),
        settings->Spawn({0, -.035f, 0}), error);
    if (!physical) {
      std::cerr << error;
      return 2;
    }
    auto &p = *physical;
    AnimatedSkeleton animated(*asettings);
    auto ik = FootIk::Load(data, evaluator.frames.rig, animated, error);
    auto input = SkeletonInputRuntime::Load(data, error);
    auto sair = SkeletonAir::Load(data, error);
    PhysicsAnimationInput anim;
    Handplant h;
    AirReckoning air;
    if (!ik || !input || !sair ||
        !anim.Load(data, evaluator.frames.rig, "normal", error) ||
        !h.Load(data, error) || !air.Load(data, error)) {
      std::cerr << error;
      return 2;
    }
    ProcessedPhysicsInput processed{};
    ResetProcessedPhysicsInput(processed);
    std::uint8_t board_animated = 0;
    std::vector<Mat4> globals;
    const SkeletonInputOwners owners{p, animated, *ik, anim};
    const auto rows = i.Word();
    o.Word(rows);
    Snapshot(o, h, air, *sair, p, animated, *ik, *input, anim, processed,
             board_animated);
    for (unsigned r = 0; r < rows; ++r) {
      const auto op = i.Word();
      o.Word(op);
      bool okay = true;
      std::optional<Mat4> target;
      error.clear();
      switch (op) {
      case 0:
        Publish(i, processed, p);
        break;
      case 1: {
        const auto kind = i.Word();
        globals.clear();
        if (kind < 4) {
          static const char *names[] = {"RIG_TPOSE", "POSTURE_STIFF_POSE",
                                        "POSTURE_SLOUCH_POSE",
                                        "POSTURE_BUFF_POSE"};
          PoseCommand command;
          command.kind = PoseCommand::Kind::Pose;
          command.name = names[kind];
          std::vector<Sqt> pose;
          if (!evaluator.Evaluate({command}, pose, error) ||
              !evaluator.Hierarchy(pose, globals, error))
            return 2;
        } else if (kind == 5) {
          PoseCommand command;
          command.kind = PoseCommand::Kind::Pose;
          command.name = "RIG_TPOSE";
          std::vector<Sqt> pose;
          if (!evaluator.Evaluate({command}, pose, error) ||
              !evaluator.Hierarchy(pose, globals, error))
            return 2;
          globals.resize(1);
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
            owners.AnimationOwners(), globals, landing, processed.timestep_2604,
            processed.flags_2468, processed.flags_2472, std::nullopt, error);
        break;
      }
      case 2:
        h.GroundQuery(processed, edges);
        break;
      case 3:
        okay = h.GroundUpdate(p, processed, animated, *ik, error);
        break;
      case 4: {
        AirTrajectoryRuntime queries;
        okay = h.Enter(p, processed, board_animated, queries, error);
        break;
      }
      case 5:
        okay =
            h.Update({processed, owners, *input, globals, *sair}, air, error);
        break;
      case 6: {
        const auto anchor = i.Floats<4>();
        const auto bone = i.Word();
        okay = AdvancePlantSkeleton(
            {processed, owners, *input, globals, *sair}, anchor,
            bone == 0xffffffffu ? std::nullopt
                                : std::optional<std::size_t>(bone),
            error);
        break;
      }
      case 7: {
        const bool right = i.Word() != 0;
        const auto position = i.Floats<4>();
        const auto delay = i.Word();
        HoldPlantFoot(p, *ik, right, position, delay);
        break;
      }
      case 8:
        sair->CapturePhysicsError(p.board, p.board_frames.animation_target);
        break;
      case 9:
        sair->ResetBoard();
        break;
      case 10: {
        const bool fast = i.Word() != 0;
        Mat4 result;
        okay = UpdateAnimatedSkeletonAir(
            *input, *sair, p.riding.reckoning_frames.system, processed, owners,
            globals, Collision(p), fast, result, error);
        if (okay)
          target = result;
        break;
      }
      case 11: {
        const auto com = i.Floats<4>();
        PhysicsPosePacket packet;
        packet.flags = i.Word();
        const auto frames = i.Word();
        std::memcpy(&packet.air_dismount_revert_frames, &frames, 4);
        Mat4 result;
        okay = UpdateKnownSkeletonAir(
            *input, *sair, p.riding.reckoning_frames.system, com, packet,
            processed, owners, globals, Collision(p), result, error);
        if (okay)
          target = result;
        break;
      }
      case 12:
        h.continuation = i.Word() != 0;
        break;
      case 13:
        if (i.Word())
          h.FullReset();
        else
          h.Reset();
        break;
      case 14: {
        const auto candidate = Candidate(i);
        const auto com = i.Floats<4>(), velocity = i.Floats<4>(),
                   normal = i.Floats<4>(), body = i.Floats<4>(),
                   heading = i.Floats<4>();
        h.Launch(candidate, com, velocity, normal, body, heading);
        break;
      }
      case 15:
        animated.motion.next_trajectory = i.Matrix();
        break;
      default:
        std::abort();
      }
      o.Status(okay, error);
      o.Word(target.has_value());
      if (target)
        o.Matrix(*target);
      Snapshot(o, h, air, *sair, p, animated, *ik, *input, anim, processed,
               board_animated);
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto w : o.words)
    for (unsigned b = 0; b < 4; ++b)
      std::cout.put(char(w >> (8 * b)));
  return 0;
}
