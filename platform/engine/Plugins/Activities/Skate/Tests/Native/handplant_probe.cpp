// SPDX-License-Identifier: Apache-2.0
#include "AnimationPose.h"
#include "Handplant.h"
#include "PlayerInputPhase.h"
#include "PhysicsSkeleton.h"
#include "PlantMath.h"
#include "PlantSkeleton.h"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
std::vector<std::uint8_t> File(const std::string &path) {
  std::ifstream file(path, std::ios::binary);
  if (!file)
    std::abort();
  return {std::istreambuf_iterator<char>(file), {}};
}
struct Input {
  std::vector<std::uint8_t> data;
  std::size_t at = 0;
  std::uint32_t Word() {
    if (at + 4 > data.size())
      std::abort();
    std::uint32_t v = 0;
    for (unsigned i = 0; i < 4; ++i)
      v |= std::uint32_t(data[at++]) << (8 * i);
    return v;
  }
  std::uint64_t Wide() {
    const auto lo = Word(), hi = Word();
    return std::uint64_t(lo) | (std::uint64_t(hi) << 32);
  }
  float Float() { return plant_math::Float(Word()); }
  template <std::size_t N> std::array<float, N> Floats() {
    std::array<float, N> v;
    for (auto &f : v)
      f = Float();
    return v;
  }
  Mat4 Matrix() {
    Mat4 m;
    for (auto &v : m)
      v = Floats<4>();
    return m;
  }
};
struct Output {
  std::vector<std::uint32_t> words;
  void Word(std::uint32_t w) { words.push_back(w); }
  void Wide(std::uint64_t w) {
    Word(std::uint32_t(w));
    Word(std::uint32_t(w >> 32));
  }
  void Float(float v) {
    std::uint32_t w;
    std::memcpy(&w, &v, 4);
    Word(w);
  }
  template <std::size_t N> void Floats(std::array<float, N> v) {
    for (float f : v)
      Float(f);
  }
  void Matrix(Mat4 m) {
    for (auto v : m)
      Floats(v);
  }
  void Status(bool okay, const std::string &error) {
    Word(std::uint32_t(okay));
    if (!okay) {
      Word(std::uint32_t(error.size()));
      for (unsigned char c : error)
        Word(c);
    }
  }
};
AirTrajectory Trajectory(Input &i) {
  return {i.Floats<4>(), i.Floats<4>(), i.Floats<4>(), i.Float()};
}
HandplantCandidate Candidate(Input &i) {
  const auto point = i.Floats<4>(), start = i.Floats<4>(), end = i.Floats<4>();
  const auto owner = i.Wide();
  const auto side = i.Word();
  std::int32_t signed_side;
  std::memcpy(&signed_side, &side, 4);
  return {point, {start, end, owner}, signed_side};
}
void CandidateOut(Output &o, HandplantCandidate c) {
  o.Floats(c.point);
  o.Floats(c.edge.start);
  o.Floats(c.edge.end);
  o.Wide(c.edge.owner);
  o.Word(std::uint32_t(c.side));
}
void TrajectoryOut(Output &o, AirTrajectory t) {
  o.Floats(t.position);
  o.Floats(t.velocity);
  o.Floats(t.acceleration);
  o.Float(t.scalar_48);
}
void SettingsOut(Output &o, const HandplantSettings &s) {
  for (auto g : s.window) {
    o.Floats(g.x);
    o.Floats(g.y);
  }
  o.Floats(std::array<float, 2>{s.depth, s.window_drop});
  for (auto g : {s.time_warp, s.out_heading, s.into_rotation, s.out_rotation}) {
    o.Floats(g.x);
    o.Floats(g.y);
  }
  o.Floats(s.hand_radius.x);
  o.Floats(s.hand_radius.y);
  o.Floats(std::array<float, 11>{
      s.curve_half_time, s.entry_blend, s.hand_out, s.hand_into, s.hand_release,
      s.minimum_speed, s.minimum_slope, s.rotation_time, s.committed_time,
      s.minimum_out_speed, s.hand_approach});
  o.Word(std::uint32_t(s.direction_frames));
  o.Floats(std::array<float, 2>{s.apex_radius, s.apex_angle});
  o.Floats(s.animation);
  o.Float(s.truck_distance);
}
void Seed(Input &i, Handplant &h) {
  h.flags = i.Word();
  h.phase = i.Float();
  h.anchor = i.Floats<4>();
  h.previous_candidate_point = i.Floats<4>();
  h.pending.reset();
  if (i.Word()) {
    const auto c = Candidate(i);
    const auto a = i.Floats<4>(), b = i.Floats<4>(), d = i.Floats<4>(),
               e = i.Floats<4>();
    h.pending = HandplantPending{c, a, b, d, e};
  }
  h.candidate.reset();
  if (i.Word())
    h.candidate = Candidate(i);
  h.initial = Trajectory(i);
  h.entry = Trajectory(i);
  for (auto &t : h.outgoing)
    t = Trajectory(i);
  for (auto &v : h.curve)
    v = i.Floats<4>();
  for (auto &m : h.rotations)
    m = i.Matrix();
  h.direction = i.Floats<4>();
  h.travel_sign = i.Float();
  h.elapsed = i.Float();
  h.warped = i.Float();
  h.apex = i.Float();
  h.estimated_phase = i.Float();
  h.out_duration = i.Float();
  h.continuation = i.Word() != 0;
  const auto hint = i.Word(), count = i.Word();
  std::memcpy(&h.direction_hint, &hint, 4);
  std::memcpy(&h.direction_count, &count, 4);
  h.ik_blend = i.Float();
  h.ik_distance = i.Float();
  h.ik_released = i.Word() != 0;
  h.ik_latched = i.Word() != 0;
}
void OwnerOut(Output &o, const Handplant &h) {
  o.Word(h.flags);
  o.Float(h.phase);
  o.Floats(h.anchor);
  o.Floats(h.previous_candidate_point);
  o.Word(std::uint32_t(h.pending.has_value()));
  if (h.pending) {
    CandidateOut(o, h.pending->candidate);
    for (auto v : {h.pending->com, h.pending->velocity, h.pending->normal,
                   h.pending->heading})
      o.Floats(v);
  }
  o.Word(std::uint32_t(h.candidate.has_value()));
  if (h.candidate)
    CandidateOut(o, *h.candidate);
  for (auto t : {h.initial, h.entry, h.outgoing[0], h.outgoing[1]})
    TrajectoryOut(o, t);
  for (auto v : h.curve)
    o.Floats(v);
  for (auto m : h.rotations)
    o.Matrix(m);
  o.Floats(h.direction);
  o.Floats(std::array<float, 6>{h.travel_sign, h.elapsed, h.warped, h.apex,
                                h.estimated_phase, h.out_duration});
  o.Word(std::uint32_t(h.continuation));
  o.Word(std::uint32_t(h.direction_hint));
  o.Word(std::uint32_t(h.direction_count));
  o.Floats(std::array<float, 2>{h.ik_blend, h.ik_distance});
  o.Word(std::uint32_t(h.ik_released));
  o.Word(std::uint32_t(h.ik_latched));
}
void EffectsOut(Output &o, const PhysicalSimulationRuntime &physical,
                const FootIk &ik, std::uint8_t board_animated) {
  for (auto limb : ik.state.limbs) {
    o.Word(std::uint32_t(limb.external_target_set));
    o.Float(limb.target_blend);
  }
  for (auto target : ik.state.external_targets)
    o.Floats(target.world_position);
  o.Word(std::uint32_t(physical.skeleton_collision.pending_reenable));
  for (auto n : physical.skeleton_collision.disable_count)
    o.Word(n);
  for (auto part : physical.skeleton_collision.parts)
    o.Word(std::uint32_t(part.enabled));
  o.Word(board_animated);
}
RawVector Raw(Vec4 v) {
  RawVector w;
  for (unsigned i = 0; i < 4; ++i)
    std::memcpy(&w[i], &v[i], 4);
  return w;
}
WorldGeometry World(Input &i) {
  std::vector<WorldTriangle> triangles;
  const auto count = i.Word();
  for (unsigned n = 0; n < count; ++n) {
    std::array<Vec3, 3> vertices;
    for (auto &v : vertices) {
      const auto a = i.Floats<3>();
      v = {a[0], a[1], a[2]};
    }
    const float fat = i.Float();
    const auto edges = i.Floats<3>();
    const auto flags = i.Word();
    const ContactMaterial material{i.Float(), i.Float(), i.Float()};
    const auto tag = i.Word();
    triangles.push_back(
        {TriangleFromVolume(vertices, fat, edges, flags), material, tag});
  }
  return WorldGeometry(std::move(triangles));
}
// Explicit caller-authored scene metadata; numerical queries remain production.
WorldGeometry AuthoredQueryWorld(Input &i) {
  auto source = World(i);
  QueryMetadata metadata;
  const auto surfaces = i.Word();
  for (unsigned n = 0; n < surfaces; ++n)
    metadata.packed_surfaces.push_back(std::uint16_t(i.Word()));
  const auto meshes = i.Word();
  for (unsigned n = 0; n < meshes; ++n) {
    QueryMesh mesh;
    mesh.triangle_range = {i.Word(), i.Word()};
    const auto min = i.Floats<3>(), max = i.Floats<3>();
    mesh.local_bounds = {{min[0], min[1], min[2]}, {max[0], max[1], max[2]}};
    const auto group = i.Word();
    std::memcpy(&mesh.matching_group, &group, 4);
    mesh.rejection_flags = i.Word();
    mesh.geometry = i.Word();
    const auto pool = i.Word();
    if (pool > 2)
      std::abort();
    mesh.pool = QueryPool(pool);
    metadata.meshes.push_back(mesh);
  }
  metadata.island_flags = i.Word();
  const char *error = nullptr;
  auto result = WorldGeometry::WithQueryMetadata(source.Triangles(),
                                                 std::move(metadata), error);
  if (!result)
    std::abort();
  return std::move(*result);
}
class MissingCandidateQuery final : public HandplantTrajectoryQueries {
  bool Query(const WorldGeometry &, const AirTrajectory &, float, float, float,
             PlantTrajectoryQueryResult &, std::string &) override {
    std::abort();
  }
};
} // namespace
int main(int argc, char **argv) {
  if (argc != 6)
    return 2;
  SettingsDatabase data;
  PhysicsSkeletons skeletons;
  AnimationPoseFrames frames;
  std::string error;
  if (!data.Load(File(argv[1]), error) ||
      !skeletons.Load(File(argv[2]), argv[4], error) ||
      !frames.rig.Load(File(argv[3]), error)) {
    std::cerr << error;
    return 2;
  }
  const auto *definition = skeletons.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  AnimationPoseEvaluator evaluator(std::move(frames));
  if (!evaluator.LoadAuthoredClips(argv[5], error)) {
    std::cerr << error;
    return 2;
  }
  const auto settings = PhysicalSimulationSettings::Load(
      data, *definition, evaluator.frames.rig, error);
  const auto animation_settings = AnimatedSkeletonSettings::Load(
      data, *definition, evaluator.frames.rig, false, error);
  if (!settings || !animation_settings) {
    std::cerr << error;
    return 2;
  }
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    auto world = World(i);
    std::vector<PlayerGrindPrimitive> edges;
    const auto n = i.Word();
    for (unsigned e = 0; e < n; ++e) {
      const auto start = i.Floats<4>(), end = i.Floats<4>();
      const auto owner = i.Wide();
      edges.push_back({start, end, owner});
    }
    auto physical = PhysicalSimulationRuntime::Initialize(
        *settings, data, evaluator, std::move(world),
        settings->Spawn({0, -.035f, 0}), error);
    if (!physical) {
      std::cerr << error;
      return 2;
    }
    auto &p = *physical;
    AnimatedSkeleton animated(*animation_settings);
    auto ik = FootIk::Load(data, evaluator.frames.rig, animated, error);
    Handplant h;
    if (!ik || !h.Load(data, error)) {
      std::cerr << error;
      return 2;
    }
    ProcessedPhysicsInput processed{};
    ResetProcessedPhysicsInput(processed);
    std::uint8_t board_animated = 0;
    SettingsOut(o, h.settings);
    const auto rows = i.Word();
    o.Word(rows);
    OwnerOut(o, h);
    EffectsOut(o, p, *ik, board_animated);
    for (unsigned r = 0; r < rows; ++r) {
      const auto op = i.Word();
      o.Word(op);
      switch (op) {
      case 0:
        Seed(i, h);
        break;
      case 1:
        h.Reset();
        break;
      case 2:
        h.FullReset();
        break;
      case 3:
        processed.flags_2476 = i.Word();
        processed.flags_2480 = i.Word();
        processed.actor_query_2948 = i.Word();
        processed.actor_query_2952 = i.Word();
        processed.vectors_544_560_592_608[2] = Raw(i.Floats<4>());
        processed.vectors_400_416[0] = Raw(i.Floats<4>());
        processed.vectors_464_480_496_512_528[0] = Raw(i.Floats<4>());
        processed.vectors_544_560_592_608[1] = Raw(i.Floats<4>());
        p.riding.reckoning_frames.heading = i.Floats<4>();
        h.GroundQuery(processed, edges);
        break;
      case 4:
        o.Status(h.GroundUpdate(p, processed, animated, *ik, error), error);
        break;
      case 5: {
        const auto candidate = Candidate(i);
        const auto com = i.Floats<4>(), velocity = i.Floats<4>(),
                   normal = i.Floats<4>(), body = i.Floats<4>(),
                   heading = i.Floats<4>();
        h.Launch(candidate, com, velocity, normal, body, heading);
        break;
      }
      case 6: {
        std::array<Mat4, 24> pose;
        for (auto &m : pose)
          m = i.Matrix();
        const auto result = h.Values(pose, i.Floats<4>());
        o.Floats(result.com);
        o.Floats(result.up);
        o.Floats(result.heading);
        break;
      }
      case 7: {
        const bool ground = i.Word() != 0;
        processed.flags_2476 = i.Word();
        processed.flags_2480 = i.Word();
        p.roots.animation_to_world = i.Matrix();
        for (auto &m : p.animation_record.pose)
          m = i.Matrix();
        for (auto &m : animated.targets)
          m = i.Matrix();
        h.UpdateIk(processed, animated, p.roots, p.animation_record, *ik,
                   ground);
        break;
      }
      case 8:
        h.settings.time_warp.x = i.Floats<8>();
        h.settings.time_warp.y = i.Floats<8>();
        break;
      case 9: {
        const bool right = i.Word() != 0;
        const auto position = i.Floats<4>();
        const auto frames = i.Word();
        HoldPlantFoot(p, *ik, right, position, frames);
        break;
      }
      case 10:
        h.BuildCurve();
        break;
      case 11:
        h.EstimateApex();
        break;
      case 12: {
        const auto heading = i.Floats<4>(), up = i.Floats<4>();
        o.Matrix(HandplantRotationFrame(heading, up));
        break;
      }
      case 13: {
        const auto a = i.Matrix(), b = i.Matrix();
        const auto weight = i.Float();
        o.Matrix(BlendHandplantRotation(a, b, weight));
        break;
      }
      case 14: {
        if (h.candidate)
          std::abort();
        MissingCandidateQuery query;
        const bool okay = h.Enter(p, processed, board_animated, query, error);
        o.Status(okay, error);
        break;
      }
      case 15: {
        using namespace plant_math;
        const auto a = i.Floats<4>(), b = i.Floats<4>();
        const float s = i.Float(), maximum = i.Float();
        const auto m = i.Matrix();
        o.Float(Dot(a, b));
        o.Floats(Cross(a, b));
        o.Floats(Add(a, b));
        o.Floats(Sub(a, b));
        o.Floats(Scale(a, s));
        o.Floats(Madd(a, s, b));
        o.Float(Reciprocal(s));
        o.Float(Length(a));
        o.Floats(Normalize(a));
        o.Floats(Point(m, a));
        o.Floats(Rotate(m, a));
        o.Floats(ClampLength(a, maximum));
        o.Float(Clamp01(s));
        break;
      }
      case 16:
        p.world = AuthoredQueryWorld(i);
        break;
      default:
        std::abort();
      }
      OwnerOut(o, h);
      EffectsOut(o, p, *ik, board_animated);
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto word : o.words)
    for (unsigned b = 0; b < 4; ++b)
      std::cout.put(char(word >> (8 * b)));
  return 0;
}
