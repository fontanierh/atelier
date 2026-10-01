// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
#include "Settings.h"
namespace atelier::skate {
struct HandplantSettings {
  std::array<PointGraph<4>, 7> window;
  float depth, window_drop;
  PointGraph<8> time_warp, out_heading, into_rotation, out_rotation;
  PointGraph<4> hand_radius;
  float curve_half_time, entry_blend, hand_out, hand_into, hand_release;
  float minimum_speed, minimum_slope, rotation_time, committed_time,
      minimum_out_speed, hand_approach;
  std::int32_t direction_frames;
  float apex_radius, apex_angle;
  std::array<float, 3> animation;
  float truck_distance;
  bool Load(const SettingsDatabase &, std::string &error);
};
} // namespace atelier::skate
