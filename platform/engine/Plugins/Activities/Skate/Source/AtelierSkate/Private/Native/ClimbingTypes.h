#pragma once
#include "NativeMath.h"
namespace atelier::skate {
struct ClimbingLedge {
  Vec3 anchor,landing,forward;
  std::array<Vec3,2> palms,normals;
};
} // namespace atelier::skate
