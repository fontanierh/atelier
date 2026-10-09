#include "SkeletonOutputBoard.h"
#include "RidingAngles.h"
#include <cmath>
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate {
namespace {
float Bits(std::uint32_t word) {
  float value;
  std::memcpy(&value, &word, 4);
  return value;
}
Vec4 InverseDirection(const Mat4 &frame, Vec4 value) {
  Vec4 out{};
  for (std::size_t lane = 0; lane < 3; ++lane) {
    const float x = value[0] * frame[lane][0];
    const float y = std::fma(value[1], frame[lane][1], x);
    out[lane] = std::fma(value[2], frame[lane][2], y);
  }
  return out;
}
Vec4 NormalizeSafe(Vec4 value) {
  const float squared = Dot3(value, value);
  const float inverse = InverseLengthSquared(squared, 2);
  const float length = squared == 0.0f ? 0.0f : squared * inverse;
  if (length > Bits(0x358637bd)) {
    for (auto &v : value)
      v *= inverse;
    return value;
  }
  return {};
}
Vec4 Subtract(Vec4 a, Vec4 b) {
  Vec4 out;
  for (std::size_t lane = 0; lane < 4; ++lane)
    out[lane] = a[lane] - b[lane];
  return out;
}
float Angle(Vec4 a, Vec4 b, Vec4 axis) {
  return RidingSignedAngle({a[0], a[1], a[2]}, {b[0], b[1], b[2]},
                           {axis[0], axis[1], axis[2]});
}
float Clamp(float value, float minimum, float maximum) {
  const float low = minimum - value >= 0.0f ? minimum : value;
  return maximum - low >= 0.0f ? low : maximum;
}
Mat4 RotationX(float angle) {
  const auto [sine, cosine] = SinCos(angle);
  return {{{1, 0, 0, 1},
           {0, cosine, sine, 0},
           {0, -sine, cosine, 0},
           {0, 0, 0, 0}}};
}
} // namespace
std::array<std::size_t, 6> SkeletonBoardBoneIndices::All() const {
  return {front_truck,       back_truck,      front_left_wheel,
          front_right_wheel, back_left_wheel, back_right_wheel};
}
void PublishSkeletonBoardOutput(SkeletonBoardOutputInput input,
                                const SkeletonBoardOutputSettings &s,
                                SkeletonBoardBoneIndices bones,
                                std::vector<Mat4> &locals) {
  const Vec4 y{0, 1, 0, 0}, z{0, 0, 1, 0};
  std::array<Mat4, 4> wheels;
  for (std::size_t wheel = 0; wheel < 4; ++wheel) {
    const auto up =
        InverseDirection(input.bodies[4 + wheel / 2], input.bodies[wheel][1]);
    wheels[wheel] = RotationX(Angle(up, y, z));
  }
  auto front = InverseDirection(
      input.skeleton_board,
      NormalizeSafe(Subtract(input.bodies[0][3], input.bodies[1][3])));
  auto back = InverseDirection(
      input.skeleton_board,
      NormalizeSafe(Subtract(input.bodies[3][3], input.bodies[2][3])));
  if (0.5f > Dot3(front, front))
    front = input.truck_frames[0][2];
  if (0.5f > Dot3(back, back))
    for (std::size_t lane = 0; lane < 4; ++lane)
      back[lane] = -input.truck_frames[1][2][lane];
  const Vec4 negative_x{-1, -0.0f, -0.0f, -0.0f};
  const float back_angle = RidingFractionWrappedAngle(
      Angle(back, negative_x, input.truck_frames[1][0]));
  const float front_angle = RidingFractionWrappedAngle(
      Angle(front, negative_x, input.truck_frames[0][0]));
  const float wobble = input.deck_wobble_tilt * s.truck_tilt_wobble_scalar;
  const float back_tilt =
      Clamp(std::fma(-s.truck_tilt_scalar, back_angle, -wobble),
            -s.truck_tilt_max_angle, s.truck_tilt_max_angle);
  const float front_tilt =
      Clamp(std::fma(-s.truck_tilt_scalar, front_angle, wobble),
            -s.truck_tilt_max_angle, s.truck_tilt_max_angle);
  const std::array<std::size_t, 2> truck_bones{bones.front_truck,
                                               bones.back_truck};
  const std::array<float, 2> tilts{front_tilt, back_tilt};
  for (std::size_t side = 0; side < 2; ++side) {
    const float compression = input.average_compression[side] < Bits(0x3a83126f)
                                  ? 0.0f
                                  : input.average_compression[side];
    const float displacement = Clamp(compression - input.deck_wobble_squish, 0,
                                     s.truck_displacement_max);
    const auto bone = truck_bones[side];
    const auto rotated =
        ComposeSkeletonAffine(locals[bone], RotationX(tilts[side]));
    Mat4 translation = SkeletonIdentity;
    translation[3] = {0, displacement, 0, 0};
    locals[bone] = ComposeSkeletonAffine(translation, rotated);
  }
  const std::array<std::size_t, 4> wheel_bones{
      bones.front_left_wheel, bones.front_right_wheel, bones.back_left_wheel,
      bones.back_right_wheel};
  for (std::size_t wheel = 0; wheel < 4; ++wheel) {
    const auto bone = wheel_bones[wheel];
    locals[bone] = ComposeSkeletonAffine(locals[bone], wheels[wheel]);
  }
}
} // namespace atelier::skate
