#include "CameraRig.h"
#include "RigidBody.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
float Maximum() { return std::numeric_limits<float>::max(); }
RigFields InitialFields(std::uint32_t mode) {
  RigFields f;
  f.heading_target = Bits(0x40490fdb);
  f.heading_reference = f.heading_target;
  f.collision_hold_time = 5;
  f.reset_time = 2;
  f.reference_height = 1000;
  f.previous_height = Maximum();
  f.distance = 1;
  f.heading_smoothing = 1;
  f.elevation_smoothing = 1;
  f.avoidance_mode = mode;
  f.flags_516 = 0x88;
  f.flags_517 = 0x30;
  return f;
}
void BindAngle(ScalarTrackerParameters &p, AngleTrackingSettings s,
               float smoothing) {
  const float radians = Bits(0x3c8efa35);
  p.speed_clamp = s.speed_clamp_degrees * radians;
  p.acceleration_clamp_min = s.acceleration_min_degrees * radians;
  p.acceleration_clamp_max = s.acceleration_max_degrees * radians;
  p.delta_umbra = s.delta_umbra_degrees * radians;
  p.delta_penumbra = s.delta_penumbra_degrees * radians;
  p.smoothing_min = smoothing;
  p.smoothing_max = smoothing;
}
float CapSmoothing(float value) {
  return value >= 1                      ? 1
         : Bits(0x3f666666) - value >= 0 ? value
                                         : Bits(0x3f666666);
}
void BindOrientation(ScalarTrackerParameters &p, OrientationTrackerSettings s,
                     float smoothing, bool clamp) {
  const float radians = Bits(0x3c8efa35);
  p.speed_clamp = Maximum();
  p.acceleration_clamp_min =
      clamp ? s.acceleration_min_degrees * radians : Maximum();
  p.acceleration_clamp_max =
      clamp ? s.acceleration_max_degrees * radians : Maximum();
  p.smoothing_min =
      smoothing < 1
          ? (s.smoothing_min - smoothing >= 0 ? smoothing : s.smoothing_min)
          : 1;
  p.smoothing_max = smoothing < 1 ? smoothing : 1;
  p.delta_umbra = s.delta_umbra_degrees * radians;
  p.delta_penumbra = s.delta_penumbra_degrees * radians;
}
bool ResetTracker(AngleTracker &tracker, float target, std::string &error) {
  if (!NormalizeAngle(target, tracker.state.target, error) ||
      !NormalizeAngle(target, tracker.state.position, error))
    return false;
  tracker.state.velocity = 0;
  tracker.state.acceleration = 0;
  return true;
}
} // namespace
float AngularRigTracking::CurrentHeading() const {
  return WrapVmx(heading.state.position + heading_offset);
}
bool AngularRigTracking::ResetHeading(bool clear, std::string &error) {
  if (!NormalizeAngle(heading_target, heading.state.target, error) ||
      !NormalizeAngle(heading_target, heading.state.position, error))
    return false;
  if (clear) {
    heading.state.velocity = 0;
    heading.state.acceleration = 0;
  }
  return true;
}
bool AngularRigTracking::ResetElevation(bool clear, std::string &error) {
  if (!NormalizeAngle(elevation_target, elevation.state.target, error) ||
      !NormalizeAngle(elevation_target, elevation.state.position, error))
    return false;
  if (clear) {
    elevation.state.velocity = 0;
    elevation.state.acceleration = 0;
  }
  return true;
}
bool AngularRigTracking::UpdateHeading(float dt, AngleTrackingSettings settings,
                                       std::string &error) {
  if ((flags_517 & 0x20) == 0 && heading_acceleration_state == 0)
    return true;
  const float distance = std::abs(WrapVmx(heading_target - CurrentHeading())),
              response = 1 - heading_smoothing,
              capped = Bits(0x3f4ccccd) - response >= 0 ? response
                                                        : Bits(0x3f4ccccd),
              smoothing = distance < Bits(0x3f490fdb)
                              ? std::fma(capped - response,
                                         distance * Bits(0x3fa2f984), response)
                              : capped;
  if (reset_time > 0 && !ResetHeading(true, error))
    return false;
  BindAngle(heading_parameters, settings, smoothing);
  if (heading_acceleration_state > 0) {
    heading_parameters.acceleration_clamp_min *= 2;
    heading_parameters.acceleration_clamp_max *= 2;
  }
  heading_parameters.overshoot_zeroes_velocity = false;
  float target;
  if (!NormalizeAngle(heading_target, target, error))
    return false;
  return heading.Update(dt, target, heading_parameters, error);
}
bool AngularRigTracking::UpdateElevation(float dt,
                                         AngleTrackingSettings settings,
                                         std::string &error) {
  if (reset_time > 0 && !ResetElevation(true, error))
    return false;
  BindAngle(elevation_parameters, settings, 1 - elevation_smoothing);
  float target;
  if (!NormalizeAngle(elevation_target, target, error))
    return false;
  return elevation.Update(dt, target, elevation_parameters, error);
}
float AnchorRigTracking::LatchSmoothing(float dt, AnchorTrackingSettings s,
                                        const Subject &subject) {
  latch_time = FloorZero(latch_time - dt);
  if (subject.physically_pushing == 0)
    flags_516 &= std::uint8_t(~4);
  else if (subject.at_pushable_speed != 0)
    flags_516 |= 4;
  if ((flags_516 & 4) != 0)
    latch_time = 0.5f;
  return Clamp(s.latch_curve.Evaluate(std::fma(-latch_time, 2.0f, 1.0f)), 0,
               1) *
         s.latch_scale;
}
float AnchorRigTracking::InputSmoothing(float dt, AnchorTrackingSettings s,
                                        const Subject &subject) {
  input_time = FloorZero(input_time - dt);
  if (subject.pumping_acceleration > s.input_threshold)
    input_time = 0.5f;
  return Clamp(s.input_curve.Evaluate(std::fma(-input_time, 2.0f, 1.0f)), 0,
               1) *
         s.input_scale;
}
void AnchorRigTracking::Update(float dt, AnchorTrackingSettings s,
                               const Subject &subject) {
  const float latch = LatchSmoothing(dt, s, subject),
              input = InputSmoothing(dt, s, subject),
              maximum = latch - input >= 0 ? latch : input,
              smoothing =
                  subject.wiping_out != 0 || (flags_517 & 0x40) != 0
                      ? 0
                      : maximum * Clamp((Length(velocity) - 8) * -0.25f, 0, 1);
  parameters.speed_clamp = s.speed_clamp;
  parameters.acceleration_clamp_min = s.acceleration_clamp;
  parameters.acceleration_clamp_max = s.acceleration_clamp;
  parameters.smoothing_min = smoothing;
  parameters.smoothing_max = smoothing;
  auto target = anchor;
  target[1] = reference_height;
  tracker.Update(dt, target, parameters);
}
void ReferenceHeightTracking::Update(float dt, const Subject &subject) {
  const bool immediate = (flags_516 & 0x40) != 0;
  if (immediate)
    transition_duration = 0;
  const float old = height;
  float target = old;
  const bool blending = !immediate && transition_time < transition_duration;
  if (blending) {
    const float fraction = Clamp(transition_time / transition_duration, 0, 1);
    target =
        std::fma(fraction, transition_end - transition_start, transition_start);
    if ((flags_517 & 8) != 0) {
      const float weight = transition_weight * transition_weight;
      target = std::fma(1 - weight, target, anchor_height * weight);
    }
  } else if (mode == 0 || mode == 2) {
    previous_height = old;
    target = anchor_height;
  } else if (immediate || old > anchor_height)
    target = anchor_height;
  const float smoothing =
      old != Maximum() && !blending && mode != 2 && subject.air_flag_452 != 0
          ? Bits(0x3c23d70a)
          : 1;
  height = std::fma(target - height, smoothing, height);
  if (subject.off_board != 0) {
    const float delta = height - anchor_height;
    if (std::abs(delta) > Bits(0x38d1b717)) {
      height_offset = delta;
      if (delta > 0) {
        height = anchor_height;
        height_offset = 0;
      }
    } else if (std::abs(height_offset) > Bits(0x3ba3d70a)) {
      height_offset *= Bits(0x3f666666);
      height += height_offset;
    } else
      height_offset = 0;
  } else
    height_offset = height - anchor_height;
  transition_time += dt;
}
bool RigFraming::Update(float dt, AngularRigTracking &angular, Vec4 tracked,
                        const Positioner &positioner, Vec4 threshold,
                        std::string &error) {
  if ((angular.flags_517 & 0x40) == 0)
    return true;
  auto camera = positioner.position;
  if ((positioner.flags & 0x80) == 0)
    camera = Madd(positioner.velocity, dt, camera);
  auto track = tracked;
  track[1] = reference_height;
  const auto delta = Sub(Sub(camera, track), offset);
  const float square = Dot3(delta, delta),
              inverse = InverseLengthSquared(square),
              magnitude = square == 0 ? 0 : square * inverse;
  Vec4 direction;
  for (std::size_t i = 0; i < 4; ++i)
    direction[i] = magnitude > threshold[i] ? delta[i] * inverse : 0;
  const auto angles = DirectionToAngles(direction);
  angular.heading_target = -angles[1] - angular.heading_offset;
  angular.elevation_target =
      (angles[0] - elevation_offset) - additional_elevation;
  distance = magnitude;
  anchor[1] = reference_height;
  return angular.ResetHeading(false, error) &&
         angular.ResetElevation(false, error);
}
bool RigPositioning::Update(
    float dt, RigPositioningSettings settings, AngularRigTracking &angular,
    const RigFraming &framing, Vec4 tracked, Positioner &positioner,
    std::vector<Vec4> &breadcrumbs, const Subject &subject,
    PositionerCollisionProvider &collision, std::string &error) {
  auto anchor = tracked;
  anchor[1] = framing.reference_height;
  const float maximum = Bits(0x3fb2b8c2),
              reference_heading = angular.CurrentHeading(),
              reference_elevation = Clamp(framing.elevation_offset +
                                              angular.elevation.state.position,
                                          -maximum, maximum),
              heading = angular.CurrentHeading(),
              elevation = Clamp(
                  (framing.additional_elevation + framing.elevation_offset) +
                      angular.elevation.state.position,
                  -maximum, maximum),
              distance = std::isnan(framing.distance) ? 1 : framing.distance;
  const auto tracking =
      subject.broken_bone_slowmo != 0 ? settings.alternate : settings.normal;
  const PositionerConfig config{
      anchor,
      framing.offset,
      reference_heading,
      reference_elevation,
      heading,
      elevation,
      distance,
      subject.wiping_out != 0 ? settings.alternate_minimum_distance
                              : settings.minimum_distance,
      std::uint8_t(collision_mode != 2),
      std::uint8_t((angular.flags_517 & 0x40) != 0),
      subject.state_flag_81,
      subject.state_height_32,
      tracking.speed_clamp,
      tracking.acceleration_clamp,
      tracking.smoothing,
      {subject.reference_positions[3], subject.reference_positions[0],
       Madd(subject.skeleton_root[1], Bits(0x3e19999a),
            subject.reference_positions[7])}};
  if (!(angular.reset_time <= 0)) {
    positioner.distance_tracker.target = distance;
    positioner.distance_tracker.position = distance;
    positioner.distance_tracker.velocity = 0;
    positioner.distance_tracker.acceleration = 0;
  }
  angular.flags_517 &= std::uint8_t(~0x40);
  positioner.Update(dt, subject.context, config, collision);
  if ((positioner.flags & 4) == 0) {
    angular.heading_acceleration_state = 1;
    elevation_weight = 1;
    avoidance_heading = positioner.heading;
    avoidance_elevation = positioner.elevation;
    for (auto &value : breadcrumbs)
      value = positioner.position;
    heading_reference = positioner.heading;
    angular.heading_target = BlendAngle(avoidance_heading, heading_reference,
                                        1 - angular.heading_acceleration_state);
    angular.elevation_target = positioner.elevation;
    elevation_reference = positioner.elevation;
    flags_516 |= (positioner.flags >> 4) & 1;
    if ((flags_516 & 1) != 0)
      angular.elevation_target = BlendAngle(
          angular.elevation_target, avoidance_elevation, elevation_weight);
    angular.elevation_target = WrapVmx(angular.elevation_target);
    if (!angular.ResetHeading(true, error) ||
        !angular.ResetElevation(true, error))
      return false;
    flags_516 |= 8;
  }
  return true;
}
bool RigAvoidance::Update(float dt, AvoidanceSettings s,
                          const Positioner &positioner, Vec4 breadcrumb,
                          const Subject &subject,
                          std::array<TrajectoryCollisionRequest *, 3> requests,
                          MovingObstacleProvider &moving, std::string &error) {
  const auto speed = [&] { return Dot3(velocity, subject.transform[2]); };
  if (avoidance_mode == 1 && speed() < 0.5f)
    return true;
  if ((flags_516 & 2) != 0 || disable_time > 0 || avoidance_mode == 0) {
    heading_weight = 0;
    elevation_weight = 0;
    return true;
  }
  if (avoidance_mode == 1) {
    auto track = tracked_anchor;
    track[1] = reference_height;
    const auto delta = Sub(breadcrumb, track);
    const float magnitude = Length(delta);
    if (Bits(0x38d1b717) > magnitude)
      return true;
    const auto angles =
        DirectionToAngles(Mul(delta, RefinedReciprocal(magnitude)));
    avoidance_heading = -angles[1];
    avoidance_elevation = angles[0];
  } else if (avoidance_mode == 2) {
    const auto angles = DirectionToAngles(subject.last_valid_ground_up);
    avoidance_heading = -angles[1];
    avoidance_elevation = angles[0];
  } else if (avoidance_mode == 3) {
    avoidance_heading = heading_reference;
    avoidance_elevation = Bits(0x3fbde44e);
  } else if (avoidance_mode == 4) {
    avoidance_heading = WrapVmx(heading_target + Bits(0x40490fdb));
    const float low = Bits(0x3e32b8c2);
    avoidance_elevation = low - elevation_target >= 0 ? low : elevation_target;
  }
  if (std::isnan(avoidance_elevation))
    return true;
  const auto prediction =
      PositionFromAngles(anchor, {}, avoidance_elevation, avoidance_heading,
                         prediction_distance, positioner.config.clamp_height,
                         positioner.radius + positioner.config.floor_height);
  const bool transitioning =
      height_transition_time < height_transition_duration;
  auto vel = velocity;
  if (transitioning)
    vel[1] = (height_transition_end - height_transition_start) /
             height_transition_duration;
  const auto acceleration = std::uint8_t(height_mode == 1 && !transitioning);
  const auto set = [&](std::size_t index, PredictionPath path) {
    paths[index].evaluator.path = path;
    paths[index].prediction_flag = 0;
    paths[index].evaluator.acceleration_flag = acceleration;
  };
  set(0, {positioner.position, vel, s.radius_padding + positioner.radius,
          s.horizon});
  if (!paths[0].evaluator.Update(subject.context, *requests[0], moving, error))
    return false;
  const float camera_time = paths[0].evaluator.last_valid_time;
  const auto second_start =
      height_mode == 1
          ? prediction
          : Vec4{anchor[0], positioner.position[1], anchor[2], anchor[0]};
  set(1, {second_start, vel, Bits(0x3ca3d70a), s.horizon});
  if (!paths[1].evaluator.Update(subject.context, *requests[1], moving, error))
    return false;
  set(2, {subject.hips_position, vel, Bits(0x3ca3d70a), s.horizon});
  if (!paths[2].evaluator.Update(subject.context, *requests[2], moving, error))
    return false;
  const float second = paths[1].evaluator.last_valid_time,
              third = paths[2].evaluator.last_valid_time,
              other = second - third >= 0 ? second : third;
  const bool acceleration_result =
      paths[1].evaluator.result_acceleration_flag != 0 ||
      paths[2].evaluator.result_acceleration_flag != 0;
  if (third >= second)
    flags_516 |= 1;
  if (subject.off_board == 0 && (positioner.flags & 0x20) != 0) {
    heading_weight = dt * 0.5f + heading_weight;
    elevation_weight = dt * 0.5f + elevation_weight;
  } else if (subject.off_board == 0 && height_mode != 1 &&
             (acceleration_result ? other * 0.5f > camera_time
                                  : other > camera_time)) {
    const float target = Clamp(1 - camera_time / s.horizon, 0, 1),
                heading =
                    heading_weight - target >= 0 ? heading_weight : target,
                elevation =
                    elevation_weight - target >= 0 ? elevation_weight : target;
    heading_weight = std::fma(1 - s.heading_smoothing, heading - heading_weight,
                              heading_weight);
    elevation_weight = std::fma(1 - s.elevation_smoothing,
                                elevation - elevation_weight, elevation_weight);
  } else if ((speed() > Bits(0x3e19999a) && reset_time <= 0) ||
             subject.wiping_out != 0) {
    const float h = heading_weight - dt / s.ease_out_time,
                e = elevation_weight - dt / s.ease_out_time;
    heading_weight = h >= 0 ? h : 0;
    elevation_weight = e >= 0 ? e : 0;
    flags_516 &= std::uint8_t(~1);
  }
  heading_weight = Clamp(heading_weight, 0, 1);
  elevation_weight = Clamp(elevation_weight, 0, 1);
  return true;
}
Vec4 Breadcrumbs::Last() const {
  return positions[(positions.size() + index - 1) % positions.size()];
}
void Breadcrumbs::Update(Vec4 value) {
  const auto delta = Sub(value, positions[index]);
  if (Dot3(delta, delta) > distance_squared_threshold) {
    ++index;
    if (index >= positions.size())
      index = 0;
    positions[index] = value;
  }
}
Rig::Rig(std::uint32_t mode) : fields(InitialFields(mode)) {
  heading_parameters.overshoot_zeroes_velocity = true;
  elevation_parameters = heading_parameters;
  anchor_parameters = heading_parameters;
  positioner.tracker_parameters = heading_parameters;
  positioner.distance_tracker.target = 1;
  positioner.distance_tracker.position = 1;
  positioner.collision_clear_time = Maximum();
  positioner.radius = Bits(0x3e051eb8);
  for (auto &path : paths) {
    path.evaluator.collision_time = Maximum();
    path.evaluator.last_valid_time = Maximum();
  }
  breadcrumbs.positions.resize(2);
  breadcrumbs.distance_squared_threshold = 1;
  std::string error;
  ResetAngles(error);
}
AngularRigTracking Rig::Angular() const {
  const auto &f = fields;
  return {heading,
          heading_parameters,
          elevation,
          elevation_parameters,
          f.heading_target,
          f.elevation_target,
          f.heading_offset,
          f.reset_time,
          f.heading_smoothing,
          f.elevation_smoothing,
          f.heading_weight,
          f.flags_517};
}
void Rig::StoreAngular(const AngularRigTracking &a) {
  heading = a.heading;
  heading_parameters = a.heading_parameters;
  elevation = a.elevation;
  elevation_parameters = a.elevation_parameters;
  fields.heading_target = a.heading_target;
  fields.elevation_target = a.elevation_target;
  fields.heading_weight = a.heading_acceleration_state;
  fields.flags_517 = a.flags_517;
}
RigFraming Rig::Framing() const {
  const auto &f = fields;
  return {f.anchor,           f.offset,
          f.elevation_offset, f.additional_elevation,
          f.reference_height, f.distance};
}
bool Rig::ResetAngles(std::string &error) {
  auto a = Angular();
  const bool ok = a.ResetHeading(true, error) && a.ResetElevation(true, error);
  StoreAngular(a);
  return ok;
}
bool Rig::Reset(std::string &error) {
  const auto old = fields;
  fields = InitialFields(old.avoidance_mode);
  fields.height_transition_weight = old.height_transition_weight;
  fields.flags_517 = (old.flags_517 & 0x0f) | 0x30;
  breadcrumbs.distance_squared_threshold = 1;
  return ResetAngles(error);
}
bool Rig::Teleport(std::string &error) {
  auto &f = fields;
  f.avoidance_heading = 0;
  f.avoidance_elevation = 0;
  f.heading_weight = 0;
  f.elevation_weight = 0;
  f.flags_516 &= std::uint8_t(~1);
  if (!ResetAngles(error))
    return false;
  anchor.target = f.anchor;
  anchor.position = f.anchor;
  anchor.velocity = {};
  anchor.acceleration = {};
  f.reference_height = f.anchor[1];
  f.height_offset = 0;
  f.offset = {};
  positioner.distance_tracker.target = f.distance;
  positioner.distance_tracker.position = f.distance;
  positioner.distance_tracker.velocity = 0;
  positioner.distance_tracker.acceleration = 0;
  f.reset_time = Bits(0x3dcccccd);
  f.disable_avoidance_time = 2;
  f.collision_hold_time = 5;
  f.height_transition_duration = 0;
  f.flags_517 &= std::uint8_t(~0x40);
  f.previous_acceleration = 0;
  f.flags_516 = (f.flags_516 & 0xb3) | 8;
  f.input_time = 0;
  f.latch_time = 0;
  return true;
}
void Rig::SetElevation(float value, bool use_avoidance) {
  auto &f = fields;
  f.elevation_target = value;
  f.elevation_reference = value;
  if (use_avoidance) {
    f.flags_516 |= std::uint8_t((positioner.flags & 0x10) != 0);
    if ((f.flags_516 & 1) != 0) {
      const float delta = WrapVmx(f.avoidance_elevation - value);
      f.elevation_target =
          WrapVmx(WrapVmx(std::fma(delta, f.elevation_weight, value)));
    }
  }
}
bool Rig::Update(float dt, RigSettings settings, Subject &subject,
                 std::array<TrajectoryCollisionRequest *, 3> requests,
                 MovingObstacleProvider &moving,
                 PositionerCollisionProvider &collision, std::string &error) {
  fields.reset_time = FloorZero(fields.reset_time - dt);
  fields.disable_avoidance_time = FloorZero(fields.disable_avoidance_time - dt);
  ++fields.frame_counter;
  std::optional<std::uint32_t> mode;
  if (subject.in_ground_physics != 0)
    mode = 0;
  else if (subject.grinding != 0 || subject.subject_flag_328 != 0)
    mode = 2;
  else if (subject.trajectory_valid != 0)
    mode = 1;
  if (mode && *mode != fields.height_mode) {
    fields.previous_height_mode = fields.height_mode;
    fields.height_mode = *mode;
    fields.mode_time = 0;
  }
  auto f = fields;
  RigAvoidance avoidance{f.anchor,
                         f.velocity,
                         anchor.position,
                         f.heading_target,
                         f.heading_reference,
                         f.elevation_target,
                         f.avoidance_heading,
                         f.avoidance_elevation,
                         f.reset_time,
                         f.disable_avoidance_time,
                         f.height_transition_start,
                         f.height_transition_end,
                         f.height_transition_duration,
                         f.height_transition_time,
                         f.reference_height,
                         f.distance,
                         f.heading_weight,
                         f.elevation_weight,
                         f.avoidance_mode,
                         f.height_mode,
                         f.flags_516,
                         paths};
  if (!avoidance.Update(dt, settings.avoidance, positioner, breadcrumbs.Last(),
                        subject, requests, moving, error))
    return false;
  paths = avoidance.paths;
  fields.avoidance_heading = avoidance.avoidance_heading;
  fields.avoidance_elevation = avoidance.avoidance_elevation;
  fields.heading_weight = avoidance.heading_weight;
  fields.elevation_weight = avoidance.elevation_weight;
  fields.flags_516 = avoidance.flags_516;
  f = fields;
  ReferenceHeightTracking height{f.anchor[1],
                                 f.height_transition_start,
                                 f.height_transition_end,
                                 f.height_transition_weight,
                                 f.height_transition_duration,
                                 f.height_transition_time,
                                 f.reference_height,
                                 f.previous_height,
                                 f.height_offset,
                                 f.height_mode,
                                 f.flags_516,
                                 f.flags_517};
  height.Update(dt, subject);
  fields.height_transition_duration = height.transition_duration;
  fields.height_transition_time = height.transition_time;
  fields.reference_height = height.height;
  fields.previous_height = height.previous_height;
  fields.height_offset = height.height_offset;
  auto angular = Angular();
  if (!angular.UpdateHeading(dt, settings.heading, error) ||
      !angular.UpdateElevation(dt, settings.elevation, error))
    return false;
  StoreAngular(angular);
  f = fields;
  const float square = Dot3(f.velocity, f.velocity),
              inverse = InverseLengthSquared(square),
              magnitude = square == 0 ? 0 : square * inverse;
  const Vec4 fallback{0, 0, 1, 0};
  Vec4 direction;
  for (std::size_t i = 0; i < 4; ++i)
    direction[i] = magnitude > settings.normalization_threshold[i]
                       ? f.velocity[i] * inverse
                       : fallback[i];
  const float acceleration = Dot3(f.acceleration, direction);
  fields.smoothed_acceleration =
      (f.previous_acceleration + acceleration) * 0.5f;
  fields.previous_acceleration = acceleration;
  AnchorRigTracking tracking{anchor,       anchor_parameters,  f.anchor,
                             f.velocity,   f.reference_height, f.latch_time,
                             f.input_time, f.flags_516,        f.flags_517};
  tracking.Update(dt, settings.anchor, subject);
  anchor = tracking.tracker;
  anchor_parameters = tracking.parameters;
  fields.latch_time = tracking.latch_time;
  fields.input_time = tracking.input_time;
  fields.flags_516 = tracking.flags_516;
  fields.collision_hold_time = (positioner.flags & 0x80) != 0
                                   ? settings.collision_hold_duration
                                   : FloorZero(fields.collision_hold_time - dt);
  auto breadcrumb = anchor.position;
  breadcrumb[1] = fields.reference_height;
  breadcrumbs.Update(breadcrumb);
  auto framing = Framing();
  angular = Angular();
  if (!framing.Update(dt, angular, anchor.position, positioner,
                      settings.normalization_threshold, error))
    return false;
  fields.anchor = framing.anchor;
  fields.distance = framing.distance;
  f = fields;
  RigPositioning positioning{f.heading_reference, f.elevation_reference,
                             f.avoidance_heading, f.avoidance_elevation,
                             f.elevation_weight,  f.collision_mode,
                             f.flags_516};
  if (!positioning.Update(dt, settings.positioning, angular, framing,
                          anchor.position, positioner, breadcrumbs.positions,
                          subject, collision, error))
    return false;
  StoreAngular(angular);
  fields.heading_reference = positioning.heading_reference;
  fields.elevation_reference = positioning.elevation_reference;
  fields.avoidance_heading = positioning.avoidance_heading;
  fields.avoidance_elevation = positioning.avoidance_elevation;
  fields.elevation_weight = positioning.elevation_weight;
  fields.flags_516 = positioning.flags_516;
  return true;
}
RigOrientation::RigOrientation()
    : basis{{{{1, 0, 0}, {0, 1, 0}, {0, 0, 1}}}}, framing_mirror(1) {
  pitch_parameters.overshoot_zeroes_velocity = true;
  yaw_parameters = pitch_parameters;
}
bool RigOrientation::Update(float dt, OrientationSettings settings,
                            float reset_time, std::uint8_t &flags,
                            std::uint8_t flags_517, std::string &error) {
  const auto target_basis = BasisFromQuaternion(target);
  const auto at = target_basis.columns[2];
  const auto angles = DirectionToAngles({at[0], at[1], at[2], 0});
  const float pitch_target = -angles[0], yaw_target = angles[1];
  float normal_yaw, distance, zero;
  if (!NormalizeAngle(yaw_target, normal_yaw, error) ||
      !NormalizeAngle(normal_yaw - yaw.state.position, distance, error) ||
      !NormalizeAngle(0, zero, error))
    return false;
  if (distance < zero) {
    float first;
    if (!NormalizeAngle(-distance, first, error) ||
        !NormalizeAngle(first, distance, error))
      return false;
  }
  const float radians = Bits(0x3c8efa35),
              umbra = settings.pan_umbra_degrees * radians,
              penumbra = settings.pan_penumbra_degrees * radians,
              fraction = distance < umbra ? 1
                         : distance < penumbra
                             ? 1 - WrapVmx(distance - umbra) /
                                       WrapVmx(penumbra - umbra)
                             : 0,
              response = settings.pan_smoothing_curve.Evaluate(fraction);
  float minimum = 1 - settings.pan_minimum_smoothing;
  minimum = -(minimum * minimum - 1);
  const float pan = CapSmoothing(
      pan_smoothing >= minimum ? (pan_smoothing - minimum) * response + minimum
                               : pan_smoothing);
  tilt_smoothing = CapSmoothing(tilt_smoothing);
  if ((flags & 8) != 0 || reset_time > 0) {
    if (!ResetTracker(pitch, pitch_target, error) ||
        !ResetTracker(yaw, yaw_target, error))
      return false;
    flags &= std::uint8_t(~8);
  }
  if ((flags & 0x40) != 0) {
    BindOrientation(pitch_parameters, settings.tilt, tilt_smoothing,
                    (flags_517 & 0x10) != 0);
    float normal;
    if (!NormalizeAngle(pitch_target, normal, error) ||
        !pitch.Update(dt, normal, pitch_parameters, error))
      return false;
  }
  BindOrientation(yaw_parameters, settings.pan, pan, true);
  if (!NormalizeAngle(yaw_target, normal_yaw, error) ||
      !yaw.Update(dt, normal_yaw, yaw_parameters, error))
    return false;
  const auto value =
      BasisFromAngles(pitch.state.position, yaw.state.position, 0);
  basis = RotateAboutAxis(value, value.columns[2], roll * framing_mirror);
  return true;
}
} // namespace atelier::skate::camera
