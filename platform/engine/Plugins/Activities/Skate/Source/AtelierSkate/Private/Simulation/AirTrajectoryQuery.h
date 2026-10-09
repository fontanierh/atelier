#pragma once
#include "AirState.h"
#include "WorldGeometry.h"
#include <vector>
namespace atelier::skate {
struct AirTrajectoryQueryRequest {
  AirTrajectory trajectory;
  float radius, start_error, end_error;
};
struct AirTrajectorySurfaceHit {
  Vec4 position, normal;
  Mat4 transform;
  std::uint32_t surface, geometry;
};
struct AirTrajectoryQueryResult {
  Vec4 contact_position, contact_normal, landing_normal;
  float contact_time;
  Mat4 contact_transform;
  std::int32_t contact_frame;
  std::uint32_t surface, geometry;
  static AirTrajectoryQueryResult Miss();
};
class AirTrajectoryWorldQueries {
public:
  virtual ~AirTrajectoryWorldQueries() = default;
  virtual bool Line(Vec4 start, Vec4 end, float radius,
                    std::optional<AirTrajectorySurfaceHit> &, std::string &) = 0;
  virtual bool Nearby(Vec4 position, float radius,
                      std::vector<std::array<Vec4, 3>> &, std::string &) = 0;
};
Vec4 AirTrajectoryPositionAt(const AirTrajectory &, float time);
Vec4 AirTrajectoryVelocityAt(const AirTrajectory &, float time);
std::pair<Vec4, float> AirTrajectoryHighestPosition(const AirTrajectory &);
bool QueryAirTrajectory(AirTrajectoryQueryRequest, AirTrajectoryWorldQueries &,
                        AirTrajectoryQueryResult &, std::string &);
bool AirTrajectoryWorldLine(const WorldGeometry &, Vec4 start, Vec4 end,
                            float radius,
                            std::optional<AirTrajectorySurfaceHit> &,
                            std::string &);
bool AirTrajectoryNearbyTriangles(const WorldGeometry &, Vec4 center,
                                  float radius,
                                  std::vector<std::array<Vec4, 3>> &,
                                  std::string &);
} // namespace atelier::skate
