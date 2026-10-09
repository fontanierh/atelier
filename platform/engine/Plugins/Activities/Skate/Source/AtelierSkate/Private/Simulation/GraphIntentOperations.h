#pragma once
#include "CompiledGraph.h"
#include "GraphConditions.h"
#include "GraphActionPhysicalConditions.h"
#include "InputIntentions.h"
#include "Settings.h"

namespace atelier::skate
{
struct ActionGraphInput;
struct ActionGraphOutput;
struct ActionIntentParameter
{
    std::optional<std::string> name, mg_intent, mg_intent_mag, mg_intent_angle, ag_intent, text;
    std::optional<std::uint32_t> float_bits;
    std::optional<std::uint8_t> boolean_byte;
    std::optional<float> default_value, scale;
    bool on_update = true;
    std::array<std::uint32_t,4> filters{};
    std::uint32_t angle_filter = 0;
    bool negate_on_mirror = true;
};
ActionIntentParameter ParseActionIntentParameter(const GraphAttributes&);
struct ActionIntentOperation
{
    enum class Kind : std::uint32_t { Unsupported, Condition, CreateMgIntent, CreateMgTimeIntent, CreateConstMgIntent, BoardAdjust, JuiceHook, BodyFlippingSignal, PrintText, CreateTrickFromGesture, PhysicalCondition };
    Kind kind = Kind::Unsupported;
    GraphOperationKind source_kind = GraphOperationKind::Behavior;
    std::string name, presentation_text;
    ActionIntentParameter config;
    std::vector<ActionIntentParameter> parameters;
    GraphCondition condition;
    GraphActionPhysicalCondition physical_condition;
    GestureGroup gesture_group=GestureGroup::Square;
    std::optional<std::string> gesture_override;
};
bool CompileActionIntentOperations(const Graph&, const GraphBinding&, std::vector<ActionIntentOperation>&, std::string& error);
struct ConstMgIntentState
{
    float value = 0;
    bool on_update = true, created = false;
    IntentMutation Begin();
    IntentMutation Update();
    IntentMutation End() const { return {IntentMutation::Kind::Remove,0}; }
};
struct TimeMgIntentState
{
    float elapsed = 0;
    IntentMutation Update(std::optional<float> action_value, float dt);
    IntentMutation End() const { return {IntentMutation::Kind::Remove,0}; }
};
struct BoardAdjustIntentState
{
    std::uint32_t wrap = 0;
    float previous_angle = 0;
    void Begin() { wrap = 0; previous_angle = 0; }
    std::optional<std::pair<float,float>> Update(std::optional<float> magnitude, std::optional<float> angle,
        std::uint32_t filter, bool negate_on_mirror, bool mirrored);
};
class ActionIntentGraphHost : public graph::Host
{
public:
    std::vector<ActionIntentOperation> operations;
    IntentMap action_intents, motion_intents, filtered_intents;
    GraphConditionInputs condition_inputs;
    GraphActionPhysicalInputs physical_inputs;
    std::vector<AnimationAttribute> animation_attributes;
    std::optional<Stance> stance;
    std::optional<bool> is_tricking;
    std::uint64_t tick=0;
    std::optional<BodyFlipSettings> body_flip_settings;
    std::vector<std::string> errors;
    bool diagnostics_overflowed = false;
    std::string Diagnostics(std::string_view separator) const;
    std::function<void(std::string_view)> presentation;
    bool FromGraph(const Graph&,const GraphBinding&,const CompiledGraph&,const SettingsDatabase&,std::string& error);
    void PrepareInput(IntentMap action, IntentMap prior_motion, std::vector<AnimationAttribute> attributes);
    void PrepareInput(const ActionGraphInput& input);
    ActionGraphOutput Output() const;
    graph::Context GetContext() const override { return {}; }
    std::uint32_t ConditionActivation(graph::Id condition,const graph::Frame&) override;
    std::uint32_t Allocate(graph::Id behavior,const graph::Frame&) override;
    void Begin(graph::Id behavior,graph::Context,const graph::Frame&) override;
    void Update(graph::Id behavior,graph::Context,const graph::Frame&) override;
    void End(graph::Id behavior,graph::Context,const graph::Frame&) override;
    void Hook(graph::Id hook,const graph::Frame&) override;
    void Release(std::uint32_t) override {}
    void Apply(std::string_view name, IntentMutation);
private:
    GraphOperationRemap remap_;
    std::vector<std::optional<graph::Id>> parents_;
    std::uint32_t next_instance_ = 1;
    std::vector<bool> created_;
    std::vector<ConstMgIntentState> constants_;
    std::vector<TimeMgIntentState> times_;
    std::vector<BoardAdjustIntentState> board_adjust_;
    std::vector<BodyFlipState> body_flip_;
    std::vector<std::string> juice_pending_;
    std::vector<GestureTrickState> gesture_tricks_;
    const ActionIntentOperation* Operation(graph::Id behavior) const;
    void Unsupported(graph::Id behavior,const ActionIntentOperation&);
    void AddError(std::string message);
};
struct MotionIntentFilterOperation
{
    std::string intent, filtered_intent;
    MotionIntentFilterSettings settings;
    static MotionIntentFilterOperation Parse(const GraphAttributes&);
    bool Execute(std::uint8_t phase,MotionIntentFilterState&,const IntentMap& input,IntentMap& output,
        float dt,std::optional<std::uint32_t> animation_flags,std::string& error) const;
};
struct AttachIntentOperation
{
    std::string intent;
    AttributeName attribute{};
    bool set = false;
    static AttachIntentOperation Parse(const GraphAttributes&);
    void Execute(std::uint8_t phase,const IntentMap& motion,
        const std::function<void(AttributeName,float)>& packet,
        const std::function<void(AttributeName,float)>& skeleton) const;
};
}
