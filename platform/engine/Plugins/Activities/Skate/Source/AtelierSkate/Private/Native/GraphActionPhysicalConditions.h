// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "MotionFrame.h"
namespace atelier::skate {
// This record must be embedded once in the SAME ActionIntentGraphHost when
// registration lands. The phase borrows it; it owns no shadow publication.
struct GraphActionPhysicalInputs {
  std::optional<MotionGraphGameplayInputs> gameplay_conditions;
  std::optional<bool> dropping_in;
};
struct GraphActionPhysicalCondition {
  enum class Kind {
    Unsupported,
    GrabbingObject,
    HandPlanting,
    FootPlanting,
    DroppingIn,
    DisableDismount,
    TimeToLand
  };
  Kind kind = Kind::Unsupported;
  NumericCondition numeric;
  std::uint32_t handplant_state = 0, direction = 0;
  bool Evaluate(const GraphActionPhysicalInputs &, const GraphConditionInputs &,
                bool &result, std::string &error) const;
};
// Exact raw-name ActionCondition parser, preceding the generic source parser.
bool ParseGraphActionPhysicalCondition(const GraphAttributes &,
                                       GraphActionPhysicalCondition &,
                                       bool &recognized, std::string &error);
} // namespace atelier::skate
