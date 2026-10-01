// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::ground_jump_math {
inline float Float(std::uint32_t word) {
  float value;
  std::memcpy(&value, &word, 4);
  return value;
}
inline Vec4 Add(Vec4 a, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] += b[i];
  return a;
}
inline Vec4 Sub(Vec4 a, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] -= b[i];
  return a;
}
inline Vec4 Scale(Vec4 a, float b) {
  for (auto &v : a)
    v *= b;
  return a;
}
inline Vec4 Madd(Vec4 a, float b, Vec4 c) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] = std::fma(a[i], b, c[i]);
  return a;
}
inline Vec4 Planar(Vec4 value, Vec4 normal) {
  return Sub(value, Scale(normal, Dot3(value, normal)));
}
inline float Maximum(float a, float b) { return a - b >= -0.0f ? a : b; }
inline float Clamp(float value, float low, float high) {
  const float lower = low - value >= -0.0f ? low : value;
  return high - lower >= -0.0f ? lower : high;
}
inline float VectorClamp(float value, float low, float high) {
  return VectorMin(high, VectorMax(low, value));
}
inline float SquareRoot(float square) {
  const float value = square * InverseLengthSquared(square, 2);
  return square == 0 ? 0 : value;
}
inline float Length(Vec4 value) { return SquareRoot(Dot3(value, value)); }
inline Vec4 Normalize(Vec4 value) {
  const float square = Dot3(value, value);
  const float inverse = InverseLengthSquared(square, 2);
  const float length = square == 0 ? 0 : square * inverse;
  return length > Float(0x358637bd) ? Scale(value, inverse) : Vec4{};
}
inline Vec4 Cross(Vec4 a, Vec4 b) {
  return {std::fma(-a[2], b[1], a[1] * b[2]),
          std::fma(-a[0], b[2], a[2] * b[0]),
          std::fma(-a[1], b[0], a[0] * b[1]), 0};
}
} // namespace atelier::skate::ground_jump_math
