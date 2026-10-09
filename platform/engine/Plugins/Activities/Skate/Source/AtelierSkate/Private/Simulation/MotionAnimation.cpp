#include "MotionAnimation.h"
#include <algorithm>
#include <cstring>
#include <filesystem>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
std::string Upper(std::string_view input) {std::string s(input);for (auto& c:s) if (c>='a'&&c<='z') c=char(c-'a'+'A');return s;}
float Float(std::uint32_t bits) {float f;std::memcpy(&f,&bits,4);return f;}
}
MotionAnimation::MotionAnimation(AnimationMetadata metadata):tree(std::move(metadata)) {}
void MotionAnimation::BeginGraphUpdate() {motion_attributes.clear();}
void MotionAnimation::AcceptMotionEffects(const IntentMap& values) {motion_intents=values;}
void MotionAnimation::EmitPacket(AttributeName name,float value) {motion_attributes.push_back({name,value});}
void MotionAnimation::Attach(std::string_view intent,AttributeName name,bool set)
{if (const auto value=MotionIntent(intent)) {EmitPacket(name,*value);if (set) SetAttribute({name,*value,false,-1});}}
void MotionAnimation::SetGrabType(MotionGrabType value) {grab_type=value;EmitPacket(EncodeAnimationName("GrabType"),float(std::uint32_t(value)+1));}
void MotionAnimation::ClearGrabType() {grab_type.reset();}
bool MotionAnimation::CurrentTime(float& output,std::string& error) const
{if (!tree.current) {error="No current animation tree";return false;}output=tree.current->Time();error.clear();return true;}
bool MotionAnimation::CurrentLength(float& output,std::string& error) const
{if (!tree.current) {error="No current animation tree";return false;}output=tree.current->Length();error.clear();return true;}
bool MotionAnimation::InTransition() const {return tree.current&&tree.current->HasTransition();}
void MotionAnimation::SynchronizeAirTime(float fraction) {if (tree.current) tree.current->SetTime(tree.current->Length()*fraction);}
bool MotionAnimation::JumpInto(AttributeName name,std::string& error)
{
    if (!ApplyParameters(error)) return false;if (!tree.current) {error="JumpInto requires a current animation tree";return false;}
    auto attribute=MotionGraphAttribute{name,0}.ToAnimation();bool found;
    if (!tree.current->QueryAttribute(name,31,attribute,found,error)) return false;if (found) tree.current->SetTime(attribute.begin_time);error.clear();return true;
}
bool MotionAnimation::NewChannel(std::string_view name,std::string_view animation,ChannelSettings settings,bool& created,std::string& error)
{
    created=false;if (channels.Has(name)) {error.clear();return true;}AnimationTree motion;if (!tree.BuildTree(animation,motion,error)) return false;motion.SetSpeed(settings.speed);AnimationTree bound;
    if (!AddAnimationBindPose(std::move(motion),std::nullopt,tree.skater_animation_flags,tree.attribute_mirror,bound,error)) return false;
    if (settings.mirrored&&!bound.AppendBindPoseMirrorMode(2,error)) return false;channels.Insert(std::string(name),std::move(bound),settings);created=true;error.clear();return true;
}
bool MotionAnimation::TransitionChannel(std::string_view name,std::string_view animation,ChannelSettings settings,TransitionSettings transition,bool resurrect,bool create_missing,bool& transitioned,std::string& error)
{
    transitioned=false;if (!channels.Has(name)) {if (create_missing) return NewChannel(name,animation,settings,transitioned,error);error.clear();return true;}
    if (!channels.CanTransition(name,resurrect)) {error.clear();return true;}AnimationTree motion;if (!tree.BuildTree(animation,motion,error)) return false;motion.SetSpeed(settings.speed);AnimationTree bound;
    if (!AddAnimationBindPose(std::move(motion),std::nullopt,tree.skater_animation_flags,tree.attribute_mirror,bound,error)) return false;
    if (settings.mirrored&&!bound.AppendBindPoseMirrorMode(2,error)) return false;channels.Transition(name,std::move(bound),settings,transition,resurrect);transitioned=true;error.clear();return true;
}
void MotionAnimation::ResetFromStock()
{
    tree.current.reset();tree.current_name.reset();channels.ResetFromStock();grab_type.reset();motion_intents.Clear();filtered_intents.Clear();motion_attributes.clear();tree.tree_attributes.clear();tree.settable.Clear();
    if (tree.skater_animation_flags) *tree.skater_animation_flags&=0x0ff7ffff;relative_stance=0;reset_action_intents=true;tree.property={false,-1,-1};
}
bool MotionAnimation::ResetToGivenStance(std::string& error)
{
    if (!tree.skater_animation_flags) {error="Stance reset requires SkaterAnim flags";return false;}
    auto& flags=*tree.skater_animation_flags;
    if ((natural_stance!=1||requested_stance!=0)&&(natural_stance!=0||requested_stance!=1)) {flags|=0xc0000000;relative_stance=std::uint32_t(natural_stance!=0);}
    else {flags&=0x3fffffff;relative_stance=std::uint32_t(natural_stance!=1);}requested_stance=0;error.clear();return true;
}
bool MotionAnimation::StockClipTranslationZ(std::string_view database,std::string_view animation,float& output,std::string& error) const
{
    const auto& metadata=tree.Metadata();const auto* source=metadata.SourceFor(animation);output=0;
    if (!source||Upper(std::filesystem::path(source->source_bank).stem().string())!=Upper(database)) {error.clear();return true;}
    const auto* clip=metadata.Clip(animation,error);if (!clip) return false;
    const auto attribute=std::find_if(clip->attributes.begin(),clip->attributes.end(),[](const auto& a){return Upper(a.name)=="ANIMTRANSZ";});if (attribute==clip->attributes.end()) {error.clear();return true;}
    if (attribute->type_id==0||attribute->type_id==1||attribute->type_id==3) {if (attribute->payload_words.empty()) {error=std::string(database)+"/"+std::string(animation)+": truncated AnimTransZ";return false;}output=Float(attribute->payload_words[0]);}
    else if (attribute->type_id==2) return SampleAnimationCurve(attribute->payload_words,0,output,error);error.clear();return true;
}
bool MotionAnimation::Advance(float dt,float phase,std::string& error)
{channels.Retire();if (!tree.Advance(dt,phase,error)) return false;return channels.Advance(dt,phase,error);}
bool MotionAnimation::ApplyParameters(std::string& error)
{
    const auto attributes=tree.settable.Entries();
    if (tree.current&&!tree.current->PrepareSelectionSpaces(attributes,error)) return false;
    if (!channels.PrepareSelectionSpaces(attributes,error)) return false;
    if (tree.current) {bool changed;if (!tree.current->SetAttributes(attributes,changed,error)) return false;}
    if (!channels.SetAttributes(attributes,error)) return false;tree.settable.Clear();error.clear();return true;
}
bool MotionAnimation::EvaluatePose(AnimationEvaluation parameters,std::vector<PoseCommand>& output,std::string& error)
{if (!tree.EvaluatePose(parameters,output,error)) return false;return channels.Evaluate(parameters,output,error);}
bool MotionAnimation::RefreshTreeAttributes(std::string& error)
{
    std::vector<AnimationAttribute> base;if (tree.current&&!tree.current->Attributes(15,base,error)) return false;
    std::vector<AnimationAttribute> merged;if (!channels.Attributes(std::move(base),15,merged,error)) return false;tree.tree_attributes=std::move(merged);error.clear();return true;
}
std::optional<float> MotionAnimation::MotionIntent(std::string_view name) const {const auto* v=motion_intents.Get(name);return v?std::optional<float>(*v):std::nullopt;}
std::optional<float> MotionAnimation::FilteredIntent(std::string_view name) const {const auto* v=filtered_intents.Get(name);return v?std::optional<float>(*v):std::nullopt;}
bool MotionAnimation::LastAttribute(AttributeName name,std::optional<AnimationAttribute>& output,std::string& error)
{const auto i=std::find_if(tree.tree_attributes.begin(),tree.tree_attributes.end(),[&](const auto& a){return a.name==name;});output=i!=tree.tree_attributes.end()?std::optional<AnimationAttribute>(*i):std::nullopt;error.clear();return true;}
void MotionAnimation::SetAttribute(SettableAttribute value) {tree.settable.SetAttribute(value);}
void MotionAnimation::SetConstructionValue(AttributeName name,AttributeName value) {tree.SetConstructionValue(name,value);}
void MotionAnimation::SetPostureEnabled(bool enabled) {tree.posture.SetRequested(enabled);}
bool MotionAnimation::Play(const PlaybackRequest& request,bool& played,std::string& error) {return tree.Play(request,played,error);}
}
