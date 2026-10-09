#include "GraphConditions.h"
#include "NativeMath.h"
#include <algorithm>
#include <cmath>
#include <cassert>
#include <cstring>
#include <limits>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
std::int32_t SaturatingInt(float value)
{
    if (std::isnan(value)) return 0;
    if (value >= 2147483648.0f) return std::numeric_limits<std::int32_t>::max();
    if (value <= -2147483648.0f) return std::numeric_limits<std::int32_t>::min();
    return static_cast<std::int32_t>(value);
}
bool White(std::uint32_t c)
{
    return c == 0 || (c >= 9 && c <= 13) || c == 0x20 || c == 0x85 || c == 0xa0 || c == 0x1680 ||
        (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 || c == 0x202f || c == 0x205f || c == 0x3000;
}
std::string_view TrimConditionName(std::string_view text)
{
    std::size_t first = text.size(), last = 0, at = 0;
    while (at < text.size())
    {
        const auto begin = at; const auto byte = static_cast<unsigned char>(text[at++]);
        std::uint32_t c = byte; unsigned remaining = 0;
        if ((byte&0xe0) == 0xc0) { c = byte&0x1f; remaining = 1; }
        else if ((byte&0xf0) == 0xe0) { c = byte&0xf; remaining = 2; }
        else if ((byte&0xf8) == 0xf0) { c = byte&7; remaining = 3; }
        while (remaining-- != 0 && at < text.size()) c = (c<<6)|(static_cast<unsigned char>(text[at++])&63);
        if (!White(c)) { if (first == text.size()) first = begin; last = at; }
    }
    return first == text.size() ? std::string_view{} : text.substr(first,last-first);
}
bool Require(bool present, const char* message, std::string& error)
{
    if (present) return true; error = message; return false;
}
}
bool NumericCondition::Matches(float value) const
{
    if (absolute) value = std::abs(value);
    switch (comparison)
    {
    case NumericComparison::None: return false;
    case NumericComparison::Equal: return value == threshold;
    case NumericComparison::NotEqual: return value != threshold;
    case NumericComparison::Greater: return value > threshold;
    case NumericComparison::Less: return value < threshold;
    case NumericComparison::GreaterEqual: return !(value < threshold);
    case NumericComparison::LessEqual: return !(value > threshold);
    case NumericComparison::GreaterAbsolute: return std::abs(value) > threshold;
    }
    return false;
}
NumericCondition ParseNumericCondition(const GraphAttributes& a)
{
    NumericComparison comparison = NumericComparison::None; std::string_view field;
    if (const auto value = a.Text("comparison"))
    {
        comparison = *value == "NotEqual" ? NumericComparison::NotEqual : *value == "GreaterThan" ? NumericComparison::Greater :
            *value == "LessThan" ? NumericComparison::Less : *value == "GreaterEqual" ? NumericComparison::GreaterEqual :
            *value == "LessEqual" ? NumericComparison::LessEqual : NumericComparison::Equal;
        field = "value";
    }
    else
    {
        const std::array<std::pair<NumericComparison,std::string_view>,7> pairs{{
            {NumericComparison::Equal,"equal"},{NumericComparison::NotEqual,"notEqual"},{NumericComparison::Greater,"greater"},
            {NumericComparison::GreaterAbsolute,"greaterThanAbs"},{NumericComparison::Less,"less"},
            {NumericComparison::GreaterEqual,"greaterEqual"},{NumericComparison::LessEqual,"lessEqual"}}};
        for (auto pair : pairs) if (a.Get(pair.second)) { comparison = pair.first; field = pair.second; break; }
    }
    return {comparison,Float(a.FloatBits(field,0)),a.BooleanByte("abs",0) != 0};
}
bool HasAnimationAttribute(const std::vector<AnimationAttribute>& attributes,AttributeName name,std::int32_t sequence,NumericCondition numeric)
{
    const auto found = std::find_if(attributes.begin(),attributes.end(),[&](const auto& a) { return a.name == name; });
    if (found == attributes.end()) return false;
    return (sequence == -1 || sequence == found->sequence_id) &&
        (numeric.comparison == NumericComparison::None || (found->kind != 0 && found->kind != 2) ||
         (found->payload[0] && numeric.Matches(Float(*found->payload[0]))));
}
bool GraphStateTime(const graph::Frame& frame,std::optional<graph::Id> target,NumericCondition numeric)
{
    if (!target || *target >= frame.state_times.size() || !frame.state_times[*target]) return false;
    const auto time = *frame.state_times[*target]; return !(time < 0) && numeric.Matches(time);
}
bool GraphPushBrakeInputs::Disabled() const
{
    const auto degrees = Asin(ground_axis_y)*Float(0x42652ee1);
    return 90.0f-degrees > maximum_ground_angle_degrees || skeleton_disables_push_brake;
}
bool ParseGraphCondition(const GraphAttributes& a,bool motion,GraphCondition& out,std::string& error)
{
    GraphCondition c; const auto raw_name = a.Text("name").value_or(""); c.operation_name = std::string(raw_name);
    const auto name = raw_name; const auto motion_name = TrimConditionName(raw_name); c.numeric = ParseNumericCondition(a);
    using K = GraphCondition::Kind;
    if (name == "HasAGIntent") { c.kind = K::HasActionIntent; c.name = a.Text("intent").value_or(""); }
    else if (name == "TimeSinceLastInput") c.kind = K::TimeSinceLastInput;
    else if (name == "PhysicsSpeedCompare") { c.kind = K::Speed; c.along_skate_z = a.BooleanByte("alongSkateZ",0) != 0; }
    else if (name == "PhysicsSpeedAndSlopeCompare") c.kind = K::SpeedAndSlope;
    else if (name == "PhysFilteredState")
    {
        const auto state = a.Text("state").value_or("");
        const std::array<std::string_view,8> states{"invalid","ground","air","grind","wipeout","teleport","offboard","offboardair"};
        const auto found = std::find(states.begin(),states.end(),state);
        if (found == states.end()) { error = "PhysFilteredState has undefined state `"+std::string(state)+"`"; return false; }
        c.kind = K::FilteredState; c.expected_category = std::uint32_t(found-states.begin());
    }
    else if (name == "IsGrinding") { c.kind = K::Grinding; if (auto n = a.Text("grindName")) c.grind_name = std::string(*n); }
    else if (name == "IsMirrored") c.kind = K::Mirrored;
    else if (name == "IsRidingFakie") c.kind = K::RidingFakie;
    else if (name == "DisablePushBrake") c.kind = K::DisablePushBrake;
    else if (name == "CurrentState") { c.kind = K::CurrentState; c.name = a.Text("state").value_or(""); }
    else if (motion && (motion_name == "HasIntent" || motion_name == "HasFilteredMotionGraphIntent"))
    {
        // The original filtered selector tests the untrimmed source name.
        c.kind = raw_name == "HasFilteredMotionGraphIntent" ? K::HasFilteredIntent : K::HasMotionIntent;
        c.name = a.Text("intent").value_or("");
    }
    else if ((motion ? motion_name : name) == "HasAnimAttribute")
    {
        c.kind = K::HasAnimationAttribute; c.attribute = EncodeAnimationName(a.Text("attribute").value_or(""));
        c.sequence_id = SaturatingInt(Float(a.FloatBits("sequenceid",0xbf800000)));
    }
    else if (motion && motion_name == "InStateForTime") { c.kind = K::InStateForTime; c.name = a.Text("state").value_or(""); }
    else if ((motion ? motion_name : name) == "InParentStateForTime") c.kind = K::InParentStateForTime;
    else if (!motion && name == "PhysicsRequestsDismount") c.kind = K::PhysicsRequestsDismount;
    else if (!motion && name == "IsLandingOnBoard") c.kind = K::IsLandingOnBoard;
    else if (!motion && name == "HasGestureIntent")
    { c.kind=K::HasGestureIntent;if (!ParseGestureGroup(a.Text("group").value_or(""),c.gesture_group,error)) return false; }
    else if (!motion && name == "IsInLocomotion") c.kind=K::IsInLocomotion;
    else if (!motion && name == "IsTricking") c.kind=K::IsTricking;
    out = std::move(c); return true;
}
void BindGraphConditionTarget(const Graph& source,const GraphBinding& binding,const GraphOperation& operation,GraphCondition& condition)
{
    using K = GraphCondition::Kind;
    if (condition.kind != K::CurrentState && condition.kind != K::InStateForTime && condition.kind != K::InParentStateForTime) return;
    std::vector<std::optional<std::uint32_t>> parents(source.elements.size());
    for (std::size_t parent = 0; parent < source.elements.size(); ++parent)
        for (auto child : source.elements[parent].children) parents[child] = std::uint32_t(parent);
    assert(operation.element < parents.size());
    auto element = parents[operation.element];
    while (element)
    {
        const auto state = std::find_if(binding.states.begin(),binding.states.end(),[&](const auto& s) { return s.element == *element; });
        if (state != binding.states.end())
        {
            const auto id = std::uint32_t(state-binding.states.begin());
            condition.target = condition.kind == K::InParentStateForTime ? std::optional<graph::Id>(id) : binding.FindState(id,condition.name,true);
            return;
        }
        element = parents[*element];
    }
}
bool GraphCondition::Evaluate(const GraphConditionInputs& in,const IntentMap& action,const IntentMap& motion,const IntentMap& filtered,
    const std::vector<AnimationAttribute>& attributes,const graph::Frame& frame,const std::vector<std::optional<graph::Id>>& parents,
    bool& result,std::string& error) const
{
    using K = Kind;
    const auto intent = [&](const IntentMap& map) { const auto value = map.Get(name); return value && (numeric.comparison == NumericComparison::None || numeric.Matches(*value)); };
    switch (kind)
    {
    case K::HasActionIntent: result = intent(action); break;
    case K::HasMotionIntent: result = intent(motion); break;
    case K::HasFilteredIntent: result = intent(filtered); break;
    case K::TimeSinceLastInput:
        if (!Require(bool(in.time_since_last_input),"TimeSinceLastInput needs PhysOut miscellaneous+128",error)) return false;
        result = numeric.Matches(*in.time_since_last_input); break;
    case K::Speed:
        if (!Require(bool(in.speeds),"PhysicsSpeedCompare needs skateboard output",error)) return false;
        result = numeric.Matches(along_skate_z ? in.speeds->forward_speed : in.speeds->speed); break;
    case K::SpeedAndSlope:
        if (!Require(bool(in.speeds),"PhysicsSpeedAndSlopeCompare needs skateboard output+192",error)) return false;
        result = numeric.Matches(in.speeds->speed_and_slope); break;
    case K::FilteredState:
        if (!Require(bool(in.physical_state),"PhysFilteredState needs filtered physical state",error)) return false;
        result = in.physical_state->category == expected_category; break;
    case K::Grinding:
        if (!Require(bool(in.physical_state),"IsGrinding needs filtered physical state",error)) return false;
        result = in.physical_state->grinding && (!grind_name || EncodeAnimationName(*grind_name) == EncodeAnimationName(in.physical_state->grind_name)); break;
    case K::Mirrored:
        if (!Require(bool(in.mirrored),"IsMirrored needs the motion-graph stance owner",error)) return false;
        result = *in.mirrored; break;
    case K::RidingFakie:
        if (!Require(bool(in.riding_fakie),"IsRidingFakie needs the motion-graph stance owner",error)) return false;
        result = *in.riding_fakie; break;
    case K::DisablePushBrake:
        if (!Require(bool(in.push_brake),"DisablePushBrake needs ground/skeleton outputs and stock angle",error)) return false;
        result = in.push_brake->Disabled(); break;
    case K::CurrentState:
    {
        auto cursor = frame.current; result = false;
        if (target) while (cursor) { if (*cursor == *target) { result = true; break; } cursor = parents[*cursor]; }
        break;
    }
    case K::HasAnimationAttribute: result = HasAnimationAttribute(attributes,attribute,sequence_id,numeric); break;
    case K::InStateForTime: case K::InParentStateForTime: result = GraphStateTime(frame,target,numeric); break;
    case K::PhysicsRequestsDismount:
        if (!Require(bool(in.physics_requests_dismount),"PhysicsRequestsDismount requires published State77",error)) return false;
        result = *in.physics_requests_dismount; break;
    case K::IsLandingOnBoard:
        if (!Require(bool(in.physical_state_16),"IsLandingOnBoard requires actual State16",error)) return false;
        result = *in.physical_state_16 == 503; break;
    case K::HasGestureIntent:result=atelier::skate::HasGestureIntent(gesture_group,action);break;
    // Original factory82BC3F68 installs8231ED5C; predicate8274CA90 is
    // li r3,0;blr. This resolved constant is separate from unsupported leaves.
    case K::IsInLocomotion:result=false;break;
    // action_conditions.rs consumes the previous MotionGraph owner's bit27.
    case K::IsTricking:
        if (!Require(bool(in.is_tricking),"IsTricking requires actual MotionGraph flag27",error)) return false;
        result=*in.is_tricking;break;
    default: error = "Unsupported graph condition `"+operation_name+"`"; return false;
    }
    return true;
}
}
