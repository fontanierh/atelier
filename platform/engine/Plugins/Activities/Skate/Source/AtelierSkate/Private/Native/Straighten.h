// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
namespace atelier::skate
{
struct StraightenSettings {PointGraph<16> time_response;float opposite_turn_limit,time_scalar,heading_time_limit,strength;};
struct StraightenInput {float heading_time,scalar_2764,turn;Vec4 forward,velocity,normal;};
Vec4 CalculateStraighten(const StraightenSettings&,const StraightenInput&);
}
