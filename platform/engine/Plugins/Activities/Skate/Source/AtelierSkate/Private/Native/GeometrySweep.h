// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Geometry.h"

namespace atelier::skate
{
// Complete thin/rounded dispatcher. Failed branches may change normal and
// fraction while retaining position/volume fields, exactly like the reference.
bool TriangleSegment(TriangleLineHit& result, Vec3 start, Vec3 direction,
                     const std::array<Vec3,3>& vertices, float line_radius, float triangle_fatness);
}
