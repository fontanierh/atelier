// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CameraGraphOperations.h"
#include "CameraSettings.h"

namespace atelier::skate::camera {
// One completed physical/animation publication. Camera history belongs to this
// owner; the caller supplies the actual live producer values in every field.
struct CameraSubjectSnapshot {
  std::uint64_t tick = 0;
  ManagerSubject subject{};
  SubjectPoseInputs pose{};
  AnchorInputs anchors{};
  ReferencePointInputs reference_points{};
  CompassPoseInputs compass{};
  CameraGraphSubject graph{};
};

struct SubjectPublisher {
  SubjectPosePublisher pose{};
  Anchors anchors{};
  Compass compass{};
  std::optional<std::uint64_t> last_tick;
  bool Publish(CameraSubjectSnapshot input, const CameraMan &manager,
               CompassSettings settings, ManagerSubject &result,
               std::string &error);
};

// Complete active camera schedule. Rendering consumes frame without advancing
// any camera clock. WorldGeometry and moving obstacles are mandatory live
// inputs.
struct CameraRuntime {
  CameraMan manager{};
  SubjectPublisher subject{};
  CameraGraph graph{};
  CameraData data{};
  CameraSettings settings{};
  std::array<TrajectoryResult, 3> trajectories{};
  std::optional<CameraFrame> frame;
  std::optional<CameraSubjectSnapshot> latest_subject;
  std::vector<SimulationRateRequest> simulation_rate_requests;

  bool Load(const SettingsDatabase &stock, const Graph &source,
            const std::vector<std::uint8_t> &camera_data, std::string &error);
  void SetAspectRatio(float value) { manager.state.aspect_ratio = value; }
  std::string_view SelectedShot() const {
    return manager.shots.current.definition.name;
  }
  bool Advance(float dt, CameraSubjectSnapshot snapshot,
               const WorldGeometry &world, Vec4 query_gravity,
               const CameraGraphEnvironment &environment,
               MovingObstacleProvider &moving, CameraFrame &result,
               std::string &error);
};
} // namespace atelier::skate::camera
