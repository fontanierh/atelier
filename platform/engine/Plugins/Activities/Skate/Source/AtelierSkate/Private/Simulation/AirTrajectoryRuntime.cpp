#include "AirTrajectoryRuntime.h"
namespace atelier::skate {
namespace {
class Queries final : public AirTrajectoryWorldQueries {
public:
  explicit Queries(const WorldGeometry &value) : world(value) {}
  bool Line(Vec4 start, Vec4 end, float radius,
            std::optional<AirTrajectorySurfaceHit> &output,
            std::string &error) override {
    return AirTrajectoryWorldLine(world, start, end, radius, output, error);
  }
  bool Nearby(Vec4 center, float radius,
              std::vector<std::array<Vec4, 3>> &output,
              std::string &error) override {
    return AirTrajectoryNearbyTriangles(world, center, radius, output, error);
  }
  const WorldGeometry &world;
};
} // namespace
bool AirTrajectoryRuntime::Query(const WorldGeometry &world,
                                 AirTrajectoryQueryRequest request,
                                 AirTrajectoryQueryResult &output,
                                 std::string &error) {
  Queries queries(world);
  return QueryAirTrajectory(request, queries, output, error);
}
bool AirTrajectoryRuntime::Query(const WorldGeometry &world,
                                 const AirTrajectory &trajectory, float radius,
                                 float start_error, float end_error,
                                 PlantTrajectoryQueryResult &output,
                                 std::string &error) {
  AirTrajectoryQueryResult result;
  if (!Query(world, {trajectory, radius, start_error, end_error}, result, error))
    return false;
  output = {result.contact_position, result.contact_normal, result.landing_normal,
            result.contact_time, result.contact_transform, result.contact_frame,
            result.surface, result.geometry};
  return true;
}
} // namespace atelier::skate
