#pragma once
#include "SkeletonAirRuntime.h"
#include "SkeletonInputRuntime.h"
namespace atelier::skate {
struct PlantSkeletonFrame {
  ProcessedPhysicsInput &processed;
  SkeletonInputOwners owners;
  SkeletonInputRuntime &input;
  const std::vector<Mat4> &actual_globals;
  SkeletonAir &air;
};
bool AdvancePlantSkeleton(PlantSkeletonFrame, Vec4 world_anchor,
                          std::optional<std::size_t> bone, std::string &error);
void HoldPlantFoot(PhysicalSimulationRuntime &, FootIk &, bool right,
                   Vec4 world_position, std::uint32_t frames);
} // namespace atelier::skate
