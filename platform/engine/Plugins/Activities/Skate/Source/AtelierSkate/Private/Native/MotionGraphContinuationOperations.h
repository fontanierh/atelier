// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationAirborne.h"
#include "AnimationKickturn.h"
#include "AnimationRidingAuxiliary.h"
#include "Graph.h"
#include "GraphMotionGrindOperations.h"
#include "GraphMotionOffboardTiming.h"
#include "GraphMotionOffboardWipeoutOperations.h"
#include "GraphMotionToggleBoard.h"
#include "GraphMotionTrickLifecycle.h"
#include <variant>

namespace atelier::skate {
struct MotionGraphToggleBoardOperation {};
using MotionGraphContinuationOperation =
    std::variant<std::monostate, GraphMotionAuxiliaryFeedbackOperation,
                 AnimationKickturnOperation, GraphMotionAirborneOperation,
                 GraphMotionOffboardTimingOperation,
                 GraphMotionTrickLifecycleOperation, GraphMotionGrindOperation,
                 GraphMotionOffboardWipeoutOperation,
                 MotionGraphToggleBoardOperation>;
using MotionGraphContinuationInstance = std::variant<
    std::monostate, AnimationFakieHeadState, AnimationKickturnState,
    GraphMotionAirborneInstance, MotionGraphOffboardTimingInstance,
    MotionGraphTrickLifecycleInstance, MotionGraphGrindState,
    MotionGraphOffboardWipeoutInstance, MotionGraphToggleBoardState>;
// Only the unregistered original families are recognized. Every parameter
// parser preserves its original raw versus trimmed name decisions.
bool ParseMotionGraphContinuationOperation(GraphOperationKind,
                                           const GraphAttributes &,
                                           MotionGraphContinuationOperation &,
                                           bool &recognized,
                                           std::string &error);
MotionGraphContinuationInstance
CreateMotionGraphContinuationInstance(const MotionGraphContinuationOperation &);
} // namespace atelier::skate
