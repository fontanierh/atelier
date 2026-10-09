#include "MotionGraphContinuationOperations.h"
namespace atelier::skate {
bool ParseMotionGraphContinuationOperation(
    GraphOperationKind kind, const GraphAttributes &a,
    MotionGraphContinuationOperation &output, bool &recognized,
    std::string &error) {
  recognized = false;
  error.clear();
  output = std::monostate{};
  if (kind != GraphOperationKind::Behavior)
    return true;
  GraphMotionGrindOperation grind;
  if (!ParseGraphMotionGrindOperation(a, grind, recognized, error))
    return false;
  if (recognized) {
    output = std::move(grind);
    return true;
  }
  GraphMotionTrickLifecycleOperation trick;
  if (!ParseGraphMotionTrickLifecycleOperation(a, trick, recognized, error))
    return false;
  if (recognized) {
    output = std::move(trick);
    return true;
  }
  AnimationKickturnOperation kickturn;
  if (!ParseAnimationKickturnOperation(a, kickturn, recognized, error))
    return false;
  if (recognized) {
    output = kickturn;
    return true;
  }
  GraphMotionAirborneOperation airborne;
  if (!ParseGraphMotionAirborneOperation(a, airborne, recognized, error))
    return false;
  if (recognized) {
    output = airborne;
    return true;
  }
  GraphMotionOffboardTimingOperation timing;
  if (!ParseGraphMotionOffboardTimingOperation(a, timing, recognized, error))
    return false;
  if (recognized) {
    output = timing;
    return true;
  }
  GraphMotionAuxiliaryFeedbackOperation auxiliary;
  if (!ParseGraphMotionAuxiliaryFeedbackOperation(a, auxiliary, recognized,
                                                  error))
    return false;
  if (recognized) {
    output = auxiliary;
    return true;
  }
  GraphMotionOffboardWipeoutOperation wipeout;
  if (!ParseGraphMotionOffboardWipeoutOperation(a, wipeout, recognized, error))
    return false;
  if (recognized) {
    output = std::move(wipeout);
    return true;
  }
  if (!ParseGraphMotionToggleBoard(a, recognized, error))
    return false;
  if (recognized)
    output = MotionGraphToggleBoardOperation{};
  return true;
}
MotionGraphContinuationInstance CreateMotionGraphContinuationInstance(
    const MotionGraphContinuationOperation &op) {
  if (std::holds_alternative<GraphMotionAuxiliaryFeedbackOperation>(op))
    return AnimationFakieHeadState{};
  if (std::holds_alternative<AnimationKickturnOperation>(op))
    return AnimationKickturnState{};
  if (const auto *p = std::get_if<GraphMotionAirborneOperation>(&op))
    return CreateGraphMotionAirborneInstance(*p);
  if (const auto *p = std::get_if<GraphMotionOffboardTimingOperation>(&op))
    return CreateMotionGraphOffboardTimingInstance(*p);
  if (const auto *p = std::get_if<GraphMotionTrickLifecycleOperation>(&op))
    return CreateMotionGraphTrickLifecycleInstance(*p);
  if (std::holds_alternative<GraphMotionGrindOperation>(op))
    return MotionGraphGrindState{};
  if (const auto *p = std::get_if<GraphMotionOffboardWipeoutOperation>(&op))
    return CreateMotionGraphOffboardWipeoutInstance(*p);
  if (std::holds_alternative<MotionGraphToggleBoardOperation>(op))
    return MotionGraphToggleBoardState{};
  return std::monostate{};
}
} // namespace atelier::skate
