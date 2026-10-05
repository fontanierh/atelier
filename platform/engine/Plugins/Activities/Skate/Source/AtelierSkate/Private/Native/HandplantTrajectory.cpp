// SPDX-License-Identifier: Apache-2.0
#include "Handplant.h"
#include "GravityScale.h"
#include "PlantMath.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace plant_math;
constexpr Vec4 Up{0, 1, 0, 0};
Vec4 Gravity() { return {0, (Float(0xc11ccccd)*GravityScale()), 0, 0}; }
Vec4 ApexPosition(Vec4 coping, Vec4 side, float radius, float angle) {
  const float sin = Sin(angle), cos = Cos(angle);
  return Madd(side, radius * sin, Madd(Up, radius * cos, coping));
}
AirTrajectory ArcBetween(Vec4 start, Vec4 end, float time) {
  return {start,
          Scale(Sub(Sub(end, start), Scale(Gravity(), 0.5f * time * time)),
                Reciprocal(time)),
          Gravity(), time};
}
AirTrajectory ToApex(Vec4 start, Vec4 end) {
  const float t = std::sqrt((-2.0f * Gravity()[1]) * (end[1] - start[1])) *
                  Reciprocal(-Gravity()[1]);
  return ArcBetween(start, end, t);
}
AirTrajectory FromApex(Vec4 start, Vec4 end) {
  const float t = std::sqrt((-2.0f * Gravity()[1]) * (start[1] - end[1])) *
                  Reciprocal(-Gravity()[1]);
  return ArcBetween(start, end, t);
}
Vec4 Bezier(std::array<Vec4, 4> p, float t) {
  const float s = 1.0f - t;
  return Madd(p[3], t * t * t,
              Madd(p[2], 3.0f * t * t * s,
                   Madd(p[0], s * s * s, Scale(p[1], 3.0f * t * s * s))));
}
} // namespace
Vec4 PlantTrajectoryPosition(const AirTrajectory &t, float time) {
  const float square = time * time;
  Vec4 p;
  for (unsigned i = 0; i < 4; ++i)
    p[i] = std::fma(t.acceleration[i] * 0.5f, square,
                    std::fma(t.velocity[i], time, t.position[i]));
  return p;
}
Vec4 PlantTrajectoryVelocity(const AirTrajectory &t, float time) {
  Vec4 p;
  for (unsigned i = 0; i < 4; ++i)
    p[i] = std::fma(t.acceleration[i], time, t.velocity[i]);
  return p;
}
void Handplant::Launch(HandplantCandidate c, Vec4 com, Vec4 velocity,
                       Vec4 normal, Vec4 body_heading, Vec4 heading) {
  using namespace plant_math;
  auto side = Normalize(Cross(Sub(c.edge.end, c.edge.start), Up));
  if (Dot(side, normal) > 0.0f)
    side = Scale(side, -1);
  direction = Scale(side, -1);
  const auto apex_position =
      ApexPosition(c.point, side, settings.apex_radius, settings.apex_angle);
  initial = ToApex(com, apex_position);
  apex = HandplantApexTime(initial);
  warped = 0;
  outgoing = {initial, initial};
  travel_sign = Dot(heading, velocity) > 0.0f ? 1.0f : -1.0f;
  rotations[0] = HandplantRotationFrame(heading, normal);
  rotations[0][3] = com;
  auto along = Normalize(Sub(c.edge.start, c.edge.end));
  const float sign =
      Dot({along[0], 0, along[2], 0}, Sub(apex_position, com)) > 0.0f ? 1.0f
                                                                      : -1.0f;
  along = Scale(along, sign * travel_sign);
  rotations[1] =
      HandplantRotationFrame(along, Normalize(Sub(c.point, apex_position)));
  rotations[1][3] = apex_position;
  rotations[2] = HandplantRotationFrame(Scale(Up, -travel_sign), normal);
  rotations[3] = rotations[2];
  EstimateApex();
  const bool changed = Length(Sub(previous_candidate_point, c.point)) > 0.15f,
             front = Dot(Sub(c.point, com), body_heading) < 0.0f;
  flags = (flags & 0x0fffffffu) | 0x80000000u | (changed ? 0x40000000u : 0) |
          (front ? 0x20000000u : 0) |
          (phase < settings.committed_time ? 0x10000000u : 0);
  anchor = c.point;
  candidate = c;
}
bool Handplant::SelectOutgoing(const WorldGeometry &world,
                               HandplantTrajectoryQueries &queries,
                               std::string &error) {
  using namespace plant_math;
  if (!candidate) {
    error = "Handplant entry requires the selected coping";
    return false;
  }
  const auto apex_position = PlantTrajectoryPosition(initial, apex),
             incoming = PlantTrajectoryVelocity(initial, apex),
             across = Scale(direction, Dot(incoming, direction)),
             tangent = Sub(incoming, across), along = Normalize(tangent);
  const float speed = Length(Add(across, ClampLength(tangent, 2)));
  if (candidate->side != 0) {
    const auto expected =
        Scale(Cross(Up, direction), candidate->side == 1 ? 1.0f : -1.0f);
    continuation = Dot(expected, along) >= 0.0f;
  }
  auto position = Madd(direction, 0.1f, anchor);
  position[1] = apex_position[1];
  std::optional<std::pair<Vec4, Vec4>> selected;
  float best_up = 1.1f;
  AirTrajectory final_trajectory{Vec4{}, Vec4{}, Vec4{}, -1};
  for (const float angle : std::array<float, 6>{
           0, 0.24f, 0.48f, Float(0x3f3851eb), 0.96f, Float(0x3f999999)}) {
    const auto sc = SinCos(angle);
    const auto velocity =
        Scale(Madd(direction, sc.first, Scale(along, sc.second)), speed);
    const AirTrajectory trajectory{position, velocity, Gravity(), 3};
    final_trajectory = trajectory;
    PlantTrajectoryQueryResult hit;
    if (!queries.Query(world, trajectory, 0.2f, 1, 1, hit, error))
      return false;
    if (hit.contact_time < 0.0f)
      continue;
    if (anchor[1] - hit.contact_position[1] <= 0.5f)
      continue;
    const auto normal = hit.landing_normal,
               point = PlantTrajectoryPosition(trajectory, hit.contact_time),
               destination = Madd(normal, 0.56f, point);
    bool finite = true;
    for (float v : destination)
      if (!std::isfinite(v)) {
        finite = false;
        break;
      }
    if (!finite || !(destination[1] < apex_position[1]))
      continue;
    if (normal[1] < 0.71f) {
      selected = std::make_pair(point, normal);
      break;
    }
    if (normal[1] < best_up) {
      best_up = normal[1];
      selected = std::make_pair(point, normal);
    }
  }
  const auto landing = selected ? selected->first
                                : PlantTrajectoryPosition(final_trajectory, 3),
             normal = selected ? selected->second : Up,
             destination = Madd(normal, 0.56f, landing);
  auto out = FromApex(apex_position, destination);
  const float fall_time = out.scalar_48;
  out.position = PlantTrajectoryPosition(out, -apex);
  out.velocity = PlantTrajectoryVelocity(out, -apex);
  out.scalar_48 = -1;
  outgoing = {out, out};
  const float along_speed = Dot(direction, outgoing[1].velocity);
  if (along_speed < settings.minimum_out_speed)
    outgoing[1].velocity =
        Madd(direction, settings.minimum_out_speed - along_speed,
             outgoing[1].velocity);
  rotations[2][3] = PlantTrajectoryPosition(out, 2.0f * apex);
  const float time = apex + fall_time;
  rotations[3] = HandplantRotationFrame(
      Scale(Normalize(PlantTrajectoryVelocity(out, time)), travel_sign),
      normal);
  rotations[3][3] = PlantTrajectoryPosition(out, time);
  out_duration = VectorMax(time - phase, 0.5f);
  BuildCurve();
  error.clear();
  return true;
}
void Handplant::BuildCurve() {
  using namespace plant_math;
  const float start = apex - settings.curve_half_time,
              end = apex + settings.curve_half_time;
  curve[0] = PlantTrajectoryPosition(initial, start);
  curve[1] =
      Madd(Sub(PlantTrajectoryPosition(initial, start + Step()), curve[0]), 6,
           curve[0]);
  curve[3] = PlantTrajectoryPosition(outgoing[1], end);
  curve[2] =
      Madd(Sub(PlantTrajectoryPosition(outgoing[1], end - Step()), curve[3]), 6,
           curve[3]);
}
HandplantValues Handplant::Values(const std::array<Mat4, 24> &pose,
                                  Vec4 physical_com) {
  using namespace plant_math;
  const float relative = warped - apex,
              fraction =
                  (1.0f + relative * Reciprocal(settings.curve_half_time)) *
                  0.5f;
  Vec4 com;
  if (fraction < 0.0f)
    com = PlantTrajectoryPosition(initial, warped);
  else if (fraction > 1.0f) {
    const float blend = Clamp01((relative - settings.curve_half_time) *
                                Reciprocal(out_duration));
    com =
        Madd(PlantTrajectoryPosition(outgoing[0], warped), blend,
             Scale(PlantTrajectoryPosition(outgoing[1], warped), 1.0f - blend));
  } else
    com = Bezier(curve, fraction);
  const float foot_y = VectorMax(pose[15][3][1], pose[19][3][1]),
              divisor = (flags & 0x20000000u) ? 5.0f : 3.2f,
              offset = (flags & 0x20000000u) ? 0.0f : -0.05f;
  com[1] += VectorMax((foot_y - physical_com[1]) / divisor + offset, 0.0f);
  const float blend =
      VectorMax(1.0f - elapsed * Reciprocal(settings.entry_blend), 0.0f);
  const auto blended = Madd(
      com, 1.0f - blend, Scale(PlantTrajectoryPosition(entry, elapsed), blend));
  if (blend > 0.0f && fraction < 0.0f) {
    const auto velocity = PlantTrajectoryVelocity(initial, warped);
    const float correction = Dot(Sub(blended, com), Normalize(velocity)) *
                             Reciprocal(Length(velocity));
    warped += std::clamp(correction, Float(0xbc088889), Float(0x3c088889));
  }
  Mat4 frame;
  if (warped < apex) {
    const float f = VectorMax(
        1.0f - (apex - warped) *
                   Reciprocal(VectorMin(apex, settings.rotation_time)),
        0.0f);
    frame = BlendHandplantRotation(rotations[0], rotations[1],
                                   settings.into_rotation.Evaluate(f));
  } else {
    const float f = warped - apex,
                out = settings.out_heading.Evaluate(
                    Clamp01(f * Reciprocal(out_duration))),
                into = settings.out_rotation.Evaluate(
                    Clamp01(f * Reciprocal(settings.rotation_time)));
    frame = BlendHandplantRotation(
        rotations[1], BlendHandplantRotation(rotations[2], rotations[3], out),
        into);
  }
  return {blended, frame[1], frame[2]};
}
} // namespace atelier::skate
