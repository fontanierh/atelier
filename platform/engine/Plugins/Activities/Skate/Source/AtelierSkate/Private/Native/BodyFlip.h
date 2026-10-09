#pragma once
#include "NativeMath.h"
#include <optional>
namespace atelier::skate {
struct PhysicalBodyFlipState {
  float angle, speed, requested_speed;
  Mat4 spin_transform, combined_transform;
};
struct PhysicalBodyFlipSettings {
  std::optional<float> smoothing, maximum_speed, spin_scale;
  float missing_attribute_value;
};
struct PhysicalBodyFlipInput {
  float requested_speed, spin_angle;
  Vec4 normal, flip_axis;
  float timestep;
  bool perfect_body_flips;
};
void UpdatePhysicalBodyFlip(PhysicalBodyFlipState &,
                            const PhysicalBodyFlipSettings &,
                            const PhysicalBodyFlipInput &);
} // namespace atelier::skate
