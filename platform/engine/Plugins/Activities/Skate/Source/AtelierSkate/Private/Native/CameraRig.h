#pragma once
#include "CameraSubject.h"
#include "CameraWorld.h"
namespace atelier::skate::camera {
struct AngleTrackingSettings {
  float speed_clamp_degrees{};
  float acceleration_min_degrees{};
  float acceleration_max_degrees{};
  float delta_umbra_degrees{};
  float delta_penumbra_degrees{};
};
struct AnchorTrackingSettings {
  PointGraph<8> latch_curve{};
  PointGraph<8> input_curve{};
  float speed_clamp{};
  float acceleration_clamp{};
  float latch_scale{};
  float input_threshold{};
  float input_scale{};
};
struct DistanceTrackingSettings {
  float speed_clamp{};
  float smoothing{};
  float acceleration_clamp{};
};
struct RigPositioningSettings {
  DistanceTrackingSettings normal{};
  DistanceTrackingSettings alternate{};
  float minimum_distance{};
  float alternate_minimum_distance{};
};
struct AvoidanceSettings {
  float horizon{};
  float heading_smoothing{};
  float elevation_smoothing{};
  float ease_out_time{};
  float radius_padding{};
};
struct OrientationTrackerSettings {
  float acceleration_min_degrees{};
  float acceleration_max_degrees{};
  float smoothing_min{};
  float delta_umbra_degrees{};
  float delta_penumbra_degrees{};
};
struct OrientationSettings {
  float pan_umbra_degrees{};
  float pan_penumbra_degrees{};
  PointGraph<8> pan_smoothing_curve{};
  float pan_minimum_smoothing{};
  OrientationTrackerSettings pan{};
  OrientationTrackerSettings tilt{};
};
struct RigSettings {
  AngleTrackingSettings heading{};
  AngleTrackingSettings elevation{};
  AnchorTrackingSettings anchor{};
  AvoidanceSettings avoidance{};
  RigPositioningSettings positioning{};
  float collision_hold_duration{};
  Vec4 normalization_threshold{};
};
struct RigFields {
  Vec4 anchor{};
  Vec4 velocity{};
  Vec4 acceleration{};
  Vec4 offset{};
  float heading_target{};
  float heading_reference{};
  float elevation_reference{};
  float elevation_target{};
  float elevation_offset{};
  float additional_elevation{};
  float heading_offset{};
  float avoidance_heading{};
  float avoidance_elevation{};
  float smoothed_acceleration{};
  float previous_acceleration{};
  float collision_hold_time{};
  float reset_time{};
  float disable_avoidance_time{};
  float height_transition_start{};
  float height_transition_end{};
  float height_transition_weight{};
  float height_transition_duration{};
  float height_transition_time{};
  float reference_height{};
  float previous_height{};
  float height_offset{};
  float latch_time{};
  float input_time{};
  float distance{};
  float heading_smoothing{};
  float elevation_smoothing{};
  float heading_weight{};
  float elevation_weight{};
  float mode_time{};
  std::uint32_t frame_counter{};
  std::uint32_t collision_mode{};
  std::uint32_t avoidance_mode{};
  std::uint32_t height_mode{};
  std::uint32_t previous_height_mode{};
  std::uint8_t flags_516{};
  std::uint8_t flags_517{};
};
struct AngularRigTracking {
  AngleTracker heading{};
  ScalarTrackerParameters heading_parameters{};
  AngleTracker elevation{};
  ScalarTrackerParameters elevation_parameters{};
  float heading_target{};
  float elevation_target{};
  float heading_offset{};
  float reset_time{};
  float heading_smoothing{};
  float elevation_smoothing{};
  float heading_acceleration_state{};
  std::uint8_t flags_517{};
  float CurrentHeading() const;
  bool ResetHeading(bool clear_motion, std::string &error);
  bool ResetElevation(bool clear_motion, std::string &error);
  bool UpdateHeading(float dt, AngleTrackingSettings settings,
                     std::string &error);
  bool UpdateElevation(float dt, AngleTrackingSettings settings,
                       std::string &error);
};
struct ReferenceHeightTracking {
  float anchor_height{};
  float transition_start{};
  float transition_end{};
  float transition_weight{};
  float transition_duration{};
  float transition_time{};
  float height{};
  float previous_height{};
  float height_offset{};
  std::uint32_t mode{};
  std::uint8_t flags_516{};
  std::uint8_t flags_517{};
  void Update(float dt, const Subject &subject);
};
struct AnchorRigTracking {
  VectorTracker tracker{};
  ScalarTrackerParameters parameters{};
  Vec4 anchor{};
  Vec4 velocity{};
  float reference_height{};
  float latch_time{};
  float input_time{};
  std::uint8_t flags_516{};
  std::uint8_t flags_517{};
  float LatchSmoothing(float dt, AnchorTrackingSettings settings,
                       const Subject &subject);
  float InputSmoothing(float dt, AnchorTrackingSettings settings,
                       const Subject &subject);
  void Update(float dt, AnchorTrackingSettings settings,
              const Subject &subject);
};
struct RigFraming {
  Vec4 anchor{};
  Vec4 offset{};
  float elevation_offset{};
  float additional_elevation{};
  float reference_height{};
  float distance{};
  bool Update(float dt, AngularRigTracking &angular, Vec4 tracked_anchor,
              const Positioner &positioner, Vec4 threshold, std::string &error);
};
struct RigPositioning {
  float heading_reference{};
  float elevation_reference{};
  float avoidance_heading{};
  float avoidance_elevation{};
  float elevation_weight{};
  std::uint32_t collision_mode{};
  std::uint8_t flags_516{};
  bool Update(float dt, RigPositioningSettings settings,
              AngularRigTracking &angular, const RigFraming &framing,
              Vec4 tracked_anchor, Positioner &positioner,
              std::vector<Vec4> &breadcrumbs, const Subject &subject,
              PositionerCollisionProvider &collision, std::string &error);
};
struct AvoidancePath {
  PathEvaluator evaluator{};
  std::uint8_t prediction_flag{};
};
struct RigAvoidance {
  Vec4 anchor{};
  Vec4 velocity{};
  Vec4 tracked_anchor{};
  float heading_target{};
  float heading_reference{};
  float elevation_target{};
  float avoidance_heading{};
  float avoidance_elevation{};
  float reset_time{};
  float disable_time{};
  float height_transition_start{};
  float height_transition_end{};
  float height_transition_duration{};
  float height_transition_time{};
  float reference_height{};
  float prediction_distance{};
  float heading_weight{};
  float elevation_weight{};
  std::uint32_t avoidance_mode{};
  std::uint32_t height_mode{};
  std::uint8_t flags_516{};
  std::array<AvoidancePath, 3> paths{};
  bool Update(float dt, AvoidanceSettings settings,
              const Positioner &positioner, Vec4 previous_breadcrumb,
              const Subject &subject,
              std::array<TrajectoryCollisionRequest *, 3> requests,
              MovingObstacleProvider &moving, std::string &error);
};
struct Breadcrumbs {
  std::vector<Vec4> positions{};
  std::size_t index{};
  float distance_squared_threshold{};
  Vec4 Last() const;
  void Update(Vec4 position);
};
struct Rig {
  RigFields fields{};
  AngleTracker heading{};
  ScalarTrackerParameters heading_parameters{};
  AngleTracker elevation{};
  ScalarTrackerParameters elevation_parameters{};
  VectorTracker anchor{};
  ScalarTrackerParameters anchor_parameters{};
  Positioner positioner{};
  std::array<AvoidancePath, 3> paths{};
  Breadcrumbs breadcrumbs{};
  explicit Rig(std::uint32_t avoidance_mode = 1);
  bool Reset(std::string &error);
  bool Teleport(std::string &error);
  void SetElevation(float elevation, bool use_avoidance);
  bool ResetAngles(std::string &error);
  AngularRigTracking Angular() const;
  void StoreAngular(const AngularRigTracking &angular);
  RigFraming Framing() const;
  bool Update(float dt, RigSettings settings, Subject &subject,
              std::array<TrajectoryCollisionRequest *, 3> requests,
              MovingObstacleProvider &moving,
              PositionerCollisionProvider &collision, std::string &error);
};
struct RigOrientation {
  Vec4 target{};
  Basis3 basis{};
  AngleTracker pitch{};
  AngleTracker yaw{};
  ScalarTrackerParameters pitch_parameters{};
  ScalarTrackerParameters yaw_parameters{};
  float pan_smoothing{};
  float tilt_smoothing{};
  float roll{};
  float framing_mirror{};
  RigOrientation();
  bool Update(float dt, OrientationSettings settings, float reset_time,
              std::uint8_t &flags_516, std::uint8_t flags_517,
              std::string &error);
};
} // namespace atelier::skate::camera
