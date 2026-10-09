#include "PlantSkeleton.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
bool AdvancePlantSkeleton(PlantSkeletonFrame frame, Vec4 anchor,
                          std::optional<std::size_t> bone, std::string &error) {
  auto &p = frame.processed;
  auto &physical = frame.owners.physical;
  auto &animated = frame.owners.animated;
  const SkeletonInputCollision collision{
      physical.collision_feedback.flags.compliant,
      physical.collision_feedback.flags.has_impulse,
      physical.collision_pose_error,
      physical.skeleton_collision.partial_ragdoll,
      physical.collision_feedback.drive_weight};
  const auto local = bone ? physical.drive_frames[*bone][3]
                          : physical.animation_record.centre_of_mass;
  UpdatePlantRoots(physical.roots, physical.riding.reckoning_frames.system,
                   anchor, local);
  animated.motion.trajectory = SkeletonIdentity;
  animated.motion.inverse_trajectory = SkeletonIdentity;
  const auto &local_board =
      bone ? physical.animation_record.pose[0] : physical.drive_frames[0];
  const auto target =
      ComposeSkeletonAffine(physical.roots.animation_to_world, local_board);
  p.flags_2468 |= 1u << 19;
  physical.board_frames.animation_target = target;
  const auto effective = frame.air.ApplyBoard(physical.board, target, true);
  physical.board_frames.physical_board = effective;
  physical.board_frames.skate_root = effective;
  if (!bone) {
    const auto position = physical.board.Bodies()[6].rates.position;
    const auto velocity = BoardAnimationTargetVelocity(
        effective[3], {position.x, position.y, position.z, 0}, p.timestep_2604);
    for (auto &body : physical.board.BodiesMut())
      body.rates.linear_velocity = {velocity[0], velocity[1], velocity[2]};
  }
  physical.board_frames.UpdateComLift(physical.roots.animation_to_world,
                                      physical.board_frames.centre_of_mass, 0);
  std::array<Mat4, 24> actual_drives;
  if (!frame.input.GeneralUpdate(p, frame.owners, frame.actual_globals,
                                 collision, actual_drives, error))
    return false;
  animated.FinishGround();
  frame.owners.animation_input.fields.flags2468 = p.flags_2468;
  error.clear();
  return true;
}
void HoldPlantFoot(PhysicalSimulationRuntime &physical, FootIk &ik, bool right,
                   Vec4 position, std::uint32_t frames) {
  const std::size_t side = right ? 1 : 0;
  ik.state.external_targets[side].world_position = position;
  ik.state.limbs[side].external_target_set = true;
  ik.state.limbs[side].target_blend = 1;
  if (frames != 0)
    for (const auto part : right ? std::array<std::size_t, 3>{19, 20, 21}
                                 : std::array<std::size_t, 3>{15, 16, 17}) {
      physical.skeleton_collision.pending_reenable = true;
      physical.skeleton_collision.disable_count[part] = frames;
      physical.skeleton_collision.parts[part].enabled = false;
    }
}
} // namespace atelier::skate
