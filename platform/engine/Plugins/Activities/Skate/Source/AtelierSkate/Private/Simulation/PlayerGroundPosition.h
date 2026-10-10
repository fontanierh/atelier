#pragma once
#include "BoardRuntime.h"
#include "PlayerInputTypes.h"
namespace atelier::skate
{
// Actual host CalculateGroundPosition82C02840. Frame translation is deliberately
// not used; wheel rigid-body centres are read from this same live board owner.
RawVector PlayerGroundPosition(const BoardRuntime&,const Mat4& ground);
Vec4 PlayerWheelGroundPosition(const std::array<Vec4,4>& wheels,const Mat4& ground);
}
