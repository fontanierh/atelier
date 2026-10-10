#include "AirTrajectoryQuery.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
float Bits(std::uint32_t word) {
  float value;
  std::memcpy(&value, &word, 4);
  return value;
}
constexpr Vec4 Up{0, 1, 0, 0};
constexpr Mat4 Identity{Vec4{1, 0, 0, 0}, Up, Vec4{0, 0, 1, 0}, Vec4{}};
Vec4 Sub(Vec4 a, Vec4 b) {
  for (std::size_t i = 0; i < 4; ++i) a[i] -= b[i];
  return a;
}
Vec4 Scale(Vec4 a, float scalar) {
  for (auto &v : a) v *= scalar;
  return a;
}
// Preserve the trajectory module's negated first product inside the FMA;
// another equivalent cross-product expression can round differently.
Vec4 Cross(Vec4 a, Vec4 b) {
  return {std::fma(-a[2], b[1], a[1] * b[2]),
          std::fma(-a[0], b[2], a[2] * b[0]),
          std::fma(-a[1], b[0], a[0] * b[1]), 0};
}
float Length(Vec4 value) {
  const float square = Dot3(value, value);
  return square == 0 ? 0 : square * InverseLengthSquared(square, 2);
}
Vec4 Normalize(Vec4 value) {
  const float square = Dot3(value, value);
  const float inverse = InverseLengthSquared(square, 2);
  const float length = square == 0 ? 0 : square * inverse;
  return length > Bits(0x358637bd) ? Scale(value, inverse) : Vec4{};
}
float StepSize(float gravity_y, float error_radius) {
  const float square = RefinedReciprocal(gravity_y, 2) * (-8.0f * error_radius);
  return square == 0 ? 0 : square * InverseLengthSquared(square, 2);
}
std::int32_t SaturatedInteger(float value) {
  if (std::isnan(value)) return 0;
  if (value >= 2147483648.0f) return std::numeric_limits<std::int32_t>::max();
  if (value <= -2147483648.0f) return std::numeric_limits<std::int32_t>::min();
  return static_cast<std::int32_t>(value);
}
std::pair<float, std::int32_t> TimeAtContact(AirTrajectoryQueryRequest request,
                                          Vec4 position, float time) {
  const auto &trajectory = request.trajectory;
  const float epsilon = Bits(0x38d1b717), step = Bits(0x3c888889);
  if (epsilon >= std::fabs(RefinedReciprocal(2, 2) * trajectory.acceleration[1])) {
    const float distance = Length(Sub(position, trajectory.position));
    if (!(std::fabs(distance) > epsilon)) return {0, 0};
    const float speed = Length(trajectory.velocity);
    if (!(std::fabs(speed) > epsilon)) return {0, 0};
    const float frames = RefinedReciprocal(speed, 2) * distance;
    return {frames * step, SaturatedInteger(std::ceil(frames))};
  }
  float closest = std::numeric_limits<float>::max();
  bool found = false;
  while (trajectory.scalar_48 >= time) {
    const auto delta = Sub(position, AirTrajectoryPositionAt(trajectory, time));
    const float square = Dot3(delta, delta);
    if (closest >= square) closest = square;
    else if (square > closest) {
      time -= step;
      found = true;
      break;
    }
    time += step;
  }
  if (!found) time = trajectory.scalar_48;
  return {time, SaturatedInteger(std::ceil(RefinedReciprocal(step, 2) * time))};
}
Vec4 AverageLandingNormal(const std::vector<std::array<Vec4, 3>> &triangles,
                         Vec4 velocity) {
  std::vector<Vec4> accepted;
  accepted.reserve(64);
  Vec4 most_up{};
  float highest = -1;
  for (std::size_t i = 0; i < triangles.size() && i < 64; ++i) {
    const auto &triangle = triangles[i];
    auto normal = Cross(Sub(triangle[1], triangle[0]),
                        Sub(triangle[2], triangle[0]));
    normal = Scale(normal, InverseLengthSquared(Dot3(normal, normal), 2));
    if (normal[1] > 0.7f || Dot3(normal, velocity) <= 0) {
      const float up = Dot3(normal, Up);
      if (up > highest) { highest = up; most_up = normal; }
      accepted.push_back(normal);
    }
  }
  if (accepted.empty()) return Up;
  Vec4 total{};
  for (const auto &normal : accepted)
    if (Dot3(most_up, normal) > 0.5f)
      for (std::size_t i = 0; i < 4; ++i) total[i] += normal[i];
  return Normalize(total);
}
bool Separated(const std::array<Vec4, 3> &vertices, Vec4 axis, Vec4 half) {
  const std::array<float, 3> projections{Dot3(vertices[0], axis),
                                       Dot3(vertices[1], axis),
                                       Dot3(vertices[2], axis)};
  const float minimum = VectorMin(VectorMin(projections[0], projections[1]), projections[2]);
  const float maximum = VectorMax(VectorMax(projections[0], projections[1]), projections[2]);
  const float radius = (half[0] * std::fabs(axis[0]) + half[1] * std::fabs(axis[1])) +
                       half[2] * std::fabs(axis[2]);
  return minimum > radius || maximum < -radius;
}
bool TriangleBox(std::array<Vec4, 3> vertices, Vec4 minimum, Vec4 maximum) {
  Vec4 center, half;
  for (std::size_t i = 0; i < 4; ++i) {
    center[i] = (minimum[i] + maximum[i]) * 0.5f;
    half[i] = (maximum[i] - minimum[i]) * 0.5f;
  }
  for (auto &v : vertices) v = Sub(v, center);
  const std::array<Vec4, 3> edges{Sub(vertices[1], vertices[0]),
                                 Sub(vertices[2], vertices[1]),
                                 Sub(vertices[0], vertices[2])};
  constexpr std::array<Vec4, 3> axes{Vec4{1, 0, 0, 0}, Up, Vec4{0, 0, 1, 0}};
  for (const auto &edge : edges)
    for (const auto &axis : axes)
      if (Separated(vertices, Cross(edge, axis), half)) return false;
  for (const auto &axis : axes)
    if (Separated(vertices, axis, half)) return false;
  return !Separated(vertices, Cross(edges[0], edges[1]), half);
}
Vec3 XYZ(Vec4 value) { return {value[0], value[1], value[2]}; }
Vec4 Lanes(Vec3 value) { return {value.x, value.y, value.z, 0}; }
} // namespace
AirTrajectoryQueryResult AirTrajectoryQueryResult::Miss() {
  return {{}, Up, Up, -1, Identity, -1, 0, 0};
}
Vec4 AirTrajectoryPositionAt(const AirTrajectory &trajectory, float time) {
  const float square = time * time;
  Vec4 result;
  for (std::size_t i = 0; i < 4; ++i)
    result[i] = std::fma(trajectory.acceleration[i] * 0.5f, square,
                         std::fma(trajectory.velocity[i], time, trajectory.position[i]));
  return result;
}
Vec4 AirTrajectoryVelocityAt(const AirTrajectory &trajectory, float time) {
  Vec4 result;
  for (std::size_t i = 0; i < 4; ++i)
    result[i] = std::fma(trajectory.acceleration[i], time, trajectory.velocity[i]);
  return result;
}
std::pair<Vec4, float> AirTrajectoryHighestPosition(const AirTrajectory &trajectory) {
  if (trajectory.velocity[1] < 0 || trajectory.acceleration[1] >= 0)
    return {trajectory.position, 0};
  const float time = trajectory.velocity[1] * RefinedReciprocal(-trajectory.acceleration[1], 2);
  return {AirTrajectoryPositionAt(trajectory, time), time};
}
bool QueryAirTrajectory(AirTrajectoryQueryRequest request, AirTrajectoryWorldQueries &world,
                        AirTrajectoryQueryResult &output, std::string &error) {
  const auto &trajectory = request.trajectory;
  float start_step = trajectory.scalar_48, end_step = trajectory.scalar_48;
  if (trajectory.acceleration[1] < 0) {
    start_step = StepSize(trajectory.acceleration[1], request.start_error * request.radius);
    end_step = StepSize(trajectory.acceleration[1], request.end_error * request.radius);
  }
  const float minimum_square = ((request.start_error * request.radius) * request.start_error) * request.radius;
  float time = 0;
  auto start = AirTrajectoryPositionAt(trajectory, time);
  auto end = AirTrajectoryPositionAt(trajectory, time + start_step);
  while (trajectory.scalar_48 > time) {
    const auto delta = Sub(end, start);
    if (Dot3(delta, delta) > minimum_square) {
      if (std::fabs(delta[0]) > Bits(0x37800000) ||
          std::fabs(delta[1]) > Bits(0x37800000) ||
          std::fabs(delta[2]) > Bits(0x37800000)) {
        std::optional<AirTrajectorySurfaceHit> hit;
        if (!world.Line(start, end, request.radius, hit, error)) return false;
        if (hit) {
          const auto [contact_time, contact_frame] = TimeAtContact(request, hit->position, time);
          std::vector<std::array<Vec4, 3>> triangles;
          if (!world.Nearby(hit->position, request.radius, triangles, error)) return false;
          const auto velocity = AirTrajectoryVelocityAt(trajectory, static_cast<float>(contact_frame) * Bits(0x3c888889));
          output = {hit->position, hit->normal, AverageLandingNormal(triangles, velocity),
                    contact_time, hit->transform, contact_frame, hit->surface, hit->geometry};
          error.clear();
          return true;
        }
      }
      start = end;
    }
    const float fraction = RefinedReciprocal(trajectory.scalar_48, 2) * time;
    const float step = std::fma(end_step, fraction, (1.0f - fraction) * start_step);
    const float next_time = time + step;
    // Original nonadvancing walks do not return. Reject those outside its valid
    // domain rather than allowing malformed inputs to stall the game thread.
    if (next_time <= time) {
      error = "Nonadvancing trajectory query step";
      return false;
    }
    time = next_time;
    end = AirTrajectoryPositionAt(trajectory, time + step);
  }
  output = AirTrajectoryQueryResult::Miss();
  error.clear();
  return true;
}
bool AirTrajectoryWorldLine(const WorldGeometry &world, Vec4 start, Vec4 end, float radius,
                            std::optional<AirTrajectorySurfaceHit> &output, std::string &error) {
  if (!std::isfinite(radius) || radius < 0) {
    error = "Non-finite trajectory collision request or invalid radius";
    return false;
  }
  for (std::size_t i = 0; i < 4; ++i)
    if (!std::isfinite(start[i]) || !std::isfinite(end[i])) {
      error = "Non-finite trajectory collision request or invalid radius";
      return false;
    }
  const auto from = XYZ(start), to = XYZ(end), delta = Subtract(to, from);
  float nearest = std::numeric_limits<float>::max();
  std::optional<AirTrajectorySurfaceHit> result;
  for (const auto index : world.LineCandidates(from, to, radius)) {
    const auto &entry = world.Triangles()[index];
    TriangleLineHit hit{};
    if (TriangleSegment(hit, from, delta, entry.triangle.vertices, radius, 0)) {
      const float lower = -hit.fraction >= 0 ? 0 : hit.fraction;
      const float fraction = 1.0f - lower >= 0 ? lower : 1;
      if (fraction < nearest) {
        nearest = fraction;
        if (index > std::numeric_limits<std::uint32_t>::max()) {
          error = "World geometry index overflow";
          return false;
        }
        result = AirTrajectorySurfaceHit{Lanes(hit.position), Lanes(entry.triangle.feature.normal),
                                         Identity, entry.tag, static_cast<std::uint32_t>(index)};
      }
    }
  }
  output = result;
  error.clear();
  return true;
}
bool AirTrajectoryNearbyTriangles(const WorldGeometry &world, Vec4 center, float radius,
                                  std::vector<std::array<Vec4, 3>> &output, std::string &error) {
  if (!std::isfinite(radius) || radius < 0) {
    error = "Invalid nearby-trajectory triangle radius";
    return false;
  }
  Vec4 minimum, maximum;
  for (std::size_t i = 0; i < 4; ++i) {
    minimum[i] = center[i] - radius;
    maximum[i] = center[i] + radius;
  }
  std::vector<std::array<Vec4, 3>> triangles;
  triangles.reserve(64);
  for (const auto index : world.LineCandidates(XYZ(center), XYZ(center), radius)) {
    const auto &vertices = world.Triangles()[index].triangle.vertices;
    const std::array<Vec4, 3> lanes{Lanes(vertices[0]), Lanes(vertices[1]), Lanes(vertices[2])};
    if (TriangleBox(lanes, minimum, maximum)) {
      triangles.push_back(lanes);
      if (triangles.size() == 64) break;
    }
  }
  output = std::move(triangles);
  error.clear();
  return true;
}
} // namespace atelier::skate
