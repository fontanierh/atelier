#include "FootplantRuntime.h"
#include "PlantMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
bool FootplantRuntime::Load(const SettingsDatabase &data, std::string &error) {
  FootplantRuntime next;
  if (!next.settings.Load(data, error))
    return false;
  next.Reset();
  *this = std::move(next);
  error.clear();
  return true;
}
void FootplantRuntime::Reset() {
  contact_time = -1;
  scalar_596 = -1;
  selected_toe.reset();
  scalar_600 = 0;
  target_blend = 0;
  active_elapsed = 0;
  scalar_612 = 0;
  candidate = false;
  hit = false;
  perform = false;
  flag_627 = false;
  launch_valid = false;
  lock_valid = false;
  contact_active = false;
  requested = false;
  request = AirTrajectory{};
  contact = {};
  adjusted_contact = {};
  vectors_352_368 = {};
  animation_com = {};
  locked_target = {};
  launch_direction = {};
  physical_com = {};
}
void FootplantRuntime::FullReset() {
  enabled = false;
  Reset();
}
void FootplantRuntime::Publish(AirOutputFields &out) const {
  if (hit) {
    out.footplant_contact_time_208 = contact_time;
    out.footplant_duration_212 = scalar_596;
    out.flag_447 = static_cast<std::uint8_t>(perform);
    out.flag_448 = static_cast<std::uint8_t>(perform || flag_627);
    out.footplant_surface_224 = surface;
    out.footplant_left_449 =
        static_cast<std::uint8_t>(flag_627 && selected_toe == 15);
    out.footplant_right_450 =
        static_cast<std::uint8_t>(flag_627 && selected_toe == 19);
    out.footplant_surface_height_216 = contact[1];
  }
}
void FootplantRuntime::ClearContact() {
  surface = 0;
  hit = false;
  contact_time = 0;
  contact = {};
}
void FootplantRuntime::PostPhysics(const ProcessedPhysicsInput &p,
                                   WipeoutRequests &out) const {
  using namespace plant_math;
  Vec4 up, velocity;
  for (std::size_t i = 0; i < 4; ++i) {
    up[i] = Float(p.vectors_544_560_592_608[0][i]);
    velocity[i] = Float(p.vectors_544_560_592_608[3][i]);
  }
  const auto down = Scale(up, -1);
  const float descending = Dot(velocity, down);
  const float horizontal = Length(Sub(velocity, Scale(down, descending)));
  if (descending > settings.max_descending_speed)
    out.Request(6, descending);
  if (horizontal > settings.max_horizontal_speed)
    out.Request(23, 0);
}
} // namespace atelier::skate
