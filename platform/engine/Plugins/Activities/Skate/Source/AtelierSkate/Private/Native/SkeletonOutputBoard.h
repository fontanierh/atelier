// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate {
struct SkeletonBoardOutputSettings {
  float truck_tilt_scalar = 0, truck_tilt_max_angle = 0;
  float truck_tilt_wobble_scalar = 0, truck_displacement_max = 0;
};
struct SkeletonBoardBoneIndices {
  std::size_t front_truck = 0, back_truck = 0;
  std::size_t front_left_wheel = 0, front_right_wheel = 0;
  std::size_t back_left_wheel = 0, back_right_wheel = 0;
  std::array<std::size_t, 6> All() const;
};
struct SkeletonBoardOutputInput {
  const std::array<Mat4, 6> &bodies;
  const Mat4 &skeleton_board;
  const std::array<Mat4, 2> &truck_frames;
  float deck_wobble_tilt, deck_wobble_squish;
  std::array<float, 2> average_compression;
};
// Caller validates bone indices as the original physical-pose worker does.
void PublishSkeletonBoardOutput(SkeletonBoardOutputInput,
                                const SkeletonBoardOutputSettings &,
                                SkeletonBoardBoneIndices,
                                std::vector<Mat4> &locals);
} // namespace atelier::skate
