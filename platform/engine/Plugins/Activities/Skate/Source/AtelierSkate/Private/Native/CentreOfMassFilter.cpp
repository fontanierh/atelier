// SPDX-License-Identifier: Apache-2.0
#include "CentreOfMassFilter.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
CentreOfMassOutput CentreOfMassFilter::Update(Vec4 input_position,
                                              Vec4 input_velocity) {
  float dt;
  const std::uint32_t dt_bits = 0x3c888889;
  std::memcpy(&dt, &dt_bits, 4);
  const auto old_velocity = velocity;
  for (std::size_t i = 0; i < 4; ++i)
    velocity[i] = std::fma(old_velocity[i], 0.75f, input_velocity[i] * 0.25f);
  float inverse = ReciprocalEstimate(dt);
  inverse = std::fma(inverse, std::fma(-dt, inverse, 1.0f), inverse);
  inverse = std::fma(inverse, std::fma(-dt, inverse, 1.0f), inverse);
  Vec4 acceleration;
  for (std::size_t i = 0; i < 4; ++i)
    acceleration[i] = (velocity[i] - old_velocity[i]) * inverse;
  if (!position_valid) {
    position = input_position;
    position_velocity = {};
    position_valid = true;
  } else {
    const Vec4 coefficient{.05f, .03f, .05f, 0}, unity{1, 1, 1, 0};
    Vec4 predicted, error;
    for (std::size_t i = 0; i < 4; ++i)
      position_velocity[i] =
          std::fma(unity[i] - coefficient[i], position_velocity[i],
                   coefficient[i] * input_velocity[i]);
    for (std::size_t i = 0; i < 4; ++i)
      predicted[i] = std::fma(position_velocity[i], dt, position[i]);
    for (std::size_t i = 0; i < 4; ++i)
      position[i] = std::fma(unity[i] - coefficient[i], predicted[i],
                             coefficient[i] * input_position[i]);
    for (std::size_t i = 0; i < 4; ++i)
      error[i] = input_position[i] - position[i];
    if (Dot3(error, accumulated_error) > 0)
      for (std::size_t i = 0; i < 4; ++i)
        position[i] = std::fma(accumulated_error[i], .08f, position[i]);
    for (std::size_t i = 0; i < 4; ++i)
      accumulated_error[i] = std::fma(accumulated_error[i], .95f,
                                      (input_position[i] - position[i]) * .05f);
  }
  return {velocity, acceleration, position};
}
} // namespace atelier::skate
