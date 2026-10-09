#include "AnimationRidingAuxiliary.h"
#include "GraphMotionName.h"
#include "RidingAnimation.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float f;std::memcpy(&f,&bits,4);return f;}
}
std::array<float,2> AnimationBumpCoefficients(Vec4 acceleration,bool mirrored,const AnimationBumpSettings& settings)
{
    acceleration[0]*=settings.scale_x_acc;const float squared=Dot3(acceleration,acceleration);float inverse=ReciprocalSquareRootEstimate(squared);
    for (unsigned i=0;i<2;++i) {inverse=std::fma(inverse*0.5f,std::fma(-squared,inverse*inverse,1.0f),inverse);}
    const float magnitude=squared==0?0.0f:squared*inverse;
    const float ratio=(magnitude-settings.min_bump_mag)/(settings.max_bump_mag-settings.min_bump_mag);
    const float t=ratio<0?0.0f:ratio>1?1.0f:ratio;
    const float weight=std::fma(t,1.0f-settings.min_bump_blend_value,settings.min_bump_blend_value);
    std::array<float,2> direction=magnitude>Float(0x358637bd)?std::array<float,2>{acceleration[0]*inverse,acceleration[2]*inverse}:std::array<float,2>{0,0};
    for (auto& v:direction) {const float value=v*weight;v=mirrored?-value:value;}
    return direction;
}
bool LoadAnimationBumpSettings(const SettingsDatabase& data,AnimationBumpSettings& output,std::string& error)
{
    AnimationGroundAccelerationSettings ground;if (!LoadAnimationGroundAccelerationSettings(data,ground,error)) return false;
    AnimationBumpSettings settings{ground.scale_x_acc,ground.min_bump_mag,0,0};
    const auto scalar=[&](std::string_view name,float& value)
    {
        const auto field=data.Field("anim_motion","bumps",name);if (!field) {error="Missing stock field anim_motion/bumps/"+std::string(name);return false;}
        if (field->type!="EA::Reflection::Float") {error="Expected float at anim_motion/bumps/"+std::string(name);return false;}
        const std::uint32_t* words;if (!field->Words(1,words)) {error="Expected 1 big-endian words, found "+std::to_string(field->is_text?field->text.size():field->byte_count*2)+" bytes of hex";return false;}
        value=Float(words[0]);if (!std::isfinite(value)) {error="Non-finite stock float anim_motion/bumps/"+std::string(name);return false;}return true;
    };
    if (!scalar("max_bump_mag",settings.max_bump_mag)||!scalar("min_bump_blend_value",settings.min_bump_blend_value)) return false;
    output=settings;error.clear();return true;
}
bool AnimationFakieHeadState::Update(MotionAnimation& animation,bool manualing,bool power_sliding,bool fakie,std::string& error)
{
    const float target=manualing?1.0f:power_sliding?0.0f:0.5f;
    if (!was_fakie&&fakie)
    {
        const ChannelSettings settings{0,true,false,1,Float(0x3e99999a),false,Float(0x3e99999a),false,false};
        const TransitionSettings transition{2,Float(0x3dcccccd),0,0,false};bool transitioned;
        if (!animation.TransitionChannel("fakie","B_FAKIE_CHANNEL",settings,transition,true,true,transitioned,error)) return false;
        value=target;
    }
    else if (was_fakie&&!fakie) animation.channels.End("fakie");
    was_fakie=fakie;
    if (fakie)
    {
        const float delta=target-value,limit=Float(0x3c23d70a),lower=-limit-delta>=0?-limit:delta,change=limit-lower>=0?lower:limit;value+=change;
        animation.SetAttribute({EncodeAnimationName("torso"),value,false,-1});
    }
    error.clear();return true;
}
bool ParseGraphMotionAuxiliaryFeedbackOperation(const GraphAttributes& attributes,GraphMotionAuxiliaryFeedbackOperation& output,bool& recognized,std::string& error)
{
    recognized=false;const auto raw=attributes.Text("name");if (!raw) {error="MotionGraph operation has no name";return false;}const auto name=TrimMotionGraphName(*raw);GraphMotionAuxiliaryFeedbackOperation op;
    if (name=="SetBumpCoefficients") {op.kind=GraphMotionAuxiliaryFeedbackOperation::Kind::Bump;op.names={EncodeAnimationName(attributes.Text("X").value_or("BumpX")),EncodeAnimationName(attributes.Text("Y").value_or("BumpY"))};}
    else if (name=="FakieHeadChannel") op.kind=GraphMotionAuxiliaryFeedbackOperation::Kind::FakieHead;
    else {error.clear();return true;}
    output=std::move(op);recognized=true;error.clear();return true;
}
bool ExecuteGraphMotionAuxiliaryFeedbackOperation(const GraphMotionAuxiliaryFeedbackOperation& operation,
    AnimationFakieHeadState& state,std::uint8_t phase,MotionAnimation& animation,const AnimationBumpSettings& settings,
    const std::optional<Vec4>& acceleration,bool manualing,bool power_sliding,std::string& error)
{
    using K=GraphMotionAuxiliaryFeedbackOperation::Kind;
    if (operation.kind==K::Bump&&phase==0)
    {
        if (!acceleration) {error="SetBumpCoefficients requires completed acceleration";return false;}
        const auto flags=animation.tree.skater_animation_flags;if (!flags) {error="SetBumpCoefficients requires actual stance";return false;}
        const auto values=AnimationBumpCoefficients(*acceleration,(*flags&0x40000000)!=0,settings);
        for (std::size_t i=0;i<values.size();++i) animation.SetAttribute({operation.names[i],values[i],false,-1});
    }
    else if (operation.kind==K::FakieHead&&phase==1)
    {
        const auto flags=animation.tree.skater_animation_flags;if (!flags) {error="FakieHeadChannel requires actual animation flags";return false;}
        return state.Update(animation,manualing,power_sliding,(*flags&0x20000000)!=0,error);
    }
    else if (operation.kind==K::Unsupported) {error="Unsupported MotionGraph auxiliary feedback operation";return false;}
    error.clear();return true;
}
}
