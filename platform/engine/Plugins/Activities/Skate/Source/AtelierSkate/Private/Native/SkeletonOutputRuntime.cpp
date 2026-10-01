// SPDX-License-Identifier: Apache-2.0
#include "SkeletonOutputRuntime.h"
#include "StockSettingsReader.h"
#include "TruckDriveFrames.h"
#include <algorithm>
#include <cmath>
#pragma clang fp contract(off)
namespace atelier::skate {
namespace {
Mat4 Matrix(const AffineTransform &v) {
  Mat4 out{};
  for (std::size_t axis = 0; axis < 3; ++axis)
    for (std::size_t lane = 0; lane < 3; ++lane)
      out[axis][lane] = v.basis.columns[axis][lane];
  out[3] = {v.translation.x, v.translation.y, v.translation.z, 0};
  return out;
}
bool EqualAscii(std::string_view a, std::string_view b) {
  if (a.size() != b.size())
    return false;
  for (std::size_t i = 0; i < a.size(); ++i) {
    const auto lower = [](unsigned char c) {
      return c >= 'A' && c <= 'Z' ? unsigned(c + ('a' - 'A')) : unsigned(c);
    };
    if (lower(static_cast<unsigned char>(a[i])) !=
        lower(static_cast<unsigned char>(b[i])))
      return false;
  }
  return true;
}
Vec4 Cross(Vec4 a, Vec4 b) {
  return {
      std::fma(-a[2], b[1], a[1] * b[2]), std::fma(-a[0], b[2], a[2] * b[0]),
      std::fma(-a[1], b[0], a[0] * b[1]), std::fma(-a[3], b[3], a[3] * b[3])};
}
Vec4 Scale(Vec4 a, float scale) {
  for (auto &v : a)
    v *= scale;
  return a;
}
Vec4 Madd(Vec4 a, float scale, Vec4 b) {
  for (std::size_t lane = 0; lane < 4; ++lane)
    b[lane] = std::fma(a[lane], scale, b[lane]);
  return b;
}
} // namespace
bool SkeletonPhysicalPoseOutput::Publish(
    const std::array<Mat4, 24> &physical_parts, const Mat4 &world_to_animation,
    SkeletonBoardOutputInput board, std::vector<Mat4> &globals,
    std::vector<Mat4> &locals, std::string &error) const {
  const auto indices = board_bones.All();
  if (globals.size() != locals.size() ||
      std::any_of(bone_indices.begin(), bone_indices.end(),
                  [&](std::size_t i) { return i >= globals.size(); }) ||
      std::any_of(indices.begin(), indices.end(),
                  [&](std::size_t i) { return i >= locals.size(); })) {
    error = "physical pose output does not match the stock animation hierarchy";
    return false;
  }
  for (std::size_t part = 0; part < 24; ++part) {
    const auto world = ComposeSkeletonAffine(
        physical_parts[part], geometry.inverse_part_frames[part]);
    globals[bone_indices[part]] =
        ComposeSkeletonAffine(world_to_animation, world);
  }
  for (std::size_t part = 24; part-- > 0;) {
    const auto bone = bone_indices[part];
    if (const auto parent = geometry.parents[part])
      locals[bone] = ComposeSkeletonAffine(
          InverseSkeletonRigid(globals[bone_indices[*parent]]), globals[bone]);
    else
      locals[bone] = globals[bone];
  }
  PublishSkeletonBoardOutput(board, board_settings, board_bones, locals);
  error.clear();
  return true;
}
std::optional<SkeletonOutputRuntime> SkeletonOutputRuntime::Load(
    const SettingsDatabase &data, const AnimationRig &animation,
    const AnimatedSkeleton &skeleton, std::string &error) {
  SkeletonOutputRuntime out;
  std::array<std::optional<std::size_t>, 24> parents{};
  const auto &indices = skeleton.settings.bone_indices;
  for (std::size_t part = 0; part < 24; ++part) {
    const auto bone = indices[part];
    if (bone >= animation.bones.size()) {
      error = "Missing output bone ancestor";
      return std::nullopt;
    }
    auto ancestor = animation.bones[bone].parent;
    std::size_t visited = 0;
    while (ancestor >= 0) {
      const auto index = std::size_t(ancestor);
      if (index >= animation.bones.size() ||
          visited >= animation.bones.size()) {
        error = "Invalid physical output hierarchy";
        return std::nullopt;
      }
      const auto found = std::find(indices.begin(), indices.end(), index);
      if (found != indices.end()) {
        parents[part] = std::size_t(found - indices.begin());
        break;
      }
      ancestor = animation.bones[index].parent;
      ++visited;
    }
  }
  const auto bone = [&](std::string_view name, std::size_t &result) -> bool {
    for (std::size_t n = 0; n < animation.bones.size(); ++n)
      if (EqualAscii(animation.bones[n].name, name)) {
        result = n;
        return true;
      }
    error = "Missing stock output bone " + std::string(name);
    return false;
  };
  auto &board = out.pose.board_bones;
  if (!bone("Truck_Front", board.front_truck) ||
      !bone("Truck_Back", board.back_truck) ||
      !bone("Left_WheelFront", board.front_left_wheel) ||
      !bone("Right_WheelFront", board.front_right_wheel) ||
      !bone("Left_WheelBack", board.back_left_wheel) ||
      !bone("Right_WheelBack", board.back_right_wheel))
    return std::nullopt;
  out.pose.bone_indices = indices;
  const auto geometry = foot_ik::Geometry::Create(
      parents, skeleton.settings.physics_frames, error);
  if (!geometry)
    return std::nullopt;
  out.pose.geometry = *geometry;
  StockSettingsReader reader(data);
  auto &settings = out.pose.board_settings;
  if (!reader.Float("physics_skeleton", "default", "TruckTiltScalar",
                    settings.truck_tilt_scalar, error) ||
      !reader.Float("physics_skeleton", "default", "TruckTiltMaxAngle",
                    settings.truck_tilt_max_angle, error) ||
      !reader.Float("physics_skeleton", "default", "TruckTiltWobbleScalar",
                    settings.truck_tilt_wobble_scalar, error) ||
      !reader.Float("physics_skeleton", "default", "TruckDisplacementMax",
                    settings.truck_displacement_max, error) ||
      !reader.Float("physicstrucks", "default", "TruckYPos",
                    out.compression_rest_height, error))
    return std::nullopt;
  const auto wobble = SkeletonWobbleSettings::Load(data, error);
  if (!wobble)
    return std::nullopt;
  out.wobble_settings = *wobble;
  return out;
}
void SkeletonOutputRuntime::TriggerWobble(SkeletonWobble &wobble, bool landing,
                                          bool reverse) const {
  wobble.Trigger(landing, reverse);
}
std::array<float, 2> AverageSkeletonWheelCompressions(
    const Mat4 &deck, const std::array<Vec4, 4> &positions, float rest_height) {
  const auto c0 = Cross(deck[1], deck[2]), c1 = Cross(deck[2], deck[0]),
             c2 = Cross(deck[0], deck[1]);
  const float determinant = Dot3(deck[0], c0);
  float inverse = ReciprocalEstimate(determinant);
  for (unsigned n = 0; n < 2; ++n)
    inverse = std::fma(inverse, std::fma(-inverse, determinant, 1.0f), inverse);
  std::array<Vec4, 3> basis;
  for (std::size_t i = 0; i < 3; ++i)
    basis[i] = Scale({c0[i], c1[i], c2[i], c1[i]}, inverse);
  Vec4 neg;
  for (std::size_t i = 0; i < 4; ++i)
    neg[i] = -deck[3][i];
  const auto position =
      Madd(basis[2], neg[2], Madd(basis[1], neg[1], Scale(basis[0], neg[0])));
  std::array<float, 4> heights;
  for (std::size_t i = 0; i < 4; ++i) {
    const auto p = positions[i];
    const auto local = Madd(
        basis[2], p[2], Madd(basis[1], p[1], Madd(basis[0], p[0], position)));
    heights[i] = local[1];
  }
  return {(heights[0] + heights[1]) * 0.5f - rest_height,
          (heights[2] + heights[3]) * 0.5f - rest_height};
}
std::array<float, 2>
SkeletonOutputRuntime::AverageCompressions(const BoardRuntime &board) const {
  const auto deck = Matrix(board.BodyTransform(BoardBodyId::Deck));
  std::array<Vec4, 4> positions;
  for (std::size_t wheel = 0; wheel < 4; ++wheel)
    positions[wheel] = Matrix(board.BodyTransform(BoardBodyId(wheel)))[3];
  return AverageSkeletonWheelCompressions(deck, positions,
                                          compression_rest_height);
}
Mat4 SkeletonOutputRuntime::AdvanceWobble(SkeletonWobble &wobble,
                                          SkeletonBody &physical,
                                          const Mat4 &deck) {
  deck_wobble = wobble.Update(wobble_settings);
  if (deck_wobble.sampled) {
    ApplySkeletonWobble(deck_wobble, physical.record.pose[0]);
    return physical.record.pose[0];
  }
  return deck;
}
bool SkeletonOutputRuntime::Publish(
    const AnimatedSkeleton &skeleton, const SkeletonRootFrames &roots,
    const SkeletonBody &physical, const BoardRuntime &board,
    std::array<AffineTransform, 2> base_trucks,
    std::array<float, 2> current_targets,
    std::array<float, 2> average_compression, std::vector<Mat4> &globals,
    std::vector<Mat4> &locals, std::string &error) const {
  (void)skeleton;
  std::array<Mat4, 6> bodies;
  for (std::size_t n = 0; n < 6; ++n)
    bodies[n] = Matrix(board.BodyTransform(BoardBodyId(n)));
  const auto frames = SteeringTruckTransforms(base_trucks, current_targets);
  const std::array<Mat4, 2> trucks{Matrix(frames[0]), Matrix(frames[1])};
  std::array<Mat4, 24> parts;
  std::copy_n(physical.record.pose.begin(), 24, parts.begin());
  return pose.Publish(parts, roots.world_to_animation,
                      {bodies, parts[0], trucks, deck_wobble.tilt,
                       deck_wobble.squish, average_compression},
                      globals, locals, error);
}
} // namespace atelier::skate
