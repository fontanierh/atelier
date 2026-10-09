#pragma once
#include "NativeMath.h"
#include <string>
namespace atelier::skate {
// Native +0..176, borrowed directly from PhysicalRidingOutputs::body_spin.
using PhysicalBodySpinState = std::array<std::uint32_t, 44>;
struct PhysicalBodySpinSettings {
  float derivative_floor, acceleration_limit;
  std::array<PointGraph<8>, 7> curves;
  Vec4 input_fade_threshold;
};
bool SetPhysicalBodySpinWords(PhysicalBodySpinState &,
                              const PhysicalBodySpinState &, std::string &);
float PhysicalBodySpinSpeed(const PhysicalBodySpinState &);
bool UpdatePhysicalBodySpin(PhysicalBodySpinState &,
                            const PhysicalBodySpinSettings &, float input,
                            float auto_spin, bool in_air, std::uint8_t mode,
                            std::string &);
bool UpdatePhysicalBodySpinGround(PhysicalBodySpinState &, float input,
                                  std::string &);
} // namespace atelier::skate
