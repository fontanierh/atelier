#include "GroundAnimationRuntime.h"
#include "AirMath.h"
#include "GroundJumpMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
Vec4 Decode(const RawVector &words) {
  Vec4 result;
  std::memcpy(result.data(), words.data(), sizeof(result));
  return result;
}
Vec3 Xyz(Vec4 v) { return {v[0], v[1], v[2]}; }
} // namespace
void GroundAnimationRuntime::Fill(const ProcessedPhysicsInput &p,
                                  AirOutputFields &out) const {
  if ((p.flags_2468 & 0x400000) != 0) {
    const auto current = Decode(p.vectors_400_416[0]);
    for (std::size_t i = 0; i < 4; ++i) {
      const float value = jump.velocity[i] - current[i];
      std::memcpy(&out.jump_velocity_delta_112[i], &value, 4);
    }
  }
  if (launched) {
    out.launched_442 = 1;
    std::memcpy(out.launch_velocity_128.data(), launch_velocity.data(),
                sizeof(launch_velocity));
  }
}
bool GroundAnimationRuntime::Enter(GroundAnimationOwners o,
                                   std::string &error) {
  launched = false;
  launch_velocity = {};
  o.life.skeleton_elapsed_16505 = true;
  o.physical.board.HookMut().drive.EnableAngularOnly(o.life.board_animated_290);
  if (o.wipeout.mode != 1) {
    o.wipeout.mode = 1;
    o.wipeout.balance = 0;
  }
  error.clear();
  return true;
}
bool GroundAnimationRuntime::Advance(GroundAnimationOwners o,
                                     const GroundSettings &settings,
                                     const GroundAnimationSettings &animation,
                                     std::string &error) {
  launched = false;
  const auto &p = o.processed;
  auto &r = o.physical.riding;
  const auto heading = r.reckoning_frames.heading;
  const PhysicalRidingPose pose{Xyz(Decode(p.animation_com_to_deck_752)),
                                o.animation_input.extra.physical_body_spin};
  PhysicalGroundPacket packet{Xyz(Decode(p.vectors_464_480_496_512_528[0])),
                              Xyz(Decode(p.vectors_464_480_496_512_528[4])),
                              p.scalar_2652, p.scalar_2616, 0};
  std::memcpy(&packet.wheel_count, &p.wheel_count_2556, 4);
  r.UpdateGroundReckoning(o.physical.board, pose, p.flags_2468,
                          o.animation_input.fields.balance,
                          (p.flags_2476 & 0x40000000) != 0, packet, heading);
  if (!AdvanceSkeleton(o, error))
    return false;
  o.physical.correction.pending = true;
  return AdvanceBoard(o, settings, animation, error);
}
void GroundAnimationRuntime::Exit(GroundAnimationOwners o) {
  auto &physical = o.physical;
  SetGroundAnimationDrag(physical.board, 0);
  physical.settings.board.collision.wheel_material =
      physical.settings.board.standard_wheel_material;
  if (jump.active) {
    auto reference = jump.velocity;
    reference[1] = std::fma(o.processed.gravity_2648, o.processed.timestep_2604,
                            reference[1]);
    const auto velocity =
        ClampAirJumpVelocity(reference, Decode(o.processed.vectors_400_416[0]));
    o.ground_runtime.SetAnimatedVelocity(physical.board, velocity);
  }
  jump = {};
}
} // namespace atelier::skate
