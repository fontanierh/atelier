#pragma once
#include "AirTrajectoryQuery.h"
#include "AnimatedSkeleton.h"
#include "PhysicalSimulationRuntime.h"
#include "PlayerGrindInputWorld.h"
#include "PlayerInputTypes.h"
namespace atelier::skate {
// Required KnownAir producer packet. The original trajectory's three padding
// words are never read by Footplant; its actual position/velocity/acceleration
// and scalar use the shared canonical trajectory record.
struct KnownAirFootplantInput {
  AirTrajectory trajectory;
  float remaining_collision_time;
  Vec4 collision_position, landing_normal;
};
struct FootplantPredictionFrame {
  const ProcessedPhysicsInput &processed;
  const BoardToolkit &toolkit;
  const AnimatedSkeleton &animated;
  const PhysicalSimulationRuntime &physical;
  const std::vector<PlayerGrindPrimitive> &edges;
};
// Complete core offboard/air_selector/ledge::filter_edges, used unchanged by
// Footplant's nearby-edge correction. XYZ endpoints retain authored order.
struct FootplantEdge {
  Vec3 start, end;
};
std::vector<FootplantEdge>
FootplantFilterEdges(const std::vector<FootplantEdge> &, Vec4 reference);
} // namespace atelier::skate
