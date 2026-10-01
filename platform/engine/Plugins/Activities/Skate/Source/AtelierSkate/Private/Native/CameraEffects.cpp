// SPDX-License-Identifier: Apache-2.0
#include "CameraEffects.h"
#include "Geometry.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
std::uint32_t SaturatingU32(float value) {
  if (std::isnan(value) || value <= 0)
    return 0;
  if (double(value) >= double(std::numeric_limits<std::uint32_t>::max()))
    return std::numeric_limits<std::uint32_t>::max();
  return static_cast<std::uint32_t>(value);
}
float SquareRoot(float v) {
  const float root = v * InverseLengthSquared(v);
  return v == 0 ? 0 : root;
}
std::array<float, 3> Angles(Basis3 basis) {
  const auto right = basis.columns[0], up = basis.columns[1],
             at = basis.columns[2];
  const float horizontal =
                  SquareRoot(std::fma(right[0], right[0], right[1] * right[1])),
              yaw = AtanRatio(-right[2], horizontal);
  return horizontal > Bits(0x3a83126f)
             ? std::array<float, 3>{AtanRatio(up[2], at[2]), yaw,
                                    AtanRatio(right[1], right[0])}
             : std::array<float, 3>{AtanRatio(-at[1], up[1]), yaw, 0};
}
} // namespace
bool ShakeEffect::LandingImpulse(Vec4 normal, Vec4 velocity, ShakeSettings s) {
  const float speed = Length(velocity);
  if (Bits(0x3727c5ac) > speed)
    return false;
  const float inverse = RefinedReciprocal(speed),
              cosine =
                  Clamp(Dot3(Mul(normal, -1), Mul(velocity, inverse)), -1, 1),
              angle = Acos(cosine) * Bits(0x3f22f983),
              weighted = speed * (1 - Clamp(angle, 0, 1));
  if (weighted <= 0)
    return false;
  const float fraction = Clamp(
                  (weighted - s.impulse_minimum_velocity) /
                      (s.impulse_maximum_velocity - s.impulse_minimum_velocity),
                  0, 1),
              value = (fraction * fraction) * s.impulse_magnitude;
  if (value > impulse) {
    impulse = value;
    return true;
  }
  return false;
}
bool ShakeEffect::Update(float dt, float speed, float distance, Basis3 basis,
                         bool enabled, const ShakeSamples &samples,
                         ShakeSettings s, Basis3 &result, std::string &error) {
  weight =
      Clamp(enabled ? std::fma(dt, 5.0f, weight) : -std::fma(dt, 5.0f, -weight),
            0, 1);
  float amplitude =
      s.amplitude_top_speed != 0
          ? std::fma(
                SampleShakeBezier(s.amplitude_curve,
                                  Clamp(speed / s.amplitude_top_speed, 0, 1)),
                s.amplitude_maximum - s.amplitude_minimum, s.amplitude_minimum)
          : s.amplitude_minimum;
  amplitude = (impulse + amplitude) * weight;
  float frequency =
      s.frequency_top_speed != 0
          ? std::fma(
                SampleShakeBezier(s.frequency_curve,
                                  Clamp(speed / s.frequency_top_speed, 0, 1)),
                s.frequency_maximum - s.frequency_minimum, s.frequency_minimum)
          : s.frequency_minimum;
  if (impulse > 0)
    frequency = s.impulse_frequency;
  time = std::fma(s.data_frames_per_second * frequency, dt, time);
  const float whole = std::trunc(RefinedReciprocal(1) * time),
              fraction = std::fma(-whole, 1.0f, time);
  if (samples.rotations.empty() ||
      samples.translations.size() != samples.rotations.size()) {
    error = "Stock camera shake has no samples";
    return false;
  }
  const auto left = std::size_t(SaturatingU32(time - fraction)) %
                    samples.rotations.size(),
             right = (left + 1) % samples.rotations.size();
  const float distance_weight =
                  Clamp((Bits(0x4059999a) - distance) * Bits(0x3fd55552), 0, 1),
              inverse_fraction = 1 - fraction;
  std::array<float, 3> angles, local;
  for (std::size_t i = 0; i < 3; ++i) {
    const float rotation =
                    std::fma(samples.rotations[left][i], inverse_fraction,
                             samples.rotations[right][i] * fraction),
                t = std::fma(samples.translations[left][i], inverse_fraction,
                             samples.translations[right][i] * fraction);
    angles[i] =
        ((rotation * amplitude) * distance_weight) * s.rotation_multiplier;
    local[i] = ((t * s.translation_multiplier) * amplitude) * distance_weight;
  }
  angles[2] *= s.dutch_multiplier;
  const auto rotation = BasisFromAngles(angles[0], angles[1], angles[2]);
  for (std::size_t i = 0; i < 3; ++i)
    translation[i] =
        std::fma(basis.columns[2][i], local[2],
                 std::fma(basis.columns[1][i], local[1],
                          std::fma(basis.columns[0][i], local[0], 0.0f)));
  translation[3] = 0;
  for (std::size_t c = 0; c < 3; ++c)
    for (std::size_t i = 0; i < 3; ++i)
      result.columns[c][i] =
          std::fma(rotation.columns[c][2], basis.columns[2][i],
                   std::fma(rotation.columns[c][1], basis.columns[1][i],
                            rotation.columns[c][0] * basis.columns[0][i]));
  impulse = (1 - s.impulse_decay) * impulse;
  if (impulse < Bits(0x3ba3d70a))
    impulse = 0;
  return true;
}
void LookInput::Update(std::array<float, 2> input, LookSettings s) {
  const float radians = Bits(0x3c8efa35),
              limit = Bits(0x3fc90fdb) - 5 * radians;
  const float h =
      Clamp((input[0] * s.heading_offset_degrees) * radians, -limit, limit);
  heading = std::fma(h - heading, s.heading_speed * Bits(0x3c888889), heading);
  const float e =
      Clamp((input[1] * s.elevation_offset_degrees) * radians, -limit, limit);
  elevation =
      std::fma(e - elevation, s.elevation_speed * Bits(0x3c888889), elevation);
}
Quat FrameComposer::Compose(float dt, float fraction, float mirror, Shot from,
                            Shot to, Vec4 fallback, Vec4 camera,
                            FrameSubject subject, FrameSettings settings) {
  const auto to_orientation =
                 Single(to, fallback, camera, mirror, subject, settings),
             from_orientation =
                 Single(from, fallback, camera, mirror, subject, settings);
  const auto orientation = Slerp(from_orientation, to_orientation, fraction);
  roll = dt > 0 ? std::fma((to.framing[0] - roll) * settings.roll_response, dt,
                           roll)
                : to.framing[0];
  return orientation;
}
Quat FrameComposer::Single(Shot shot, Vec4 fallback, Vec4 camera, float mirror,
                           FrameSubject subject, FrameSettings settings) {
  reference = shot.ReferencePoint(subject.positions,
                                  subject.board_offset_direction, fallback);
  yaw = shot.framing[1] * mirror;
  pitch = -shot.framing[2];
  const auto framing = BasisFromAngles(pitch, yaw, 0);
  auto direction = Sub(reference, camera);
  if (!(std::abs(direction[0]) > Bits(0x34000000) ||
        std::abs(direction[1]) > Bits(0x34000000) ||
        std::abs(direction[2]) > Bits(0x34000000)))
    direction = {0, 0, 1, 0};
  else {
    direction[3] = 0;
    direction = Normalize(direction);
    const float ceiling =
        Sin(settings.maximum_pitch_degrees * Bits(0x3c8efa35));
    if (direction[1] > ceiling) {
      direction[1] = ceiling;
      direction = Normalize(direction);
    }
  }
  const auto look = LookBasis({direction[0], direction[1], direction[2]});
  Basis3 result;
  for (std::size_t c = 0; c < 3; ++c)
    for (std::size_t i = 0; i < 3; ++i)
      result.columns[c][i] =
          std::fma(look.columns[2][i], framing.columns[c][2],
                   std::fma(look.columns[1][i], framing.columns[c][1],
                            look.columns[0][i] * framing.columns[c][0]));
  return QuaternionFromBasis(result);
}
Quat QuaternionFromBasis(Basis3 basis) {
  const auto right = basis.columns[0], up = basis.columns[1],
             at = basis.columns[2];
  const float x = right[0], y = up[1], z = at[2], trace = (x + y) + z;
  float sum;
  Vec4 companion;
  std::size_t dominant;
  if (trace > 0) {
    sum = (x + y) + (z + 1);
    companion = {up[2] - at[1], at[0] - right[2], right[1] - up[0], 0.5f};
    dominant = 3;
  } else if (x > y && x > z) {
    sum = (x + (-y)) + ((-z) + 1);
    companion = {0.5f, up[0] + right[1], at[0] + right[2], up[2] - at[1]};
    dominant = 0;
  } else if (y > z) {
    sum = ((-x) + y) + ((-z) + 1);
    companion = {up[0] + right[1], 0.5f, at[1] + up[2], at[0] - right[2]};
    dominant = 1;
  } else {
    sum = ((-x) + (-y)) + (z + 1);
    companion = {at[0] + right[2], at[1] + up[2], 0.5f, right[1] - up[0]};
    dominant = 2;
  }
  const float inverse = InverseLengthSquared(sum), root = sum * inverse,
              half = 0.5f * inverse;
  for (std::size_t i = 0; i < 4; ++i)
    companion[i] *= i == dominant ? root : half;
  return companion;
}
SimulationRateRequest SlowMotionSettings::Request(float progress) const {
  return {
      1 / std::fma(timescale.Evaluate(progress), fps_at_scale_one - 60, 60.0f),
      1};
}
std::pair<SlowMotionController, SimulationRateRequest>
SlowMotionController::Begin(SlowMotionSettings s) {
  return {{}, s.Request(0)};
}
SimulationRateRequest SlowMotionController::Update(float dt, float duration,
                                                   SlowMotionSettings s) {
  elapsed += dt;
  float progress;
  if (!(duration > 0)) {
    if (!latched_prediction)
      time_before_prediction += dt;
    progress = Bits(0x3dcccccd);
  } else {
    if (!latched_prediction) {
      air_duration = duration;
      latched_prediction = true;
    }
    progress = elapsed / (time_before_prediction + air_duration);
  }
  return s.Request(progress);
}
SimulationRateRequest SlowMotionController::End() {
  return {Bits(0x3c888889), 0};
}
CameraFrame::CameraFrame()
    : basis{{{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}}}, previous_basis(basis) {}
bool CameraFrame::Motion(float dt, Basis3 value, Vec4 point,
                         std::string &error) {
  const float inverse = dt != 0 ? 1 / dt : 1;
  linear_velocity = Mul(Sub(point, position), inverse);
  const auto old = Angles(basis), next = Angles(value);
  for (std::size_t i = 0; i < 3; ++i) {
    float delta;
    if (!NormalizeAngle(next[i] - old[i], delta, error))
      return false;
    angular_velocity[i] = delta * inverse;
  }
  angular_velocity[3] = 0;
  return true;
}
float LensFieldOfView(float lens, float aspect) {
  const float angle = Atan(35 / (lens * 2)), degrees = angle * Bits(0x42e52ee1);
  return SquareRoot((degrees * degrees) / (aspect + 1));
}
} // namespace atelier::skate::camera
