// SPDX-License-Identifier: Apache-2.0
#include "Braking.h"
#include "GroundAnimationRuntime.h"
#include "GroundJumpMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
Vec4 Decode(const RawVector &words) {
  Vec4 result;
  std::memcpy(result.data(), words.data(), sizeof(result));
  return result;
}
Vec3 Xyz(Vec4 v) { return {v[0], v[1], v[2]}; }
QueuedPointForce PointForce(std::uint32_t tag, const std::array<float, 8> &v) {
  return {tag, {v[0], v[1], v[2]}, {v[4], v[5], v[6]}};
}
AirStateBindingInput Bind(GroundAnimationOwners o) {
  // These are all the live fields read by the original launch_info and
  // selector_input helpers. Frame-only fields of the shared view are unused.
  const auto &p = o.processed;
  const auto &f = o.physical;
  const auto g = f.settings.board.step.simulation.gravity_acceleration;
  AirStateBindingInput b{};
  b.vectors_400_416 = p.vectors_400_416;
  b.vectors_464_480_496_512_528 = p.vectors_464_480_496_512_528;
  b.vectors_544_560_592_608 = p.vectors_544_560_592_608;
  b.prepared_jump_704 = p.prepared_jump_704;
  b.flags_2468 = p.flags_2468;
  b.flags_2472 = p.flags_2472;
  b.flags_2476 = p.flags_2476;
  b.state_2504 = p.state_2504;
  b.state_variant_index_2528 = p.state_variant_index_2528;
  b.external_physics_flags = p.external_physics_1616.flags;
  b.transition_2636 = p.transition_2636;
  b.timestep_2604 = p.timestep_2604;
  b.world_gravity = {g.x, g.y, g.z, 0};
  b.reckoning_system = f.riding.reckoning_frames.system;
  b.reckoning_inverse = f.riding.reckoning_frames.inverse_system;
  b.skeleton_local_centre_of_mass = f.board_frames.local_centre_of_mass;
  b.skeleton_local_board_position = f.board_frames.local_board_position;
  if (o.toolkit)
    b.toolkit_deck = o.toolkit->deck;
  b.trajectory_cone_x = o.trajectory.settings.cone_x;
  b.trajectory_cone_z = o.trajectory.settings.cone_z;
  return b;
}
} // namespace
void SetGroundAnimationDrag(BoardRuntime &board, float drag) {
  for (auto &body : board.BodiesMut())
    body.inertia.linear_drag = drag * ground_jump_math::Float(0x426fffff);
}
bool GroundAnimationRuntime::AdvanceBoard(GroundAnimationOwners o,
                                          const GroundSettings &s,
                                          const GroundAnimationSettings &a,
                                          std::string &error) {
  const auto &p = o.processed;
  if (!o.toolkit) {
    error = "GroundAnimation requires current BoardToolkit";
    return false;
  }
  const auto &t = *o.toolkit;
  o.ground.steering.Update(0, s.Board().steering.tilt_blending, p.flags_2468,
                           p.flags_2472);
  auto &physical = o.physical;
  physical.settings.board.collision.wheel_material = s.wheel_material;
  if (p.state_variant_index_2528 >= a.modes.size()) {
    error = "Invalid GroundAnimation physics mode " +
            std::to_string(p.state_variant_index_2528);
    return false;
  }
  auto mode = a.modes[p.state_variant_index_2528];
  mode.minimum_height_64 *= o.trainer.pop;
  mode.minimum_height_68 *= o.trainer.pop;
  mode.maximum_height *= o.trainer.pop;
  jump = CalculateGroundJump(
      {p.flags_2468, p.flags_2480, p.flags_2484, p.flags_2488, t.effective[2],
       t.forward, Decode(p.vectors_400_416[0]),
       Decode(p.vectors_464_480_496_512_528[1]),
       Decode(p.vectors_544_560_592_608[0]), t.filtered_normal,
       Decode(p.vectors_544_560_592_608[2]), Decode(p.prepared_jump_704),
       o.animation_input.extra.jump_strength,
       o.animation_input.extra.jump_controls, p.gravity_2648, p.scalar_2656},
      mode, a.jump);
  if (jump.active) {
    const auto velocity = jump.velocity;
    o.ground_runtime.SetAnimatedVelocity(physical.board, velocity);
    launched = true;
    SetGroundAnimationDrag(physical.board, 0);
    AirLaunchInfo info;
    if (!BindAirLaunchInfo(Bind(o), info, error))
      return false;
    info.start_velocity = velocity;
    info.player_jumped = true;
    AirSelectorInput input;
    if (!BindAirSelectorInput(Bind(o), o.air_settings, input, error))
      return false;
    bool submitted;
    if (!o.trajectory.Launch(info, input, physical.world, submitted, error))
      return false;
    if (!o.toolkit) {
      error = "Jump trajectory requires current board toolkit";
      return false;
    }
    const auto context =
        AirTrajectoryGrindContext::FromProcessed(p, o.toolkit->deck[3]);
    bool valid;
    if (!o.trajectory.Update(input, physical.world, context, valid, error))
      return false;
    const auto &packet = o.trajectory.selector.LaunchInfo();
    if (!packet) {
      error = "GroundAnimation launch has no retained trajectory packet";
      return false;
    }
    launch_velocity = packet->start_velocity;
    error.clear();
    return true;
  }
  const auto settings = s.Board();
  const float balance = o.animation_input.fields.balance;
  const float front_scale = balance <= 0 ? balance >= -0.0f ? 1 : 2 : 0;
  const float rear_scale = balance >= -0.0f ? balance <= 0 ? 1 : 2 : 0;
  const auto foot = [&](float offset, float absorption, float amount) {
    return CalculateGroundForce(
        settings.ground_force,
        {1, offset, absorption, amount, balance, p.scalar_2656, t.transverse_up,
         Decode(p.vectors_400_416[0]), Decode(p.vectors_544_560_592_608[0])});
  };
  const auto front = foot(s.foot_force_offset, 0, front_scale);
  const auto rear =
      foot(-s.foot_force_offset, s.absorption_rear * 0, rear_scale);
  const auto brake = CalculateBraking(
      {p.flags_2468, o.animation_input.fields.brake, p.scalar_2612,
       t.absolute_speed, s.surface_braking_factor, Xyz(t.horizontal_forward)},
      settings.propulsion.braking);
  const auto friction = CalculateSlideFriction(
      settings.slide_friction,
      {p.state_timer_2664, Decode(p.vectors_464_480_496_512_528[0]),
       Decode(p.vectors_400_416[0]), t.deck[0], p.scalar_2656, p.scalar_2764});
  const auto normal = physical.riding.reckoning.ground_normal;
  const float drag =
      CalculateLinearDrag({p.flags_2468, t.absolute_speed, balance,
                           o.life.manual_drag_2724, normal.y},
                          settings.linear_drag);
  const auto collision = o.ground_runtime.CalculateCollisionForce(
      {p.flags_2472,
       Decode(p.collision_pose_error_736),
       Decode(p.vectors_400_416[1]),
       t.travel_direction,
       Decode(p.vectors_544_560_592_608[0]),
       {normal.x, normal.y, normal.z, 0},
       p.timestep_2604,
       t.total_mass});
  if (collision)
    physical.board.ForcesMut().Append(
        {15, Xyz(collision->force_2528), Xyz(collision->point_2544)});
  else {
    physical.board.ForcesMut().Append(PointForce(4, front));
    physical.board.ForcesMut().Append(PointForce(5, rear));
    physical.board.ForcesMut().Append(PointForce(1, friction));
    physical.board.ForcesMut().Append(brake);
    SetGroundAnimationDrag(physical.board, drag);
  }
  error.clear();
  return true;
}
} // namespace atelier::skate
