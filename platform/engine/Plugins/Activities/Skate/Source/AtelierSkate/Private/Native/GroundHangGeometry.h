// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "WorldGeometry.h"
namespace atelier::skate
{
struct HangGeometryInput {Vec3 edge_start,edge_end,reference_point;};
struct HangLine {Vec3 start,end;float radius;};
std::optional<std::array<HangLine,6>> GroundHangLines(HangGeometryInput,float deck_center_to_truck);
bool GroundHungClassification(const std::array<std::optional<float>,6>&);
bool DetectGroundHungGeometry(const WorldGeometry&,HangGeometryInput,float deck_center_to_truck,bool&,std::string&);
}
