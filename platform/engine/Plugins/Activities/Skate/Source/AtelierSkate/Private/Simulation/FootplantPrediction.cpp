#include "FootplantPrediction.h"
#include "GravityScale.h"
#include "AirReckoning.h"
#include "FootplantRuntime.h"
#include "PlantMath.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
namespace P = plant_math;
Vec4 Lanes(Vec3 v) { return {v.x, v.y, v.z, 0}; }
Vec4 Decode(RawVector words) {
  Vec4 v;
  for (std::size_t i = 0; i < 4; ++i)
    v[i] = P::Float(words[i]);
  return v;
}
// filter_edges uses wipeout_state::math, whose unguarded normalization and
// negative-first cross FMA differ from the Footplant math leaves.
Vec4 EdgeNormalize(Vec4 a) {
  return P::Scale(a, InverseLengthSquared(Dot3(a, a), 2));
}
Vec4 EdgeCross(Vec4 a, Vec4 b) {
  return {
      std::fma(-a[2], b[1], a[1] * b[2]), std::fma(-a[0], b[2], a[2] * b[0]),
      std::fma(-a[1], b[0], a[0] * b[1]), std::fma(-a[3], b[3], a[3] * b[3])};
}
Vec4 EdgeNormalizeOr(Vec4 a, Vec4 fallback) {
  const float square = Dot3(a, a);
  const float length =
      square == 0 ? 0 : square * InverseLengthSquared(square, 2);
  return length > P::Float(0x358637bd) ? EdgeNormalize(a) : fallback;
}
} // namespace
std::vector<FootplantEdge>
FootplantFilterEdges(const std::vector<FootplantEdge> &edges, Vec4 reference) {
  using namespace plant_math;
  std::vector<Vec4> directions;
  directions.reserve(edges.size());
  for (const auto &edge : edges)
    directions.push_back(
        EdgeNormalize(Sub(Lanes(edge.end), Lanes(edge.start))));
  std::vector<FootplantEdge> accepted;
  for (std::size_t i = 0; i < edges.size(); ++i) {
    const auto &edge = edges[i];
    const auto start = Lanes(edge.start);
    const auto midpoint = Scale(Add(start, Lanes(edge.end)), 0.5f);
    bool keep = true;
    for (std::size_t j = 0; j < edges.size(); ++j) {
      if (i == j)
        continue;
      const auto parallel = EdgeCross(directions[i], directions[j]);
      if (!(Dot3(parallel, parallel) < 0.0001f))
        continue;
      const auto delta = Sub(Lanes(edges[j].start), start);
      const auto off =
          Sub(delta, Scale(directions[j], Dot3(directions[j], delta)));
      const float distance = Dot3(off, off);
      if (!(distance > 0.0001f && distance < 0.010000001f))
        continue;
      const auto from_mid = Sub(Lanes(edges[j].start), midpoint);
      if (!(Dot3(from_mid, Sub(Lanes(edges[j].end), midpoint)) < 0))
        continue;
      const auto other_point = Add(
          midpoint,
          Sub(from_mid, Scale(directions[j], Dot3(directions[j], from_mid))));
      const auto a = Sub(midpoint, reference), b = Sub(other_point, reference);
      const auto normal = EdgeNormalizeOr(
          EdgeCross(directions[i], EdgeCross(Vec4{0, 1, 0, 0}, directions[i])),
          {});
      const float height = Dot3(delta, normal);
      if ((height > -0.02f && Dot3(a, a) > Dot3(b, b)) || height > 0.02f) {
        keep = false;
        break;
      }
    }
    if (keep) {
      accepted.push_back(edge);
      if (accepted.size() == 40)
        break;
    }
  }
  return accepted;
}
void FootplantRuntime::UpdateCandidate(const KnownAirFootplantInput &input,
                                       FootplantPredictionFrame frame) {
  using namespace plant_math;
  candidate = false;
  const Vec4 offset{0, settings.deck_bounds_y_offset, 0, 0};
  const auto upper = Add(settings.deck_bounds, offset);
  const auto lower = Sub(offset, settings.deck_bounds);
  const auto &physical = frame.physical.skeleton.record.pose;
  const std::array<Vec4, 2> toes{physical[15][3], physical[19][3]};
  const std::array<Vec4, 2> board{
      Point(frame.toolkit.inverse_effective, toes[0]),
      Point(frame.toolkit.inverse_effective, toes[1])};
  const auto outside = [&](Vec4 p) {
    for (std::size_t i = 0; i < 3; ++i)
      if (lower[i] > p[i] || p[i] > upper[i])
        return true;
    return false;
  };
  physical_com = Madd(input.trajectory.velocity, Step(),
                      frame.physical.board_frames.centre_of_mass);
  animation_com = Madd(input.trajectory.velocity, Step(),
                       Point(frame.physical.roots.animation_to_world,
                             frame.physical.animation_record.centre_of_mass));
  std::size_t side;
  if (outside(board[0]))
    side = 0;
  else if (outside(board[1]))
    side = 1;
  else
    return;
  const std::size_t toe = side == 0 ? 15 : 19;
  selected_toe = toe;
  candidate = true;
  selected_world = Point(frame.physical.roots.animation_to_world,
                         frame.physical.animation_record.pose[toe][3]);
  selected_record = toes[side];
  leg_direction = Normalize(Sub(selected_record, physical_com));
}
void FootplantRuntime::UpdateLaunch(const KnownAirFootplantInput &input) {
  using namespace plant_math;
  if (!hit)
    contact_time = input.remaining_collision_time;
  const auto future = Madd(input.trajectory.acceleration, contact_time,
                           input.trajectory.velocity);
  const auto raw = Sub(Normalize(future), input.landing_normal);
  const auto from = Scale(current_up, -1);
  const float angle = Float(0x420c0000) * Float(0x3c8efa35);
  const auto direction =
      Normalize(ClampAirReckoningVectorWithinMaxAngle(raw, from, angle));
  // Original second pure limiter is evaluated but its result is discarded.
  (void)ClampAirReckoningVectorWithinMaxAngle(
      Sub(adjusted_contact, physical_com), from, angle);
  launch_direction = Normalize(direction);
  launch_valid = true;
  request = {
      Madd(launch_direction, settings.leg_length_on_landing, physical_com),
      input.trajectory.velocity,
      {0, (Float(0xc11ccccd)*GravityScale()), 0, 0},
      -1};
}
bool FootplantRuntime::ConsumeAndSubmit(const KnownAirFootplantInput &input,
                                        FootplantPredictionFrame frame,
                                        FootIk &ik,
                                        SkeletonCollisionMode &collision,
                                        std::string &error) {
  using namespace plant_math;
  hit = false;
  if (enabled && result.contact_time >= 0) {
    contact_time = Clamp01(result.contact_time);
    contact = result.contact_position;
    surface = result.surface;
    hit = true;
    NearbyEdge(frame);
    adjusted_contact =
        Madd(input.landing_normal, settings.foot_volume_y_offset, contact);
    if (!contact_active) {
      if (candidate && contact_time > Float(0x3de147ae) &&
          contact_time < 0.3f) {
        contact_active = true;
        active_elapsed = 0;
      } else
        ClearContact();
    } else if (active_elapsed + contact_time < 0) {
      contact_active = false;
      ClearContact();
      active_elapsed = 0;
    }
    if (contact_active) {
      requested |= (frame.processed.flags_2480 & (1u << 23)) != 0;
      active_elapsed += Step();
      UpdatePose(input, frame.physical.roots, ik, collision);
    }
  }
  current_up = Decode(frame.processed.vectors_544_560_592_608[0]);
  const auto g =
      frame.physical.settings.board.step.simulation.gravity_acceleration;
  const AirTrajectory submitted{
      request.position, request.velocity, {g.x, g.y, g.z, 0}, 1};
  AirTrajectoryQueryResult next;
  if (!AirTrajectoryRuntime::Query(
          frame.physical.world,
          AirTrajectoryQueryRequest{submitted, Float(0x3d23d70a), 1, 1}, next,
          error))
    return false;
  result = next;
  completed_trajectory = submitted;
  enabled = true;
  error.clear();
  return true;
}
void FootplantRuntime::NearbyEdge(FootplantPredictionFrame frame) {
  using namespace plant_math;
  std::vector<FootplantEdge> edges;
  for (const auto &e : frame.edges) {
    bool inside = true;
    for (std::size_t i = 0; i < 3; ++i)
      inside &= VectorMin(e.start[i], e.end[i]) <= contact[i] + 2 &&
                VectorMax(e.start[i], e.end[i]) >= contact[i] - 2;
    if (inside)
      edges.push_back({{e.start[0], e.start[1], e.start[2]},
                       {e.end[0], e.end[1], e.end[2]}});
  }
  const float original_height = contact[1];
  float best = 0.25f;
  for (const auto &edge : FootplantFilterEdges(edges, frame.toolkit.deck[3])) {
    const auto start = Lanes(edge.start);
    const auto delta = Sub(Lanes(edge.end), start);
    const auto raw = Cross(Cross(delta, Vec4{0, 1, 0, 0}), delta);
    const auto normal =
        Length(raw) > Float(0x358637bd) ? Normalize(raw) : Vec4{0, 1, 0, 0};
    const auto time =
        AirTrajectoryDescendingPlaneTime(completed_trajectory, start, normal);
    if (!time)
      continue;
    const auto arc = AirTrajectoryPositionAt(completed_trajectory, *time);
    const float edge_length = Length(delta);
    const auto direction = edge_length > Float(0x37800000)
                               ? Scale(delta, Reciprocal(edge_length))
                               : delta;
    const auto point = Madd(
        direction,
        VectorMax(VectorMin(Dot(direction, Sub(arc, start)), edge_length), 0),
        start);
    const float distance = Length(Sub(arc, point));
    if (distance < best && point[1] - original_height > Float(0xbcf5c28f)) {
      contact_time = *time;
      current_up = normal;
      contact = point;
      surface = 0;
      hit = true;
      best = distance;
    }
  }
}
void FootplantRuntime::UpdatePose(const KnownAirFootplantInput &input,
                                  const SkeletonRootFrames &roots, FootIk &ik,
                                  SkeletonCollisionMode &collision) {
  using namespace plant_math;
  const float angle = Acos(Dot(launch_direction, leg_direction));
  const float turns = angle * Float(0x3e22f983),
              fraction = turns - std::floor(turns);
  const float wrapped =
      (fraction - (fraction > 0.5f ? 1.0f : 0.0f)) * Float(0x40c90fdb);
  if (requested && candidate && contact_time < 0.3f) {
    const float contact_length = Length(Sub(adjusted_contact, animation_com));
    const float leg_length = Length(Sub(selected_world, animation_com));
    const float distance =
        leg_length < contact_length ? leg_length : contact_length;
    const auto com = Point(roots.world_to_animation, animation_com);
    const auto velocity = Rotate(roots.world_to_animation,
                                 Scale(input.trajectory.velocity, -Step()));
    const auto direction = Rotate(roots.world_to_animation, launch_direction);
    auto target = Madd(direction, distance, Add(com, velocity));
    if (lock_valid)
      target =
          Add(locked_target, ClampLength(Sub(target, locked_target), 0.15f));
    locked_target = target;
    lock_valid = true;
    const std::size_t side = selected_toe == 15 ? 0 : 1;
    ik.state.external_targets[side].animation_position = target;
    ik.state.limbs[side].local_target_set = true;
    ik.state.limbs[side].target_blend = target_blend;
    target_blend = Clamp01(target_blend + 0.12f);
    if (contact_time < 0.2f)
      for (const auto part : side == 0
                                 ? std::array<std::size_t, 3>{15, 16, 17}
                                 : std::array<std::size_t, 3>{19, 20, 21}) {
        collision.pending_reenable = true;
        collision.disable_count[part] = 2;
        collision.parts[part].enabled = false;
      }
  }
  if (requested)
    perform = hit && !(contact_time > 0.017f) &&
              settings.max_leg_angle_error * Float(0x3c8efa35) > wrapped;
  else {
    target_blend = 0;
    perform = false;
  }
}
} // namespace atelier::skate
