// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationPlayback.h"
#include "Graph.h"
#include "GraphController.h"
#include "Intents.h"
#include <optional>
#include <string>
#include <vector>

namespace atelier::skate
{
enum class NumericComparison : std::uint32_t { None, Equal, NotEqual, Greater, Less, GreaterEqual, LessEqual, GreaterAbsolute };
struct NumericCondition
{
    NumericComparison comparison = NumericComparison::None;
    float threshold = 0;
    bool absolute = false;
    bool Matches(float value) const;
};
NumericCondition ParseNumericCondition(const GraphAttributes& attributes);
bool HasAnimationAttribute(const std::vector<AnimationAttribute>&, AttributeName, std::int32_t sequence_id, NumericCondition);
bool GraphStateTime(const graph::Frame&, std::optional<graph::Id> target, NumericCondition);
struct GraphSpeedInputs { float speed, forward_speed, speed_and_slope; };
struct GraphPhysicalStateInputs { std::uint32_t category; bool grinding; std::string grind_name; };
struct GraphPushBrakeInputs
{
    float ground_axis_y;
    bool skeleton_disables_push_brake;
    float maximum_ground_angle_degrees;
    bool Disabled() const;
};
struct GraphConditionInputs
{
    std::optional<GraphSpeedInputs> speeds;
    std::optional<GraphPhysicalStateInputs> physical_state;
    std::optional<float> time_since_last_input;
    std::optional<bool> mirrored, riding_fakie;
    std::optional<GraphPushBrakeInputs> push_brake;
    std::optional<bool> physics_requests_dismount;
    std::optional<std::uint32_t> physical_state_16;
};
struct GraphCondition
{
    enum class Kind : std::uint32_t
    {
        Unsupported, HasActionIntent, TimeSinceLastInput, Speed, SpeedAndSlope,
        FilteredState, Grinding, Mirrored, RidingFakie, DisablePushBrake, CurrentState,
        HasMotionIntent, HasFilteredIntent, HasAnimationAttribute,
        InStateForTime, InParentStateForTime, PhysicsRequestsDismount, IsLandingOnBoard
    };
    Kind kind = Kind::Unsupported;
    std::string operation_name, name;
    NumericCondition numeric;
    std::optional<graph::Id> target;
    std::optional<std::string> grind_name;
    bool along_skate_z = false;
    std::uint32_t expected_category = 0;
    AttributeName attribute{};
    std::int32_t sequence_id = -1;
    // bool return reports evaluation success; result remains distinct from an
    // absent required physical producer. Unsupported leaves carry diagnostics.
    bool Evaluate(const GraphConditionInputs&, const IntentMap& action, const IntentMap& motion,
        const IntentMap& filtered, const std::vector<AnimationAttribute>& attributes,
        const graph::Frame&, const std::vector<std::optional<graph::Id>>& parents,
        bool& result, std::string& error) const;
};
bool ParseGraphCondition(const GraphAttributes&, bool motion_graph, GraphCondition&, std::string& error);
void BindGraphConditionTarget(const Graph&, const GraphBinding&, const GraphOperation&, GraphCondition&);
}
