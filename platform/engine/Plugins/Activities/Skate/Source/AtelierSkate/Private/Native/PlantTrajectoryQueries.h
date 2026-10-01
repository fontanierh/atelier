// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirState.h"
#include "WorldGeometry.h"
namespace atelier::skate {
struct PhysicalRidingOutputs;
struct ProcessedPhysicsInput;
struct PlantTrajectoryQueryResult {
  Vec4 contact_position, contact_normal, landing_normal;
  float contact_time;
  Mat4 contact_transform;
  std::int32_t contact_frame;
  std::uint32_t surface, geometry;
};
class HandplantTrajectoryQueries {
public:
  virtual ~HandplantTrajectoryQueries() = default;
  virtual bool Query(const WorldGeometry &, const AirTrajectory &, float radius,
                     float start_error, float end_error,
                     PlantTrajectoryQueryResult &, std::string &) = 0;
};
class HandplantAirReckoning {
public:
  virtual ~HandplantAirReckoning() = default;
  virtual void UpdatePlant(PhysicalRidingOutputs &,
                           const ProcessedPhysicsInput &, Vec4 up,
                           Vec4 heading) = 0;
};
} // namespace atelier::skate
