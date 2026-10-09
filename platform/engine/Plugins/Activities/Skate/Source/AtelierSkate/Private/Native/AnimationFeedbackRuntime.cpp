#include "AnimationFeedbackRuntime.h"
#include <cstring>
#pragma clang fp contract(off)
namespace atelier::skate {
bool AnimationFeedbackRuntime::Load(const SettingsDatabase &data,
                                    std::string &error) {
  AnimationFeedbackRuntime next{};
  if (!LoadAnimationTurnFeedbackSettings(data, next.settings, error) ||
      !LoadAnimationGroundAccelerationSettings(data, next.bump_settings, error))
    return false;
  *this = next;
  error.clear();
  return true;
}
void AnimationFeedbackRuntime::Reset() {
  state.ResetHistory();
  previous_lateral_tilt = {};
  published_previous_lateral_tilt = {};
}
AnimationPhysicalFeedback AnimationFeedbackRuntime::Update(
    const BoardMotionOutput &motion, const PumpingState &pumping,
    const SpeedWobbleState &wobble, AnimationReckoningFeedback reckoning,
    AnimationControlFeedback controls,
    AnimationGroundAccelerationInput acceleration, Vec4 lateral_tilt) {
  published_previous_lateral_tilt = previous_lateral_tilt;
  previous_lateral_tilt = lateral_tilt;
  float wobble_36;
  std::memcpy(&wobble_36, &wobble.words[5], 4);
  return PublishPhysicalAnimationFeedback(
      state, settings,
      {motion.speed, motion.forward_speed, motion.ground_speed,
       motion.linear_velocity.y},
      {pumping.pumping, pumping.absorption, pumping.ground_normal_absorption,
       pumping.minimum_crouch, pumping.deck_angle_absorption,
       pumping.pump_acceleration},
      wobble_36, reckoning, controls,
      PublishAnimationGroundAcceleration(acceleration, bump_settings));
}
AnimationPhysicalFeedback InitialAnimationPhysicalFeedback() {
  return {
      {0, 0, 0, 0, 0, 0},      {0, 0, 0, 0, 0, 0, 0, 0}, 0, {0, 0, 0, 0}, false,
      {0, 0, 0, 0, 0, 0, 0, 0}};
}
} // namespace atelier::skate
