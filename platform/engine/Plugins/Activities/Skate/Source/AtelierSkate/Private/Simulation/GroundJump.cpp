#include "GroundJump.h"
#include "AirMath.h"
#include "GroundJumpMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
GroundJump CalculateGroundJump(GroundJumpInput i, GroundJumpMode mode,
                               const GroundJumpSettings &s) {
  using namespace ground_jump_math;
  const bool hippy = (i.flags_2480 & 0x1000) != 0;
  if ((i.flags_2468 & 0x400000) == 0 && !hippy)
    return {};
  const auto normal = i.filtered_ground_normal;
  const float y_scalar = s.y_scalar_vs_normal_y.Evaluate(normal[1]);
  const auto current = Planar(i.current_velocity, normal);
  auto prepared = Planar(i.prepared_velocity, normal);
  if (Dot3(Sub(current, prepared), Sub(current, prepared)) > 7) {
    const float agreement =
        VectorClamp(Dot3(Normalize(current), Normalize(prepared)), 0, 1);
    const float fraction =
        Acos(agreement) * RefinedReciprocal(Float(0x40490fdb), 2);
    const float bound =
        Length(prepared) * s.speed_scalar_vs_angle.Evaluate(fraction);
    AirMath math;
    prepared = math.ClampLength(current, bound);
  }
  Vec4 velocity;
  if ((i.flags_2488 & 0x10000000) != 0) {
    velocity = Madd(i.effective_forward, 2.3f, prepared);
    velocity[1] += 1;
  } else {
    const float minimum = hippy ? s.hippy_minimum_height
                          : (i.flags_2484 & 0x800) != 0
                              ? mode.minimum_height_64
                              : mode.minimum_height_68;
    const float speed_fraction =
        Clamp(i.surface_speed / s.speed_response_max_speed, 0, 1);
    const float low = std::fma(
        s.minimum_height_vs_speed.Evaluate(speed_fraction),
        minimum - s.absolute_minimum_height, s.absolute_minimum_height);
    const float high =
        std::fma(s.maximum_height_vs_speed.Evaluate(speed_fraction),
                 (hippy ? s.hippy_maximum_height : mode.maximum_height) -
                     s.absolute_minimum_height,
                 s.absolute_minimum_height);
    const float height =
        std::fma(low, 1 - i.jump_strength, high * i.jump_strength);
    const float current_height =
        Dot3(Sub(i.animation_com_position, i.ground_reference_position),
             i.reference_up);
    const float remaining = Maximum(height - current_height, 0);
    const float square = (remaining * i.gravity_y) * -2;
    const float speed = SquareRoot(square);
    const float angle = Acos(VectorClamp(normal[1], -1, 1));
    const float fraction = Clamp(angle * Float(0x3f22f983), 0, 1);
    const float response =
        Maximum(s.vertical_response.Evaluate(fraction), s.minimum_scalar);
    velocity = Madd(normal, speed * response, prepared);
  }
  const float bonus = Clamp((y_scalar - 1) * velocity[1], 0, s.maximum_y_bonus);
  velocity[1] += bonus;
  const float projected = Dot3(velocity, normal);
  const Vec4 up{0, 1, 0, 0};
  const auto side = Normalize(Cross(up, i.forward));
  const float x = -((i.jump_controls[0] * s.adjust_x_factor) * projected);
  const float z = (i.jump_controls[1] * s.adjust_z_factor) * projected;
  const auto correction = Madd(side, x, Scale(Cross(side, up), z));
  return {Add(velocity, correction), 0, true};
}
} // namespace atelier::skate
