// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PlayerInputTypes.h"
namespace atelier::skate
{
class GrindCamera
{
public:
    Vec4 current{},previous{},error{},midpoint{};std::uint32_t family=0;bool active=false;
    void ConditionFields(GrindOutputFields&);
};
}
