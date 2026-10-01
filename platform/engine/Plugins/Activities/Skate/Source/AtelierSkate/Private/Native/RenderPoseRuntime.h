// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "FootIk.h"
#include "FootPhysicalOutput.h"
#include "PhysicalSimulationRuntime.h"
#include "SkaterAnimation.h"
#include "SkeletonOutputRuntime.h"
#include "Steering.h"
#include "WipeoutRuntime.h"
namespace atelier::skate {
struct RenderPoseOwners {
  PhysicalSimulationRuntime &physical;
  const AnimatedSkeleton &animated;
  const ProcessedPhysicsInput &processed;
  PhysicalPlayerInput &publication;
  FootIk &ik;
  const WipeoutRuntime &wipeout;
  const SkaterAnimation &animation;
  const TruckSteeringState &steering;
  SkeletonWobble &wobble;
  SkeletonOutputRuntime &skeleton_output;
  FootPhysicalOutputs &foot_physical;
  std::vector<Mat4> &render_pose;
  std::uint64_t &pose_generation;
};
// Complete physics/render_pose.rs::publish, in source order. Preceding
// FinishSkater post-state/wipeout/offboard work belongs to the coordinator.
// Correction, wobble, IK and physical publications survive later failures;
// render_pose and generation commit only after complete hierarchy publication.
bool PublishRenderPose(RenderPoseOwners,
                       std::array<float, 2> average_compression,
                       std::string &error);
// Exact original output::compose_hierarchy_in_place, including partial-write
// validation order and forward-parent semantics. Errors are the Rust Debug
// payload, before the caller's source context is added.
bool ComposeRenderHierarchy(std::int32_t bone_count,
                            const std::vector<std::int32_t> &parents,
                            std::int32_t detached_parent,
                            std::vector<Mat4> &matrices, std::string &error);
} // namespace atelier::skate
