#pragma once
#include "CameraTracking.h"
#include "WorldGeometry.h"
#include <functional>
#include <vector>
namespace atelier::skate::camera {
struct FatLine {
  Vec4 start{}, end{};
  float radius = 0;
};
struct FatLineResult {
  Vec4 position{}, normal{};
  float fraction = 0;
  std::uint8_t hit = 0;
  std::uint32_t surface = 0;
};
Vec4 PositionFromAngles(Vec4 anchor, Vec4 offset, float elevation,
                        float heading, float distance,
                        std::uint8_t clamp_height, float minimum_height);
Vec4 ProjectHit(Vec4 end, Vec4 first_query_start, FatLineResult result);
class PositionerCollisionProvider {
public:
  virtual ~PositionerCollisionProvider() = default;
  virtual void Submit(std::array<FatLine, 6> lines, std::uint32_t context) = 0;
  virtual std::array<FatLineResult, 6> Results() = 0;
};
class DropCollisionProvider {
public:
  virtual ~DropCollisionProvider() = default;
  virtual bool Query(std::array<FatLine, 10> lines, std::uint32_t context,
                     std::array<FatLineResult, 10> &result,
                     std::string &error) = 0;
};
bool WorldLine(const WorldGeometry &world, Vec4 start, Vec4 end, float radius,
               FatLineResult &result, std::string &error);
class CameraCollision final : public PositionerCollisionProvider,
                              public DropCollisionProvider {
public:
  explicit CameraCollision(const WorldGeometry &value) : world(value) {}
  const WorldGeometry &world;
  std::array<FatLineResult, 6> results{};
  std::optional<std::string> error;
  void Submit(std::array<FatLine, 6> lines, std::uint32_t context) override;
  std::array<FatLineResult, 6> Results() override { return results; }
  bool Query(std::array<FatLine, 10> lines, std::uint32_t context,
             std::array<FatLineResult, 10> &result,
             std::string &error) override;
};
struct PositionerConfig {
  Vec4 anchor{}, offset{};
  float reference_heading = 0, reference_elevation = 0, heading = 0,
        elevation = 0, distance = 0, minimum_distance = 0;
  std::uint8_t collision_enabled = 0, bypass_distance_tracker = 0,
               clamp_height = 0;
  float floor_height = 0, speed_clamp = 0, acceleration_clamp = 0,
        smoothing = 0;
  std::array<Vec4, 3> query_starts{};
};
struct Positioner {
  ScalarTracker distance_tracker;
  ScalarTrackerParameters tracker_parameters;
  Vec4 offset{}, previous_valid_position{}, reference_position{};
  float collision_clear_time = 0;
  PositionerConfig config;
  Vec4 position{}, velocity{};
  float distance = 0, heading = 0, elevation = 0, radius = 0,
        available_distance = 0;
  std::uint8_t flags = 0;
  std::uint32_t Update(float dt, std::uint32_t context, PositionerConfig value,
                       PositionerCollisionProvider &collision);
  std::uint32_t Resolve(std::uint32_t context,
                        PositionerCollisionProvider &collision);
  void SubmitCollision(std::uint32_t context,
                       PositionerCollisionProvider &collision);
  std::uint32_t ResolveCollision(std::uint32_t context,
                                 PositionerCollisionProvider &collision);
  Vec4 PositionAt(float elevation, float heading, float distance) const;
};
struct PathObstacle {
  Vec4 position{}, velocity{};
  float radius = 0;
};
struct PredictionPath {
  Vec4 position{}, velocity{};
  float radius = 0, horizon = 0;
};
float CandidateCollisionTime(PredictionPath path, const PathObstacle *obstacles,
                             std::size_t count);
class TrajectoryCollisionRequest {
public:
  virtual ~TrajectoryCollisionRequest() = default;
  virtual void Submit(PredictionPath path, std::uint32_t context,
                      std::uint8_t acceleration_flag) = 0;
  virtual bool IsReady() = 0;
  virtual float CollisionTime() = 0;
};
class MovingObstacleProvider {
public:
  virtual ~MovingObstacleProvider() = default;
  virtual std::size_t Collect(Vec4 position, Vec4 velocity, float radius,
                              std::array<PathObstacle, 50> &output) = 0;
};
struct PathEvaluator {
  std::uint32_t request_state = 0;
  PredictionPath path;
  std::uint8_t acceleration_flag = 0;
  float collision_time = 0, last_valid_time = 0;
  std::uint8_t found = 0, result_acceleration_flag = 0,
               submitted_acceleration_flag = 0;
  std::int32_t pending_polls = 0;
  void UpdateRequest(std::uint32_t context,
                     TrajectoryCollisionRequest &request);
  bool Update(std::uint32_t context, TrajectoryCollisionRequest &request,
              MovingObstacleProvider &moving, std::string &error);
};
struct TrajectoryQuery {
  Vec4 position{}, velocity{}, gravity{};
  float duration = 0, radius = 0, start_error = 0, end_error = 0;
  using Line = std::function<bool(Vec4, Vec4, float, std::optional<Vec4> &,
                                  std::string &)>;
  bool CollisionTime(const Line &line, float &result, std::string &error) const;
  Vec4 Evaluate(float time) const;
  float StepSize(float error_radius) const;
  float TimeAtContact(Vec4 position, float time) const;
};
struct TrajectoryResult {
  bool ready = false;
  float time = -1;
  std::optional<std::string> error;
};
class CameraTrajectory final : public TrajectoryCollisionRequest {
public:
  CameraTrajectory(const WorldGeometry &w, Vec4 g, TrajectoryResult &r)
      : world(w), gravity(g), result(r) {}
  const WorldGeometry &world;
  Vec4 gravity;
  TrajectoryResult &result;
  void Submit(PredictionPath path, std::uint32_t context,
              std::uint8_t acceleration_flag) override;
  bool IsReady() override { return result.ready; }
  float CollisionTime() override { return result.time; }
};
struct DropSettings {
  float minimum_test_distance = 0, total_test_time = 0,
        maximum_test_distance = 0, maximum_drop_distance = 0;
};
struct DropProbe {
  Vec4 start{}, end{}, normal{};
  float depth = 0;
  bool valid = false, hit = false;
};
struct DropPredictor {
  Vec4 horizontal_velocity{}, steepest_normal{};
  bool has_normal = false;
  float elevation = 0, distance_offset = 0, target_elevation = 0, spacing = 0;
  std::size_t selected = 0;
  std::array<DropProbe, 5> probes{};
  std::optional<
      std::pair<std::array<FatLine, 10>, std::array<FatLineResult, 10>>>
      pending;
  void Reset();
  static Vec4 PredictionVelocity(bool reset, Mat4 transform, Vec4 rig_velocity,
                                 DropSettings settings);
  bool Update(Vec4 position, Vec4 velocity, bool enabled, bool offboard,
              std::uint32_t context, DropSettings settings,
              DropCollisionProvider &query, std::string &error);
  float DropDepth() const;
  std::array<FatLine, 10> Lines(Vec4 position, float depth) const;
  void Consume(std::array<FatLine, 10> lines,
               std::array<FatLineResult, 10> results, float maximum_depth);
  void UpdateElevation(bool enabled, bool offboard);
};
} // namespace atelier::skate::camera
