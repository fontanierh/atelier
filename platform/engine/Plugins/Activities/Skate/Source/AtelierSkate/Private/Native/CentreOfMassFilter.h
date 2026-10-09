#pragma once
#include "NativeMath.h"
namespace atelier::skate {
struct CentreOfMassOutput {
  Vec4 velocity, acceleration, position;
};
class CentreOfMassFilter {
public:
  Vec4 velocity{}, position{}, position_velocity{}, accumulated_error{};
  bool position_valid = false;
  void Reset() { *this = CentreOfMassFilter{}; }
  CentreOfMassOutput Update(Vec4 physical_position, Vec4 physical_velocity);
};
} // namespace atelier::skate
