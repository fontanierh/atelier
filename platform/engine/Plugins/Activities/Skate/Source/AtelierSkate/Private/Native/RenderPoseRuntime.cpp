// SPDX-License-Identifier: Apache-2.0
#include "RenderPoseRuntime.h"
#include <algorithm>
#include <cstring>
namespace atelier::skate {
bool ComposeRenderHierarchy(std::int32_t count,
                            const std::vector<std::int32_t> &parents,
                            std::int32_t detached_parent,
                            std::vector<Mat4> &matrices, std::string &error) {
  const auto n = std::size_t(std::max(count, std::int32_t(0)));
  if (matrices.size() < std::max(n, std::size_t(1))) {
    error = "ShortInput";
    return false;
  }
  // Identical source/destination pointers: ShortOutput cannot follow a valid
  // ShortInput check, exactly as in compose_hierarchy_in_place.
  if (parents.size() < n) {
    error = "ShortParents";
    return false;
  }
  for (std::size_t bone = 0; bone < n; ++bone) {
    const auto parent = parents[bone];
    if (parent != -1 && parent != detached_parent &&
        (parent < 0 || std::size_t(parent) >= matrices.size())) {
      error = "InvalidParent { bone: " + std::to_string(bone) +
              ", parent: " + std::to_string(parent) + " }";
      return false;
    }
  }
  for (std::size_t bone = 0; bone < n; ++bone) {
    const auto parent = parents[bone];
    if (parent != -1 && parent != detached_parent)
      matrices[bone] =
          ConcatenateAffine(matrices[bone], matrices[std::size_t(parent)]);
  }
  error.clear();
  return true;
}
bool PublishRenderPose(RenderPoseOwners o,
                       std::array<float, 2> average_compression,
                       std::string &error) {
  const auto deck = o.physical.DeckFrame();
  const auto &p = o.processed;
  const bool wiping_out = o.wipeout.RequestsWipeout(p);
  Vec4 normal;
  std::memcpy(normal.data(), p.vectors_544_560_592_608[0].data(), 16);
  o.physical.correction.Apply(o.physical.skeleton, normal, wiping_out,
                              p.flags_2468, p.flags_2476);
  const auto board =
      o.skeleton_output.AdvanceWobble(o.wobble, o.physical.skeleton, deck);
  o.ik.PostPhysics(o.physical.skeleton,
                   {p.state_2508, p.category_2512,
                    o.physical.riding.ground.part_contact_count != 0,
                    wiping_out, p.flags_2468, p.flags_2484, p.state_timer_2664,
                    p.player_state_value_2520,
                    o.physical.roots.world_to_animation, board});
  const auto feet = o.foot_physical.Publish(
      o.physical.skeleton.record,
      o.physical.settings.board.step.simulation.time_step);
  auto &physical = o.publication;
  physical.skeleton.flag_597 = std::uint8_t(o.ik.state.contacts.support_failed);
  physical.skeleton.flag_600 = std::uint8_t(feet.within_deck_box[0]);
  physical.skeleton.flag_601 = std::uint8_t(feet.within_deck_box[1]);
  std::memcpy(physical.skeleton.anim_to_world_11920.data(),
              o.physical.roots.animation_to_world.data(), sizeof(Mat4));
  std::memcpy(physical.reckoning.vector_16.data(),
              o.physical.board_frames.com_velocity.data(), 16);
  std::memcpy(physical.reckoning.vector_64.data(),
              o.physical.board_frames.centre_of_mass.data(), 16);
  const auto up = o.physical.riding.reckoning.up;
  const Vec4 up_lanes{up.x, up.y, up.z, 0};
  std::memcpy(physical.reckoning.vector_96.data(), up_lanes.data(), 16);
  std::vector<Mat4> globals;
  if (!o.animation.evaluator->Hierarchy(o.animation.pose, globals, error))
    return false;
  std::vector<Mat4> locals;
  for (const auto &sqt : o.animation.pose)
    locals.push_back(SqtToMatrix(sqt));
  if (!o.skeleton_output.Publish(
          o.animated, o.physical.roots, o.physical.skeleton, o.physical.board,
          o.physical.settings.board.step.base_truck_transforms,
          o.steering.targets, average_compression, globals, locals, error))
    return false;
  std::vector<std::int32_t> parents;
  for (const auto &bone : o.animation.evaluator->frames.rig.bones)
    parents.push_back(bone.parent);
  if (!ComposeRenderHierarchy(std::int32_t(locals.size()), parents, 0, locals,
                              error)) {
    error = "Physical render hierarchy: " + error;
    return false;
  }
  o.render_pose = std::move(locals);
  ++o.pose_generation;
  error.clear();
  return true;
}
} // namespace atelier::skate
