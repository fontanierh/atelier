// SPDX-License-Identifier: Apache-2.0
#include "GraphActionPhysicalConditions.h"
#include "GraphMotionPhysicalConditions.h"
#include <cstring>
namespace atelier::skate {
bool ParseGraphActionPhysicalCondition(const GraphAttributes &a,
                                       GraphActionPhysicalCondition &out,
                                       bool &recognized, std::string &error) {
  GraphActionPhysicalCondition c;
  using K = GraphActionPhysicalCondition::Kind;
  const auto name = a.Text("name").value_or("");
  recognized = true;
  error.clear();
  if (name == "IsGrabbingObject")
    c.kind = K::GrabbingObject;
  else if (name == "IsHandPlanting") {
    // The original ActionCondition uses this same GameplayCondition
    // factory; reuse its exact state/direction parsing and diagnostics.
    GraphMotionPhysicalCondition shared;
    bool known;
    if (!ParseGraphMotionPhysicalCondition(a, shared, known, error))
      return false;
    c.kind = K::HandPlanting;
    c.handplant_state = shared.value;
    c.direction = shared.direction;
  } else if (name == "IsFootPlanting")
    c.kind = K::FootPlanting;
  else if (name == "IsDroppingIn")
    c.kind = K::DroppingIn;
  else if (name == "DisableDismount")
    c.kind = K::DisableDismount;
  else if (name == "TimeToLand") {
    c.kind = K::TimeToLand;
    c.numeric = ParseNumericCondition(a);
  } else
    recognized = false;
  out = c;
  return true;
}
bool GraphActionPhysicalCondition::Evaluate(
    const GraphActionPhysicalInputs &p, const GraphConditionInputs &condition,
    bool &result, std::string &error) const {
  using K = Kind;
  error.clear();
  switch (kind) {
  case K::GrabbingObject:
  case K::HandPlanting:
  case K::FootPlanting:
    if (!p.gameplay_conditions) {
      error = "ActionGraph requires actual physical condition outputs";
      return false;
    }
    if (kind == K::GrabbingObject)
      result = p.gameplay_conditions->grabbing_object;
    else if (kind == K::FootPlanting)
      result = p.gameplay_conditions->footplant_active &&
               p.gameplay_conditions->footplant_duration >= 0.0f;
    else {
      const auto &v = *p.gameplay_conditions;
      const bool active = handplant_state == 0
                              ? v.state == 600
                              : (v.handplant_flags & 0x80000000) != 0;
      result = active &&
               (direction == 2 ||
                (direction == 1 && (v.handplant_flags & 0x20000000) != 0) ||
                (direction == 0 && (v.handplant_flags & 0x20000000) == 0));
    }
    return true;
  case K::DroppingIn:
    if (!p.dropping_in) {
      error = "IsDroppingIn requires completed grind output";
      return false;
    }
    result = *p.dropping_in;
    return true;
  case K::DisableDismount: {
    if (!condition.push_brake) {
      error = "DisableDismount requires actual Ground80 and Skeleton598";
      return false;
    }
    const std::uint32_t bits = 0x3f23d70a;
    float threshold;
    std::memcpy(&threshold, &bits, 4);
    result = threshold > condition.push_brake->ground_axis_y ||
             condition.push_brake->skeleton_disables_push_brake;
    return true;
  }
  case K::TimeToLand:
    if (!p.gameplay_conditions) {
      error =
          "ActionGraph TimeToLand requires actual physical condition outputs";
      return false;
    }
    result = p.gameplay_conditions->time_to_land_valid &&
             numeric.Matches(p.gameplay_conditions->time_to_land);
    return true;
  case K::Unsupported:
    error = "Unbound ActionGraph physical condition";
    return false;
  }
  error = "Unbound ActionGraph physical condition";
  return false;
}
} // namespace atelier::skate
