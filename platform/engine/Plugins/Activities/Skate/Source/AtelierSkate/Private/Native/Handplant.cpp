// SPDX-License-Identifier: Apache-2.0
#include "Handplant.h"
#include "AnimatedSkeleton.h"
#include "FootIk.h"
#include "PlantMath.h"
#include "PlantSkeleton.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace plant_math;
constexpr Vec4 Up{0, 1, 0, 0};
Vec4 Decode(RawVector words) {
  Vec4 value;
  for (unsigned i = 0; i < 4; ++i)
    value[i] = Float(words[i]);
  return value;
}
std::int32_t Increment(std::int32_t value) {
  std::uint32_t word;
  std::memcpy(&word, &value, 4);
  ++word;
  std::memcpy(&value, &word, 4);
  return value;
}
class SurfaceQueries final : public PlayerGrindSurfaceQueries {
public:
  SurfaceQueries(const WorldGeometry &w, std::array<std::uint32_t, 2> a)
      : world(w), actor(a) {}
  const WorldGeometry &world;
  std::array<std::uint32_t, 2> actor;
  bool Query(std::size_t i, PlayerGrindProbe p,
             std::optional<PlayerGrindProbeHit> &r,
             std::string &error) override {
    return PlayerGrindSurfaceProbe(world, actor, i, p, r, error);
  }
};
} // namespace
Handplant::Handplant()
    : phase(std::numeric_limits<float>::max()),
      initial{Vec4{}, Vec4{}, Vec4{}, -1}, entry(initial),
      outgoing{initial, initial},
      rotations{SkeletonIdentity, SkeletonIdentity, SkeletonIdentity,
                SkeletonIdentity} {}
bool Handplant::Load(const SettingsDatabase &data, std::string &error) {
  Handplant value;
  if (!value.settings.Load(data, error))
    return false;
  *this = std::move(value);
  return true;
}
void Handplant::Reset() {
  flags &= ~0xb0000000u;
  phase = std::numeric_limits<float>::max();
  anchor = {};
  pending.reset();
  candidate.reset();
  elapsed = -1;
  warped = -1;
  apex = -1;
  estimated_phase = -1;
  out_duration = 0;
  direction = {};
  continuation = true;
}
void Handplant::ResetIk() {
  ik_blend = 0;
  ik_distance = -1;
  ik_released = false;
  ik_latched = false;
}
void Handplant::FullReset() {
  Reset();
  ResetIk();
  direction_hint = 0;
  direction_count = 0;
}
void Handplant::EstimateApex() {
  using namespace plant_math;
  const float offset = warped - apex,
              stride = std::abs(offset * Float(0x3eaaaaab));
  float mean = 0;
  for (unsigned i = 0; i < 4; ++i)
    mean += 1.0f + settings.time_warp.Evaluate(offset + float(i) * stride);
  mean *= 0.25f;
  if (mean != 0.0f)
    estimated_phase = (-1.0f / mean) * offset;
  phase = estimated_phase;
}
float HandplantApexTime(const AirTrajectory &t) {
  return t.velocity[1] < 0.0f || t.acceleration[1] >= 0.0f
             ? 0.0f
             : t.velocity[1] * plant_math::Reciprocal(-t.acceleration[1]);
}
void Handplant::GroundQuery(const ProcessedPhysicsInput &p,
                            const PlayerGrindStaticProvider &world) {
  GroundQuery(p, world.Primitives());
}
void Handplant::GroundQuery(
    const ProcessedPhysicsInput &p,
    const std::vector<PlayerGrindPrimitive> &primitives) {
  using namespace plant_math;
  if ((p.flags_2476 & (1u << 22)) == 0) {
    FullReset();
    return;
  }
  const auto com = Decode(p.vectors_544_560_592_608[2]),
             velocity = Decode(p.vectors_400_416[0]),
             normal = Decode(p.vectors_464_480_496_512_528[0]),
             heading = Decode(p.vectors_544_560_592_608[1]);
  if ((p.flags_2480 & (1u << 29)) != 0 || (p.flags_2480 & (1u << 28)) == 0) {
    direction_hint = 0;
    direction_count = 0;
  } else if (normal[1] < 0.95f) {
    if (direction_hint == 0)
      direction_hint = candidate ? candidate->side : 0;
    const std::int32_t side =
        Dot(velocity, Normalize(Cross(Up, normal))) > 0.0f ? 1 : 2;
    if (direction_hint == side)
      direction_count = 0;
    else {
      direction_count = Increment(direction_count);
      if (direction_count > settings.direction_frames)
        direction_hint = 0;
    }
  } else {
    direction_hint = 0;
    direction_count = 0;
  }
  const auto selected = SelectHandplantContact(settings, com, velocity, normal,
                                               direction_hint, primitives);
  const auto old_point = candidate ? candidate->point : Vec4{};
  const auto hint = direction_hint, count = direction_count;
  Reset();
  previous_candidate_point = old_point;
  direction_hint = hint;
  direction_count = count;
  candidate = selected;
  if (selected)
    pending = HandplantPending{*selected, com, velocity, normal, heading};
}
bool Handplant::GroundUpdate(PhysicalSimulationRuntime &physical,
                             const ProcessedPhysicsInput &p,
                             const AnimatedSkeleton &animated, FootIk &ik,
                             std::string &error) {
  if ((p.flags_2476 & (1u << 22)) == 0) {
    FullReset();
    error.clear();
    return true;
  }
  if (pending) {
    const auto submitted = *pending;
    pending.reset();
    const auto &c = submitted.candidate;
    const PlayerGrindSurfaceInput query{c.edge.start, c.edge.end, c.point,
                                        std::nullopt, settings.truck_distance};
    SurfaceQueries queries(physical.world,
                           {p.actor_query_2948, p.actor_query_2952});
    PlayerGrindSurface surface;
    if (!InvestigatePlayerGrindSurface(query, queries, surface, error))
      return false;
    if (PreparePlayerGrindSurface(query) &&
        surface.kind != PlayerGrindGeometryKind::Impossible)
      Launch(c, submitted.com, submitted.velocity, submitted.normal,
             submitted.heading, physical.riding.reckoning_frames.heading);
  }
  if (flags & 0x80000000u)
    UpdateIk(p, animated, physical.roots, physical.animation_record, ik, true);
  error.clear();
  return true;
}
bool Handplant::Enter(PhysicalSimulationRuntime &physical,
                      const ProcessedPhysicsInput &p,
                      std::uint8_t &board_animated,
                      HandplantTrajectoryQueries &queries, std::string &error) {
  physical.board.HookMut().drive.EnableAngularOnly(board_animated);
  entry = {Decode(p.vectors_544_560_592_608[2]),
           Decode(p.vectors_544_560_592_608[3]),
           {0, plant_math::Float(0xc11ccccd), 0, 0},
           -1};
  warped = 0;
  elapsed = 0;
  continuation = true;
  return SelectOutgoing(physical.world, queries, error);
}
bool Handplant::Update(PlantSkeletonFrame frame, HandplantAirReckoning &air,
                       std::string &error) {
  using namespace plant_math;
  auto &physical = frame.owners.physical;
  physical.skeleton_collision.DisableHandplantContacts(2);
  warped += (1.0f + settings.time_warp.Evaluate(warped - apex)) * Step();
  EstimateApex();
  elapsed += Step();
  std::array<Mat4, 24> pose;
  for (std::size_t i = 0; i < 24; ++i)
    pose[i] = ComposeSkeletonAffine(physical.roots.animation_to_world,
                                    physical.animation_record.pose[i]);
  const auto values =
      Values(pose, Decode(frame.processed.vectors_544_560_592_608[2]));
  air.UpdatePlant(physical.riding, frame.processed, values.up, values.heading);
  UpdateIk(frame.processed, frame.owners.animated, physical.roots,
           physical.animation_record, frame.owners.ik, false);
  return AdvancePlantSkeleton(frame, values.com, std::nullopt, error);
}
void Handplant::UpdateIk(const ProcessedPhysicsInput &p,
                         const AnimatedSkeleton &animated,
                         const SkeletonRootFrames &roots,
                         const SkeletonAnimationRecord &record, FootIk &ik,
                         bool ground) {
  using namespace plant_math;
  if (ground &&
      ((p.flags_2480 & (1u << 29)) != 0 || (p.flags_2480 & (1u << 28)) == 0))
    ResetIk();
  const bool right =
      ((flags & 0x20000000u) != 0) ^ ((p.flags_2476 & (1u << 2)) != 0);
  const std::size_t side = right ? 1 : 0, limb = 2 + side;
  const auto world = [&](std::size_t part) {
    return Point(roots.animation_to_world, record.pose[part][3]);
  };
  auto hand = world(3 + side * 4);
  const auto shoulder = world(6 + side * 4);
  const bool attached = phase > -settings.hand_release;
  if (!attached)
    ik_released = true;
  const auto shoulder_delta = Sub(shoulder, anchor);
  if (!ik_released && Length(shoulder_delta) > Float(0x37800000)) {
    const auto axis = Normalize(shoulder_delta);
    const float projection = Dot(Sub(hand, anchor), axis);
    if (projection <= 0.0f)
      ik_released = true;
    else {
      const auto on_axis = Madd(axis, projection, anchor);
      if (ik_latched)
        hand = on_axis;
      else {
        const auto radial = Sub(hand, on_axis);
        const float radius = settings.hand_radius.Evaluate(projection);
        if (Length(radial) > radius)
          hand = Madd(Normalize(radial), radius, on_axis);
      }
    }
    const auto delta = Sub(hand, anchor);
    const float distance = Length(delta);
    if (ik_distance < 0.0f)
      ik_distance = distance;
    ik_distance = VectorMin(distance, ik_distance - settings.hand_approach);
    if (ik_distance < Float(0x37800000) || distance < Float(0x37800000))
      ik_released = true;
    else
      hand = Madd(Normalize(delta), ik_distance, anchor);
    if (!ik_released && !ik_latched) {
      const auto on_axis = Madd(axis, Dot(Sub(hand, anchor), axis), anchor);
      if (Length(Sub(hand, on_axis)) < 0.02f)
        ik_latched = true;
    }
  }
  if (ik_released)
    hand = anchor;
  const auto delta = Sub(hand, shoulder);
  if (Length(delta) > 0.65f)
    hand = Madd(Normalize(delta), 0.65f, shoulder);
  ik_blend = Clamp01(ik_blend + (attached ? Step() / settings.hand_into
                                          : -Step() / settings.hand_out));
  if (ik_blend > 0.0f) {
    const auto original =
        Point(roots.animation_to_world, animated.targets[limb][3]);
    const auto d = Sub(hand, original);
    if (Length(d) > 0.65f)
      hand = Madd(Normalize(d), 0.65f, original);
    ik.state.external_targets[limb].world_position = hand;
    ik.state.limbs[limb].external_target_set = true;
    ik.state.limbs[limb].target_blend = ik_blend;
  }
}
} // namespace atelier::skate
