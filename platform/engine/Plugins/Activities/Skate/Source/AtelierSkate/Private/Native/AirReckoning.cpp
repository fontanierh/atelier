// SPDX-License-Identifier: Apache-2.0
#include "AirReckoning.h"
#include "BoardGroundAngle.h"
#include "StockSettingsReader.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
float Float(std::uint32_t word) {
  float v;
  std::memcpy(&v, &word, 4);
  return v;
}
Vec4 Lanes(Vec3 v) { return {v.x, v.y, v.z, 0}; }
Vec3 Vector(Vec4 v) { return {v[0], v[1], v[2]}; }
float Wrap(float angle) {
  const float turns = angle * Float(0x3e22f983),
              fraction = turns - std::floor(turns);
  return (fraction - (fraction > 0.5f ? 1.0f : 0.0f)) * Float(0x40c90fdb);
}
float Length(Vec4 v) {
  const float sq = Dot3(v, v), inverse = InverseLengthSquared(sq, 2);
  return sq == 0 ? 0.0f : sq * inverse;
}
Vec4 Normalize(Vec4 v) {
  const float inverse = InverseLengthSquared(Dot3(v, v), 2);
  for (auto &x : v)
    x *= inverse;
  return v;
}
Vec4 NormalizeSafe(Vec4 v, Vec4 fallback) {
  const float sq = Dot3(v, v), inverse = InverseLengthSquared(sq, 2),
              magnitude = sq == 0 ? 0.0f : sq * inverse;
  if (magnitude > Float(0x358637bd)) {
    for (auto &x : v)
      x *= inverse;
    return v;
  }
  return fallback;
}
Vec4 Cross(Vec4 a, Vec4 b) {
  return {
      std::fma(-a[2], b[1], a[1] * b[2]), std::fma(-a[0], b[2], a[2] * b[0]),
      std::fma(-a[1], b[0], a[0] * b[1]), std::fma(-a[3], b[3], a[3] * b[3])};
}
float Angle(Vec4 a, Vec4 b) {
  return BoardGroundAngleBetween(Vector(a), Vector(b));
}
Vec4 RotateHeading(Vec4 heading, Vec4 up, float angle) {
  const float x = up[0], y = up[1], z = up[2];
  const auto sc = SinCos(angle);
  const float s = sc.first, c = sc.second, t = 1.0f - c;
  const float tx = t * x, ty = t * y, tz = t * z, sx = s * x, sy = s * y,
              sz = s * z;
  const float xx = std::fma(tx, x, c), yx = ty * x - sz,
              zx = std::fma(tz, x, sy);
  const std::array<Vec4, 3> columns{
      {{xx, std::fma(tx, y, sz), tx * z - sy, xx},
       {yx, std::fma(ty, y, c), std::fma(ty, z, sx), yx},
       {zx, tz * y - sx, std::fma(tz, z, c), zx}}};
  Vec4 output;
  for (std::size_t i = 0; i < 4; ++i) {
    const float first = columns[0][i] * heading[0],
                second = std::fma(columns[1][i], heading[1], first);
    output[i] = std::fma(columns[2][i], heading[2], second);
  }
  return output;
}
void AdvanceHistory(GroundNormalFilter &filter, Vec4 up) {
  // FilterRaw with the unchanged current controls is the public equivalent of
  // source filter(up); it neither reconstructs nor reinitializes its history.
  Vec4 control;
  for (std::size_t i = 0; i < 4; ++i)
    control[i] = Float(filter.words[i]);
  filter.FilterRaw(control, up);
  filter.PublishCurrent(up);
}
void PublishUp(GroundOrientation &orientation, Vec4 up, Vec4 old_up) {
  Vec4 velocity;
  for (std::size_t i = 0; i < 4; ++i)
    velocity[i] = up[i] - old_up[i];
  orientation.up_velocity = Vector(velocity);
  orientation.up = Vector(up);
  orientation.target = orientation.up;
}
bool ReadGraph(const StockSettingsReader &reader, std::string_view category,
               std::string_view name, bool negative, PointGraph<8> &output,
               std::string &error) {
  std::vector<std::uint32_t> words;
  if (!reader.Words(category, "default", name, negative ? 20 : 16, words,
                    error))
    return false;
  const std::size_t start = negative ? 4 : 0;
  for (std::size_t i = 0; i < 8; ++i) {
    output.x[i] = Float(words[start + i]);
    output.y[i] = Float(words[start + 8 + i]);
  }
  return true;
}
} // namespace
Vec4 ClampAirReckoningVectorWithinMaxAngle(Vec4 target, Vec4 from,
                                           float maximum) {
  const auto normalized_from = NormalizeSafe(from, {}),
             normalized_target = NormalizeSafe(target, {});
  auto axis = Cross(normalized_target, normalized_from);
  const float cosine = VectorMin(
                  VectorMax(Dot3(normalized_target, normalized_from), -1), 1),
              angle = Acos(cosine);
  const float turns = std::floor(std::fma(angle, Float(0x3e22f983), 0.5f)),
              closest_angle = std::fma(-turns, Float(0x40c90fdb), angle);
  if (std::abs(closest_angle) < maximum || Dot3(axis, axis) < Float(0x37800000))
    return target;
  axis = Normalize(axis);
  const auto sc = SinCos(-maximum * 0.5f);
  Vec4 q;
  for (std::size_t i = 0; i < 4; ++i)
    q[i] = axis[i] * sc.first;
  const auto first = Cross(q, from);
  Vec4 intermediate;
  for (std::size_t i = 0; i < 4; ++i)
    intermediate[i] = std::fma(sc.second, from[i], first[i]);
  const auto second = Cross(q, intermediate);
  const float magnitude = Length(target);
  Vec4 rotated;
  for (std::size_t i = 0; i < 4; ++i)
    rotated[i] = std::fma(second[i], 2.0f, from[i]) * magnitude;
  return rotated;
}
bool UpdateAirReckoning(GroundOrientation &orientation, ReckoningFrames &frames,
                        PhysicalBodySpinState &spin, AirReckoningState &state,
                        const AirReckoningSettings &settings,
                        const AirReckoningInput &input, std::string &error) {
  const auto old_up = Lanes(orientation.up);
  orientation.dynamic_up = orientation.up;
  frames.target_lean_angle = 0;
  state.secondary_lean_angle = 0;
  const auto ground_normal = orientation.ground_filter.Update(
      settings.ground_normal_smoothing, input.landing_normal);
  orientation.ground_normal = Vector(ground_normal);
  if (input.additive_spin)
    state.spin_speed = input.grind_adjusted_body_spin + input.target_spin;
  else if (input.direct_spin)
    state.spin_speed = input.target_spin;
  else {
    if (!UpdatePhysicalBodySpin(spin, settings.body_spin,
                                input.physical_body_spin, input.target_spin,
                                true, std::uint8_t(input.easy_body_spins),
                                error))
      return false;
    state.spin_speed = PhysicalBodySpinSpeed(spin);
  }
  state.spin_angle =
      std::fma(state.spin_speed, Float(0x3c888889), state.spin_angle);
  if (state.flip_active) {
    PhysicalBodyFlipState flip{state.flip_angle, state.flip_speed,
                               state.flip_requested_speed, state.spin_transform,
                               frames.body_flip};
    UpdatePhysicalBodyFlip(flip, settings.body_flip,
                           {input.flip_request, state.spin_angle, old_up,
                            state.flip_axis, input.timestep,
                            input.perfect_body_flips});
    state.flip_angle = flip.angle;
    state.flip_speed = flip.speed;
    state.flip_requested_speed = flip.requested_speed;
    state.spin_transform = flip.spin_transform;
    frames.body_flip = flip.combined_transform;
  }
  const float wrapped = Wrap(Angle(old_up, ground_normal)),
              maximum = wrapped * input.normal_blend;
  const Vec4 target =
      std::abs(wrapped) >= Float(0x40c8f61e)
          ? (std::abs(old_up[1]) < Float(0x3f7d70a4) ? Vec4{0, 1, 0, 0}
                                                     : Vec4{1, 0, 0, 0})
          : ground_normal;
  const auto candidate =
      Normalize(ClampAirReckoningVectorWithinMaxAngle(target, old_up, maximum));
  const float max_delta =
      settings.max_up_angle_delta.Evaluate(Length(input.com_to_deck));
  const auto selected =
      std::abs(Wrap(Angle(candidate, old_up))) > max_delta
          ? ClampAirReckoningVectorWithinMaxAngle(candidate, old_up, max_delta)
          : candidate;
  const auto up = NormalizeSafe(selected, old_up);
  PublishUp(orientation, up, old_up);
  if (!state.flip_active)
    frames.heading =
        RotateHeading(frames.heading, up, input.timestep * state.spin_speed);
  AdvanceHistory(orientation.slow_filter, up);
  AdvanceHistory(orientation.fast_filter, up);
  frames.CalculateTransform(up, ground_normal);
  frames.CalculateTilt(input.reverse_stance, settings.tilt_vs_rotation,
                       settings.tilt_vs_slope);
  error.clear();
  return true;
}
bool UpdatePlantAirReckoning(GroundOrientation &orientation,
                             ReckoningFrames &frames,
                             PhysicalBodySpinState &spin,
                             AirReckoningState &state,
                             const AirReckoningSettings &settings, Vec4 up,
                             Vec4 heading, bool reverse, std::string &error) {
  frames.heading = heading;
  if (!UpdatePhysicalBodySpin(spin, settings.body_spin, 0, 0, true, 0, error))
    return false;
  const auto previous = Lanes(orientation.up);
  orientation.dynamic_up = orientation.up;
  frames.target_lean_angle = 0;
  state.secondary_lean_angle = 0;
  const auto normal = Normalize(
      orientation.ground_filter.Update(settings.ground_normal_smoothing, up));
  orientation.ground_normal = Vector(normal);
  up = NormalizeSafe(ClampAirReckoningVectorWithinMaxAngle(normal, previous, 1),
                     previous);
  PublishUp(orientation, up, previous);
  AdvanceHistory(orientation.slow_filter, up);
  AdvanceHistory(orientation.fast_filter, up);
  frames.CalculateTransform(up, normal);
  frames.CalculateTilt(reverse, settings.tilt_vs_rotation,
                       settings.tilt_vs_slope);
  error.clear();
  return true;
}
bool AirReckoning::Load(const SettingsDatabase &data, std::string &error) {
  AirReckoning value;
  const StockSettingsReader reader(data);
  std::vector<std::uint32_t> control;
  if (!reader.Words("physics_reckoning", "default", "GroundNormalSmoothing", 4,
                    control, error))
    return false;
  for (std::size_t i = 0; i < 4; ++i)
    value.settings.ground_normal_smoothing[i] = Float(control[i]);
  constexpr std::array<std::string_view, 5> names{"easy", "normal", "hardcore",
                                                  "motorized", "test"};
  for (std::size_t i = 0; i < 5; ++i) {
    if (!reader.Boolean("physics_mode", names[i], "EasyBodySpins",
                        value.modes[i].easy_body_spins, error) ||
        !reader.Boolean("physics_mode", names[i], "PerfectBodyFlips",
                        value.modes[i].perfect_body_flips, error))
      return false;
  }
  auto &s = value.settings;
  if (!ReadGraph(reader, "physics_reckoning", "Air_MaxUpVectAngleDelta", true,
                 s.max_up_angle_delta, error) ||
      !ReadGraph(reader, "physics_reckoning", "TiltVsRotAir", false,
                 s.tilt_vs_rotation, error) ||
      !ReadGraph(reader, "physics_reckoning", "TiltVsSlopeAir", false,
                 s.tilt_vs_slope, error) ||
      !reader.Float("physics_bodyspin", "default", "MinDerivativeScalar",
                    s.body_spin.derivative_floor, error) ||
      !reader.Float("physics_bodyspin", "default", "MaxDeltaOppositeDirection",
                    s.body_spin.acceleration_limit, error))
    return false;
  constexpr std::array<std::string_view, 7> curves{
      "Hash_BEA30B5DC6AFF26A",    "MaxDeltaVsTime",
      "MaxDeltaForAutoVsTime",    "Hash_3974F0228331EB22",
      "DerivativeBodySpinVsTime", "Hash_D7C6855B7814D048",
      "PropBodySpinVsTime"};
  for (std::size_t i = 0; i < 7; ++i)
    if (!ReadGraph(reader, "physics_bodyspin", curves[i], true,
                   s.body_spin.curves[i], error))
      return false;
  s.body_spin.input_fade_threshold.fill(Float(0x37800000));
  float smoothing, maximum, scale;
  if (!reader.Float("physics_reckoning", "default", "FlipSpeedSmoothingFactor",
                    smoothing, error) ||
      !reader.Float("physics_reckoning", "default", "FlipMaxSpeed", maximum,
                    error) ||
      !reader.Float("physics_reckoning", "default", "FlipBodySpinScalar", scale,
                    error))
    return false;
  s.body_flip = {smoothing, maximum, scale, 0};
  value.stock_spin_curves = s.body_spin.curves;
  value.stock_spin_acceleration = s.body_spin.acceleration_limit;
  *this = std::move(value);
  error.clear();
  return true;
}
void AirReckoning::SetSpinScale(float scale) {
  for (std::size_t index : {0u, 1u, 5u, 6u})
    for (std::size_t i = 0; i < 8; ++i)
      settings.body_spin.curves[index].y[i] =
          stock_spin_curves[index].y[i] * scale;
  settings.body_spin.acceleration_limit = stock_spin_acceleration * scale;
}
PhysicsAirReckoningFields
AirReckoning::Fields(const PhysicalRidingOutputs &riding) const {
  return {Lanes(riding.reckoning.up), Lanes(riding.reckoning.ground_normal),
          state.spin_angle, state.spin_speed};
}
bool AirReckoning::Update(PhysicalRidingOutputs &riding,
                          const ProcessedPhysicsInput &p, float body_spin,
                          Vec4 landing_normal, float normal_blend,
                          float target_spin, float flip_request,
                          PhysicsAirReckoningFields &output,
                          std::string &error) {
  if (p.state_variant_index_2528 >= modes.size()) {
    error =
        "Undefined physics mode " + std::to_string(p.state_variant_index_2528);
    return false;
  }
  const auto mode = modes[p.state_variant_index_2528];
  Vec4 com_to_deck;
  for (std::size_t i = 0; i < 4; ++i)
    com_to_deck[i] = Float(p.animation_com_to_deck_752[i]);
  const AirReckoningInput input{landing_normal,
                                normal_blend,
                                target_spin,
                                flip_request,
                                com_to_deck,
                                p.timestep_2604,
                                body_spin,
                                p.grind_adjusted_body_spin_2644,
                                (p.flags_2484 & (1u << 15)) != 0,
                                (p.flags_2472 & (1u << 28)) != 0,
                                (p.flags_2468 & (1u << 20)) != 0,
                                mode.easy_body_spins,
                                mode.perfect_body_flips};
  if (!UpdateAirReckoning(riding.reckoning, riding.reckoning_frames,
                          riding.body_spin, state, settings, input, error))
    return false;
  output = Fields(riding);
  return true;
}
void AirReckoning::UpdatePlant(PhysicalRidingOutputs &riding,
                               const ProcessedPhysicsInput &p, Vec4 up,
                               Vec4 heading) {
  std::string error;
  if (!UpdatePlantAirReckoning(riding.reckoning, riding.reckoning_frames,
                               riding.body_spin, state, settings, up, heading,
                               (p.flags_2468 & (1u << 20)) != 0, error))
    std::abort();
}
} // namespace atelier::skate
