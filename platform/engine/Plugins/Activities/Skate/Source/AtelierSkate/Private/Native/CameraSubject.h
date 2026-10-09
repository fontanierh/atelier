#pragma once
#include "CameraTracking.h"
#include <array>
namespace atelier::skate::camera {
struct AnchorInputs {
  Vec4 board_position{};
  Vec4 board_velocity{};
  Vec4 board_acceleration{};
  Vec4 board_offset_direction{};
  Vec4 center_of_mass{};
  Vec4 damped_center_of_mass{};
  Vec4 skeleton_root_up{};
  Vec4 grind_point{};
  bool grinding{};
  bool reset{};
};
struct AnchorState {
  Vec4 position{};
  Vec4 velocity{};
  Vec4 acceleration{};
};
struct Anchors {
  std::array<AnchorState, 7> entries{};
  Vec4 grind_position{};
  void Update(AnchorInputs input);
};
struct SubjectPoseInputs {
  Mat4 physical_transform{};
  Mat4 skeleton_root{};
  Vec4 center_of_mass{};
  Vec4 reckoned_center_of_mass{};
  bool wiping_out{};
  bool state_flag_75{};
};
struct PublishedSubjectPose {
  Mat4 transform{};
  Vec4 damped_center_of_mass{};
};
struct SubjectPosePublisher {
  Mat4 previous_physical_transform{};
  SubjectPosePublisher();
  PublishedSubjectPose Publish(SubjectPoseInputs input);
};
struct Subject {
  Mat4 transform{};
  Mat4 skeleton_root{};
  Vec4 hips_position{};
  Vec4 last_valid_ground_up{};
  std::array<Vec4, 10> reference_positions{};
  std::uint32_t context{};
  float pumping_acceleration{};
  float state_height_32{};
  std::uint8_t in_ground_physics{};
  std::uint8_t grinding{};
  std::uint8_t trajectory_valid{};
  std::uint8_t wiping_out{};
  std::uint8_t physically_pushing{};
  std::uint8_t at_pushable_speed{};
  std::uint8_t off_board{};
  std::uint8_t air_flag_452{};
  std::uint8_t state_flag_81{};
  std::uint8_t broken_bone_slowmo{};
  std::uint8_t subject_flag_328{};
};
struct ReferencePointInputs {
  Vec4 head{};
  Vec4 hips{};
  Vec4 left_foot{};
  Vec4 right_foot{};
  Vec4 board{};
  Vec4 centre_of_mass{};
  Vec4 damped_centre_of_mass{};
  Vec4 grind_position{};
  Vec4 tracked_anchor{};
  Vec4 incline_normal{};
  std::uint8_t grinding{};
  std::array<Vec4, 10> Positions() const;
};
struct ManagerSubject {
  Subject rig{};
  std::array<AnchorState, 7> anchors{};
  std::array<float, 9> compass{};
  Vec4 board_offset_direction{};
  Vec4 ground_normal{};
  Vec4 launch_position{};
  Vec4 launch_normal{};
  Vec4 landing_position{};
  Vec4 landing_normal{};
  Vec4 apex_position{};
  Vec4 direction_424{};
  std::array<float, 2> look{};
  Vec4 steering{};
  float trajectory_time{};
  float trajectory_duration{};
  float apex_time{};
  float value_512{};
  float value_516{};
  std::uint8_t reset{};
  std::uint8_t flag_556{};
  std::uint8_t stance_560{};
  std::uint8_t stance_592{};
  std::uint8_t flag_652{};
  std::uint8_t shake_variant{};
  std::uint8_t special_effect{};
  std::uint8_t flag_684{};
  bool IsGroundCamera(std::uint32_t height_mode) const;
  float SteeringForTurn(bool mirrored) const;
  float SteeringForBlend(bool mirrored) const;
  float ValidTrajectoryDuration() const;
  float LookHeading() const;
};
struct CompassSettings {
  float heading_response{};
  float time_before_lineup{};
  float lineup_speed{};
  float minimum_deadzone_speed{};
  float maximum_deadzone_speed{};
  float maximum_deadzone_size{};
  float deadzone_smoothing{};
};
struct CompassInputs {
  Vec4 ground_normal{};
  Vec4 landing_normal{};
  Mat4 transform{};
  Vec4 trajectory_direction{};
  Vec4 launch_position{};
  Vec4 landing_position{};
  Vec4 grind_direction{};
  Vec4 skeleton_direction{};
  Vec4 camera_position{};
  Vec4 look_target{};
  std::array<float, 2> look{};
  float trajectory_fraction{};
  std::uint32_t selected_compass{};
  bool no_trajectory{};
  bool state_103{};
  bool wiping_out{};
  bool grinding{};
  bool air_flag_452{};
};
struct CompassPoseInputs {
  Vec4 skeleton_direction{};
  Vec4 look_target{};
  Vec4 board_velocity{};
  Vec4 trajectory_direction{};
  bool state_103{};
  CompassInputs Bind(const ManagerSubject &subject, Vec4 camera_position,
                     std::uint32_t selected_compass) const;
};
struct Compass {
  std::array<float, 9> headings{};
  float movement_heading{};
  float orbit_delta{};
  Vec4 velocity{};
  Vec4 damped_velocity{};
  Vec4 previous_position{};
  Vec4 orbit_position{};
  bool previous_reset{};
  float stopped_time{};
  float deadzone_size{};
  std::array<float, 2> deadzone_position{};
  std::array<float, 2> deadzone_velocity{};
  Compass();
  std::array<float, 9> Update(float dt, CompassInputs input,
                              CompassSettings settings);
  void UpdateMovement(float dt, CompassInputs input, CompassSettings settings);
  void UpdateDeadzone(float dt, std::array<float, 2> target);
  void UpdateOrbit(float dt, CompassInputs input);
  void UpdateFollow(CompassInputs input);
};
} // namespace atelier::skate::camera
