#include "CameraSubject.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
namespace {
int Sign(float value) { return value >= 0 ? (value > 0 ? 1 : 0) : -1; }
Vec4 Cross(Vec4 a, Vec4 b) {
  return {std::fma(-a[2], b[1], a[1] * b[2]),
          std::fma(-a[0], b[2], a[2] * b[0]),
          std::fma(-a[1], b[0], a[0] * b[1]), 0};
}
Vec4 SafeNormalize(Vec4 value) {
  return Length(value) > Bits(0x358637bd) ? Normalize(value) : Vec4{};
}
Vec4 Rotate(Quat q, Vec4 v) {
  const auto first = Cross(q, v), intermediate = Madd(v, q[3], first),
             second = Cross(q, intermediate);
  return Madd(second, 2, v);
}
} // namespace
void Anchors::Update(AnchorInputs input) {
  const float dt = Bits(0x3c888889), inverse = RefinedReciprocal(dt);
  const auto board = Madd(input.board_offset_direction, Bits(0x3e99999a),
                          input.board_position);
  const auto air =
      Sub(input.center_of_mass, Mul(input.skeleton_root_up, Bits(0x3ea8f5c3)));
  if (input.reset || input.grinding)
    grind_position =
        Madd(input.board_offset_direction, 0.5f,
             input.reset ? input.board_position : input.grind_point);
  else
    grind_position = Madd(input.board_velocity, dt, grind_position);
  const std::array<Vec4, 7> positions{
      board,  input.center_of_mass,        air,   grind_position,
      Vec4{}, input.damped_center_of_mass, Vec4{}};
  for (std::size_t i = 0; i < 7; ++i) {
    auto &state = entries[i];
    const auto previous = state.position;
    state.position = positions[i];
    state.velocity =
        input.reset ? Vec4{} : Mul(Sub(state.position, previous), inverse);
    state.acceleration =
        (i == 0 || i == 2 || i == 3) ? input.board_acceleration : Vec4{};
  }
}
SubjectPosePublisher::SubjectPosePublisher()
    : previous_physical_transform{
          {{1, 0, 0, 0}, {0, 1, 0, 0}, {0, 0, 1, 0}, {0, 0, 0, 0}}} {}
PublishedSubjectPose SubjectPosePublisher::Publish(SubjectPoseInputs input) {
  const auto transform = input.wiping_out || input.state_flag_75
                             ? input.skeleton_root
                             : previous_physical_transform;
  previous_physical_transform = input.physical_transform;
  auto damped = input.reckoned_center_of_mass;
  const auto delta = Sub(damped, input.center_of_mass);
  const float distance = Length(delta), maximum = Bits(0x3e147ae1);
  if (distance > maximum)
    damped = Madd(Mul(delta, RefinedReciprocal(distance)), maximum,
                  input.center_of_mass);
  return {transform, damped};
}
std::array<Vec4, 10> ReferencePointInputs::Positions() const {
  return {head,
          hips,
          grinding != 0 ? grind_position : board,
          centre_of_mass,
          board,
          centre_of_mass,
          tracked_anchor,
          Mul(Add(left_foot, right_foot), 0.5f),
          damped_centre_of_mass,
          incline_normal};
}
bool ManagerSubject::IsGroundCamera(std::uint32_t mode) const {
  return mode == 2 || (flag_556 == 0 && rig.trajectory_valid == 0 &&
                       trajectory_duration <= Bits(0x3ecccccd));
}
float ManagerSubject::SteeringForTurn(bool mirrored) const {
  float selected =
      std::abs(steering[3]) > std::abs(steering[2]) ? steering[3] : steering[2];
  if (Sign(selected) != Sign(steering[0]) ||
      std::abs(selected) < std::abs(steering[0]))
    selected = steering[0];
  return std::uint8_t(mirrored) == stance_560 ? selected : -selected;
}
float ManagerSubject::SteeringForBlend(bool mirrored) const {
  const float secondary =
      std::abs(steering[3]) > std::abs(steering[2]) ? steering[3] : steering[2];
  const float selected = Sign(steering[1]) != Sign(secondary) ||
                                 std::abs(steering[1]) < std::abs(secondary)
                             ? secondary
                             : steering[1];
  return std::uint8_t(mirrored) == stance_560 ? selected : -selected;
}
float ManagerSubject::ValidTrajectoryDuration() const {
  return rig.trajectory_valid != 0 ? trajectory_duration : 0;
}
float ManagerSubject::LookHeading() const {
  return -DirectionToAngles(Normalize(Vec4{look[0], 0, look[1], 0}))[1];
}
Compass::Compass() : previous_reset(true) {}
CompassInputs CompassPoseInputs::Bind(const ManagerSubject &subject,
                                      Vec4 camera_position,
                                      std::uint32_t selected_compass) const {
  const bool trajectory = subject.rig.trajectory_valid != 0;
  return {
      subject.rig.last_valid_ground_up,
      trajectory ? subject.landing_normal : subject.ground_normal,
      subject.rig.transform,
      subject.rig.grinding != 0 ? subject.direction_424
      : trajectory              ? trajectory_direction
                                : Normalize(board_velocity),
      trajectory ? subject.launch_position : Vec4{},
      trajectory ? subject.landing_position : Vec4{},
      subject.direction_424,
      skeleton_direction,
      camera_position,
      look_target,
      subject.look,
      trajectory
          ? Clamp(subject.trajectory_time / subject.trajectory_duration, 0, 1)
          : 0,
      selected_compass,
      !trajectory,
      state_103,
      subject.rig.wiping_out != 0,
      subject.rig.grinding != 0,
      subject.rig.air_flag_452 != 0};
}
std::array<float, 9> Compass::Update(float dt, CompassInputs input,
                                     CompassSettings settings) {
  if (previous_reset) {
    previous_position = input.transform[3];
    stopped_time = 0;
    deadzone_size = 0;
  }
  UpdateMovement(dt, input, settings);
  float launch = Heading(input.ground_normal),
        landing = Heading(input.landing_normal);
  const float pi = Bits(0x40490fdb), tau = Bits(0x40c90fdb);
  if (std::abs(launch - landing) > pi) {
    if (launch >= landing)
      landing += tau;
    else
      launch += tau;
  }
  headings[1] =
      WrapVmx(std::fma(landing - launch, input.trajectory_fraction, launch));
  headings[0] = movement_heading;
  const auto difference =
      Horizontal(Sub(input.landing_position, input.launch_position));
  if (input.trajectory_fraction > 0 && Length(difference) > 1) {
    headings[4] = dt == 0 ? DirectionToAngles(input.skeleton_direction)[1]
                          : -DirectionToAngles(input.trajectory_direction)[1];
    headings[0] = WrapVmx(
        BlendAngle(headings[0], headings[4], input.trajectory_fraction));
  }
  headings[3] = Heading(input.transform[2]);
  UpdateOrbit(dt, input);
  UpdateFollow(input);
  const auto direction =
      Horizontal(Sub(input.transform[3], input.camera_position));
  const float forward = Heading(input.transform[2]),
              camera_heading = Heading(direction),
              delta = WrapFloor(camera_heading - forward),
              minimum = Bits(0x3f9c61aa);
  headings[8] = std::abs(delta) <= minimum
                    ? (delta >= 0 ? forward + minimum : forward - minimum)
                    : camera_heading;
  previous_reset = dt == 0;
  return headings;
}
void Compass::UpdateFollow(CompassInputs input) {
  const auto relative = Sub(input.transform[3], input.camera_position);
  if (input.selected_compass != 7)
    headings[7] = Heading(Horizontal(relative));
  else if (input.air_flag_452)
    headings[7] =
        Heading(Horizontal(Sub(input.look_target, input.transform[3])));
  else {
    const auto horizontal = Horizontal(velocity);
    const float speed = Length(horizontal);
    if (speed > 0.7f) {
      const float maximum =
                      Clamp((speed - 0.7f) * Bits(0x3ede9bd3), 0, 1) * 0.6f,
                  target = Heading(horizontal), previous = Heading(relative);
      headings[7] =
          Clamp(WrapFloor(target - previous) * 0.25f, -maximum, maximum) +
          previous;
    }
  }
}
void Compass::UpdateMovement(float dt, CompassInputs input, CompassSettings s) {
  if (!input.no_trajectory)
    return;
  const bool reset = dt == 0 || previous_reset;
  if (reset) {
    velocity = {};
    damped_velocity = {};
  } else {
    velocity =
        Mul(Sub(input.transform[3], previous_position), RefinedReciprocal(dt));
    const float speed = Length(Horizontal(velocity)),
                fraction = Clamp(
                    (speed - s.maximum_deadzone_speed) /
                        (s.minimum_deadzone_speed - s.maximum_deadzone_speed),
                    0, 1);
    deadzone_size =
        std::fma(std::fma(fraction, s.maximum_deadzone_size, -deadzone_size),
                 1 - s.deadzone_smoothing, deadzone_size);
    UpdateDeadzone(dt, {input.transform[3][0], input.transform[3][2]});
    damped_velocity = {deadzone_velocity[0], 0, deadzone_velocity[1],
                       deadzone_velocity[0]};
    previous_position = input.transform[3];
  }
  const float speed = Length(Horizontal(velocity));
  if (reset)
    movement_heading = -DirectionToAngles(input.skeleton_direction)[1];
  else if (input.grinding)
    movement_heading = -DirectionToAngles(input.grind_direction)[1];
  else {
    float target = movement_heading, weight = 1;
    stopped_time = input.wiping_out || speed > 0.5f ? 0 : stopped_time + dt;
    if (speed > 0.5f) {
      weight = Clamp(s.heading_response, 0, 1);
      target = -DirectionToAngles(Normalize(damped_velocity))[1];
    } else if (!input.state_103 && stopped_time >= s.time_before_lineup) {
      weight = s.lineup_speed;
      target = -DirectionToAngles(input.transform[2])[1];
    }
    movement_heading = BlendAngle(movement_heading, target, weight);
  }
}
void Compass::UpdateDeadzone(float dt, std::array<float, 2> target) {
  const auto old = deadzone_position;
  const std::array<float, 2> difference{target[0] - old[0], target[1] - old[1]};
  const float square =
      difference[0] * difference[0] + difference[1] * difference[1];
  float inverse = ReciprocalSquareRootEstimate(square);
  for (unsigned i = 0; i < 2; ++i)
    inverse = std::fma(inverse * 0.5f,
                       std::fma(-square, inverse * inverse, 1.0f), inverse);
  const float distance = square == 0 ? 0 : square * inverse;
  if (distance > deadzone_size)
    for (std::size_t i = 0; i < 2; ++i)
      deadzone_position[i] =
          std::fma(difference[i] * inverse, distance - deadzone_size, old[i]);
  for (std::size_t i = 0; i < 2; ++i)
    deadzone_velocity[i] =
        dt == 0 ? 0 : (deadzone_position[i] - old[i]) * (1 / dt);
}
void Compass::UpdateOrbit(float dt, CompassInputs input) {
  const auto position = input.transform[3];
  if (input.selected_compass != 6 || dt == 0) {
    orbit_position = input.camera_position;
    headings[6] = Heading(Horizontal(Sub(position, orbit_position)));
    orbit_delta = 0;
    return;
  }
  const float stick = -input.look[0];
  float step = 0, retained = 0.95f;
  if (std::abs(stick) > 0.3f) {
    retained = 0.9f;
    step = ((stick - (stick >= 0 ? 0.3f : -0.3f)) * dt) * Bits(0x408f9d9c);
  }
  orbit_delta = WrapVmx(std::fma(1 - retained, step, orbit_delta * retained));
  const float half = orbit_delta * 0.5f;
  orbit_position = Add(position, Rotate({0, Sin(half), 0, Cos(half)},
                                        Sub(orbit_position, position)));
  const auto from = Horizontal(Sub(orbit_position, position)),
             previous = Horizontal(Sub(input.camera_position, position)),
             from_direction = SafeNormalize(from),
             previous_direction = SafeNormalize(previous),
             normal = Cross(from_direction, previous_direction);
  if (Dot3(from_direction, previous_direction) < Bits(0x3f5db22d)) {
    const float magnitude = Length(normal);
    if (magnitude >= 0.001f) {
      const float inverse = RefinedReciprocal(magnitude),
                  h = -Bits(0x3f060a92) * 0.5f, sine = Sin(h);
      orbit_position =
          Add(position,
              Rotate({normal[0] * inverse * sine, normal[1] * inverse * sine,
                      normal[2] * inverse * sine, Cos(h)},
                     previous));
    } else
      orbit_position = input.camera_position;
  }
  const auto relative = Sub(position, orbit_position);
  const float distance = Length(relative);
  if (distance > 0.001f)
    orbit_position = Sub(position, Mul(relative, 2 / distance));
  headings[6] = Heading(Horizontal(Sub(position, orbit_position)));
}
} // namespace atelier::skate::camera
