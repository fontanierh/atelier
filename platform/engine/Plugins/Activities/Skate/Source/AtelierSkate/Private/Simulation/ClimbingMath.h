#pragma once
#include "SimulationMath.h"
#include <optional>
namespace atelier::skate::climbing_math {
// This is the current authored extension's glam 0.32.1 arithmetic, distinct
// from the simulation's affine frames and reciprocal/trigonometric kernels.
inline constexpr Mat4 Identity{{Vec4{1,0,0,0},Vec4{0,1,0,0},Vec4{0,0,1,0},Vec4{0,0,0,1}}};
inline constexpr Vec3 Up{0,1,0};
Vec3 Add(Vec3,Vec3);Vec3 Sub(Vec3,Vec3);Vec3 ScaleVector(Vec3,float);
float Dot(Vec3,Vec3);Vec3 Cross(Vec3,Vec3);float Length(Vec3);
float Distance(Vec3,Vec3);Vec3 Normalize(Vec3);std::optional<Vec3> TryNormalize(Vec3);
Vec3 NormalizeOrZero(Vec3);Vec3 Orthonormal(Vec3);Vec3 Lerp(Vec3,Vec3,float);
float Length4(Vec4);Quat NormalizeQuat(Quat);Quat InverseQuat(Quat);
Quat MultiplyQuat(Quat,Quat);Quat RotationAxes(Vec3,Vec3,Vec3);
Quat RotationY(float);Quat RotationArc(Vec3,Vec3);Quat Slerp(Quat,Quat,float);
Vec3 Rotate(Quat,Vec3);
Mat4 Matrix(const Mat4& simulation);Mat4 Simulation(const Mat4& homogeneous);
Mat4 Multiply(const Mat4&,const Mat4&);Mat4 Inverse(const Mat4&);
float Determinant(const Mat4&);Vec3 Point(const Mat4&,Vec3);Vec3 Vector(const Mat4&,Vec3);
Vec3 Translation(const Mat4&);float Smooth(float);
struct Transform {
  Vec3 translation{};Quat rotation{0,0,0,1};Vec3 scale{1,1,1};
  Mat4 ToMatrix() const;
  static Transform FromMatrix(const Mat4&);
};
Transform Blend(Transform,Transform,float);
} // namespace atelier::skate::climbing_math
