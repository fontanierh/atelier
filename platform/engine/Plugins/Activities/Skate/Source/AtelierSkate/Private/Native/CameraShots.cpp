// SPDX-License-Identifier: Apache-2.0
#include "CameraShots.h"
#include "CameraWorld.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::camera {
std::string AsciiLower(std::string_view name) {
  std::string result(name);
  for (char &c : result)
    if (c >= 'A' && c <= 'Z')
      c = char(c - 'A' + 'a');
  return result;
}
Shot::Shot()
    : smoothing{Bits(0x3f4ccccd), Bits(0x3f4ccccd), Bits(0x3f4ccccd),
                Bits(0x3f4ccccd)},
      position_heading(Bits(0x40490fdb)) {}
void Shot::UpdateNormal(float north, float heading_mirror) {
  if (use_previous_shot != 0)
    return;
  const float from = position_heading,
              delta = WrapVmx(-position_heading - from),
              heading =
                  WrapVmx(std::fma(delta, (1 - heading_mirror) * 0.5f, from));
  arm_orientation =
      QuaternionFromAngles(position_elevation, WrapVmx(heading + north), 0);
}
Vec4 Shot::ReferencePoint(const std::array<Vec4, 10> &positions, Vec4 direction,
                          Vec4 fallback) const {
  const auto offset = Mul(direction, board_offset);
  Vec4 sum{};
  float weight_sum = 0;
  for (std::size_t i = 0; i < 10; ++i) {
    const float weight = reference_weights[i];
    weight_sum = weight + weight_sum;
    sum = Madd(Add(positions[i], offset), weight, sum);
  }
  return Bits(0x38d1b717) > std::abs(weight_sum)
             ? fallback
             : Mul(sum, RefinedReciprocal(weight_sum));
}
float InterpolateFloat(float from, float to, std::uint32_t style,
                       float fraction) {
  return style == 0   ? std::fma(to - from, SineBlend(fraction), from)
         : style == 1 ? to
                      : from;
}
void Shot::InterpolateFrom(Shot from, Shot to, float fraction) {
  const auto blend = [fraction](float a, float b) {
    return InterpolateFloat(a, b, 0, fraction);
  };
  distance = blend(from.distance, to.distance);
  lens_length = blend(from.lens_length, to.lens_length);
  for (std::size_t i = 0; i < 4; ++i)
    smoothing[i] = blend(from.smoothing[i], to.smoothing[i]);
  for (std::size_t i = 0; i < 10; ++i)
    reference_weights[i] =
        blend(from.reference_weights[i], to.reference_weights[i]);
  board_offset = blend(from.board_offset, to.board_offset);
  position_elevation = blend(from.position_elevation, to.position_elevation);
  for (std::size_t i = 0; i < 3; ++i)
    framing[i] = blend(from.framing[i], to.framing[i]);
  follow_subject_in_air = to.follow_subject_in_air;
  mirror_for_stance = to.mirror_for_stance;
  snap_to_reference_point = to.snap_to_reference_point;
  use_previous_shot = to.use_previous_shot;
  use_drop_predictor = to.use_drop_predictor;
  use_free_camera_stick = to.use_free_camera_stick;
  avoidance_override = to.avoidance_override;
  blur = blend(from.blur, to.blur);
  transition_blur = to.transition_blur;
  subject_opacity = blend(from.subject_opacity, to.subject_opacity);
  collision_hint = to.collision_hint;
  anchor = to.anchor;
  compass_north = to.compass_north;
  world_heading = blend(from.world_heading, to.world_heading);
  arm_orientation =
      Slerp(from.arm_orientation, to.arm_orientation, SineBlend(fraction));
  camera_orientation = Slerp(from.camera_orientation, to.camera_orientation,
                             SineBlend(fraction));
}
float FilterBlendValue(float previous, float raw, float smoothing,
                       float minimum, float maximum) {
  const float response = 1 - smoothing,
              next = std::fma(response * response, raw - previous, previous),
              lower = minimum - next >= 0 ? minimum : next;
  return maximum - lower >= 0 ? lower : maximum;
}
std::optional<BlendIntervalResult> BlendInterval(std::array<float, 3> points,
                                                 std::array<bool, 3> present,
                                                 float value) {
  std::size_t count = 0;
  while (count < 3 && present[count])
    ++count;
  if (count == 0)
    return std::nullopt;
  for (std::size_t i = 0; i < count; ++i)
    if (points[i] > value)
      return i == 0 ? BlendIntervalResult{0, 0, 1}
                    : BlendIntervalResult{i - 1, i,
                                          (value - points[i - 1]) /
                                              (points[i] - points[i - 1])};
  return BlendIntervalResult{count > 1 ? count - 2 : 0, count - 1, 1};
}
bool StockShots::Load(std::string_view name, ShotDefinition &result,
                      std::string &error) const {
  const auto found = definitions.find(AsciiLower(name));
  if (found == definitions.end()) {
    error = "Missing stock camera shot " + std::string(name);
    return false;
  }
  result = found->second;
  return true;
}
bool ShotNode::Setup(const ShotDatabase &database, ShotEnvironment &env,
                     std::vector<std::string> &ancestry, std::size_t &count,
                     std::string &error) {
  if (definition.shot_type != 1)
    return true;
  ancestry.push_back(definition.name);
  for (const auto &name : definition.children) {
    if (!name)
      break;
    for (const auto &parent : ancestry)
      if (AsciiLower(parent) == AsciiLower(*name)) {
        error = "Cyclic stock camera shot " + *name;
        return false;
      }
    ++count;
    if (count > 64) {
      error = "Stock camera shot exceeds its 64-child capacity";
      return false;
    }
    ShotNode child;
    if (!database.Load(*name, child.definition, error) ||
        !child.Setup(database, env, ancestry, count, error))
      return false;
    children.push_back(std::move(child));
  }
  ancestry.pop_back();
  definition.blend_value =
      env.RawBlendValue(definition.blend_type, definition.blend_value, 0);
  return true;
}
bool ShotNode::Update(float dt, ShotEnvironment &env, std::string &error) {
  if (definition.shot_type == 0) {
    auto entry = definition.shot.compass_north;
    if (entry == 6 && env.SpecialCameraFlag())
      entry = 5;
    float north;
    if (!env.CompassNorth(entry, north, error))
      return false;
    definition.shot.UpdateNormal(north, env.HeadingMirror());
    return true;
  }
  if (children.empty())
    return true;
  const float raw =
      env.RawBlendValue(definition.blend_type, definition.blend_value, dt);
  definition.blend_value = FilterBlendValue(
      definition.blend_value, raw, definition.blend_smoothing,
      definition.blend_points[0], definition.blend_points[children.size() - 1]);
  const auto interval = BlendInterval(
      definition.blend_points,
      {children.size() > 0, children.size() > 1, children.size() > 2},
      definition.blend_value);
  if (!interval)
    return true;
  const float fraction =
      Sin(interval->fraction * Bits(0x40490fdb) - Bits(0x3fc90fdb)) * 0.5f +
      0.5f;
  if (!children[interval->left].Update(dt, env, error) ||
      !children[interval->right].Update(dt, env, error))
    return false;
  definition.shot.InterpolateFrom(children[interval->left].definition.shot,
                                  children[interval->right].definition.shot,
                                  fraction);
  return true;
}
void ShotManager::ApplyGraphTransition(float incoming, float outgoing) {
  if (incoming >= 0)
    current.definition.transition_time = incoming;
  else if (transition_override >= 0)
    current.definition.transition_time = transition_override;
  transition_override = outgoing >= 0 ? outgoing : -1;
}
Shot ShotManager::FirstLeaf() const {
  const auto *node = &current;
  while (!node->children.empty())
    node = &node->children.front();
  return node->definition.shot;
}
bool ShotManager::SetShot(std::string_view name, bool force,
                          const ShotDatabase &database, ShotEnvironment &env,
                          ShotPlacement placement, bool &changed,
                          std::string &error) {
  if (!force && AsciiLower(current.definition.name) == AsciiLower(name)) {
    changed = false;
    return true;
  }
  ShotNode next;
  if (!database.Load(name, next.definition, error))
    return false;
  previous = interpolated;
  if (next.definition.shot.use_previous_shot != 0) {
    auto &shot = next.definition.shot;
    shot.distance = interpolated.distance;
    shot.lens_length = interpolated.lens_length;
    shot.position_heading = interpolated.position_heading;
    shot.position_elevation = interpolated.position_elevation;
    shot.framing = interpolated.framing;
    shot.arm_orientation = interpolated.arm_orientation;
  }
  current = std::move(next);
  if (instant_changes)
    MakeInstant();
  else
    elapsed = 0;
  std::vector<std::string> ancestry;
  std::size_t count = 0;
  if (!current.Setup(database, env, ancestry, count, error))
    return false;
  const auto shot = current.definition.shot;
  const auto target = PositionFromAngles(
      placement.anchor, {}, shot.position_elevation, shot.position_heading,
      shot.distance, placement.clamp_height, placement.floor_height);
  transition_distance = Length(Sub(target, placement.camera_position));
  changed = true;
  return true;
}
bool ShotManager::Update(float dt, ShotEnvironment &env, float &fraction,
                         std::string &error) {
  elapsed = dt + elapsed;
  if (!current.Update(dt, env, error))
    return false;
  transition_duration = Duration(false);
  fraction = transition_duration <= 0 ? 1 : elapsed / transition_duration;
  fraction = -fraction >= 0 ? 0 : fraction;
  fraction = 1 - fraction >= 0 ? fraction : 1;
  interpolated.InterpolateFrom(previous, current.definition.shot, fraction);
  return true;
}
void ShotManager::MakeInstant() {
  transition_override = -1;
  elapsed = Duration(false);
}
float ShotManager::Duration(bool camera_man) const {
  const auto &d = current.definition;
  if (d.transition_units == 1)
    return d.transition_time * Bits(0x3c888889);
  if (d.transition_units == 2) {
    const float speed = camera_man && d.transition_time <= 0
                            ? Bits(0x38d1b717)
                            : d.transition_time;
    return transition_distance / speed;
  }
  return d.transition_time;
}
bool ShotManager::IsTransitioning() const { return elapsed < Duration(true); }
float ShotManager::FramingFraction() const {
  const float duration = Duration(true);
  return duration <= 0 ? 1 : SineBlend(Clamp(elapsed / duration, 0, 1));
}
} // namespace atelier::skate::camera
