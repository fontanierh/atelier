// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
#include "Settings.h"
namespace atelier::skate {
struct FootplantSettings {
  Vec4 deck_bounds{};
  float max_leg_angle_error = 0, leg_length_on_landing = 0;
  float foot_volume_y_offset = 0, deck_bounds_y_offset = 0;
  PointGraph<8> radial_speed_scale{};
  float max_horizontal_speed = 0, max_descending_speed = 0;
  float release_outward_speed = 0, end_handle = 0, end_angle = 0;
  float end_leg_length = 0, start_handle = 0, min_duration = 0,
        max_duration = 0;
  bool Load(const SettingsDatabase &, std::string &error);
};
} // namespace atelier::skate
