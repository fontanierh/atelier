// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "RigidBody.h"
namespace atelier::skate
{
void ApplyDeckAxisDisplacement(BodyRates&,Vec3 requested);
void ApplyDeckLimitedDisplacement(BodyRates&,Vec3 requested);
void ApplyDeckAngularDisplacement(BodyRates&,Vec3 displacement);
void ApplyGroundBodyTorque(BodyRates&);
}
