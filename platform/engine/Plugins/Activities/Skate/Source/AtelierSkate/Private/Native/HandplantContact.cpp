// SPDX-License-Identifier: Apache-2.0
#include "Handplant.h"
#include "PlantMath.h"
#include <algorithm>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace plant_math;
constexpr Vec4 Up{0, 1, 0, 0};
bool ClipDepth(std::array<Vec4, 2> &segment, float value, bool above) {
  const float sign = above ? 1.0f : -1.0f;
  const float a = (segment[0][2] - value) * sign,
              b = (segment[1][2] - value) * sign;
  if (a <= 0.0f && b <= 0.0f)
    return false;
  const float delta = segment[1][2] - segment[0][2];
  if (std::abs(delta) >= Float(0x37800000)) {
    const float t = (value - segment[0][2]) * Reciprocal(delta);
    if (t > 0.0f && t < 1.0f)
      segment[std::size_t(b <= 0.0f)] =
          Madd(Sub(segment[1], segment[0]), t, segment[0]);
  }
  return true;
}
bool Clip(std::array<Vec4, 2> &segment, float a, float b) {
  if (a < 0.0f && b < 0.0f)
    return false;
  if ((a < 0.0f) != (b < 0.0f))
    segment[std::size_t(a >= 0.0f)] =
        Madd(Sub(segment[1], segment[0]), a * Reciprocal(a - b), segment[0]);
  return true;
}
} // namespace
std::optional<HandplantCandidate>
SelectHandplantContact(const HandplantSettings &settings, Vec4 com,
                       Vec4 velocity, Vec4 normal, std::int32_t hint,
                       const std::vector<PlayerGrindPrimitive> &edges) {
  using namespace plant_math;
  if (!(Length(velocity) > settings.minimum_speed && velocity[1] > 0.0f &&
        std::abs(normal[1]) <= 0.95f &&
        Acos(std::clamp(normal[1], -1.0f, 1.0f)) * Float(0x42652ee1) >
            settings.minimum_slope))
    return std::nullopt;
  Mat4 frame = SkeletonIdentity;
  if (std::abs(normal[1]) <= 0.99f) {
    frame[0] = Normalize(Cross(Up, normal));
    frame[1] = Up;
    frame[2] = Cross(frame[0], Up);
  }
  frame[3] = com;
  const auto inverse = InverseSkeletonRigid(frame);
  velocity = Rotate(inverse, velocity);
  velocity = {velocity[0],
              std::sqrt(velocity[0] * velocity[0] + velocity[1] * velocity[1]),
              0, 0};
  if (hint != 0 && hint != (velocity[0] > 0.0f ? 1 : 2))
    velocity[0] = (hint == 1 ? 1.0f : -1.0f) * Float(0x37800000);
  std::array<float, 7> g;
  for (std::size_t i = 0; i < 7; ++i)
    g[i] = settings.window[i].Evaluate(velocity[1]);
  const float lo_x = VectorMax(g[1], std::abs(velocity[0]) - g[5]),
              hi_x = VectorMin(g[6], std::abs(velocity[0]) + g[4]);
  if (hi_x <= lo_x)
    return std::nullopt;
  const float lo_y = VectorMax(g[0], velocity[1] - g[3]),
              hi_y = velocity[1] + g[2];
  const float sign = velocity[0] > 0.0f ? 1.0f : -1.0f;
  const auto apex = [&](float x, float y) {
    const AirTrajectory trajectory{Point(inverse, com),
                                   {x * sign, y, 0, 0},
                                   {0, Float(0xc11ccccd), 0, 0},
                                   -1};
    auto p = PlantTrajectoryPosition(trajectory, HandplantApexTime(trajectory));
    p[1] -= settings.window_drop;
    return p;
  };
  const auto a = apex(lo_x, lo_y), b = apex(hi_x, lo_y), c = apex(lo_x, hi_y),
             d = apex(hi_x, hi_y);
  const std::array<Vec4, 4> polygon = d[0] > c[0]
                                          ? std::array<Vec4, 4>{c, d, b, a}
                                          : std::array<Vec4, 4>{d, c, a, b};
  struct Clipped {
    PlayerGrindPrimitive edge;
    std::array<Vec4, 2> segment;
  };
  std::vector<Clipped> candidates;
  std::size_t admitted = 0;
  for (const auto &edge : edges) {
    bool nearby = true;
    for (std::size_t i = 0; i < 3; ++i) {
      const float extent = std::array<float, 3>{2, 4, 2}[i];
      if (!(VectorMin(edge.start[i], edge.end[i]) <= com[i] + extent &&
            VectorMax(edge.start[i], edge.end[i]) >= com[i] - extent)) {
        nearby = false;
        break;
      }
    }
    if (!nearby)
      continue;
    if (admitted == 40)
      break;
    ++admitted;
    const auto start = Point(inverse, edge.start),
               end = Point(inverse, edge.end);
    if (std::abs(Normalize(Sub(end, start))[0]) <= 0.71f)
      continue;
    std::array<Vec4, 2> segment{start, end};
    if (!ClipDepth(segment, -settings.depth, true) ||
        !ClipDepth(segment, 0.0f, false))
      continue;
    bool valid = true;
    for (std::size_t i = 0; i < 4; ++i) {
      const auto delta = Sub(polygon[(i + 1) % 4], polygon[i]);
      const auto n = Normalize({delta[1], -delta[0], 0, 0});
      const float d0 = Dot(Sub(segment[0], polygon[i]), n),
                  d1 = Dot(Sub(segment[1], polygon[i]), n);
      if (!Clip(segment, d0, d1)) {
        valid = false;
        break;
      }
    }
    if (valid)
      candidates.push_back({edge, segment});
  }
  std::optional<std::size_t> best;
  float height = -std::numeric_limits<float>::max(), depth = height;
  for (std::size_t i = 0; i < candidates.size(); ++i) {
    const auto &segment = candidates[i].segment;
    const auto p = segment[0][1] > segment[1][1] ? segment[0] : segment[1];
    if (p[1] > height + 0.1f ||
        (p[1] > height - 0.1f && p[1] <= height + 0.1f && p[2] > depth)) {
      best = i;
      height = p[1];
      depth = p[2];
    }
  }
  if (!best)
    return std::nullopt;
  std::vector<bool> connected(candidates.size(), false);
  connected[*best] = true;
  for (bool reverse : {false, true}) {
    auto ends = candidates[*best].segment;
    if (reverse)
      std::swap(ends[0], ends[1]);
    for (;;) {
      std::optional<std::pair<std::size_t, std::array<Vec4, 2>>> next;
      for (std::size_t i = 0; i < candidates.size() && !next; ++i) {
        if (connected[i])
          continue;
        const auto &s = candidates[i].segment;
        for (std::size_t e = 0; e < 2; ++e)
          if (Dot(Sub(ends[1], s[e]), Sub(ends[1], s[e])) < Float(0x3b23d70a) &&
              std::abs(Acos(std::clamp(Dot(Normalize(Sub(ends[1], ends[0])),
                                           Normalize(Sub(s[1 - e], s[e]))),
                                       -1.0f, 1.0f))) < Float(0x3f060a92)) {
            next = std::make_pair(i, std::array<Vec4, 2>{s[e], s[1 - e]});
            break;
          }
      }
      if (!next)
        break;
      connected[next->first] = true;
      ends = next->second;
    }
  }
  const auto bottom = Scale(Add(polygon[2], polygon[3]), 0.5f),
             top = Scale(Add(polygon[0], polygon[1]), 0.5f),
             delta = Sub(top, bottom);
  auto target =
      Madd(delta, Clamp01((height - bottom[1]) * Reciprocal(delta[1])), bottom);
  target = {target[0], target[1], 0, 0};
  Vec4 nearest{};
  float distance = std::numeric_limits<float>::max();
  for (std::size_t i = 0; i < candidates.size(); ++i) {
    if (!connected[i])
      continue;
    const auto &segment = candidates[i].segment;
    const auto segment_delta = Sub(segment[1], segment[0]);
    const float square = Dot(segment_delta, segment_delta);
    const auto p =
        square > Float(0x37800000)
            ? Madd(segment_delta,
                   Clamp01(Dot(Sub(target, segment[0]), segment_delta) *
                           Reciprocal(square)),
                   segment[0])
            : segment[0];
    const float d = Dot(Sub(p, target), Sub(p, target));
    if (d < distance) {
      distance = d;
      nearest = p;
    }
  }
  return HandplantCandidate{Point(frame, nearest), candidates[*best].edge,
                            velocity[0] > 0.0f ? 1 : 2};
}
} // namespace atelier::skate
