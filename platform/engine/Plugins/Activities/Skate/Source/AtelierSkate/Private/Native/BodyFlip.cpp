// SPDX-License-Identifier: Apache-2.0
#include "BodyFlip.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
float Float(std::uint32_t w) {
  float v;
  std::memcpy(&v, &w, 4);
  return v;
}
float Clamp(float value, float lower, float upper) {
  value = lower - value >= 0.0f ? lower : value;
  return upper - value >= 0.0f ? value : upper;
}
Mat4 Rotation(Vec4 axis, float angle) {
  const float x = axis[0], y = axis[1], z = axis[2];
  const auto sc = SinCos(angle);
  const float s = sc.first, c = sc.second, t = 1.0f - c;
  const float tx = t * x, ty = t * y, tz = t * z, sx = s * x, sy = s * y,
              sz = s * z;
  const float xx = std::fma(tx, x, c), yx = ty * x - sz,
              zx = std::fma(tz, x, sy);
  return {{{xx, std::fma(tx, y, sz), tx * z - sy, xx},
           {yx, std::fma(ty, y, c), std::fma(ty, z, sx), yx},
           {zx, tz * y - sx, std::fma(tz, z, c), zx},
           {0, 0, 0, 0}}};
}
} // namespace
void UpdatePhysicalBodyFlip(PhysicalBodyFlipState &state,
                            const PhysicalBodyFlipSettings &settings,
                            const PhysicalBodyFlipInput &input) {
  const float fallback = settings.missing_attribute_value;
  const float smoothing = settings.smoothing.value_or(fallback),
              maximum = settings.maximum_speed.value_or(fallback),
              spin_scale = settings.spin_scale.value_or(fallback);
  state.requested_speed = input.requested_speed;
  float speed =
      std::fma(input.requested_speed - state.speed, smoothing, state.speed);
  if (input.perfect_body_flips) {
    const float full_turn = Float(0x40c90fdb),
                remaining_rate = (full_turn - std::abs(state.angle)) * 12.0f;
    const float sign = speed > 0.0f ? 1.0f : -1.0f;
    if (!(std::abs(speed) < remaining_rate))
      speed = sign * remaining_rate;
    state.angle = Clamp(std::fma(speed, Float(0x3c888889), state.angle),
                        -full_turn, full_turn);
  } else {
    speed = Clamp(speed, -maximum, maximum);
    state.angle = std::fma(input.timestep, speed, state.angle);
  }
  state.speed = speed;
  state.spin_transform = Rotation(input.normal, input.spin_angle * spin_scale);
  if (state.angle != 0.0f) {
    const auto flip = Rotation(input.flip_axis, state.angle),
               spin = state.spin_transform;
    for (std::size_t col = 0; col < 4; ++col)
      for (std::size_t lane = 0; lane < 4; ++lane) {
        const float first =
            col == 3 ? std::fma(spin[col][0], flip[0][lane], flip[3][lane])
                     : spin[col][0] * flip[0][lane];
        const float second = std::fma(spin[col][1], flip[1][lane], first);
        state.combined_transform[col][lane] =
            std::fma(spin[col][2], flip[2][lane], second);
      }
  }
}
} // namespace atelier::skate
