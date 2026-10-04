// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <utility>

namespace atelier::skate
{
struct Vec3
{
    float x = 0.0f, y = 0.0f, z = 0.0f;
    constexpr Vec3() = default;
    constexpr Vec3(float x_value, float y_value, float z_value)
        : x(x_value), y(y_value), z(z_value) {}
};
using Vec4 = std::array<float,4>;
using Quat = Vec4;
using Mat4 = std::array<Vec4,4>;
struct Basis3 { std::array<std::array<float,3>,3> columns{}; };
struct Sqt { Vec4 scale{}, rotation{}, translation{}; };

// Ordinary operations must compile with FP contraction disabled. FMA appears
// only where the frozen Rust implementation explicitly calls f32::mul_add.
// The console's vector unit flushed denormal operands and results to zero, and the session's thread runs the same
// way: kept, a squared length that settles into the denormal range (a filter decaying onto an exact axis on flat
// ground) overflows InverseLengthSquared's refinement and Length3 returns NaN. False where it cannot be set.
bool FlushDenormalsToZero();
float Dot3(const Vec4& left, const Vec4& right);
float Dot4(const Vec4& left, const Vec4& right);
float Dot3(Vec3 left, Vec3 right);
float ReciprocalEstimate(float value);
float ReciprocalSquareRootEstimate(float value);
float RefinedReciprocal(float value, unsigned refinements = 2);
float InverseLengthSquared(float value, unsigned refinements = 2);
float VectorMin(float left, float right);
float VectorMax(float left, float right);
float Length3(const Vec4& value);
float Length3(Vec3 value);
Vec4 Normalize3(const Vec4& value, unsigned refinements = 2);
Vec4 Normalize4(const Vec4& value, unsigned refinements = 2);
Vec3 Normalize3(Vec3 value, unsigned refinements = 2);
Vec4 Cross3(const Vec4& left, const Vec4& right);
Vec3 Cross3(Vec3 left, Vec3 right);
Vec3 Madd(Vec3 value, float factor, Vec3 addend);
Vec3 Scale(Vec3 value, float factor);
Vec3 Subtract(Vec3 left, Vec3 right);
Vec4 LimitLength3(const Vec4& value, float limit);

// Distinct recovered power trees; Sin/Cos are not wrappers around SinCos.
std::pair<float,float> SinCos(float angle);
float Sin(float angle);
float Cos(float angle);
float Asin(float value);
float Acos(float value);
float Atan(float value);

Quat QuaternionMultiply(const Quat& first, const Quat& second);
std::array<float,3> QuaternionRotate(const Quat& rotation, const std::array<float,3>& vector);
Quat QuaternionBlend(const Quat& first, const Quat& second, float weight);
Mat4 SqtToMatrix(const Sqt& input);
Mat4 ConcatenateAffine(const Mat4& local, const Mat4& parent);
Mat4 InverseAffine(const Mat4& frame);
std::pair<Vec4,float> RotationAxisAngle(const Mat4& rotation);
Mat4 AxisRotation(const Vec4& axis, float angle);
std::pair<Mat4,float> InterpolateMatrix(const Mat4& first, const Mat4& second, float weight);
Mat4 InterpolateAffine(const Mat4& first, const Mat4& second, float weight);

template<std::size_t N> struct PointGraph
{
    static_assert(N > 0, "PointGraph requires a point");
    std::array<float,N> x{}, y{};
    float Evaluate(float input) const
    {
        if (input < x[0]) return y[0];
        if (!(input < x[N-1])) return y[N-1];
        for (std::size_t upper = 1; upper < N; ++upper)
        {
            if (!(input < x[upper])) continue;
            const std::size_t lower = upper-1;
            const float width = x[upper]-x[lower];
            if (width <= 0.0f) return y[upper];
            const float slope = (y[upper]-y[lower])/width;
            return std::fma(slope,input-x[lower],y[lower]);
        }
        return y[0];
    }
};
}
