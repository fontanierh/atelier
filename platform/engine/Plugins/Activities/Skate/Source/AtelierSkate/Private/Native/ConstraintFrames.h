// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "RigidBody.h"

namespace atelier::skate::constraint_frame
{
struct QuaternionRows {std::array<Vec3,3> axes;Quat relative;};
QuaternionRows Rows(Quat a,Quat b);
Quat Compose(Quat a,Quat b);
Basis3 Basis(Quat q);
Vec3 TransformDirection(Basis3 basis,Vec3 vector);
Vec3 PointRate(Vec3 linear,Vec3 angular,Vec3 arm);
Vec3 MultiplyInertia(PackedWorldInverseInertia inertia,Vec3 vector);
Vec3 MultiplyInertiaFromZero(PackedWorldInverseInertia inertia,Vec3 vector);
std::array<Vec3,3> Columns(Basis3 basis);
std::array<float,3> Project(Vec3 vector,const std::array<Vec3,3>& axes);
}
