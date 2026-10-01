// SPDX-License-Identifier: Apache-2.0
#include "FootplantRuntime.h"
#include "PlantMath.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
Vec4 Decode(RawVector words) {
  Vec4 value;
  for (std::size_t i = 0; i < 4; ++i)
    value[i] = plant_math::Float(words[i]);
  return value;
}
std::int32_t SaturatedInteger(float value) {
  if (std::isnan(value))
    return 0;
  if (value >= 2147483648.0f)
    return std::numeric_limits<std::int32_t>::max();
  if (value <= -2147483648.0f)
    return std::numeric_limits<std::int32_t>::min();
  return static_cast<std::int32_t>(value);
}
// Exact air_phase/input.rs required fields read from the live owners after
// PlantSkeleton advance. The other binding fields are not read by either
// accepted BindAirLaunchInfo or BindAirSelectorInput.
AirStateBindingInput Bind(PlantSkeletonFrame frame,
                          const std::optional<BoardToolkit> &toolkit,
                          const AirTrajectoryRuntime &trajectory) {
  const auto &p = frame.processed;
  const auto &physical = frame.owners.physical;
  AirStateBindingInput out{};
  out.vectors_400_416 = p.vectors_400_416;
  out.vectors_464_480_496_512_528 = p.vectors_464_480_496_512_528;
  out.vectors_544_560_592_608 = p.vectors_544_560_592_608;
  out.prepared_jump_704 = p.prepared_jump_704;
  out.flags_2468 = p.flags_2468;
  out.flags_2472 = p.flags_2472;
  out.flags_2476 = p.flags_2476;
  out.state_2504 = p.state_2504;
  out.state_variant_index_2528 = p.state_variant_index_2528;
  out.external_physics_flags = p.external_physics_1616.flags;
  out.timestep_2604 = p.timestep_2604;
  out.transition_2636 = p.transition_2636;
  const auto gravity =
      physical.settings.board.step.simulation.gravity_acceleration;
  out.world_gravity = {gravity.x, gravity.y, gravity.z, 0};
  out.reckoning_system = physical.riding.reckoning_frames.system;
  out.reckoning_inverse = physical.riding.reckoning_frames.inverse_system;
  out.skeleton_local_centre_of_mass =
      physical.board_frames.local_centre_of_mass;
  out.skeleton_local_board_position =
      physical.board_frames.local_board_position;
  if (toolkit)
    out.toolkit_deck = toolkit->deck;
  out.trajectory_cone_x = trajectory.settings.cone_x;
  out.trajectory_cone_z = trajectory.settings.cone_z;
  return out;
}
} // namespace
bool FootplantRuntime::GroundEnter(PhysicalSimulationRuntime &physical,
                                   const ProcessedPhysicsInput &p,
                                   std::uint8_t &board_animated,
                                   std::string &error) {
  physical.board.HookMut().drive.EnableAngularOnly(board_animated);
  for (const auto part : {15, 16, 19, 20}) {
    physical.skeleton_collision.parts[part].volume_group = 4;
    physical.skeleton_collision.parts[part].enabled = false;
    physical.skeleton_collision.disable_count[part] = 0;
  }
  const auto frames = Start(Decode(p.vectors_544_560_592_608[2]),
                            Decode(p.vectors_544_560_592_608[3]));
  if (frames != 0)
    for (const auto part : selected_toe == 19
                               ? std::array<std::size_t, 3>{19, 20, 21}
                               : std::array<std::size_t, 3>{15, 16, 17}) {
      physical.skeleton_collision.pending_reenable = true;
      physical.skeleton_collision.disable_count[part] = frames;
      physical.skeleton_collision.parts[part].enabled = false;
    }
  error.clear();
  return true;
}
std::uint32_t FootplantRuntime::Start(Vec4 com, Vec4 velocity) {
  using namespace plant_math;
  perform = false;
  scalar_600 = 0;
  flag_627 = true;
  const auto anchor = adjusted_contact;
  vectors_352_368[1] = anchor;
  const auto offset = Sub(com, anchor);
  const auto radial = Normalize(offset);
  const float multiplier = settings.radial_speed_scale.Evaluate(
      Length(Scale(radial, Dot(velocity, radial))));
  const auto rotation = Cross(offset, velocity);
  const float angular_speed = Length(rotation);
  if (!(angular_speed > Float(0x37800000)))
    return 0;
  const auto axis = Scale(rotation, Reciprocal(angular_speed));
  const float angular_rate = angular_speed * multiplier;
  const auto normal = Scale(axis, -1);
  const Vec4 up{0, 1, 0, 0};
  const auto projected_up = Normalize(Sub(up, Scale(normal, Dot(up, normal))));
  const float raw_dot = Dot(radial, projected_up);
  float angle = Length(projected_up) == 0 ? 0
                                          : Acos(raw_dot < -1  ? -1
                                                 : raw_dot > 1 ? 1
                                                               : raw_dot);
  if (Dot(Cross(radial, projected_up), normal) < 0)
    angle = -angle;
  const float min_end = angle + angular_rate * settings.min_duration;
  const float max_end = angle + angular_rate * settings.max_duration;
  const float end_angle = VectorMin(
      VectorMax(min_end, settings.end_angle * Float(0x3c8efa35)), max_end);
  const float delta = end_angle - angle;
  scalar_596 = delta / angular_rate;
  const auto [sin, cos] = SinCos(delta * 0.5f);
  const auto q = Scale(axis, sin);
  const auto end_radial =
      Madd(Cross(q, Madd(radial, cos, Cross(q, radial))), 2, radial);
  const auto end = Madd(end_radial, settings.end_leg_length, anchor);
  const auto middle = Normalize(Add(end_radial, radial));
  const auto release =
      Madd(Sub(velocity, Scale(middle, Dot(velocity, middle))), multiplier,
           Scale(middle, settings.release_outward_speed));
  scalar_612 = Length(release);
  vectors_352_368[0] = Scale(release, Reciprocal(scalar_612));
  curve = {com,
           Madd(Scale(velocity, multiplier), scalar_596 * settings.start_handle,
                com),
           Sub(end, Scale(release, scalar_596 * settings.end_handle)), end};
  const auto frames = SaturatedInteger(scalar_596 * Float(0xc26fffff));
  // Rust release subtraction wraps; unsigned arithmetic preserves those bits.
  return 4u - static_cast<std::uint32_t>(frames);
}
void FootplantRuntime::Adjust(float t, std::array<float, 2> input) {
  using namespace plant_math;
  const float amount = std::fma(1.0f - t, 0.02f, t * 0.01f);
  Vec4 movement{input[0] * amount, 0, input[1] * amount, 0};
  const float projection = Dot(movement, Normalize(current_up));
  if (projection > 0)
    movement = Sub(movement, Scale(current_up, projection));
  const auto previous = curve[3];
  curve[3] = Add(previous, movement);
  const auto direction = Normalize(Sub(curve[3], curve[2]));
  curve[2] = Sub(curve[3], Scale(direction, Length(Sub(curve[2], previous))));
  vectors_352_368[0] = direction;
}
bool FootplantRuntime::GroundUpdate(PlantSkeletonFrame frame,
                                    const std::optional<BoardToolkit> &toolkit,
                                    const AirStateSettings &air_settings,
                                    AirTrajectoryRuntime &trajectory,
                                    std::array<float, 2> body_adjust,
                                    std::string &error) {
  using namespace plant_math;
  scalar_600 += Step();
  const float t = scalar_600 / scalar_596;
  Adjust(t, body_adjust);
  const float u = 1.0f - t;
  const auto position =
      Madd(curve[3], t * t * t,
           Madd(curve[2], 3.0f * t * t * u,
                Madd(curve[0], u * u * u, Scale(curve[1], 3.0f * t * u * u))));
  const bool launched = scalar_600 > scalar_596;
  if (launched)
    flag_627 = false;
  const auto anchor = vectors_352_368[1];
  const auto velocity = Scale(vectors_352_368[0], scalar_612);
  HoldPlantFoot(frame.owners.physical, frame.owners.ik, selected_toe != 15,
                anchor, 0);
  if (!AdvancePlantSkeleton(frame, position, std::nullopt, error))
    return false;
  if (launched) {
    const auto binding = Bind(frame, toolkit, trajectory);
    AirLaunchInfo info;
    if (!BindAirLaunchInfo(binding, info, error))
      return false;
    info.start_velocity = velocity;
    info.start_position_override = Add(anchor, Vec4{0, 0.2f, 0, 0});
    info.board_position_override =
        Add(info.start_position_override, Vec4{0, -0.1f, 0, 0});
    info.use_position_override = true;
    info.player_jumped = true;
    AirSelectorInput input;
    if (!BindAirSelectorInput(binding, air_settings, input, error))
      return false;
    bool launched_result;
    auto &physical = frame.owners.physical;
    if (!trajectory.Launch(info, input, physical.world, launched_result, error))
      return false;
    bool valid;
    if (!trajectory.Update(input, physical.world,
                           AirTrajectoryGrindContext::FromProcessed(
                               frame.processed, physical.DeckFrame()[3]),
                           valid, error))
      return false;
  }
  error.clear();
  return true;
}
} // namespace atelier::skate
