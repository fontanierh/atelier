// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "CameraEffects.h"
#include "CameraRig.h"
namespace atelier::skate::camera {
struct ManagerState {
  Vec4 anchor{};
  Vec4 anchor_velocity{};
  Vec4 landing_normal{};
  Vec4 launch_position{};
  Vec4 ground_normal{};
  Vec4 previous_velocity{};
  Vec4 incline_normal{};
  std::uint32_t selected_anchor{};
  float frontside_angle{};
  float ground_heading{};
  float velocity_incline{};
  float absolute_velocity_incline{};
  float launch_incline{};
  float signed_landing_incline{};
  float landing_incline{};
  float direction_incline{};
  float field_of_view{};
  float apex_height{};
  float apex_time{};
  float time_without_trajectory{};
  float landing_height_delta{};
  float apex_height_ratio{};
  float launch_landing_heading_delta{};
  float trajectory_camera_distance{};
  float steering_time{};
  float centred_time{};
  float opacity{};
  float aspect_ratio{};
  float blur{};
  float effect_weight{};
  float collision_elevation{};
  std::uint32_t frames{};
  std::uint32_t slowmo_frames{};
  std::uint32_t instant_frames{};
  std::uint8_t flags{};
  std::uint8_t options{};
  ScalarTracker heading_mirror{};
  ScalarTracker framing_mirror{};
  ManagerState();
  bool ResetRequested() const { return (options & 0x80) != 0; }
  void RequestReset() { options |= 0x80; }
  bool Mirrored() const { return (flags & 8) != 0; }
  void UpdateTiming(const ManagerSubject &subject, float steering_threshold);
  void UpdateMirrors(float dt, const ManagerSubject &subject, const Rig &rig,
                     const ShotManager &shots);
  bool UpdateAir(const ManagerSubject &subject, Rig &rig,
                 std::optional<std::pair<Vec4, Vec4>> &impulse,
                 std::string &error);
  bool UpdateIncline(const ManagerSubject &subject, std::string &error);
  bool UpdateSlopeRelation(const ManagerSubject &subject, std::string &error);
  float BindShot(Shot shot, const ManagerSubject &subject, Rig &rig,
                 RigOrientation &orientation, const DropPredictor &drop,
                 LookInput look, float previous_roll, bool transitioning);
};
struct ManagerSettings {
  RigSettings rig{};
  OrientationSettings orientation{};
  FrameSettings framing{};
  DropSettings drop{};
  LookSettings look{};
  ShakeSettings shake{};
  float steering_threshold{};
};
struct CameraMan {
  ManagerState state{};
  Rig rig{};
  ShotManager shots{};
  RigOrientation orientation{};
  FrameComposer composer{};
  DropPredictor drop{};
  LookInput look{};
  std::array<ShakeEffect, 2> shake{};
  CameraFrame frame{};
  Vec4 subject_forward{};
  float heading_multiplier{};
  CameraMan();
  bool Prepare(const ManagerSubject &subject, ManagerSettings settings,
               std::string &error);
  bool SetShot(std::string_view name, bool force, const ManagerSubject &subject,
               const ShotDatabase &database, bool &changed, std::string &error);
  bool Update(float dt, ManagerSubject &subject, ManagerSettings settings,
              std::array<const ShakeSamples *, 2> samples,
              std::array<TrajectoryCollisionRequest *, 3> requests,
              MovingObstacleProvider &moving,
              PositionerCollisionProvider &positioning,
              DropCollisionProvider &dropping, CameraFrame &result,
              std::string &error);
  bool BindAnchor(const ManagerSubject &subject, bool reset,
                  std::string &error);
  bool FinishFrame(float dt, const ManagerSubject &subject,
                   ShakeSettings settings,
                   std::array<const ShakeSamples *, 2> samples, bool reset,
                   std::string &error);
};
struct BlendEnvironment final : ShotEnvironment {
  const ManagerState &state;
  const ManagerSubject &subject;
  const Rig &rig;
  Vec4 rig_forward{}, angular_velocity{};
  float heading_multiplier = 0, previous_distance = 0;
  BlendEnvironment(const CameraMan &manager, const ManagerSubject &subject);
  float HeadingMirror() const override { return heading_multiplier; }
  bool CompassNorth(std::uint32_t entry, float &result,
                    std::string &error) const override;
  bool SpecialCameraFlag() const override { return (state.flags & 0x10) != 0; }
  float RawBlendValue(std::uint32_t kind, float authored, float dt) override;
  float AirProgress() const;
  float ApexProgress() const;
};
} // namespace atelier::skate::camera
