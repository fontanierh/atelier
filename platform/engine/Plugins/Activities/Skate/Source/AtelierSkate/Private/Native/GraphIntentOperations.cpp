// SPDX-License-Identifier: Apache-2.0
#include "GraphIntentOperations.h"
#include <cmath>
#include <cassert>
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) { float value; std::memcpy(&value,&bits,4); return value; }
std::optional<float> Value(const IntentMap& values,std::string_view name)
{
    const auto v = values.Get(name); return v ? std::optional<float>(*v) : std::nullopt;
}
std::optional<std::string> Text(const GraphAttributes& a,std::string_view name)
{
    const auto v = a.Text(name); return v ? std::optional<std::string>(*v) : std::nullopt;
}
std::uint32_t ActionFilter(std::optional<std::string_view> value)
{
    const std::array<std::string_view,7> names{"negate","abs","oneMinus","clamp","angleFlip","angleRot90","angleRotN90"};
    if (value) for (std::size_t i = 0; i < names.size(); ++i) if (*value == names[i]) return std::uint32_t(i)+1;
    return 0;
}
std::optional<float> OptionalFloat(const GraphAttributes& a,std::string_view name)
{
    const auto v = a.Get(name); return v ? std::optional<float>(Float(v->float_bits)) : std::nullopt;
}
CreateMgIntent Handler(const ActionIntentParameter& p) { return {p.on_update,p.default_value,p.scale.value_or(1),p.filters}; }
}
ActionIntentParameter ParseActionIntentParameter(const GraphAttributes& a)
{
    ActionIntentParameter p;
    p.name = Text(a,"name"); p.mg_intent = Text(a,"MGIntent"); p.mg_intent_mag = Text(a,"MGIntentMag"); p.mg_intent_angle = Text(a,"MGIntentAngle");
    p.ag_intent = Text(a,"AGIntent"); p.text = Text(a,"value");
    if (const auto v = a.Get("value")) { p.float_bits = v->float_bits; p.boolean_byte = v->boolean_byte; }
    p.default_value = OptionalFloat(a,"defaultValue"); p.scale = OptionalFloat(a,"scale"); p.on_update = a.BooleanByte("onUpdate",1) != 0;
    const auto first = a.Text("filter1");
    p.filters = {ActionFilter(first ? first : a.Text("filter")),ActionFilter(a.Text("filter2")),ActionFilter(a.Text("fakieFilter")),ActionFilter(a.Text("mirrorFilter"))};
    p.angle_filter = ActionFilter(a.Text("angleFilter")); p.negate_on_mirror = a.BooleanByte("negateOnMirror",1) != 0;
    return p;
}
bool CompileActionIntentOperations(const Graph& source,const GraphBinding& binding,std::vector<ActionIntentOperation>& output,std::string& error)
{
    std::vector<ActionIntentOperation> result;
    for (const auto& operation : binding.operations)
    {
        assert(operation.element < source.elements.size());
        const auto& element = source.elements[operation.element];
        const GraphAttributes a(element.attributes);
        const auto failed_factory = [&]
        {
            const auto kind = operation.kind == GraphOperationKind::Behavior ? "behaviour" :
                operation.kind == GraphOperationKind::Condition ? "condition" : "hook";
            error = "Graph "+element.tag+" at byte "+std::to_string(element.source_offset)+": "+
                kind+" `"+operation.name+"`: "+error;
            return false;
        };
        const auto name = a.Text("name"); if (!name) { error = "operation has no name attribute"; return failed_factory(); }
        ActionIntentOperation out; out.source_kind = operation.kind; out.name = std::string(*name); out.config = ParseActionIntentParameter(a);
        using K = ActionIntentOperation::Kind;
        if (operation.kind == GraphOperationKind::Condition)
        {
            bool physical = false;
            if (!ParseGraphActionPhysicalCondition(a,out.physical_condition,physical,error)) return failed_factory();
            if (physical) out.kind = K::PhysicalCondition;
            else
            {
                if (!ParseGraphCondition(a,false,out.condition,error)) return failed_factory();
                BindGraphConditionTarget(source,binding,operation,out.condition);
                if (out.condition.kind != GraphCondition::Kind::Unsupported) out.kind = K::Condition;
            }
        }
        else if (operation.kind == GraphOperationKind::Behavior)
        {
            if (*name == "CreateMGIntentFromAGIntent") out.kind = K::CreateMgIntent;
            else if (*name == "CreateMGTimeIntentFromAGIntent") out.kind = K::CreateMgTimeIntent;
            else if (*name == "CreateConstMGIntent") out.kind = K::CreateConstMgIntent;
            else if (*name == "BoardAdjust") out.kind = K::BoardAdjust;
            else if (*name == "JuiceHook") out.kind = K::JuiceHook;
            else if (*name == "BodyFlippingSignal") out.kind = K::BodyFlippingSignal;
            else if (*name == "PrintText2D") { out.kind = K::PrintText; out.presentation_text = a.Text("text").value_or(""); }
            else if (*name == "CreateTrickIntentFromGesture")
            {out.kind=K::CreateTrickFromGesture;if (!ParseGestureGroup(a.Text("group").value_or("Square"),out.gesture_group,error)) return failed_factory();out.gesture_override=Text(a,"override");}
        }
        for (auto element : operation.parameters) out.parameters.push_back(ParseActionIntentParameter(GraphAttributes(source.elements[element].attributes)));
        result.push_back(std::move(out));
    }
    output = std::move(result); return true;
}
IntentMutation ConstMgIntentState::Begin() { created = true; return {IntentMutation::Kind::Set,value}; }
IntentMutation ConstMgIntentState::Update()
{
    const auto mutation = on_update || created ? IntentMutation{} : End(); created = false; return mutation;
}
IntentMutation TimeMgIntentState::Update(std::optional<float> value,float dt)
{
    if (value) { elapsed += dt; return {IntentMutation::Kind::Set,elapsed}; }
    elapsed = 0; return End();
}
std::optional<std::pair<float,float>> BoardAdjustIntentState::Update(std::optional<float> magnitude,std::optional<float> source_angle,
    std::uint32_t filter,bool negate_on_mirror,bool mirrored)
{
    if (!magnitude || !source_angle) { Begin(); return std::nullopt; }
    auto angle = *source_angle; if (filter <= 7) angle = ApplyIntentFilter(angle,filter);
    if (negate_on_mirror && mirrored) angle *= -1.0f;
    const auto crossed = previous_angle*angle < 0 && std::abs(previous_angle) > Float(0x3fc90fdb);
    if (wrap == 0 && crossed && previous_angle < 0) wrap = 1;
    else if (wrap == 0 && crossed && previous_angle > 0) wrap = 2;
    else if (wrap == 1 && crossed && previous_angle > 0) wrap = 0;
    else if (wrap == 2 && crossed && previous_angle < 0) wrap = 0;
    previous_angle = angle;
    return std::pair<float,float>{*magnitude,wrap == 1 ? Float(0xc0490fdb) : wrap == 2 ? Float(0x40490fdb) : angle};
}
bool ActionIntentGraphHost::FromGraph(const Graph& source,const GraphBinding& binding,const CompiledGraph& compiled,const SettingsDatabase& data,std::string& error)
{
    if (!CompileActionIntentOperations(source,binding,operations,error)) return false;
    const auto gesture = data.Field("anim_motion","body_flip","extend_bodyflip_gesture"), takeoff = data.Field("anim_motion","body_flip","extend_takeoff_point");
    if (!gesture || !gesture->Float() || !takeoff || !takeoff->Float()) { error = "BodyFlippingSignal requires stock anim_motion settings"; return false; }
    body_flip_settings = BodyFlipSettings{*gesture->Float(),*takeoff->Float()}; remap_ = compiled.operations;
    parents_.clear(); for (const auto& state : binding.states) parents_.push_back(state.parent);
    const auto count = remap_.behaviors.size(); created_.assign(count,false); constants_.clear();
    for (auto operation : remap_.behaviors)
    {
        assert(operation < operations.size());
        const auto& p = operations[operation].config; constants_.push_back({p.float_bits ? Float(*p.float_bits) : 0.0f,p.on_update,false});
    }
    times_.assign(count,{}); board_adjust_.assign(count,{}); body_flip_.assign(count,{}); juice_pending_.assign(count,{}); gesture_tricks_.assign(count,{}); next_instance_ = 1;
    action_intents.Clear(); motion_intents.Clear(); filtered_intents.Clear(); condition_inputs = {}; physical_inputs = {}; animation_attributes.clear(); stance.reset();is_tricking.reset();tick=0; errors.clear(); diagnostics_overflowed = false;
    return true;
}
void ActionIntentGraphHost::PrepareInput(IntentMap action,IntentMap prior,std::vector<AnimationAttribute> attributes)
{
    errors.clear(); diagnostics_overflowed = false; action_intents = std::move(action); motion_intents = std::move(prior); animation_attributes = std::move(attributes);
}
const ActionIntentOperation* ActionIntentGraphHost::Operation(graph::Id behavior) const
{
    if (behavior >= remap_.behaviors.size() || remap_.behaviors[behavior] >= operations.size()) return nullptr;
    return &operations[remap_.behaviors[behavior]];
}
void ActionIntentGraphHost::AddError(std::string message)
{
    if (errors.size() < 64) errors.push_back(std::move(message)); else diagnostics_overflowed = true;
}
std::string ActionIntentGraphHost::Diagnostics(std::string_view separator) const
{
    std::string result;
    for (const auto& message : errors) { if (!result.empty()) result += separator; result += message; }
    if (diagnostics_overflowed) { if (!result.empty()) result += separator; result += "graph diagnostics truncated after 64 entries"; }
    return result;
}
void ActionIntentGraphHost::Unsupported(graph::Id behavior,const ActionIntentOperation& operation)
{
    const auto kind = operation.source_kind == GraphOperationKind::Behavior ? "Behavior" : operation.source_kind == GraphOperationKind::Condition ? "Condition" : "Hook";
    AddError("ActionGraph behavior "+std::to_string(behavior)+": "+kind+" `"+operation.name+"`");
}
void ActionIntentGraphHost::Apply(std::string_view name,IntentMutation mutation)
{
    if (mutation.kind == IntentMutation::Kind::Set) motion_intents.Insert(name,mutation.value);
    else if (mutation.kind == IntentMutation::Kind::Remove) motion_intents.Remove(name);
}
std::uint32_t ActionIntentGraphHost::ConditionActivation(graph::Id id,const graph::Frame& frame)
{
    if (id >= remap_.conditions.size() || remap_.conditions[id] >= operations.size())
    { AddError("ActionGraph condition "+std::to_string(id)+" is unbound"); return 0; }
    const auto& operation = operations[remap_.conditions[id]]; bool result = false; std::string error;
    condition_inputs.is_tricking=is_tricking;
    if (operation.kind == ActionIntentOperation::Kind::PhysicalCondition)
    {
        if (!operation.physical_condition.Evaluate(physical_inputs,condition_inputs,result,error))
        {
            AddError(error);
            return 0;
        }
        return result;
    }
    if (!operation.condition.Evaluate(condition_inputs,action_intents,motion_intents,filtered_intents,animation_attributes,frame,parents_,result,error))
    {
        // The original core Condition branch adds the compact condition ID;
        // extra animation/state and physical leaves forward their own error.
        using K = GraphCondition::Kind;
        const auto kind = operation.condition.kind;
        const bool core = kind >= K::HasActionIntent && kind <= K::CurrentState;
        AddError(core ? "ActionGraph condition "+std::to_string(id)+": "+error : error);
        return 0;
    }
    return result;
}
std::uint32_t ActionIntentGraphHost::Allocate(graph::Id id,const graph::Frame&)
{
    assert(id < created_.size());
    created_[id] = false; times_[id] = {}; body_flip_[id] = {}; juice_pending_[id].clear();gesture_tricks_[id]={};
    const auto result = next_instance_; ++next_instance_; if (next_instance_ == 0) next_instance_ = 1; return result;
}
void ActionIntentGraphHost::Begin(graph::Id id,graph::Context,const graph::Frame&)
{
    const auto* operation = Operation(id); if (!operation) return; const auto& p = operation->config; using K = ActionIntentOperation::Kind;
    switch (operation->kind)
    {
    case K::CreateTrickFromGesture:
        if (stance) gesture_tricks_[id].Begin(operation->gesture_group,operation->gesture_override?std::optional<std::string_view>(*operation->gesture_override):std::nullopt,action_intents,motion_intents,stance->second);
        else AddError("CreateTrickIntentFromGesture requires published skater stance");break;
    case K::Unsupported: Unsupported(id,*operation); break;
    case K::PrintText: if (presentation) presentation(operation->presentation_text); break;
    case K::BodyFlippingSignal:
        if (body_flip_settings) body_flip_[id].Begin(*body_flip_settings); else AddError("BodyFlippingSignal requires stock anim_motion settings"); break;
    case K::BoardAdjust: board_adjust_[id].Begin(); break;
    case K::CreateConstMgIntent: if (p.mg_intent) Apply(*p.mg_intent,constants_[id].Begin()); break;
    case K::CreateMgIntent:
        if (p.mg_intent && p.ag_intent)
        {
            bool created = created_[id]; const auto mutation = Handler(p).Enter(created,Value(action_intents,*p.ag_intent),stance);
            created_[id] = created; Apply(*p.mg_intent,mutation);
        }
        else AddError("ActionGraph behavior "+std::to_string(id)+": missing AGIntent/MGIntent");
        break;
    default: break;
    }
}
void ActionIntentGraphHost::Update(graph::Id id,graph::Context,const graph::Frame& frame)
{
    const auto* operation = Operation(id); if (!operation) return; const auto& p = operation->config; using K = ActionIntentOperation::Kind;
    if (operation->kind == K::Unsupported) { Unsupported(id,*operation); return; }
    if (operation->kind == K::CreateTrickFromGesture) {gesture_tricks_[id].Update(motion_intents);return;}
    if (operation->kind == K::JuiceHook) { motion_intents.Remove(juice_pending_[id]); juice_pending_[id].clear(); return; }
    if (operation->kind == K::BodyFlippingSignal)
    {
        if (!body_flip_settings) { AddError("BodyFlippingSignal requires stock anim_motion settings"); return; }
        if (!condition_inputs.physical_state) { AddError("BodyFlippingSignal requires published filtered state"); return; }
        const std::array<std::string_view,2> names{"FrontFlip","BackFlip"};
        const auto result = body_flip_[id].Update({action_intents.Contains(names[0]),action_intents.Contains(names[1])},condition_inputs.physical_state->category,frame.dt,*body_flip_settings);
        if (result) motion_intents.Insert(names[*result],1); else for (auto name : names) motion_intents.Remove(name);
        return;
    }
    if (operation->kind == K::BoardAdjust)
    {
        if (!p.mg_intent_mag || !p.mg_intent_angle) return;
        const auto result = board_adjust_[id].Update(Value(action_intents,"BoardAdjustMag"),Value(action_intents,"BoardAdjustAngle"),p.angle_filter,p.negate_on_mirror,stance && stance->second);
        if (result) { motion_intents.Insert(*p.mg_intent_mag,result->first); motion_intents.Insert(*p.mg_intent_angle,result->second); }
        else { motion_intents.Remove(*p.mg_intent_mag); motion_intents.Remove(*p.mg_intent_angle); }
        return;
    }
    if (operation->kind == K::CreateConstMgIntent) { if (p.mg_intent) Apply(*p.mg_intent,constants_[id].Update()); return; }
    if (!p.ag_intent || !p.mg_intent) return;
    const auto value = Value(action_intents,*p.ag_intent);
    if (operation->kind == K::CreateMgIntent)
    {
        bool created = created_[id]; const auto mutation = Handler(p).Update(created,value,stance); created_[id] = created; Apply(*p.mg_intent,mutation);
    }
    else if (operation->kind == K::CreateMgTimeIntent) Apply(*p.mg_intent,times_[id].Update(value,frame.dt));
}
void ActionIntentGraphHost::End(graph::Id id,graph::Context,const graph::Frame&)
{
    const auto* operation = Operation(id); if (!operation) return; const auto& p = operation->config;
    if (operation->kind == ActionIntentOperation::Kind::CreateTrickFromGesture) {gesture_tricks_[id].End(motion_intents);return;}
    if (operation->kind == ActionIntentOperation::Kind::BoardAdjust)
    { if (p.mg_intent_mag) motion_intents.Remove(*p.mg_intent_mag); if (p.mg_intent_angle) motion_intents.Remove(*p.mg_intent_angle); return; }
    if (p.mg_intent) Apply(*p.mg_intent,{IntentMutation::Kind::Remove,0});
}
void ActionIntentGraphHost::Hook(graph::Id id,const graph::Frame&)
{
    if (id >= remap_.hooks.size() || remap_.hooks[id] >= operations.size())
    { AddError("ActionGraph hook index "+std::to_string(id)+" is unbound"); return; }
    const auto& operation = operations[remap_.hooks[id]]; if (operation.kind == ActionIntentOperation::Kind::Unsupported) Unsupported(id,operation);
}
MotionIntentFilterOperation MotionIntentFilterOperation::Parse(const GraphAttributes& a)
{
    MotionIntentFilterOperation op; op.intent = a.Text("intent").value_or(""); op.filtered_intent = a.Text("filteredIntent").value_or("");
    const auto number = [&](std::string_view name,std::uint32_t fallback) { return Float(a.FloatBits(name,fallback)); };
    const auto blend = number("blend",0x3f800000); auto& s = op.settings;
    s.starting_value = number("startingValue",0); s.default_value = number("defaultValue",0); s.scale = number("scale",0x3f800000);
    const auto first = a.Text("filter1"); s.filters = {IntentFilterKind(first ? first : a.Text("filter")),IntentFilterKind(a.Text("filter2")),IntentFilterKind(a.Text("fakieFilter")),IntentFilterKind(a.Text("mirrorFilter"))};
    s.ramp_time = OptionalFloat(a,"rampTime"); s.blend_rising = a.Get("blendRising") ? number("blendRising",0) : blend; s.blend_falling = a.Get("blendFalling") ? number("blendFalling",0) : blend;
    s.blend_out = OptionalFloat(a,"blendOut"); s.clamp_velocity = OptionalFloat(a,"clampVel"); s.clamp_acceleration = OptionalFloat(a,"clampAcc"); return op;
}
bool MotionIntentFilterOperation::Execute(std::uint8_t phase,MotionIntentFilterState& state,const IntentMap& input,IntentMap& output,float dt,std::optional<std::uint32_t> flags,std::string& error) const
{
    if (phase == 0) output.Insert(filtered_intent,state.Begin(settings));
    else if (phase == 1)
    {
        if (!flags) { error = "FilterMotionGraphIntent requires live animation stance flags"; return false; }
        output.Insert(filtered_intent,state.Update(settings,Value(input,intent),dt,{(*flags&0x20000000) != 0,(*flags&0x40000000) != 0}));
    }
    else output.Remove(filtered_intent);
    return true;
}
AttachIntentOperation AttachIntentOperation::Parse(const GraphAttributes& a)
{
    return {std::string(a.Text("intent").value_or("0")),EncodeAnimationName(a.Text("attr").value_or("0")),a.BooleanByte("set",0) != 0};
}
void AttachIntentOperation::Execute(std::uint8_t phase,const IntentMap& motion,const std::function<void(AttributeName,float)>& packet,const std::function<void(AttributeName,float)>& skeleton) const
{
    if (phase != 1) return;
    AttachIntent(Value(motion,intent),set,[&](float value) { packet(attribute,value); },[&](float value) { skeleton(attribute,value); });
}
}
