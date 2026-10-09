#include "CameraWorld.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
Vec4 PositionFromAngles(Vec4 anchor, Vec4 offset, float elevation,
                        float heading, float distance,
                        std::uint8_t clamp_height, float minimum_height) {
  const auto [se, ce] = SinCos(-elevation);
  const auto [sh, ch] = SinCos(-heading);
  const std::array<Vec4, 3> first{Vec4{1, 0, 0, 1}, Vec4{0, ce, se, 0},
                                  Vec4{0, -se, ce, 0}},
      second{Vec4{ch, 0, -sh, ch}, Vec4{0, 1, 0, 0}, Vec4{sh, 0, ch, sh}};
  std::array<Vec4, 3> product;
  for (std::size_t c = 0; c < 3; ++c)
    for (std::size_t i = 0; i < 4; ++i)
      product[c][i] = std::fma(
          second[2][i], first[c][2],
          std::fma(second[1][i], first[c][1], second[0][i] * first[c][0]));
  Vec4 point;
  for (std::size_t i = 0; i < 4; ++i) {
    float value = product[0][i] * 0;
    value = std::fma(product[1][i], 0.0f, value);
    value = std::fma(product[2][i], distance, value);
    point[i] = (value + offset[i]) + anchor[i];
  }
  if (clamp_height != 0 && minimum_height > point[1])
    point[1] = minimum_height;
  return point;
}
Vec4 ProjectHit(Vec4 end, Vec4 start, FatLineResult result) {
  if (!std::isnan(result.position[0]) && !std::isnan(result.position[1]) &&
      !std::isnan(result.position[2]) && result.hit != 0)
    return Madd(Sub(end, start), Clamp(result.fraction, 0, 1), start);
  return end;
}
bool WorldLine(const WorldGeometry &world, Vec4 start, Vec4 end, float radius,
               FatLineResult &result, std::string &error) {
  if (!std::isfinite(radius) || radius < 0) {
    error = "Invalid stock camera collision radius";
    return false;
  }
  const Vec3 from{start[0], start[1], start[2]}, to{end[0], end[1], end[2]},
      delta{end[0] - start[0], end[1] - start[1], end[2] - start[2]};
  float fraction = std::numeric_limits<float>::max();
  result = {};
  for (const auto index : world.LineCandidates(from, to, radius)) {
    const auto &entry = world.Triangles()[index];
    TriangleLineHit hit{};
    if (TriangleSegment(hit, from, delta, entry.triangle.vertices, radius, 0)) {
      const float candidate = Clamp(hit.fraction, 0, 1);
      if (candidate < fraction) {
        fraction = candidate;
        const auto normal = entry.triangle.feature.normal;
        result = {{hit.position.x, hit.position.y, hit.position.z, 0},
                  {normal.x, normal.y, normal.z, 0},
                  candidate,
                  1,
                  entry.tag};
      }
    }
  }
  return true;
}
void CameraCollision::Submit(std::array<FatLine, 6> lines, std::uint32_t) {
  results = {};
  for (std::size_t i = 0; i < 6; ++i) {
    std::string failure;
    FatLineResult hit;
    if (WorldLine(world, lines[i].start, lines[i].end, lines[i].radius, hit,
                  failure))
      results[i] = hit;
    else
      error = std::move(failure);
  }
}
bool CameraCollision::Query(std::array<FatLine, 10> lines, std::uint32_t,
                            std::array<FatLineResult, 10> &output,
                            std::string &failure) {
  for (std::size_t i = 0; i < 10; ++i)
    if (!WorldLine(world, lines[i].start, lines[i].end, lines[i].radius,
                   output[i], failure))
      return false;
  return true;
}
std::uint32_t Positioner::Update(float dt, std::uint32_t context,
                                 PositionerConfig value,
                                 PositionerCollisionProvider &collision) {
  config = value;
  offset = config.offset;
  if (collision_clear_time < 5)
    offset = Mul(offset, collision_clear_time * Bits(0x3e4ccccd));
  if (config.bypass_distance_tracker != 0) {
    distance_tracker.target = config.distance;
    distance_tracker.position = config.distance;
  } else {
    const float acceleration = distance_tracker.position < Bits(0x3f866666)
                                   ? 100
                                   : config.acceleration_clamp;
    tracker_parameters.acceleration_clamp_min = acceleration;
    tracker_parameters.acceleration_clamp_max = acceleration;
    tracker_parameters.speed_clamp = config.speed_clamp;
    tracker_parameters.smoothing_min = config.smoothing;
    tracker_parameters.smoothing_max = config.smoothing;
    distance_tracker.Update(dt, config.distance, tracker_parameters);
  }
  radius = Bits(0x3e051eb8);
  const auto previous = position;
  const auto result = Resolve(context, collision);
  if (dt > 0)
    velocity = Mul(Sub(position, previous), RefinedReciprocal(dt));
  collision_clear_time = (flags & 0xc0) != 0 ? 0 : collision_clear_time + dt;
  return result;
}
Vec4 Positioner::PositionAt(float e, float h, float d) const {
  return PositionFromAngles(config.anchor, offset, e, h, d, config.clamp_height,
                            radius + config.floor_height);
}
std::uint32_t Positioner::Resolve(std::uint32_t context,
                                  PositionerCollisionProvider &collision) {
  available_distance = config.distance;
  flags = (flags & 0xc1) | 0x0c;
  heading = config.heading;
  elevation = config.elevation;
  distance = distance_tracker.position;
  position = PositionAt(elevation, heading, distance);
  const auto result = ResolveCollision(context, collision);
  if (result == 1 || result == 2) {
    const float d = Length(Sub(position, config.anchor));
    distance_tracker.target = d;
    distance_tracker.position = d;
    distance_tracker.velocity = 0;
    distance_tracker.acceleration = 0;
    distance = d;
  }
  if (result == 3) {
    position = previous_valid_position;
    flags &= std::uint8_t(~8);
  } else {
    previous_valid_position = position;
    flags = (flags & std::uint8_t(~0x20)) | (result == 2 ? 0x20 : 0);
  }
  flags = (flags & 0x3f) | (result != 0 ? 0x80 : 0);
  return result;
}
void Positioner::SubmitCollision(std::uint32_t context,
                                 PositionerCollisionProvider &collision) {
  reference_position = PositionAt(config.reference_elevation,
                                  config.reference_heading, config.distance);
  std::array<FatLine, 6> lines;
  for (std::size_t i = 0; i < 6; ++i)
    lines[i] = {config.query_starts[i % 3],
                i < 3 ? position : reference_position, radius};
  collision.Submit(lines, context);
}
std::uint32_t
Positioner::ResolveCollision(std::uint32_t context,
                             PositionerCollisionProvider &collision) {
  SubmitCollision(context, collision);
  const auto results = collision.Results();
  if (config.collision_enabled != 0) {
    flags |= 2;
    available_distance = 0;
    for (std::size_t i = 3; i < 6; ++i) {
      if (results[i].hit != 0) {
        const auto point =
            ProjectHit(reference_position, config.query_starts[0], results[i]);
        const float d = Length(Sub(point, config.anchor));
        if (!(available_distance - d >= 0))
          available_distance = d;
      } else {
        available_distance = config.distance;
        flags &= std::uint8_t(~2);
      }
    }
    if (results[0].hit != 0 && results[1].hit != 0 && results[2].hit != 0) {
      position = ProjectHit(position, config.query_starts[0], results[0]);
      return Length(Sub(position, config.query_starts[0])) <
                     radius + config.minimum_distance
                 ? 2
                 : 1;
    }
  }
  return 0;
}
float CandidateCollisionTime(PredictionPath path, const PathObstacle *obstacles,
                             std::size_t count) {
  float result = std::numeric_limits<float>::max();
  for (std::size_t i = 0; i < count; ++i) {
    const auto &obstacle = obstacles[i];
    const auto separation = Sub(obstacle.position, path.position),
               velocity = Sub(obstacle.velocity, path.velocity);
    const float radius = obstacle.radius + path.radius,
                clearance = Dot3(separation, separation) - radius * radius;
    float time;
    if (clearance < 0)
      time = 0;
    else {
      const float approach = Dot3(separation, velocity);
      if (!(approach < 0))
        continue;
      const float square = Dot3(velocity, velocity);
      time = (-1 / square) * approach;
      if (!(std::fma(approach, time, clearance) < 0))
        continue;
    }
    if (time < path.horizon && time < result)
      result = time;
  }
  return result;
}
void PathEvaluator::UpdateRequest(std::uint32_t context,
                                  TrajectoryCollisionRequest &request) {
  if (request_state == 0) {
    request.Submit(path, context, acceleration_flag);
    submitted_acceleration_flag = acceleration_flag;
    request_state = 1;
    pending_polls = 0;
  } else if (request_state == 1) {
    if (request.IsReady()) {
      float result = request.CollisionTime();
      if (result < 0)
        result = std::numeric_limits<float>::max();
      found = 1;
      request_state = 0;
      result_acceleration_flag = submitted_acceleration_flag;
      if (collision_time - result >= 0)
        collision_time = result;
    } else {
      std::uint32_t bits;
      std::memcpy(&bits, &pending_polls, 4);
      ++bits;
      std::memcpy(&pending_polls, &bits, 4);
      if (pending_polls > 3) {
        request_state = 0;
        last_valid_time = std::numeric_limits<float>::max();
      }
    }
  }
}
bool PathEvaluator::Update(std::uint32_t context,
                           TrajectoryCollisionRequest &request,
                           MovingObstacleProvider &moving, std::string &error) {
  found = 0;
  collision_time = std::numeric_limits<float>::max();
  UpdateRequest(context, request);
  std::array<PathObstacle, 50> obstacles{};
  const auto count =
      moving.Collect(path.position, path.velocity, path.radius, obstacles);
  if (count > 50) {
    error = "native moving-sphere capacity exceeded";
    return false;
  }
  const float time = CandidateCollisionTime(path, obstacles.data(), count);
  if (time < path.horizon) {
    found = 1;
    if (collision_time - time >= 0)
      collision_time = time;
  }
  if (found != 0)
    last_valid_time = collision_time;
  return true;
}
Vec4 TrajectoryQuery::Evaluate(float time) const {
  const float square = time * time;
  return Madd(Mul(gravity, 0.5f), square, Madd(velocity, time, position));
}
float TrajectoryQuery::StepSize(float error_radius) const {
  const float square = RefinedReciprocal(gravity[1]) * (-8 * error_radius);
  return square == 0 ? 0 : square * InverseLengthSquared(square);
}
float TrajectoryQuery::TimeAtContact(Vec4 contact, float time) const {
  const float frame = Bits(0x3c888889), epsilon = Bits(0x38d1b717);
  if (epsilon >= std::abs(RefinedReciprocal(2) * gravity[1])) {
    const float distance = Length(Sub(contact, position));
    if (!(std::abs(distance) > epsilon))
      return 0;
    const float speed = Length(velocity);
    if (!(std::abs(speed) > epsilon))
      return 0;
    return (RefinedReciprocal(speed) * distance) * frame;
  }
  float closest = std::numeric_limits<float>::max();
  while (duration >= time) {
    const auto delta = Sub(contact, Evaluate(time));
    const float square = Dot3(delta, delta);
    if (closest >= square)
      closest = square;
    else if (square > closest)
      return time - frame;
    time += frame;
  }
  return duration;
}
bool TrajectoryQuery::CollisionTime(const Line &line, float &result,
                                    std::string &error) const {
  float start_step = duration, end_step = duration;
  if (gravity[1] < 0) {
    start_step = StepSize(start_error * radius);
    end_step = StepSize(end_error * radius);
  }
  // Zero/nonadvancing steps hang the original walk. Reject outside its valid
  // request domain; this guard is not a claimed original failure diagnostic.
  if (duration > 0 &&
      (!(start_step > 0) || !(end_step > 0) || !std::isfinite(duration) ||
       !std::isfinite(start_step) || !std::isfinite(end_step))) {
    error = "Camera trajectory has a nonadvancing step outside the original "
            "valid domain";
    return false;
  }
  const float minimum = ((start_error * radius) * start_error) * radius;
  float time = 0;
  auto start = Evaluate(time), end = Evaluate(time + start_step);
  while (duration > time) {
    const auto delta = Sub(end, start);
    if (Dot3(delta, delta) > minimum) {
      if (std::abs(delta[0]) > Bits(0x37800000) ||
          std::abs(delta[1]) > Bits(0x37800000) ||
          std::abs(delta[2]) > Bits(0x37800000)) {
        std::optional<Vec4> contact;
        if (!line(start, end, radius, contact, error))
          return false;
        if (contact) {
          result = TimeAtContact(*contact, time);
          return true;
        }
      }
      start = end;
    }
    const float fraction = RefinedReciprocal(duration) * time,
                step =
                    std::fma(end_step, fraction, (1 - fraction) * start_step);
    const float next = time + step;
    if (!(next > time)) {
      error = "Camera trajectory has a nonadvancing step outside the original "
              "valid domain";
      return false;
    }
    time = next;
    end = Evaluate(time + step);
  }
  result = -1;
  return true;
}
void CameraTrajectory::Submit(PredictionPath path, std::uint32_t,
                              std::uint8_t flag) {
  result.ready = false;
  result.error.reset();
  const TrajectoryQuery query{path.position,
                              path.velocity,
                              flag != 0 ? gravity : Vec4{},
                              path.horizon,
                              path.radius,
                              1,
                              1};
  std::string error;
  float time;
  if (query.CollisionTime(
          [this](Vec4 start, Vec4 end, float radius, std::optional<Vec4> &hit,
                 std::string &failure) {
            FatLineResult r;
            if (!WorldLine(world, start, end, radius, r, failure))
              return false;
            hit = r.hit != 0 ? std::optional<Vec4>(r.position) : std::nullopt;
            return true;
          },
          time, error)) {
    result.time = time;
    result.ready = true;
  } else
    result.error = std::move(error);
}
void DropPredictor::Reset() {
  horizontal_velocity = {};
  steepest_normal = {};
  has_normal = false;
  elevation = 0;
  distance_offset = 0;
  target_elevation = 0;
  spacing = 0;
  selected = 0;
  pending.reset();
}
Vec4 DropPredictor::PredictionVelocity(bool reset, Mat4 transform,
                                       Vec4 velocity, DropSettings settings) {
  return reset || settings.minimum_test_distance > Length(velocity)
             ? Mul(transform[2], settings.minimum_test_distance)
             : velocity;
}
bool DropPredictor::Update(Vec4 position, Vec4 velocity, bool enabled,
                           bool offboard, std::uint32_t context,
                           DropSettings settings, DropCollisionProvider &query,
                           std::string &error) {
  horizontal_velocity = {velocity[0], 0, velocity[2], 0};
  if (enabled) {
    float span = Length(horizontal_velocity) * settings.total_test_time;
    span = -span >= 0 ? 0 : span;
    span = settings.maximum_test_distance - span >= 0
               ? span
               : settings.maximum_test_distance;
    spacing = span / 5;
    if (pending) {
      auto value = std::move(*pending);
      pending.reset();
      Consume(value.first, value.second, settings.maximum_drop_distance);
    }
    const auto lines = Lines(position, settings.maximum_drop_distance);
    std::array<FatLineResult, 10> results;
    if (!query.Query(lines, context, results, error))
      return false;
    pending = std::make_pair(lines, results);
    float greatest = 0;
    selected = 0;
    for (std::size_t i = 0; i < 5; ++i) {
      if (!probes[i].valid)
        break;
      if (probes[i].depth > greatest) {
        selected = i;
        greatest = probes[i].depth;
      }
    }
  } else {
    selected = 0;
    for (auto &p : probes) {
      p.valid = false;
      p.depth = 0;
    }
  }
  UpdateElevation(enabled, offboard);
  return true;
}
float DropPredictor::DropDepth() const {
  return probes[selected].valid ? probes[selected].depth : 0;
}
std::array<FatLine, 10> DropPredictor::Lines(Vec4 position, float depth) const {
  const auto direction = Normalize(horizontal_velocity);
  std::array<FatLine, 10> lines;
  for (std::size_t index = 0; index < 10; ++index) {
    const auto point =
        Madd(Mul(direction, spacing), float(index / 2 + 1), position);
    lines[index] =
        index % 2 == 0
            ? FatLine{position, point, Bits(0x3c23d70a)}
            : FatLine{point, Sub(point, Mul(Vec4{0, 1, 0, 0}, depth)),
                      Bits(0x3dcccccd)};
  }
  return lines;
}
void DropPredictor::Consume(std::array<FatLine, 10> lines,
                            std::array<FatLineResult, 10> results,
                            float maximum) {
  has_normal = false;
  for (std::size_t i = 0; i < 5; ++i) {
    if (results[2 * i].hit != 0) {
      for (std::size_t j = i; j < 5; ++j) {
        probes[j].valid = false;
        probes[j].depth = 0;
      }
      break;
    }
    const auto line = lines[2 * i + 1];
    const auto result = results[2 * i + 1];
    auto &p = probes[i];
    p = {line.start, line.end, {}, maximum, true, result.hit != 0};
    if (p.hit) {
      p.depth = Length(Sub(result.position, line.start));
      p.end = result.position;
      p.normal = result.normal;
      if (!has_normal ||
          std::abs(steepest_normal[1]) > std::abs(result.normal[1])) {
        steepest_normal = result.normal;
        has_normal = true;
      }
    }
  }
}
void DropPredictor::UpdateElevation(bool enabled, bool offboard) {
  const auto probe = probes[selected];
  float angle = probe.valid
                    ? AtanRatio(probe.depth, float(selected + 1) * spacing)
                    : 0,
        half = Bits(0x3fc90fdb);
  if (angle - half >= 0)
    angle = half;
  const float limit = (offboard ? 40.0f : 70.0f) * Bits(0x3c8efa35);
  if (angle - limit >= 0)
    angle = limit;
  target_elevation = enabled && angle >= Bits(0x3e860a92) ? angle : 0;
  const float delta = std::abs(target_elevation - elevation),
              degrees = delta * Bits(0x42652ee1);
  float step = std::fma(degrees - 7, Bits(0x3d3a2e8c), Bits(0x3dcccccd));
  step = Bits(0x3dcccccd) - step >= 0 ? Bits(0x3dcccccd) : step;
  step = Bits(0x3fcccccd) - step >= 0 ? step : Bits(0x3fcccccd);
  if (degrees > step)
    elevation = elevation >= target_elevation
                    ? -std::fma(step, Bits(0x3c8efa35), -elevation)
                    : std::fma(step, Bits(0x3c8efa35), elevation);
  else
    elevation = target_elevation;
}
} // namespace atelier::skate::camera
