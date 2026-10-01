// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GraphMotionFeedbackOperations.h"
#include "GraphMotionPushOperations.h"
#include "GraphMotionSliding.h"
#include "MotionGraphContinuationOperations.h"
namespace atelier::skate {
struct MotionGraphContinuationSettings {
  GraphMotionPushSettings pushing;
  MotionGraphGrindSettings grind;
  MotionGraphWipeoutSettings wipeout;
  AnimationBumpSettings bump;
  GraphMotionFeedbackSettings feedback;
  GraphMotionSlidingSettings sliding;
  AnimationAirborneSettings airborne;
  AnimationKickturnSettings kickturn;
  MotionGraphTrickLifecycleSettings tricks;
  // Complete MotionHost::from_graph order: pushing, grind, wipeout, bump,
  // turning/crouching/tilt/pump, slide, spin/leg, kickturn, manual, hippy,
  // finger. No optional graph branch changes constructor reads.
  bool Load(const SettingsDatabase &, const AnimationMetadata &,
            std::string &error);
};
} // namespace atelier::skate
