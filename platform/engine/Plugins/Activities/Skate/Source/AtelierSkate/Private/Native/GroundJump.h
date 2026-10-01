// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate {
struct GroundJump {
  Vec4 velocity{};
  float scalar_16 = 0;
  bool active = false;
};
struct GroundJumpMode {
  float minimum_height_64, minimum_height_68, maximum_height;
};
struct GroundJumpSettings {
  PointGraph<16> vertical_response;
  PointGraph<8> y_scalar_vs_normal_y, speed_scalar_vs_angle;
  PointGraph<8> minimum_height_vs_speed, maximum_height_vs_speed;
  float speed_response_max_speed, minimum_scalar, maximum_y_bonus;
  float adjust_z_factor, adjust_x_factor, absolute_minimum_height;
  float hippy_minimum_height, hippy_maximum_height;
};
struct GroundJumpInput {
  std::uint32_t flags_2468, flags_2480, flags_2484, flags_2488;
  Vec4 effective_forward, forward, current_velocity, ground_reference_position;
  Vec4 reference_up, filtered_ground_normal, animation_com_position;
  Vec4 prepared_velocity;
  float jump_strength;
  std::array<float, 2> jump_controls;
  float gravity_y, surface_speed;
};
GroundJump CalculateGroundJump(GroundJumpInput, GroundJumpMode,
                               const GroundJumpSettings &);
} // namespace atelier::skate
