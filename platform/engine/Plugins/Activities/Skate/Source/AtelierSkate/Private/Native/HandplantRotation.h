#pragma once
#include "NativeMath.h"
namespace atelier::skate {
Mat4 HandplantRotationFrame(Vec4 heading, Vec4 up);
Mat4 BlendHandplantRotation(Mat4 a, Mat4 b, float weight);
} // namespace atelier::skate
