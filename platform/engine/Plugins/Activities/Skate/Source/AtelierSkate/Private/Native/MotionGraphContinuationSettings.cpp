// SPDX-License-Identifier: Apache-2.0
#include "MotionGraphContinuationSettings.h"
#include "StockSettingsReader.h"
#include <cmath>
#include <cstring>
namespace atelier::skate {
namespace {
float Float(std::uint32_t word) {
  float f;
  std::memcpy(&f, &word, 4);
  return f;
}
template <std::size_t N, std::size_t Prefix>
bool Curve(StockSettingsReader &r, std::string_view c, std::string_view k,
           std::string_view name, PointGraph<N> &out, std::string &error) {
  std::vector<std::uint32_t> words;
  if (!r.Words(c, k, name, Prefix + N * 2, words, error))
    return false;
  for (std::size_t i = 0; i < N; ++i) {
    out.x[i] = Float(words[Prefix + i]);
    out.y[i] = Float(words[Prefix + N + i]);
  }
  return true;
}
} // namespace
bool MotionGraphContinuationSettings::Load(const SettingsDatabase &data,
                                           const AnimationMetadata &metadata,
                                           std::string &error) {
  MotionGraphContinuationSettings next;
  StockSettingsReader r(data);
  // Validate the source-ordered pushing reads through the common original
  // reader. The accepted pushing loader then reuses its complete metadata
  // evaluation and metrics kernels; it cannot observe a missing field first.
  auto &p = next.pushing;
  if (!Curve<8, 4>(r, "anim_motion", "pushing", "button_time_max",
                   p.curves.button_time_max, error) ||
      !Curve<8, 4>(r, "anim_motion", "pushing", "button_time_to_dv",
                   p.curves.button_time_to_dv, error) ||
      !Curve<8, 4>(r, "anim_motion", "pushing", "blend_speed_over_frames",
                   p.curves.blend_speed_over_frames, error) ||
      !Curve<8, 4>(r, "anim_motion", "pushing", "blend_acc_over_frames",
                   p.curves.blend_acc_over_frames, error) ||
      !r.Float("anim_motion", "pushing", "pushing_usemaxpushfromteleporttime",
               p.teleport_window, error) ||
      !r.Float("anim_motion", "pushing", "max_holding_acc",
               p.maximum_holding_acceleration, error) ||
      !r.Float("anim_motion", "pushing", "dynamic_out_factor_speed_vs_acc",
               p.out_speed_weight, error) ||
      !r.Float("anim_motion", "pushing", "last_push_out_time",
               p.maximum_out_factor, error) ||
      !p.Load(data, metadata, error))
    return false;
  auto &g = next.grind;
  if (!r.Float("anim_motion", "grind_twist", "twist_smoothing", g.fade.response,
               error) ||
      !r.Float("anim_motion", "grind_twist", "twist_sensitivity",
               g.fade.input_scale, error) ||
      !r.Float("anim_motion", "grind_twist", "twist_max_delta_delta",
               g.fade.acceleration, error) ||
      !r.Float("anim_motion", "grind_twist", "twist_max_delta",
               g.fade.maximum_step, error) ||
      !r.Float("anim_motion", "grind_height", "min_grind_disttocog",
               g.height[0], error) ||
      !r.Float("anim_motion", "grind_height", "max_grind_disttocog",
               g.height[1], error) ||
      !r.Float("anim_motion", "grind_height", "grind_disttocog_speed",
               g.height[2], error))
    return false;
  auto &w = next.wipeout;
  if (!r.Float("anim_wipeout", "default", "controlled_drives_thresh",
               w.threshold, error) ||
      !r.Float("anim_wipeout", "default", "clamp_twist_vel", w.twist_velocity,
               error) ||
      !r.Float("anim_wipeout", "default", "clamp_twist_acc",
               w.twist_acceleration, error) ||
      !r.Float("anim_wipeout", "default", "clamp_lean_vel", w.lean_velocity,
               error) ||
      !r.Float("anim_wipeout", "default", "blend_twist", w.twist_blend,
               error) ||
      !r.Float("anim_wipeout", "default", "blend_lean", w.lean_blend, error) ||
      !r.Float("anim_wipeout", "default", "blend_gesture_y", w.gesture_y_blend,
               error) ||
      !r.Float("anim_wipeout", "default", "blend_gesture_x", w.gesture_x_blend,
               error))
    return false;
  auto &b = next.bump;
  if (!r.Float("anim_motion", "bumps", "scale_x_acc", b.scale_x_acc, error) ||
      !r.Float("anim_motion", "bumps", "min_bump_mag", b.min_bump_mag, error) ||
      !r.Float("anim_motion", "bumps", "max_bump_mag", b.max_bump_mag, error) ||
      !r.Float("anim_motion", "bumps", "min_bump_blend_value",
               b.min_bump_blend_value, error))
    return false;
  auto &turn = next.feedback.turning;
  const auto carving = [&](std::string_view n, float &v) {
    return r.Float("anim_carving", "default", n, v, error);
  };
  if (!Curve<16, 4>(r, "anim_carving", "default", "quickMagMap",
                    turn.remaps[0].magnitude, error) ||
      !Curve<16, 4>(r, "anim_carving", "default", "quickAngleMap",
                    turn.remaps[0].angle, error) ||
      !carving("quickAngleOffset", turn.remaps[0].angle_offset) ||
      !Curve<16, 4>(r, "anim_carving", "default", "slowMagMap",
                    turn.remaps[1].magnitude, error) ||
      !Curve<16, 4>(r, "anim_carving", "default", "slowAngleMap",
                    turn.remaps[1].angle, error) ||
      !carving("slowAngleOffset", turn.remaps[1].angle_offset) ||
      !Curve<8, 4>(r, "anim_carving", "default", "speed_tuck", turn.speed_tuck,
                   error) ||
      !Curve<8, 4>(r, "anim_carving", "default", "blend_lean_in", turn.blend,
                   error) ||
      !carving("speed_tuck_start", turn.speed_threshold) ||
      !carving("clamp_curr_lean", turn.maximum_delta) ||
      !r.Float("anim_motion", "power_slide", "slide_turn_value",
               turn.override_turn, error))
    return false;
  auto &c = next.feedback.crouching;
  const auto crouch = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "crouching", n, v, error);
  };
  const auto ap = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "auto_pump", n, v, error);
  };
  if (!Curve<8, 4>(r, "anim_motion", "crouching", "crouching_max_height",
                   c.maximum_height, error) ||
      !Curve<8, 0>(r, "anim_motion", "crouching", "absorption_upforce",
                   c.absorption_upforce, error) ||
      !Curve<8, 0>(r, "anim_motion", "crouching", "pump_maxspeed",
                   c.pump_maxspeed, error) ||
      !crouch("crouching_min_height", c.minimum_height) ||
      !crouch("crouch_max_ratio", c.maximum_ratio) ||
      !crouch("crouch_max_delta_delta", c.maximum_delta_delta) ||
      !crouch("crouch_max_delta", c.maximum_delta) ||
      !crouch("crouch_blend_input", c.input_blend) ||
      !crouch("pump_maxspeed_yaxis", c.pump_vertical_speed) ||
      !crouch("MaxCrouchFromDeckAngle", c.maximum_crouch_from_deck) ||
      !crouch("absorption_skateboard_damping", c.skateboard_damping) ||
      !crouch("absorption_maxforce", c.maximum_force) ||
      !crouch("absorption_ground_maxforce", c.maximum_ground_force) ||
      !crouch("absorption_factor", c.absorption_factor))
    return false;
  auto &auto_pump = c.auto_pump;
  if (!Curve<4, 4>(r, "anim_motion", "auto_pump", "auto_pump_max_crouch",
                   auto_pump.maximum_crouch, error) ||
      !ap("auto_pump_sufficient_crouch", auto_pump.sufficient_crouch) ||
      !ap("auto_pump_standing_thresh", auto_pump.standing_threshold) ||
      !ap("auto_pump_rise_speed", auto_pump.rise_speed) ||
      !ap("auto_pump_pump_speed", auto_pump.pump_speed) ||
      !ap("auto_pump_potential_thresh", auto_pump.potential_threshold) ||
      !ap("auto_pump_potential_blend", auto_pump.potential_blend) ||
      !ap("auto_pump_intent_mag_start", auto_pump.intent_magnitude_start) ||
      !ap("auto_pump_intent_angle_region", auto_pump.intent_angle_region) ||
      !ap("auto_pump_crouch_time", auto_pump.crouch_time) ||
      !ap("auto_pump_crouch_speed", auto_pump.crouch_speed))
    return false;
  auto &tilt = next.feedback.body_tilt;
  const auto tf = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "body_tilt", n, v, error);
  };
  if (!Curve<4, 4>(r, "anim_motion", "body_tilt", "body_tilt_bodyspin_factor",
                   tilt.body_spin_factor, error) ||
      !tf("body_tilt_ground_clamp_vel", tilt.ground_velocity) ||
      !tf("body_tilt_ground_clamp_acc", tilt.ground_acceleration) ||
      !tf("body_tilt_air_clamp_vel", tilt.air_velocity) ||
      !tf("body_tilt_air_clamp_acc", tilt.air_acceleration))
    return false;
  auto &pump = next.feedback.pumping;
  const auto pf = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "anim_pump", n, v, error);
  };
  if (!Curve<8, 0>(r, "anim_motion", "anim_pump", "pump_amplify", pump.amplify,
                   error) ||
      !pf("pump_prop_blend", pump.input_blend) ||
      !pf("max_phys_pump", pump.maximum_physics_pump) ||
      !pf("new_pump_thresh", pump.new_pump_threshold) ||
      !pf("pump_blendin", pump.blend_in) ||
      !pf("pump_blendout", pump.blend_out))
    return false;
  auto &slide = next.sliding;
  const auto sf = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "power_slide", n, v, error);
  };
  if (!sf("slide_speed_threshold", slide.speed_threshold) ||
      !sf("well_into_slide_time", slide.well_into_slide) ||
      !Curve<4, 4>(r, "anim_motion", "power_slide", "slide_speed_factor",
                   slide.speed_factor, error) ||
      !Curve<4, 4>(r, "anim_motion", "power_slide", "not_sliding_time_thresh",
                   slide.time_threshold, error) ||
      !Curve<4, 4>(r, "anim_motion", "power_slide", "not_sliding_threshold",
                   slide.threshold, error) ||
      !Curve<8, 4>(r, "anim_motion", "power_slide", "slide_speed_to_lean",
                   slide.speed_to_lean, error) ||
      !Curve<8, 4>(r, "anim_motion", "power_slide", "slide_phys_to_anim_spin",
                   slide.phys_to_anim_spin, error) ||
      !sf("slide_smooth", slide.smooth) ||
      !sf("slide_min_entry", slide.minimum_entry) ||
      !sf("slide_turn_value", slide.turn))
    return false;
  auto &spin = next.airborne.spin;
  const auto bs = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "body_spin", n, v, error);
  };
  const auto ih = [&](std::string_view n, float &v) {
    return r.Float("anim_motion", "inair_disttocog", n, v, error);
  };
  if (!Curve<8, 0>(r, "anim_motion", "body_spin", "spin_map", spin.map,
                   error) ||
      !Curve<8, 0>(r, "animation", "default", "LandingDistanceScalarVsNormalY",
                   spin.landing_distance, error) ||
      !bs("spin_influence_blendout", spin.blend_out) ||
      !bs("spin_influence_blendin", spin.blend_in) ||
      !bs("spin_clamp_influence_deltadelta", spin.maximum_acceleration) ||
      !bs("spin_clamp_influence_delta", spin.maximum_delta) ||
      !ih("preland_final_disttocom", spin.final_height) ||
      !ih("preland_disttocom_vel", spin.height_velocity) ||
      !ih("landingondeck_disttocog", spin.on_deck_height) ||
      !tf("overide_preland_x", spin.prelanding.override_x) ||
      !tf("overide_preland_velY", spin.prelanding.override_velocity_y))
    return false;
  auto &leg = next.airborne.air_leg;
  if (!Curve<4, 4>(r, "anim_motion", "inair_disttocog", "lo_air_arm_extend",
                   leg.arm_extension, error) ||
      !ih("goingup_disttocog_speed", leg.going_up_speed) ||
      !ih("goingdown_disttocog_speed", leg.going_down_speed) ||
      !ih("min_inair_disttocog", leg.minimum_height) ||
      !ih("preland_disttocom_vel", leg.preland_velocity) ||
      !ih("preland_final_disttocom", leg.preland_final_height) ||
      !ih("offboard_preland_disttocom_vel_multiplier",
          leg.offboard_multiplier) ||
      !Curve<8, 4>(r, "anim_motion", "kickturn", "kickturn_spin",
                   next.kickturn.spin, error) ||
      !Curve<8, 4>(r, "anim_motion", "kickturn", "kickturn_balance",
                   next.kickturn.height, error))
    return false;
  auto &t = next.tricks;
  if (!Curve<8, 0>(r, "anim_motion", "manual", "manual_balance",
                   t.manual_balance, error) ||
      !r.Float("anim_motion", "manual", "manual_clamp_vel",
               t.manual_velocity_limit, error) ||
      !r.Float("anim_motion", "manual", "manual_clamp_acc",
               t.manual_acceleration_limit, error) ||
      !Curve<8, 4>(r, "anim_motion", "hippy_flip",
                   "antic_length_to_hippy_height", t.hippy_height, error))
    return false;
  std::vector<std::uint32_t> finger;
  if (!r.Words("anim_motion", "Hash_41DB0C4F82003A15", "Hash_E0C1407B688858AD",
               20, finger, error))
    return false;
  t.finger_minimum = Float(finger[0]);
  t.finger_maximum = Float(finger[2]);
  if (!std::isfinite(t.finger_minimum) || !std::isfinite(t.finger_maximum) ||
      t.finger_minimum > t.finger_maximum) {
    error = "FingerFlipOut has invalid stock timer bounds";
    return false;
  }
  for (std::size_t i = 0; i < 8; ++i) {
    t.finger_curve.x[i] = Float(finger[4 + i]);
    t.finger_curve.y[i] = Float(finger[12 + i]);
  }
  *this = std::move(next);
  error.clear();
  return true;
}
} // namespace atelier::skate
