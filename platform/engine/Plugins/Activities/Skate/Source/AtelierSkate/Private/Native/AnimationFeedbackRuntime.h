#pragma once
#include "BoardMotionOutput.h"
#include "Pumping.h"
#include "RidingAnimation.h"
#include "SpeedWobble.h"
namespace atelier::skate {
// The sole host animation_feedback.rs conditioner. Completed physical feedback
// remains the coordinator's separate stored publication, as in the source.
class AnimationFeedbackRuntime {
public:
  TurnConditionerSettings settings;
  AnimationGroundAccelerationSettings bump_settings;
  TurnConditionerState state;
  Vec4 previous_lateral_tilt{}, published_previous_lateral_tilt{};
  bool Load(const SettingsDatabase &, std::string &error);
  void Reset();
  AnimationPhysicalFeedback
  Update(const BoardMotionOutput &, const PumpingState &,
         const SpeedWobbleState &, AnimationReckoningFeedback,
         AnimationControlFeedback, AnimationGroundAccelerationInput,
         Vec4 lateral_tilt);
};
// Exact initial_feedback() constructor publication. Per-frame absence has no
// corresponding fallback; AdvanceAnimationPhase requires actual owner records.
AnimationPhysicalFeedback InitialAnimationPhysicalFeedback();
} // namespace atelier::skate
