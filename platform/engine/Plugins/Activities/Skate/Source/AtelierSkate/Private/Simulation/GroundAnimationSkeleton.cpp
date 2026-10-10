#include "GroundAnimationRuntime.h"
namespace atelier::skate {
bool GroundAnimationRuntime::AdvanceSkeleton(GroundAnimationOwners o,
                                             std::string &error) {
  const auto &f = o.physical;
  const SkeletonInputCollision collision{
      f.collision_feedback.flags.compliant,
      f.collision_feedback.flags.has_impulse, f.collision_pose_error,
      f.skeleton_collision.partial_ragdoll, f.collision_feedback.drive_weight};
  Mat4 target;
  return UpdateAnimatedSkeletonAir(
      o.skeleton_input, o.skeleton_air, f.riding.reckoning_frames.system,
      o.processed, o.SkeletonOwners(), o.packet.hierarchy, collision, true,
      target, error);
}
} // namespace atelier::skate
