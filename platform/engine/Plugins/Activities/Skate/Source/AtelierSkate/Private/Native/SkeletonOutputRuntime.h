#pragma once
#include "AnimatedSkeleton.h"
#include "BoardRuntime.h"
#include "FootIkTypes.h"
#include "SkeletonBody.h"
#include "SkeletonOutputBoard.h"
#include "SkeletonWobble.h"
namespace atelier::skate {
struct SkeletonPhysicalPoseOutput {
  std::array<std::size_t, 24> bone_indices{};
  foot_ik::Geometry geometry;
  SkeletonBoardBoneIndices board_bones;
  SkeletonBoardOutputSettings board_settings;
  bool Publish(const std::array<Mat4, 24> &physical_parts,
               const Mat4 &world_to_animation, SkeletonBoardOutputInput,
               std::vector<Mat4> &globals, std::vector<Mat4> &locals,
               std::string &error) const;
};
class SkeletonOutputRuntime {
public:
  SkeletonPhysicalPoseOutput pose;
  SkeletonWobbleSettings wobble_settings;
  SkeletonWobbleOutput deck_wobble;
  float compression_rest_height = 0;
  static std::optional<SkeletonOutputRuntime> Load(const SettingsDatabase &,
                                                   const AnimationRig &,
                                                   const AnimatedSkeleton &,
                                                   std::string &error);
  // The coordinator passes the same sole wobble used by ground and teleport.
  void TriggerWobble(SkeletonWobble &wobble, bool landing, bool reverse) const;
  std::array<float, 2> AverageCompressions(const BoardRuntime &) const;
  Mat4 AdvanceWobble(SkeletonWobble &, SkeletonBody &, const Mat4 &deck);
  bool Publish(const AnimatedSkeleton &, const SkeletonRootFrames &,
               const SkeletonBody &, const BoardRuntime &,
               std::array<AffineTransform, 2> base_trucks,
               std::array<float, 2> current_targets,
               std::array<float, 2> average_compression,
               std::vector<Mat4> &globals, std::vector<Mat4> &locals,
               std::string &error) const;
};
// Full original contact_feedback::average_wheel_compressions arithmetic over
// live mass-frame observations; all four stored lanes participate unchanged.
std::array<float, 2>
AverageSkeletonWheelCompressions(const Mat4 &deck,
                                 const std::array<Vec4, 4> &wheel_positions,
                                 float rest_height);
} // namespace atelier::skate
