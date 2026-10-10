#include "CameraManager.h"
#include "RigidBody.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
constexpr Vec4 Up{0, 1, 0, 0};
float AngleBetween(Vec4 a, Vec4 b) {
  const float a_square = Dot3(a, a), b_square = Dot3(b, b),
              epsilon = Bits(0x38d1b717);
  if (!(a_square > epsilon && b_square > epsilon))
    return 0;
  return Acos(
      VectorMin(VectorMax(Dot3(Mul(a, InverseLengthSquared(a_square, 1)),
                               Mul(b, InverseLengthSquared(b_square, 1))),
                          -1),
                1));
}
} // namespace
ManagerState::ManagerState() {
  landing_normal = Up;
  ground_normal = Up;
  time_without_trajectory = std::numeric_limits<float>::max();
  opacity = 1;
  aspect_ratio = Bits(0x3fe38e39);
  blur = 1;
  effect_weight = 1;
  instant_frames = 3;
  flags = 2;
  options = 0x60;
  heading_mirror.target = 1;
  heading_mirror.position = 1;
  framing_mirror = heading_mirror;
}
void ManagerState::UpdateTiming(const ManagerSubject &s, float threshold) {
  const float step = Bits(0x3c888889);
  time_without_trajectory =
      s.rig.trajectory_valid != 0 ? 0 : time_without_trajectory + step;
  if (s.reset != 0 || ResetRequested()) {
    options |= 0x80;
    flags &= std::uint8_t(~4);
    trajectory_camera_distance = 0;
    centred_time = 0;
    steering_time = 0;
    collision_elevation = 0;
    instant_frames = 3;
    anchor_velocity = {};
  }
  steering_time =
      std::abs(s.steering[0]) <= threshold ? 0 : steering_time + step;
  centred_time = std::abs(s.SteeringForTurn(Mirrored())) >= threshold
                     ? 0
                     : centred_time + step;
  flags = (flags & std::uint8_t(~8)) |
          (std::uint8_t(s.stance_592 != s.stance_560) << 3);
}
void ManagerState::UpdateMirrors(float dt, const ManagerSubject &subject,
                                 const Rig &rig, const ShotManager &shots) {
  if (!ResetRequested() && !subject.IsGroundCamera(rig.fields.height_mode))
    return;
  const auto option = ResetRequested()
                          ? shots.FirstLeaf().mirror_for_stance
                          : shots.current.definition.shot.mirror_for_stance;
  const float target = option != 0 && Mirrored() ? -1 : 1;
  if (ResetRequested()) {
    for (auto *tracker : {&heading_mirror, &framing_mirror}) {
      tracker->target = target;
      tracker->position = target;
      tracker->velocity = 0;
      tracker->acceleration = 0;
    }
  } else {
    heading_mirror.Update(dt, target, MirrorParameters(100, 500));
    framing_mirror.Update(dt, target, MirrorParameters(15, 50));
  }
}
bool ManagerState::UpdateSlopeRelation(const ManagerSubject &s,
                                       std::string &error) {
  launch_landing_heading_delta = Bits(0x40490fdb);
  if (s.launch_normal[1] < Bits(0x3f7d70a4) &&
      s.landing_normal[1] < Bits(0x3f7d70a4)) {
    float launch, landing, delta;
    if (!NormalizeAngle(DirectionToAngles(s.launch_normal)[1], launch, error) ||
        !NormalizeAngle(DirectionToAngles(s.landing_normal)[1], landing,
                        error) ||
        !NormalizeAngle(landing - launch, delta, error))
      return false;
    launch_landing_heading_delta = std::abs(delta);
  }
  return true;
}
bool ManagerState::UpdateAir(const ManagerSubject &s, Rig &rig,
                             std::optional<std::pair<Vec4, Vec4>> &impulse,
                             std::string &error) {
  const float previous_delta = landing_height_delta;
  landing_height_delta = s.landing_position[1] - s.launch_position[1];
  apex_height = s.apex_position[1] - s.launch_position[1];
  apex_time = s.apex_time;
  launch_position = s.launch_position;
  apex_height_ratio = trajectory_camera_distance != 0
                          ? apex_height / trajectory_camera_distance
                          : 0;
  landing_normal = s.landing_normal;
  launch_incline = Acos(Clamp(s.launch_normal[1], -1, 1));
  flags &= std::uint8_t(~0x10);
  const bool ground = s.IsGroundCamera(rig.fields.height_mode);
  if (ground || s.rig.trajectory_valid == 0)
    flags &= std::uint8_t(~4);
  else {
    if ((flags & 4) != 0) {
      if (std::abs(landing_height_delta - previous_delta) > Bits(0x3a83126f))
        rig.fields.flags_517 |= 8;
    } else {
      if (selected_anchor >= s.anchors.size()) {
        error = "Camera anchor index outside original capacity";
        return false;
      }
      trajectory_camera_distance = Length(
          Sub(rig.positioner.position, s.anchors[selected_anchor].position));
      rig.fields.flags_517 &= std::uint8_t(~8);
    }
    flags |= 4;
    landing_incline = Acos(Clamp(landing_normal[1], -1, 1));
    signed_landing_incline = landing_incline;
    if (Dot3(s.rig.transform[2], landing_normal) > 0)
      signed_landing_incline = -landing_incline;
    if (launch_incline > Bits(0x3f9c61aa) && landing_incline > Bits(0x3f060a92))
      flags |= 0x10;
    if (!UpdateSlopeRelation(s, error))
      return false;
  }
  rig.fields.height_transition_weight =
      !ground && s.rig.trajectory_valid != 0
          ? Clamp(s.trajectory_time / s.trajectory_duration, 0, 1)
          : 0;
  impulse.reset();
  if (ground) {
    if ((flags & 0x40) == 0 && (rig.positioner.flags & 0x80) == 0) {
      if (Dot3(previous_velocity, ground_normal) < -0.0f)
        impulse = std::make_pair(ground_normal, previous_velocity);
      landing_height_delta = 0;
    }
  } else if (rig.fields.height_transition_time >=
                 rig.fields.height_transition_duration &&
             s.rig.trajectory_valid != 0 && landing_height_delta > -3 &&
             s.flag_684 == 0) {
    if ((flags & 2) != 0 || s.rig.air_flag_452 != 0)
      rig.fields.flags_516 |= 0x40;
    else if (rig.fields.previous_height != std::numeric_limits<float>::max() &&
             rig.fields.reference_height != std::numeric_limits<float>::max()) {
      rig.fields.height_transition_start = rig.fields.reference_height;
      rig.fields.height_transition_end =
          landing_height_delta + rig.fields.reference_height;
      rig.fields.height_transition_duration =
          s.trajectory_duration - s.trajectory_time;
      rig.fields.height_transition_time = 0;
    }
  }
  flags = (flags & std::uint8_t(~0x40)) | (std::uint8_t(ground) << 6);
  previous_velocity = rig.fields.velocity;
  return true;
}
bool ManagerState::UpdateIncline(const ManagerSubject &s, std::string &error) {
  ground_normal = s.ground_normal;
  const auto normal = s.rig.last_valid_ground_up;
  if (normal[1] > Bits(0x3f7fff58) && s.rig.grinding == 0) {
    velocity_incline = 0;
    absolute_velocity_incline = 0;
    frontside_angle = 0;
    ground_heading = 0;
    direction_incline = 0;
    flags &= std::uint8_t(~0x20);
    return true;
  }
  const auto direction = Length(anchor_velocity) > Bits(0x358637bd)
                             ? Normalize(anchor_velocity)
                             : s.rig.transform[2];
  velocity_incline = Bits(0x3fc90fdb) - AngleBetween(Up, direction);
  absolute_velocity_incline =
      velocity_incline < 0 ? -velocity_incline : velocity_incline;
  ground_heading = DirectionToAngles(normal)[1];
  const auto projected = Mul(normal, Dot3(Up, normal)),
             tangent = Normalize(Sub(Up, projected));
  const Vec4 cross{std::fma(-normal[2], tangent[1], normal[1] * tangent[2]),
                   std::fma(-normal[0], tangent[2], normal[2] * tangent[0]),
                   std::fma(-normal[1], tangent[0], normal[0] * tangent[1]), 0};
  frontside_angle = AtanRatio(Dot3(direction, cross), Dot3(direction, tangent));
  flags =
      (flags & std::uint8_t(~0x20)) | (std::uint8_t(frontside_angle > 0) << 5);
  if (Mirrored())
    frontside_angle *= -1;
  if (std::abs(anchor_velocity[0]) > Bits(0x34000000) ||
      std::abs(anchor_velocity[1]) > Bits(0x34000000) ||
      std::abs(anchor_velocity[2]) > Bits(0x34000000))
    return NormalizeAngle(Bits(0x3fc90fdb) - AngleBetween(s.direction_424, Up),
                          direction_incline, error);
  return true;
}
float ManagerState::BindShot(Shot shot, const ManagerSubject &s, Rig &rig,
                             RigOrientation &orientation,
                             const DropPredictor &drop, LookInput look,
                             float previous_roll, bool transitioning) {
  const bool reset = ResetRequested();
  auto &f = rig.fields;
  f.avoidance_mode = std::uint32_t((options & 0x20) != 0);
  f.flags_516 = (f.flags_516 & std::uint8_t(~0x62)) |
                (std::uint8_t(transitioning) << 5) |
                ((shot.follow_subject_in_air << 6) & 0x40) |
                ((shot.avoidance_override << 1) & 2);
  f.flags_517 = (f.flags_517 & 0x7f) | (s.stance_560 << 7);
  const auto basis = BasisFromQuaternion(shot.arm_orientation);
  const auto at = basis.columns[2];
  const auto angles = DirectionToAngles({at[0], at[1], at[2], 0});
  float elevation = -angles[0], heading = angles[1], distance = shot.distance;
  if (s.special_effect != 0) {
    elevation += Bits(0x3eb2b8c2);
    const float time = float(frames) * Bits(0x3dd67750),
                distance_wave = Sin(time * Bits(0x3d321643)),
                heading_wave = Sin(time * Bits(0x3c23d70a));
    heading = std::fma(heading_wave, Bits(0x40278d36), heading);
    distance = (distance_wave + distance) + 1;
  }
  float drop_elevation = 0;
  if ((options & 0x40) != 0) {
    const float speed = Length(anchor_velocity),
                minimum = (options & 0x10) != 0 ? 0.7f : 0.9f,
                maximum = (options & 0x10) != 0 ? 0.8f : 1.0f,
                scale = Clamp(-std::fma(speed - 4, Bits(0x3cccccd0), -maximum),
                              minimum, maximum);
    drop_elevation = drop.elevation * scale;
    distance = drop.distance_offset + distance;
  }
  float collision = 0;
  if (!reset) {
    const float maximum = distance - 2.5f >= 0 ? 2.5f : distance,
                fraction = Clamp((maximum - rig.positioner.available_distance) /
                                     maximum,
                                 0, 1),
                angle =
                    (s.rig.off_board != 0 ? 60.0f : 50.0f) * Bits(0x3c8efa35);
    float target = std::fma(angle, fraction, -drop_elevation);
    target = target >= 0 ? target : 0;
    if (s.IsGroundCamera(f.height_mode) && s.ground_normal[1] < -0.2f)
      target *= -1;
    const bool outward = (target > 0 && collision_elevation < target) ||
                         (target < 0 && collision_elevation > target);
    const float step = angle * (outward ? Bits(0x3d888889) : Bits(0x3c23d70a));
    collision_elevation =
        std::abs(target - collision_elevation) > step
            ? (target >= collision_elevation ? collision_elevation + step
                                             : collision_elevation - step)
            : target;
    collision = Clamp(collision_elevation, -Bits(0x3fb2b8c2), Bits(0x3fb2b8c2));
  }
  f.distance = distance;
  const float reference = WrapFloor(heading);
  f.heading_reference = reference;
  f.heading_target =
      reset ? reference
            : BlendAngle(f.avoidance_heading, reference, 1 - f.heading_weight);
  rig.SetElevation(elevation, !reset);
  f.elevation_offset = drop_elevation + look.elevation;
  f.additional_elevation = collision;
  f.flags_517 = (f.flags_517 & std::uint8_t(~0x20)) |
                (std::uint8_t(shot.compass_north != 5) << 5);
  blur = reset ? 0 : transitioning ? shot.transition_blur : shot.blur;
  const float mirror = shot.compass_north == 2 ? 1 : heading_mirror.position;
  orientation.framing_mirror =
      shot.compass_north == 2 ? 1 : framing_mirror.position;
  f.collision_mode = shot.collision_hint;
  const float h = 1 - shot.smoothing[0], e = 1 - shot.smoothing[1],
              pan = 1 - shot.smoothing[2], tilt = 1 - shot.smoothing[3];
  f.heading_smoothing = 1 - (-std::fma(h, h, -1.0f));
  f.elevation_smoothing = 1 - (-std::fma(e, e, -1.0f));
  orientation.pan_smoothing = -std::fma(pan, pan, -1.0f);
  orientation.tilt_smoothing = -std::fma(tilt, tilt, -1.0f);
  orientation.roll = previous_roll;
  return mirror;
}
BlendEnvironment::BlendEnvironment(const CameraMan &m, const ManagerSubject &s)
    : state(m.state), subject(s), rig(m.rig), rig_forward(m.subject_forward),
      angular_velocity{}, heading_multiplier(m.heading_multiplier),
      previous_distance(m.shots.previous.distance) {}
bool BlendEnvironment::CompassNorth(std::uint32_t entry, float &result,
                                    std::string &error) const {
  if (entry >= subject.compass.size()) {
    error = "Camera compass index outside original capacity";
    return false;
  }
  result = subject.compass[entry];
  return true;
}
float BlendEnvironment::AirProgress() const {
  if (subject.IsGroundCamera(rig.fields.height_mode))
    return 1;
  if (state.apex_height <= 0)
    return 0;
  const float remaining = subject.trajectory_duration - subject.trajectory_time;
  return Clamp(subject.trajectory_duration <= 0
                   ? 1
                   : (subject.trajectory_duration - remaining) /
                         subject.trajectory_duration,
               0, 1);
}
float BlendEnvironment::ApexProgress() const {
  if (subject.IsGroundCamera(rig.fields.height_mode))
    return (state.flags & 0x40) != 0 ? 0 : 1;
  if (state.apex_height <= 0 ||
      subject.ValidTrajectoryDuration() < state.apex_time)
    return 0;
  const float twice = state.apex_time * 2,
              remaining = subject.ValidTrajectoryDuration() - twice;
  return subject.trajectory_time > twice
             ? Clamp((subject.trajectory_time - twice) / remaining + 1, 1, 2)
             : subject.trajectory_time / twice;
}
float BlendEnvironment::RawBlendValue(std::uint32_t kind, float authored,
                                      float dt) {
  const auto &s = subject;
  const auto &m = state;
  const float degrees = Bits(0x42652ee1);
  switch (kind) {
  case 0:
    return authored;
  case 1:
    return std::abs(Dot3(rig.fields.velocity, s.rig.transform[2]));
  case 2:
    return Dot3(rig.fields.acceleration, rig_forward);
  case 3:
    return heading_multiplier * (-angular_velocity[1]);
  case 4:
    return m.apex_height;
  case 5:
    return AirProgress();
  case 6:
    return m.velocity_incline * degrees;
  case 7:
    return previous_distance;
  case 8:
    return ApexProgress();
  case 9:
    return m.absolute_velocity_incline * degrees;
  case 10:
    return m.landing_incline * degrees;
  case 11:
    return m.Mirrored() ? -s.steering[1] : s.steering[1];
  case 12:
    return s.SteeringForBlend(m.Mirrored());
  case 13:
    return dt == 0 ? 0 : s.SteeringForTurn(m.Mirrored());
  case 14:
    return dt == 0 ? 0 : std::numeric_limits<float>::max();
  case 15:
    return m.frontside_angle;
  case 16:
    return s.ValidTrajectoryDuration();
  case 17:
    return s.look[0];
  case 18:
    return s.look[1];
  case 19:
    return s.LookHeading();
  case 20:
    return m.direction_incline * degrees;
  case 21:
    return s.value_512;
  case 22:
    return -s.value_516;
  case 23:
    return m.effect_weight;
  default:
    return 0.5f;
  }
}
CameraMan::CameraMan() : subject_forward{0, 0, 1, 0}, heading_multiplier(1) {}
bool CameraMan::Prepare(const ManagerSubject &subject, ManagerSettings settings,
                        std::string &error) {
  state.UpdateTiming(subject, settings.steering_threshold);
  std::optional<std::pair<Vec4, Vec4>> impulse;
  if (!state.UpdateAir(subject, rig, impulse, error))
    return false;
  if (impulse)
    shake[0].LandingImpulse(impulse->first, impulse->second, settings.shake);
  return state.UpdateIncline(subject, error);
}
bool CameraMan::SetShot(std::string_view name, bool force,
                        const ManagerSubject &subject,
                        const ShotDatabase &database, bool &changed,
                        std::string &error) {
  BlendEnvironment env(*this, subject);
  return shots.SetShot(name, force, database, env,
                       {rig.fields.anchor, rig.positioner.position,
                        rig.positioner.config.clamp_height,
                        rig.positioner.config.floor_height},
                       changed, error);
}
bool CameraMan::BindAnchor(const ManagerSubject &subject, bool reset,
                           std::string &error) {
  const auto selected =
      reset ? shots.interpolated.anchor : shots.current.definition.shot.anchor;
  if (!reset && selected != state.selected_anchor)
    rig.fields.flags_517 |= 0x40;
  state.selected_anchor = selected;
  if (selected >= subject.anchors.size()) {
    error = "Camera anchor index outside original capacity";
    return false;
  }
  const auto anchor = subject.anchors[selected];
  state.anchor = anchor.position;
  state.anchor_velocity = reset ? Vec4{} : anchor.velocity;
  rig.fields.acceleration = Sub(state.anchor_velocity, rig.fields.velocity);
  rig.fields.velocity = state.anchor_velocity;
  rig.fields.anchor = state.anchor;
  subject_forward = subject.rig.transform[2];
  rig.fields.flags_516 |= 0x10;
  composer.reference = reset ? state.anchor : rig.anchor.position;
  return true;
}
bool CameraMan::FinishFrame(float dt, const ManagerSubject &s,
                            ShakeSettings settings,
                            std::array<const ShakeSamples *, 2> samples,
                            bool reset, std::string &error) {
  const auto old_basis = frame.basis;
  const auto old_position = frame.position;
  const auto basis = orientation.basis;
  const auto position = rig.positioner.position;
  if (!frame.Motion(dt, basis, position, error))
    return false;
  const bool enabled = s.rig.wiping_out == 0 ||
                       (rig.positioner.flags & 0x80) != 0 ||
                       s.rig.broken_bone_slowmo != 0;
  const auto velocity = rig.fields.velocity;
  const float speed = Length({velocity[0], 0, velocity[2], 0}) *
                      (s.flag_652 != 0 ? Bits(0x3f6147ae) : 1),
              distance = Length(Sub(rig.fields.anchor, position));
  Basis3 first, second;
  if (!shake[0].Update(dt, speed, distance, basis, enabled, *samples[0],
                       settings, first, error) ||
      !shake[1].Update(dt, s.shake_variant != 0 ? speed * 50 : speed, distance,
                       basis, enabled, *samples[1], settings, second, error))
    return false;
  const auto selected = std::size_t(s.shake_variant != 0);
  frame.basis = selected == 0 ? first : second;
  frame.position = position;
  frame.shake_translation = shake[selected].translation;
  rig.fields.offset = frame.shake_translation;
  frame.discontinuity = (rig.positioner.flags & 0x40) != 0 || reset;
  frame.previous_basis = frame.discontinuity ? frame.basis : old_basis;
  frame.previous_position = frame.discontinuity ? position : old_position;
  frame.field_of_view_degrees = state.field_of_view;
  frame.opacity = state.opacity;
  frame.blur = state.blur;
  return true;
}
bool CameraMan::Update(float dt, ManagerSubject &subject,
                       ManagerSettings settings,
                       std::array<const ShakeSamples *, 2> samples,
                       std::array<TrajectoryCollisionRequest *, 3> requests,
                       MovingObstacleProvider &moving,
                       PositionerCollisionProvider &positioning,
                       DropCollisionProvider &dropping, CameraFrame &result,
                       std::string &error) {
  if (shots.current.definition.name.empty()) {
    error = "The stock camera graph has not selected a shot";
    return false;
  }
  ++state.frames;
  if (state.frames > 30)
    state.flags |= 1;
  state.UpdateMirrors(dt, subject, rig, shots);
  const bool reset = state.ResetRequested();
  if ((state.options & 0x40) != 0) {
    if (reset)
      drop.Reset();
    const auto velocity = DropPredictor::PredictionVelocity(
        reset, subject.rig.transform, rig.fields.velocity, settings.drop);
    if (!drop.Update(subject.rig.transform[3], velocity,
                     shots.current.definition.shot.use_drop_predictor != 0 &&
                         !reset,
                     subject.rig.off_board != 0, subject.rig.context,
                     settings.drop, dropping, error))
      return false;
  }
  const bool look_enabled =
      (reset ? shots.FirstLeaf().use_free_camera_stick
             : shots.current.definition.shot.use_free_camera_stick) != 0;
  rig.fields.flags_517 = (rig.fields.flags_517 & std::uint8_t(~0x10)) |
                         (std::uint8_t(!look_enabled) << 4);
  look.Update(look_enabled ? subject.look : std::array<float, 2>{},
              settings.look);
  if (reset) {
    shots.MakeInstant();
    rig.fields.velocity = {};
    rig.fields.acceleration = {};
    state.slowmo_frames = 0;
    shake = {};
    heading_multiplier = state.heading_mirror.position;
    orientation.framing_mirror = state.framing_mirror.position;
  } else {
    state.slowmo_frames =
        subject.rig.broken_bone_slowmo != 0 ? state.slowmo_frames + 1 : 0;
    if (state.slowmo_frames == 1) {
      const float impulse = settings.shake.impulse_magnitude * 20;
      if (impulse > shake[0].impulse)
        shake[0].impulse = impulse;
    }
  }
  BlendEnvironment env(*this, subject);
  float fraction;
  if (!shots.Update(dt, env, fraction, error) ||
      !BindAnchor(subject, reset, error))
    return false;
  heading_multiplier =
      state.BindShot(shots.interpolated, subject, rig, orientation, drop, look,
                     composer.roll, shots.IsTransitioning());
  if (reset) {
    if (!rig.Teleport(error))
      return false;
    frame.shake_translation = {};
  }
  if (!rig.Update(dt, settings.rig, subject.rig, requests, moving, positioning,
                  error))
    return false;
  state.opacity = shots.interpolated.subject_opacity;
  state.field_of_view =
      LensFieldOfView(shots.interpolated.lens_length, state.aspect_ratio);
  orientation.target = composer.Compose(
      dt, shots.FramingFraction(), orientation.framing_mirror, shots.previous,
      shots.current.definition.shot, rig.anchor.position,
      rig.positioner.position,
      {subject.rig.reference_positions, subject.board_offset_direction},
      settings.framing);
  if (!orientation.Update(dt, settings.orientation, rig.fields.reset_time,
                          rig.fields.flags_516, rig.fields.flags_517, error) ||
      !FinishFrame(dt, subject, settings.shake, samples, reset, error))
    return false;
  shots.instant_changes = reset || state.instant_frames > 0;
  if (reset) {
    state.options &= std::uint8_t(~0x80);
    state.flags |= 2;
  } else if (subject.IsGroundCamera(rig.fields.height_mode))
    state.flags &= std::uint8_t(~2);
  if (state.instant_frames > 0)
    --state.instant_frames;
  result = frame;
  return true;
}
} // namespace atelier::skate::camera
