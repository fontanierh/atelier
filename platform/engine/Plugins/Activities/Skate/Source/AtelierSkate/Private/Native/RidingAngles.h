// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
float RidingSignedAngle(Vec3 from,Vec3 to,Vec3 axis);
float RidingFractionWrappedAngle(float angle);
}
