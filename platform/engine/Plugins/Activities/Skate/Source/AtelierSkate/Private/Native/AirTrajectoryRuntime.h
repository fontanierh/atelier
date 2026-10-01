// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AirTrajectoryQuery.h"
#include "PlantTrajectoryQueries.h"
namespace atelier::skate {
// The shared complete collision query used by the selector and plant callers.
// Selector ownership is added separately; this type contains no synthetic
// pending results or gameplay state.
class AirTrajectoryRuntime : public HandplantTrajectoryQueries {
public:
  static bool Query(const WorldGeometry &, AirTrajectoryQueryRequest,
                    AirTrajectoryQueryResult &, std::string &);
  bool Query(const WorldGeometry &, const AirTrajectory &, float radius,
             float start_error, float end_error, PlantTrajectoryQueryResult &,
             std::string &) override;
};
} // namespace atelier::skate
