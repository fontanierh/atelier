// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "ClimbingMath.h"
#include "ClimbingTypes.h"
#include "WorldGeometry.h"
namespace atelier::skate {
std::optional<ClimbingLedge> FindClimbingLedge(const WorldGeometry&,Vec3 feet,Vec3 facing);
std::optional<ClimbingLedge> FindAirClimbingLedge(const WorldGeometry&,Vec3 feet,Vec3 facing);
bool ClearClimbingLedge(const WorldGeometry&,ClimbingLedge);
} // namespace atelier::skate
