// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
float WipeoutSignedAngle(Vec4 left,Vec4 right,Vec4 axis);
float WipeoutProjectedAngle(Vec4 left,Vec4 right,Vec4 axis);
float WipeoutWrapAngle(float angle);
}
