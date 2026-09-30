// SPDX-License-Identifier: Apache-2.0
#include "SkaterAnimation.h"
#include <cstring>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float FixedPhysicalStep() {const std::uint32_t word=0x3c888889;float value;std::memcpy(&value,&word,4);return value;}
}
SkaterAnimation::SkaterAnimation(std::shared_ptr<const AnimationSource> value,const AnimationStockGraphs& graphs):
    animation(value->metadata),motion(animation),evaluator(value->evaluator),source(std::move(value)),
    action_controller(graphs.action.runtime.program.topology.states.size()),
    motion_controller(graphs.motion.runtime.program.topology.states.size()),state(true) {}
bool SkaterAnimation::FromSource(const SettingsDatabase& data,const AnimationStockGraphs& graphs,
    std::string_view pro_skater,std::shared_ptr<const AnimationSource> source,
    std::unique_ptr<SkaterAnimation>& output,std::string& error)
{
    if (!source||!source->evaluator) {error="Missing native animation source";return false;}
    auto owner=std::unique_ptr<SkaterAnimation>(new SkaterAnimation(std::move(source),graphs));
    owner->motion.playback_context={owner->state.Switch(),owner->state.Mirrored(),std::nullopt,EncodeAnimationName(pro_skater),std::nullopt};
    if (!owner->motion.FromGraph(graphs.motion.source,graphs.motion.binding,graphs.motion.runtime,data,error)) {error="Stock MotionGraph initialization: "+error;return false;}
    std::vector<std::string> names;std::vector<std::int32_t> mirror;
    for (const auto& bone:owner->evaluator->frames.rig.bones) {names.push_back(bone.name);mirror.push_back(bone.mirror);}
    if (!owner->animation.tree.SetHierarchy(names,mirror,error)) return false;
    for (const auto posture:{PosturePose::Stiff,PosturePose::Slouch,PosturePose::Buff})
    {
        const auto name=PosturePoseName(posture);const auto pose=owner->evaluator->frames.NamedPose(name,error);if (!pose) return false;
        if (pose->samples.size()!=names.size()) {error="Stock posture "+std::string(name)+" has "+std::to_string(pose->samples.size())+" bones; skater hierarchy has "+std::to_string(names.size());return false;}
    }
    owner->animation.tree.posture_bank_valid=true;owner->animation.tree.skater_animation_flags=owner->state.flags;
    if (!owner->action.FromGraph(graphs.action.source,graphs.action.binding,graphs.action.runtime,data,error)) {error="Stock ActionGraph initialization: "+error;return false;}
    owner->packet.bone_count=std::uint32_t(names.size());owner->packet.hierarchy.assign(names.size(),AnimationResetPose);owner->packet.local.assign(names.size(),AnimationResetPose);owner->packet.timestep=FixedPhysicalStep();
    output=std::move(owner);error.clear();return true;
}
void SkaterAnimation::SetCustomisation(std::uint32_t natural,std::uint32_t style)
{
    if (natural<=1&&state.publication.natural_stance!=std::int32_t(natural)) {state.publication.natural_stance=std::int32_t(natural);state.flags^=0xc0000000;}
    const std::string_view name=style==1?"Loose":style==2?"Gonzo":style==3?"Aggressive":"";
    motion.playback_context.pro_skater=EncodeAnimationName(name);
}
bool SkaterAnimation::EvaluateInitialPose(std::vector<Mat4>& output,std::string& error)
{
    PoseCommand command;command.kind=PoseCommand::Kind::Pose;command.name="RIG_TPOSE";std::vector<Sqt> evaluated;
    if (!evaluator->Evaluate({command},evaluated,error)) return false;pose=std::move(evaluated);return evaluator->Hierarchy(pose,output,error);
}
bool SkaterAnimation::PublishPhysical(const AnimationPhysical& p,std::string& error)
{
    animation.natural_stance=std::uint32_t(state.publication.natural_stance);animation.relative_stance=std::uint32_t(state.publication.relative_stance);
    if (!p.conditions.speeds) {error="Animation requires completed board speed output";return false;}
    const auto stance=Stance();action.stance=atelier::skate::Stance{stance.first,stance.second};action.condition_inputs=p.conditions;motion.physical.conditions=p.conditions;
    motion.playback_context.is_mirrored=state.Mirrored();motion.playback_context.is_switch=state.Switch();motion.playback_context.board_available=p.board_present;
    completed_physical=p;motion.physical.physical_stance=p.physical_stance;motion.physical.foot_frame=p.foot_frame;motion.physical.animation_height_72=p.feedback.crouching.animation_height_72;
    motion.ground_projected_speed=p.fakie.ground_projected_speed;motion.deck_velocity=p.fakie.deck_velocity;
    const bool board_attached_or_onboard=p.board_present||!p.physical_28_byte75;
    state.flags=(state.flags&~(std::uint32_t(1)<<17))|(std::uint32_t(board_attached_or_onboard)<<17);animation.tree.skater_animation_flags=state.flags;error.clear();return true;
}
bool SkaterAnimation::Advance(const AnimationStockGraphs& graphs,float dt,const IntentMap& action_intents,
    const AnimationPhysical& physical,AnimationAdditionalResetFields& reset_fields,std::string& error)
{
    const auto tick=ticks;if (!PublishPhysical(physical,error)) return false;
    action.PrepareInput(ActionGraphInput{tick,action_intents,animation.motion_intents,animation.tree.tree_attributes});action.is_tricking=motion.flags.doing_trick;
    action_controller.Update(graphs.action.runtime.program,dt,action);
    if (!action.errors.empty()||action.diagnostics_overflowed) {error=action.Diagnostics("\n");return false;}
    const auto action_output=action.Output();animation.BeginGraphUpdate();motion.AcceptActionGraph(MotionGraphInput{action_output.tick,action_output});motion.animation_phase=state.phase;
    motion_controller.Update(graphs.motion.runtime.program,dt,motion);state.phase=motion.animation_phase;
    if (!motion.errors.empty()||motion.diagnostics_overflowed) {error=motion.Diagnostics("\n");return false;}
    if (!animation.tree.skater_animation_flags) {error="MotionGraph lost the SkaterAnim flag owner";return false;}
    state.flags=*animation.tree.skater_animation_flags;state.publication.relative_stance=std::int32_t(animation.relative_stance);
    const bool reset_action=animation.reset_action_intents;animation.reset_action_intents=false;if (reset_action) action.action_intents.Clear();
    if (!animation.ApplyParameters(error)||!animation.Advance(dt,state.phase,error)||!animation.RefreshTreeAttributes(error)) return false;
    state.ApplyStanceEvents(animation.tree.tree_attributes);std::vector<PoseCommand> commands;
    if (!animation.EvaluatePose({state.CullThreshold(),true},commands,error)) return false;
    std::vector<Sqt> evaluated;if (!evaluator->Evaluate(commands,evaluated,error)) return false;pose=std::move(evaluated);
    std::vector<Mat4> hierarchy;if (!evaluator->Hierarchy(pose,hierarchy,error)) return false;std::vector<Mat4> local;local.reserve(pose.size());for (const auto& sample:pose) local.push_back(SqtToMatrix(sample));
    attributes.ReplaceFrom(animation.motion_attributes,animation.tree.tree_attributes);state.PreparePublication();
    if (!ResetAnimationPacket(packet,reset_fields,error)) {error="Animation packet reset: "+error;return false;}
    std::int32_t publication_result;
    if (!PublishAnimationEvaluated(state.publication,hierarchy,local,packet,double(FixedPhysicalStep()),"signup",publication_result,error)) {error="Skater pose publication: "+error;return false;}
    state.FinishPublication();animation.tree.skater_animation_flags=state.flags;++ticks;error.clear();return true;
}
}
