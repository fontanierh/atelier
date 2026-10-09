#pragma once
#include "NativeMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::plant_math {
inline float Float(std::uint32_t word) {
  float value;
  std::memcpy(&value, &word, 4);
  return value;
}
inline float Step() { return Float(0x3c888889); }
inline float Dot(Vec4 a, Vec4 b) {
  return (a[0] * b[0] + a[1] * b[1]) + a[2] * b[2];
}
inline Vec4 Cross(Vec4 a, Vec4 b) {
  return {std::fma(a[1], b[2], -a[2] * b[1]),
          std::fma(a[2], b[0], -a[0] * b[2]),
          std::fma(a[0], b[1], -a[1] * b[0]), 0};
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
inline Vec4 Scale(Vec4 a, float s) {
  for (auto &v : a)
    v *= s;
  return a;
}
inline Vec4 Madd(Vec4 a, float s, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i)
    a[i] = std::fma(a[i], s, b[i]);
  return a;
}
inline float Reciprocal(float s) {
  float r = 1.0f / s;
  for (unsigned i = 0; i < 2; ++i)
    r = std::fma(std::fma(-s, r, 1.0f), r, r);
  return r;
}
inline float Rsqrt(float s) {
  float r = 1.0f / std::sqrt(s);
  for (unsigned i = 0; i < 2; ++i)
    r = std::fma(r * 0.5f, std::fma(-s, r * r, 1.0f), r);
  return r;
}
inline float Length(Vec4 a) {
  const float s = Dot(a, a);
  const float l = s * Rsqrt(s);
  return s == 0.0f ? 0.0f : l;
}
inline Vec4 Normalize(Vec4 a) {
  const float s = Dot(a, a), r = Rsqrt(s), l = s == 0.0f ? 0.0f : s * r;
  return l > Float(0x358637bd) ? Scale(a, r) : Vec4{};
}
inline Vec4 Point(const Mat4 &m, Vec4 p) {
  Vec4 v;
  for (std::size_t i = 0; i < 4; ++i) {
    const float x = std::fma(m[0][i], p[0], m[3][i]);
    const float y = std::fma(m[1][i], p[1], x);
    v[i] = std::fma(m[2][i], p[2], y);
  }
  return v;
}
inline Vec4 Rotate(const Mat4 &m, Vec4 p) {
  Vec4 v;
  for (std::size_t i = 0; i < 4; ++i) {
    const float x = m[0][i] * p[0];
    const float y = std::fma(m[1][i], p[1], x);
    v[i] = std::fma(m[2][i], p[2], y);
  }
  return v;
}
inline Vec4 ClampLength(Vec4 v, float maximum) {
  const float l = Length(v);
  if (!(l >= Float(0x37800000)))
    return v;
  const float capped = maximum - l >= 0.0f ? l : maximum;
  return Scale(Scale(v, capped), Reciprocal(l));
}
inline float Clamp01(float v) {
  const float a = -v >= 0.0f ? 0.0f : v;
  return 1.0f - a >= 0.0f ? a : 1.0f;
}
} // namespace atelier::skate::plant_math
