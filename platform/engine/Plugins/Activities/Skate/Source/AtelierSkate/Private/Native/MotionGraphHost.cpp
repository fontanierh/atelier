// SPDX-License-Identifier: Apache-2.0
#include "MotionGraphHost.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <set>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
std::int32_t Signed(std::uint32_t word) {std::int32_t value;std::memcpy(&value,&word,4);return value;}
TransitionSettings Transition(const GraphAttributes& a)
{
    const auto type=a.Text("transType").value_or("");
    return {type=="play"?1u:type=="sequence"?4u:type=="channelblend"?3u:2u,
        Float(a.FloatBits("time",0x3e4ccccd)),std::uint32_t(a.BooleanByte("transitionUnder",0)!=0),
        a.BooleanByte("blendWithCurrentFrame",0)?1u:a.BooleanByte("blendMatchPhase",0)?2u:a.BooleanByte("blendMatchFrame",0)?3u:0u,
        a.BooleanByte("useChannelFromWeights",0)!=0};
}
bool KnownBehavior(std::string_view name)
{
    static const std::set<std::string_view> names{
        "PlayAnimation","CreateAttribute","ScoringTrick","ScoringGrabs","SetScoreAugmentation","SetTrickHeight",
        "SetTrickAttr","SetDark","MonitorUnderflip","SetGrabType","SetDeckPitchAndYaw","ClearTrickAttr",
        "SetManualAngle","HandBusy","MaintainShove","EndShimmy","IsDoingTrick","IsAnticipating","IsLanding",
        "IsManualing","DisableTricks","SetLandingData","StoreLandingData","ChooseRandomLanding","SetBumpCoefficients",
        "UpdateIsWeightOnNose","TweakProject","InitPush","PushCycle","PushOut","ComputeRepushDeadline",
        "ComputeFirstPushStrength","ComputeTargetCoefsFromSpeedAndStrength","SetPushCoefs","Pumping","DisallowPumping",
        "FakieHeadChannel","KickTurnSteering","ToggleBoard","AddRunoutAttribs","BipedCadence","MatchCadence",
        "MatchAirTime","OffboardBodyTweakBlend","AirDismounting","MatchTwistAndLean","ControlAirLegExtension","BodySpin",
        "CharacterGesture","EndGesture","Shove","HippyJumpAntic","FingerFlipOut","JumpInto","FootPlantAbsorb",
        "SetHandPlantAnticLength","ScoringHandPlants","CreateGrindAttributes","ControlGrindCrouch","GrindControlFade",
        "MovingObject","InitMovingObjects","UpdateStandingOnCar","EnterSkitchingBehaviour","SkitchingBehaviour",
        "SkitchShimmyingBehaviour","LandOnBoard","Wipeout","EnableWipeoutGestures","AttachIntent","FilterMotionGraphIntent",
        "SetTurning","PowerSliding","CreateSlide","PowerSlideDecel","PowerSlideSpin","PowerSlideManualAtt",
        "InCandidateSlidingState","IsPowerSliding","ApplyingBodyTilt","SettingBodyTilt","Crouching","UpdateRidingFakie",
        "UpdateTimeSinceTeleport","UpdateTimeSinceKickturn","ResetTimeSinceKickturn","SetManualOutTimer",
        "UpdateManualOutTimer","SetDistComToBoard","ForcePhysics","SetSpeed","ResetSkaterAnimation","ResetToGivenStance","PrintText2D"};
    return names.find(name)!=names.end();
}
MotionGraphInstance InstanceFor(const MotionGraphOperation& operation)
{
    using K=MotionGraphOperation::Kind;
    switch (operation.kind)
    {
    case K::Feedback:return CreateGraphMotionFeedbackInstance(operation.feedback);
    case K::Push:return GraphMotionPushInstance{};
    case K::CharacterGesture:return MotionGraphCharacterGestureState{};
    case K::Shove:return MotionGraphShoveState{};
    case K::Animation:return MotionAnimationOperationState{};
    case K::IntentFilter:return MotionIntentFilterState{};
    case K::SlideUpdate:return GraphMotionSlidingState{};
    case K::SlideDeceleration:return 0.0f;
    case K::Dark:case K::MonitorUnderflip:case K::WeightOnNose:return std::int32_t(0);
    case K::Anticipating:case K::Landing:case K::Manualing:case K::DoingTrick:case K::DisableTricks:return MotionGraphLandingInstance{};
    case K::JumpInto:return MotionGraphJumpInstance{};
    default:return std::monostate{};
    }
}
void MarkFakie(const GraphBinding& binding,std::uint32_t expression,std::vector<bool>& flags)
{
    for (auto child:binding.expressions[expression].children)
    {
        if (child.kind==GraphNodeKind::Operation && binding.operations[child.index].name=="IsRidingFakie") flags[child.index]=true;
        else if (child.kind==GraphNodeKind::Expression) MarkFakie(binding,child.index,flags);
    }
}
}
bool ParseMotionGraphOperation(GraphOperationKind source_kind,const GraphAttributes& a,MotionGraphOperation& output,std::string& error)
{
    const auto raw=a.Text("name");if (!raw) {error="MotionGraph operation has no name";return false;}
    const auto name=TrimMotionGraphName(*raw);MotionGraphOperation op;op.name=std::string(name);op.source_kind=source_kind;using K=MotionGraphOperation::Kind;
    const auto number=[&](std::string_view key,std::uint32_t fallback){return Float(a.FloatBits(key,fallback));};
    if (source_kind==GraphOperationKind::Condition)
    {
        bool recognized=false;
        if (!ParseGraphMotionSpecialCondition(a,op.special_condition,recognized,error)) return false;
        if (recognized) op.kind=K::SpecialCondition;
        else
        {
            if (!ParseGraphMotionPhysicalCondition(a,op.physical_condition,recognized,error)) return false;
            if (recognized) op.kind=K::PhysicalCondition;
            else
            {
                if (!ParseGraphMotionCondition(a,op.condition,error)) return false;
                op.kind=K::Condition;if (op.condition.kind==GraphMotionCondition::Kind::Unsupported) op.condition.operation_name=op.name;
            }
        }
    }
    else if (source_kind==GraphOperationKind::Hook)
    {
        // motion_hooks.rs tests the raw authored spelling.
        if (*raw=="GrabSlide") {op.kind=K::GrabSlideHook;op.right=a.BooleanByte("right",1)!=0;}
        else if (*raw=="OverideNextAnimTransitionHook") {op.kind=K::OverrideHook;op.transition=Transition(a);}
        else if (*raw=="MongoPushToAntic") {op.kind=K::MongoPushHook;op.text=a.Text("anim").value_or("");}
    }
    else
    {
        bool push_recognized=false,gesture_recognized=false,shove_recognized=false;
        bool animation_recognized=false,feedback_recognized=false,score_recognized=false;
        if (!ParseGraphMotionPushOperation(a,op.push,push_recognized,error)) return false;
        if (!push_recognized&&!ParseMotionGraphGestureOperation(a,op.gesture,gesture_recognized,error)) return false;
        if (!push_recognized&&!gesture_recognized&&!ParseGraphMotionShoveOperation(a,op.shove,shove_recognized,error)) return false;
        const bool specialized=push_recognized||gesture_recognized||shove_recognized;
        if (!specialized&&!ParseMotionAnimationOperation(a,op.animation,animation_recognized,error)) return false;
        if (!specialized&&!animation_recognized&&!ParseGraphMotionFeedbackOperation(a,op.feedback,feedback_recognized,error)) return false;
        if (!specialized&&!animation_recognized&&!feedback_recognized&&!ParseGraphMotionScoreOperation(a,op.score,score_recognized,error)) return false;
        if (push_recognized) op.kind=K::Push;
        else if (gesture_recognized) op.kind=op.gesture==MotionGraphGestureOperation::Character?K::CharacterGesture:K::EndGesture;
        else if (shove_recognized) op.kind=K::Shove;
        else if (animation_recognized) op.kind=K::Animation;
        else if (feedback_recognized) op.kind=K::Feedback;
        else if (score_recognized) op.kind=K::Score;
        else if (name=="AttachIntent") {op.kind=K::Attach;op.attach=AttachIntentOperation::Parse(a);}
        else if (name=="FilterMotionGraphIntent") {op.kind=K::IntentFilter;op.filter=MotionIntentFilterOperation::Parse(a);}
        else if (name=="PrintText2D") op.kind=K::PrintText;
        else if (*raw=="SetGrabType") {op.kind=K::GrabType;op.text=a.Text("grab").value_or("");}
        else if (*raw=="SetDark") op.kind=K::Dark;
        else if (*raw=="MonitorUnderflip") op.kind=K::MonitorUnderflip;
        else if (*raw=="IsAnticipating") op.kind=K::Anticipating;
        else if (*raw=="IsLanding") op.kind=K::Landing;
        else if (*raw=="IsManualing") op.kind=K::Manualing;
        else if (*raw=="IsDoingTrick") op.kind=K::DoingTrick;
        else if (*raw=="DisableTricks") {op.kind=K::DisableTricks;op.value=number("length",0x3f000000);}
        else if (*raw=="UpdateManualOutTimer") op.kind=K::ManualOutTimer;
        else if (*raw=="SetManualOutTimer") {op.kind=K::SetManualOutTimer;op.value=number("length",0x3e29fbe7);}
        else if (*raw=="UpdateTimeSinceTeleport") op.kind=K::TimeSinceTeleport;
        else if (*raw=="UpdateTimeSinceKickturn") op.kind=K::TimeSinceKickturn;
        else if (*raw=="ResetTimeSinceKickturn") op.kind=K::ResetKickturn;
        else if (*raw=="SetDistComToBoard")
        {op.kind=K::DistComToBoard;op.attribute=EncodeAnimationName(a.Text("attribute").value_or(""));op.set_manually=a.BooleanByte("setManually",0)!=0;op.adjust_for_velocity=a.BooleanByte("adjustForVel",0)!=0;}
        else if (*raw=="ForcePhysics")
        {op.kind=K::ForcePhysics;const auto force=a.Text("force").value_or("FOLLOW_ANIMATION_DATA");op.ordinal=force=="FORCE_PHYSICS_SKATEBOARD"?1:force=="FORCE_ANIM_SKATEBOARD"?2:0;}
        else if (name=="SetSpeed")
        {op.kind=K::SetSpeed;op.attribute=EncodeAnimationName(a.Text("attribute").value_or(""));if (const auto value=a.Get("setToValue")) op.optional_value=Float(value->float_bits);}
        else if (name=="ApplyingBodyTilt") op.kind=K::ApplyingBodyTilt;
        else if (name=="ResetSkaterAnimation") op.kind=K::ResetAnimation;
        else if (name=="ResetToGivenStance") op.kind=K::ResetGivenStance;
        else if (*raw=="HandBusy") {op.kind=K::HandBusy;op.ordinal=a.Text("hand").value_or("bs")=="bs"?0:1;}
        else if (*raw=="MaintainShove") op.kind=K::MaintainShove;
        else if (*raw=="PowerSliding") op.kind=K::SlideUpdate;
        else if (*raw=="CreateSlide") {op.kind=K::SlideCreate;op.right=a.BooleanByte("right",1)!=0;}
        else if (*raw=="PowerSlideManualAtt") op.kind=K::SlideManual;
        else if (*raw=="PowerSlideDecel") op.kind=K::SlideDeceleration;
        else if (*raw=="PowerSlideSpin") op.kind=K::SlideSpin;
        else if (*raw=="InCandidateSlidingState") op.kind=K::SlideCandidate;
        else if (*raw=="IsPowerSliding") op.kind=K::PowerSlidingFlag;
        else if (*raw=="UpdateIsWeightOnNose") op.kind=K::WeightOnNose;
        else if (name=="ClearTrickAttr") op.kind=K::ClearTrickAttribute;
        else if (name=="JumpInto") {op.kind=K::JumpInto;op.attribute=EncodeAnimationName(a.Text("attribute").value_or(a.Text("attr").value_or("JumpInto")));}
        else if (name=="UpdateStandingOnCar") op.kind=K::SourceStandingOnCarNoop;
        else if (name=="AirDismounting" || name=="EnterSkitchingBehaviour" || name=="SkitchingBehaviour" || name=="SkitchShimmyingBehaviour") op.kind=K::SourceMissingProducer;
        else if (KnownBehavior(name)) op.kind=K::Unported;
    }
    output=std::move(op);error.clear();return true;
}
bool MotionGraphHost::FromGraph(const Graph& source,const GraphBinding& binding,const CompiledGraph& compiled,const SettingsDatabase& data,std::string& error)
{
    std::vector<MotionGraphOperation> parsed;MotionGraphCapabilities report;
    for (const auto& operation:binding.operations)
    {
        MotionGraphOperation out;const GraphAttributes attributes(source.elements[operation.element].attributes);
        if (!ParseMotionGraphOperation(operation.kind,attributes,out,error)) return false;
        if (out.kind==MotionGraphOperation::Kind::Animation) for (auto parameter:operation.parameters)
            if (!AddMotionAnimationParameter(out.animation,GraphAttributes(source.elements[parameter].attributes),error)) return false;
        if (out.kind==MotionGraphOperation::Kind::Condition) BindGraphMotionCondition(source,binding,operation,out.condition);
        const auto kind=out.kind;
        if (kind==MotionGraphOperation::Kind::Unsupported || (kind==MotionGraphOperation::Kind::Condition && out.condition.kind==GraphMotionCondition::Kind::Unsupported)) report.source_unsupported.push_back(out.name);
        else if (kind==MotionGraphOperation::Kind::Unported || (kind==MotionGraphOperation::Kind::Condition && out.condition.kind==GraphMotionCondition::Kind::Unported)) report.unported.push_back(out.name);
        else if (kind==MotionGraphOperation::Kind::SourceMissingProducer) report.source_missing_producers.push_back(out.name);
        else {++report.supported;if (kind==MotionGraphOperation::Kind::SourceStandingOnCarNoop) report.source_placeholder_noops.push_back(out.name);}
        parsed.push_back(std::move(out));
    }
    GraphMotionSlidingSettings sliding;if (!sliding.Load(data,error)) return false;sliding_settings=sliding;
    GraphMotionFeedbackSettings feedback;if (!LoadGraphMotionFeedbackSettings(data,feedback,error)) return false;feedback_settings=feedback;
    MotionGraphPrelandingConditionSettings prelanding;if (!prelanding.Load(data,error)) return false;prelanding_condition_settings=prelanding;
    GraphMotionPushSettings push;if (!push.Load(data,animation.tree.Metadata(),error)) return false;pushing=std::move(push);
    operations=std::move(parsed);capabilities=std::move(report);remap_=compiled.operations;
    parents_.clear();for (const auto& state:binding.states) parents_.push_back(state.parent);
    automatic_fakie_conditions_.assign(binding.operations.size(),false);
    const std::vector<std::string> automatic{"Motion","OnBoard","OnGround","RidingIdle","Riding","Turning","Switch"};
    for (const auto& transition:binding.transitions) if (transition.target && transition.expression)
    {
        std::vector<std::string> names;auto cursor=transition.target;
        while (cursor) {names.push_back(binding.states[*cursor].name);cursor=binding.states[*cursor].parent;}
        std::reverse(names.begin(),names.end());if (names==automatic) MarkFakie(binding,*transition.expression,automatic_fakie_conditions_);
    }
    instances.clear();for (auto operation:remap_.behaviors) instances.push_back(InstanceFor(operations[operation]));
    next_instance_=1;condition_random=MotionConditionRandom{};physical={};flags={};trick_requests={};riding={};push_state=MotionGraphPushState{};
    slide_latch={};is_power_sliding=false;applying_body_tilt=false;hold_fakie=false;busy_hands={};keep_shove_channels=false;animation_phase=0;
    feedback_owner={};score_packet={};moving_objects={};trick_height_settings={true,true};
    push_physical.reset();gesture_physical.reset();gesture_publication.reset();shove_physical.reset();
    turning_physical.reset();crouching_physical.reset();body_tilt_physical.reset();fakie_physical.reset();pumping_acceleration.reset();deck_yaw_pitch.reset();
    riding_condition_inputs.reset();grind_condition_inputs.reset();landing_inputs.reset();wipeout_condition_inputs.reset();prelanding_inputs.reset();
    action_controls={};action_intents.Clear();turning_output={};state_requests.clear();time_tags.reset();errors.clear();diagnostics_overflowed=false;
    ground_projected_speed.reset();deck_velocity.reset();reckoning_z.reset();reckoning_ground.reset();error.clear();return true;
}
void MotionGraphHost::AcceptActionGraph(const MotionGraphInput& input)
{
    assert(input.tick==input.action.tick);errors.clear();diagnostics_overflowed=false;
    turning_output=input.action.turning;state_requests=input.action.state_requests;action_controls=input.action.controls;
    action_intents=input.action.controls.authored_values;animation.AcceptMotionEffects(input.action.motion_effects);
}
void MotionGraphHost::AddError(std::string error)
{if (errors.size()<64) errors.push_back(std::move(error));else diagnostics_overflowed=true;}
std::string MotionGraphHost::Diagnostics(std::string_view separator) const
{
    std::string text;for (const auto& error:errors) {if (!text.empty()) text+=separator;text+=error;}
    if (diagnostics_overflowed) {if (!text.empty()) text+=separator;text+="graph diagnostics truncated after 64 entries";}return text;
}
MotionConditionContext MotionGraphHost::ConditionContext()
{return {animation,action_controls,action_intents,physical,riding,flags,trick_requests,slide_latch,playback_context,push_state,time_tags,parents_,condition_random};}
std::uint32_t MotionGraphHost::ConditionActivation(graph::Id condition,const graph::Frame& frame)
{
    if (condition>=remap_.conditions.size() || remap_.conditions[condition]>=operations.size()) {AddError("Unbound MotionGraph condition");return 0;}
    const auto id=remap_.conditions[condition];if (hold_fakie && automatic_fakie_conditions_[id]) return 0;
    const auto& operation=operations[id];bool result=false;std::string error;bool success=false;
    if (operation.kind==MotionGraphOperation::Kind::PhysicalCondition) success=operation.physical_condition.Evaluate({animation,physical,riding_condition_inputs},result,error);
    else if (operation.kind==MotionGraphOperation::Kind::SpecialCondition)
    {
        if (!prelanding_condition_settings) {AddError("MotionGraph special conditions require loaded settings");return 0;}
        success=operation.special_condition.Evaluate({grind_condition_inputs,landing_inputs,wipeout_condition_inputs,prelanding_inputs,*prelanding_condition_settings},result,error);
    }
    else if (operation.kind==MotionGraphOperation::Kind::Condition) success=operation.condition.Evaluate(ConditionContext(),frame,result,error);
    else {AddError("Unsupported MotionGraph condition "+operation.name);return 0;}
    if (!success) {AddError(std::move(error));return 0;}return result;
}
std::uint32_t MotionGraphHost::Allocate(graph::Id behavior,const graph::Frame&)
{
    if (behavior<remap_.behaviors.size()) instances[behavior]=InstanceFor(operations[remap_.behaviors[behavior]]);
    const auto handle=next_instance_;++next_instance_;if (next_instance_==0) next_instance_=1;return handle;
}
void MotionGraphHost::Run(graph::Id behavior,const graph::Frame& frame,std::uint8_t phase)
{
    if (behavior>=remap_.behaviors.size() || remap_.behaviors[behavior]>=operations.size()) {AddError("MotionGraph behavior "+std::to_string(behavior)+": Unbound MotionGraph behavior");return;}
    std::string error;if (!Execute(behavior,operations[remap_.behaviors[behavior]],frame,phase,error)) AddError("MotionGraph behavior "+std::to_string(behavior)+": "+error);
}
void MotionGraphHost::Begin(graph::Id id,graph::Context,const graph::Frame& frame) {Run(id,frame,0);}
void MotionGraphHost::Update(graph::Id id,graph::Context,const graph::Frame& frame) {Run(id,frame,1);}
void MotionGraphHost::End(graph::Id id,graph::Context,const graph::Frame& frame) {Run(id,frame,2);}
bool MotionGraphHost::SlideDirection(float& output,std::string& error) const
{
    if (!deck_velocity) {error="Slide direction requires actual Motion80 velocity";return false;}
    if (!physical.foot_frame) {error="Slide direction requires actual Motion273 orientation flag";return false;}
    if (!reckoning_z) {error="Slide direction requires actual Reckoning Ground Z";return false;}
    output=GraphMotionSlideDirection(*deck_velocity,*reckoning_z,physical.foot_frame->skateboard_flipped);return true;
}
bool MotionGraphHost::Execute(graph::Id behavior,const MotionGraphOperation& op,const graph::Frame& frame,std::uint8_t phase,std::string& error)
{
    if (behavior>=instances.size()) {error="Unallocated MotionGraph behavior";return false;}
    auto& instance=instances[behavior];using K=MotionGraphOperation::Kind;
    const auto set=[&](AttributeName name,float value){animation.SetAttribute({name,value,false,-1});};
    switch (op.kind)
    {
    case K::Feedback:
    {
        auto* state=std::get_if<GraphMotionFeedbackInstance>(&instance);if (!state) {error="Physical feedback instance was not allocated";return false;}
        if (!feedback_settings) {error="Physical feedback requires original settings";return false;}
        GraphMotionFeedbackContext context{animation,feedback_owner,slide_latch,*feedback_settings};
        context.turning=turning_physical?&*turning_physical:nullptr;context.crouching=crouching_physical?&*crouching_physical:nullptr;
        context.body_tilt=body_tilt_physical?&*body_tilt_physical:nullptr;context.fakie=fakie_physical?&*fakie_physical:nullptr;
        context.pumping_acceleration=pumping_acceleration?&*pumping_acceleration:nullptr;context.deck_yaw_pitch=deck_yaw_pitch?&*deck_yaw_pitch:nullptr;
        context.mirrored=playback_context.is_mirrored;context.doing_trick=flags.doing_trick;context.is_power_sliding=is_power_sliding;context.applying_body_tilt=applying_body_tilt;
        return ExecuteGraphMotionFeedbackOperation(op.feedback,*state,phase,frame,context,error);
    }
    case K::Score:return op.score.Execute({animation,condition_random,score_packet,moving_objects,playback_context,trick_height_settings},phase,error);
    case K::Push:
    {
        auto* state=std::get_if<GraphMotionPushInstance>(&instance);if (!state) {error="Push operation/instance mismatch";return false;}
        if (!pushing) {error="Push operations require loaded stock pushing settings";return false;}
        return op.push.Execute(*state,{*pushing,push_state,animation,push_physical,riding.time_since_teleport,frame.dt},phase,error);
    }
    case K::CharacterGesture:
    {
        auto* state=std::get_if<MotionGraphCharacterGestureState>(&instance);if (!state) {error="CharacterGesture operation/instance mismatch";return false;}
        const auto category=physical.conditions.physical_state?std::optional<std::uint32_t>(physical.conditions.physical_state->category):std::nullopt;
        const auto height=crouching_physical?std::optional<float>(crouching_physical->animation_height_72):std::nullopt;
        return ExecuteMotionGraphCharacterGesture(*state,{animation,busy_hands,gesture_physical,category,playback_context,height,gesture_publication},phase,error);
    }
    case K::EndGesture:
        if (phase==0) {for (auto& entry:instances) if (auto* state=std::get_if<MotionGraphCharacterGestureState>(&entry)) state->End(animation);gesture_publication.reset();}break;
    case K::Shove:
    {
        auto* state=std::get_if<MotionGraphShoveState>(&instance);if (!state) {error="Shove operation/instance mismatch";return false;}
        return ExecuteGraphMotionShoveOperation(op.shove,*state,{animation,shove_physical,busy_hands,playback_context,keep_shove_channels},phase,error);
    }
    case K::Unsupported:error="Unsupported MotionGraph Behavior "+op.name;return false;
    case K::Unported:error="Unported C++ MotionGraph behavior "+op.name;return false;
    case K::SourceMissingProducer:error="MotionGraph stock gameplay producer "+op.name+" is not implemented";return false;
    case K::PrintText:case K::SourceStandingOnCarNoop:break;
    case K::Animation:
    {auto* state=std::get_if<MotionAnimationOperationState>(&instance);if (!state) {error="Animation operation/instance mismatch";return false;}return ExecuteMotionAnimationOperation(op.animation,*state,phase,playback_context,animation,error);}
    case K::Attach:op.attach.Execute(phase,animation.motion_intents,[&](auto name,float value){animation.EmitPacket(name,value);},set);break;
    case K::IntentFilter:
    {auto* state=std::get_if<MotionIntentFilterState>(&instance);if (!state) {error="Intent filter instance was not allocated";return false;}return op.filter.Execute(phase,*state,animation.motion_intents,animation.filtered_intents,frame.dt,animation.tree.skater_animation_flags,error);}
    case K::GrabType:
    {
        MotionGrabType grab;if (op.text=="FS") grab=MotionGrabType::Fs;else if (op.text=="BS") grab=MotionGrabType::Bs;else if (op.text=="Nose") grab=MotionGrabType::Nose;else if (op.text=="Tail") grab=MotionGrabType::Tail;
        else {error="SetGrabType has unknown grab type \""+op.text+"\"";return false;}
        if (phase==0) animation.SetGrabType(grab);else if (phase==2) animation.ClearGrabType();break;
    }
    case K::Dark:riding.dark=phase!=2;if (phase==1) animation.EmitPacket(EncodeAnimationName("IsDark"),1);break;
    case K::MonitorUnderflip:
    {
        auto* updates=std::get_if<std::int32_t>(&instance);if (!updates) {error="Trick operation/instance mismatch";return false;}
        if (phase==0) *updates=0;else if (phase==2) trick_requests={};else
        {
            *updates=Signed(std::uint32_t(*updates)+1);if (*updates>1)
            {
                const std::array<std::string_view,10> names{{"U_L_F_Kickflip","U_L_F_Heelflip","U_L_B_Kickflip","U_L_B_Heelflip","U_Nollie","U_Fingerflip","U_Kickflip","U_Heelflip","U_N_Kickflip","U_N_Heelflip"}};
                if (std::any_of(names.begin(),names.end(),[&](auto name){return animation.motion_intents.Contains(name);})) trick_requests.underflip=true;
                else if (animation.motion_intents.Contains("DarkCatch")) trick_requests.dark_catch=true;
            }
        }break;
    }
    case K::Anticipating:if (phase!=1) flags.anticipating=phase==0;break;
    case K::Landing:if (phase!=1) flags.landing=phase==0;break;
    case K::Manualing:if (phase!=1) flags.manualing=phase==0;break;
    case K::DoingTrick:if (phase!=1) flags.doing_trick=phase==0;break;
    case K::DisableTricks:
    {
        auto* state=std::get_if<MotionGraphLandingInstance>(&instance);if (!state) {error="Landing operation/instance mismatch";return false;}
        if (phase==0) {flags.tricks_allowed=false;state->value=op.value;state->complete=false;}
        else if (phase==1) {if (!state->complete) {state->value-=frame.dt;if (state->value<0) {flags.tricks_allowed=true;state->complete=true;}}}
        else flags.tricks_allowed=true;break;
    }
    case K::ManualOutTimer:
        if (phase==2) riding.manual_out_timer=0;else if (phase==1 && !flags.manualing) {const auto remaining=riding.manual_out_timer-frame.dt;riding.manual_out_timer=remaining>=0?remaining:0;}break;
    case K::SetManualOutTimer:if (phase==2) riding.manual_out_timer=op.value;break;
    case K::TimeSinceTeleport:
        if (phase==1) {if (!physical.conditions.physical_state) {error="UpdateTimeSinceTeleport needs filtered physical state";return false;}if (physical.conditions.physical_state->category==5) riding.time_since_teleport=0;else riding.time_since_teleport+=frame.dt;}break;
    case K::TimeSinceKickturn:if (phase==1) riding.time_since_kickturn+=frame.dt;break;
    case K::ResetKickturn:if (phase==0 || phase==2) riding.time_since_kickturn=0;break;
    case K::DistComToBoard:
        if (phase==0)
        {
            float height;if (op.set_manually) height=Float(0x3f266666);else {if (!physical.animation_height_72) {error="SetDistComToBoard requires actual PhysOutAnimation distance";return false;}height=*physical.animation_height_72;}
            float correction=0;if (op.adjust_for_velocity) {const auto v=frame.dt*riding.last_good_landing_velocity,cap=Float(0x3e19999a);correction=cap-v>=0?v:cap;}set(op.attribute,height-correction);
        }break;
    case K::ForcePhysics:if (phase==0) riding.force_mode=op.ordinal;break;
    case K::SetSpeed:
        if (phase==1) {if (!op.optional_value && !crouching_physical) {error="SetSpeed requires actual ground-projected speed";return false;}set(op.attribute,std::abs(op.optional_value?*op.optional_value:crouching_physical->body_164));}break;
    case K::ApplyingBodyTilt:if (phase==0) applying_body_tilt=true;else if (phase==2) applying_body_tilt=false;break;
    case K::ResetAnimation:case K::ResetGivenStance:
        if (phase==0)
        {
            if (op.kind==K::ResetAnimation)
            {action_intents.Clear();action_controls={};flags={};is_power_sliding=false;riding.last_good_landing_velocity=0;riding.manual_out_timer=0;busy_hands={};gesture_publication.reset();animation.ResetFromStock();}
            else if (!animation.ResetToGivenStance(error)) return false;
            playback_context.is_mirrored=animation.tree.skater_animation_flags?std::optional<bool>((*animation.tree.skater_animation_flags&0x40000000)!=0):std::nullopt;
            playback_context.is_switch=animation.relative_stance==1;
        }break;
    case K::HandBusy:if (phase==0) ++busy_hands[op.ordinal];else if (phase!=1) --busy_hands[op.ordinal];break;
    case K::MaintainShove:
        if (phase==1) keep_shove_channels=true;else if (phase==2) {keep_shove_channels=false;if (animation.channels.Has("SkitchAntic")) animation.channels.End("SkitchAntic");}break;
    case K::SlideUpdate:
        if (phase==1)
        {
            if (!physical.conditions.physical_state) {error="PowerSliding requires actual filtered physical category";return false;}
            if (!sliding_settings) {error="PowerSliding requires original anim_motion settings";return false;}
            const auto category=physical.conditions.physical_state->category;float speed=0,direction=0;
            if (category==1) {if (!ground_projected_speed) {error="PowerSliding requires actual Motion164 speed";return false;}speed=*ground_projected_speed;if (!SlideDirection(direction,error)) return false;}
            auto* state=std::get_if<GraphMotionSlidingState>(&instance);if (!state) {error="PowerSliding has an invalid instance";return false;}
            state->Update(animation.motion_intents,category,speed,direction,frame.dt,*sliding_settings,slide_latch);
        }break;
    case K::SlideCreate:
        if (phase==0) {if (!animation.tree.skater_animation_flags) {error="CreateSlide requires actual animation stance flags";return false;}slide_latch.BeginSlide((*animation.tree.skater_animation_flags&0x20000000)!=0);}
        else if (phase==1) {if (!sliding_settings) {error="CreateSlide requires original anim_motion settings";return false;}const auto values=CreateGraphMotionSlide(slide_latch,op.right,animation.MotionIntent("RightSlide"),animation.MotionIntent("LeftSlide"),*sliding_settings);animation.EmitPacket(EncodeAnimationName("slide"),values[0]);animation.EmitPacket(EncodeAnimationName("turn"),values[1]);}break;
    case K::SlideManual:if (phase==1) if (const auto value=animation.MotionIntent("Manual");value && *value<0) animation.EmitPacket(EncodeAnimationName("balance"),*value);break;
    case K::SlideDeceleration:
    {
        auto* previous=std::get_if<float>(&instance);if (!previous) {error="PowerSlideDecel has an invalid instance";return false;}
        if (phase==0) *previous=0;else if (phase==1)
        {
            if (!deck_velocity) {error="PowerSlideDecel requires actual Motion80 velocity";return false;}
            if (!reckoning_ground) {error="PowerSlideDecel requires actual Reckoning Ground frame";return false;}
            if (!sliding_settings) {error="PowerSlideDecel requires original anim_motion settings";return false;}
            set(EncodeAnimationName("decel"),GraphMotionSlideDeceleration(*previous,*deck_velocity,*reckoning_ground,*sliding_settings));
        }break;
    }
    case K::SlideSpin:if (phase==0) {float direction;if (!SlideDirection(direction,error)) return false;if (!sliding_settings) {error="PowerSlideSpin requires original anim_motion settings";return false;}set(EncodeAnimationName("slidespin"),GraphMotionSlideSpin(direction,*sliding_settings));}break;
    case K::SlideCandidate:if (phase!=1) slide_latch.SetCandidateEnabled(phase==0);break;
    case K::PowerSlidingFlag:if (phase!=1) is_power_sliding=phase==0;break;
    case K::WeightOnNose:
        if (phase!=1) {if (!animation.tree.skater_animation_flags) {error="UpdateIsWeightOnNose requires live ISkaterAnim";return false;}auto& value=*animation.tree.skater_animation_flags;value=(value&~0x10000000u)|(phase==0?0x10000000u:0);}break;
    case K::ClearTrickAttribute:
        if (phase==2) {auto& values=animation.tree.construction_values;const auto key=EncodeAnimationName("Trick");values.erase(std::remove_if(values.begin(),values.end(),[&](const auto& entry){return entry.first==key;}),values.end());}break;
    case K::JumpInto:
    {
        auto* state=std::get_if<MotionGraphJumpInstance>(&instance);if (!state) {error="JumpInto instance was not allocated";return false;}
        if (phase==1 && state->first_update) {if (!animation.JumpInto(op.attribute,error)) return false;state->first_update=false;}break;
    }
    default:error="Invalid MotionGraph behavior instance "+op.name;return false;
    }
    return true;
}
void MotionGraphHost::Hook(graph::Id hook,const graph::Frame&)
{
    if (hook>=remap_.hooks.size() || remap_.hooks[hook]>=operations.size()) {AddError("Unsupported MotionGraph hook None");return;}
    const auto& op=operations[remap_.hooks[hook]];using K=MotionGraphOperation::Kind;
    if (op.kind==K::GrabSlideHook) slide_latch.Grab(op.right);
    else if (op.kind==K::OverrideHook) playback_context.transition_override=op.transition;
    else if (op.kind==K::MongoPushHook)
    {
        ChannelSettings settings;settings.priority=0;settings.keep_alive=false;settings.mirrored=false;settings.speed=1;
        settings.blend_in=Float(0x3dcccccd);settings.hold_during_blend_in=false;settings.blend_out=Float(0x3d8f5c29);
        settings.hold_during_blend_out=false;settings.use_attributes=false;bool created;std::string error;
        if (!animation.NewChannel(op.text,op.text,settings,created,error)) AddError(std::move(error));
    }
    else AddError("Unsupported MotionGraph hook "+op.name);
}
}
