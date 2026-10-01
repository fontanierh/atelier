// SPDX-License-Identifier: Apache-2.0
#include "HandplantRotation.h"
#include "DriveFrames.h"
#include "PlantMath.h"
#include "SkeletonPoseFrames.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
Mat4 HandplantRotationFrame(Vec4 heading, Vec4 up) {
  using namespace plant_math;
  if (std::abs(Dot(heading, up)) > Float(0x3f7fff58)) {
    heading = {1, 0, 0, 0};
    if (std::abs(Dot(heading, up)) > Float(0x3f7fff58))
      heading = {0, 0, 1, 0};
  }
  const auto right = Normalize(Cross(up, heading)),
             forward = Normalize(Cross(right, up));
  return {right, Normalize(Cross(forward, right)), forward, Vec4{}};
}
Mat4 BlendHandplantRotation(Mat4 a, Mat4 b, float weight) {
  using namespace plant_math;
  if (weight >= 1.0f)
    return b;
  if (weight <= 0.0f)
    return a;
  const auto relative = ComposeSkeletonAffine(b, InverseSkeletonRigid(a));
  Basis3 basis;
  for (std::size_t i = 0; i < 3; ++i)
    for (std::size_t j = 0; j < 3; ++j)
      basis.columns[i][j] = relative[i][j];
  const auto q = QuaternionFromBasis(basis);
  const float sign = q[3] < 0.0f ? -1.0f : 1.0f,
              angle = 2.0f * Acos(std::clamp(q[3] * sign, -1.0f, 1.0f));
  auto result = a;
  if (angle < Float(0x3d0efa35)) {
    for (std::size_t i = 0; i < 3; ++i)
      result[i] = Normalize(Madd(Sub(b[i], a[i]), weight, a[i]));
  } else {
    const auto axis = Normalize({q[0] * sign, q[1] * sign, q[2] * sign, 0});
    const auto sc = SinCos(angle * weight);
    for (std::size_t i = 0; i < 3; ++i)
      result[i] =
          Madd(axis, Dot(axis, a[i]) * (1.0f - sc.second),
               Madd(Cross(axis, a[i]), sc.first, Scale(a[i], sc.second)));
  }
  result[3] = Madd(Sub(b[3], a[3]), weight, a[3]);
  return result;
}
} // namespace atelier::skate
