// SPDX-License-Identifier: Apache-2.0
#include "GraphMotionGrindOperations.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float out;std::memcpy(&out,&bits,4);return out;}
float Bound(float value,float minimum,float maximum)
{value=minimum-value>=0.0f?minimum:value;return maximum-value>=0.0f?value:maximum;}
void Set(MotionAnimation& animation,AttributeName name,float value,bool normalized=false)
{animation.SetAttribute({name,value,normalized,-1});}
}
bool MotionGraphGrindSettings::Load(const SettingsDatabase& data,std::string& error)
{
    const auto get=[&](std::string_view key,std::string_view name,float& out)
    {
        const auto* field=data.Field("anim_motion",key,name);const auto value=field?field->Float():std::nullopt;
        if (!value) {error="Expected finite stock float at anim_motion/"+std::string(key)+"/"+std::string(name);return false;}out=*value;return true;
    };
    if (!get("grind_twist","twist_smoothing",fade.response) || !get("grind_twist","twist_sensitivity",fade.input_scale) ||
        !get("grind_twist","twist_max_delta_delta",fade.acceleration) || !get("grind_twist","twist_max_delta",fade.maximum_step) ||
        !get("grind_height","min_grind_disttocog",height[0]) || !get("grind_height","max_grind_disttocog",height[1]) ||
        !get("grind_height","grind_disttocog_speed",height[2]))
        return false;
    error.clear();
    return true;
}
float MotionGraphGrindFadeState::Begin(float low,float high,float twist)
{
    const auto initial=Bound(twist,low,high);*this={true,0,initial,initial,0,low,high};return initial;
}
std::optional<float> MotionGraphGrindFadeState::Update(float dt,float intent,MotionGraphGrindFadeSettings settings)
{
    if (just_began) {just_began=false;return std::nullopt;}elapsed+=dt;
    target=Bound(std::fma(settings.input_scale,intent,target),minimum,maximum);
    const auto desired=std::fma(1.0f-settings.response,value,target*settings.response);
    const auto next_step=Bound(desired-value,step-settings.acceleration,step+settings.acceleration);
    step=Bound(next_step,-settings.maximum_step,settings.maximum_step);
    value=Bound(value+step,minimum,maximum);return value;
}
bool MotionGraphGrindFacingBackwards(Vec3 n,Vec3 b,bool processed,bool mirrored)
{const auto side=std::fma(-n.x,b.z,n.z*b.x);return (!(side<=0.0f))^processed^mirrored;}
float MotionGraphGrindCrouch(float previous,float intent,float physical,float minimum,float maximum,float rate,float dt)
{
    const auto input=Bound(1.0f-intent,minimum,maximum),observed=Bound(1.0f-physical,minimum,maximum);
    const auto desired=input-observed>=0.0f?observed:input,step=dt*rate;return Bound(desired,previous-step,previous+step);
}
float MotionGraphGrindMirroredTwist(float twist,bool mirrored)
{if (!mirrored) return twist;const auto pi=Float(0x40490fdb);return twist>=0.0f?pi-twist:-pi-twist;}
bool MotionGraphGrindEndpoints(MotionAnimation& animation,AttributeName name,std::array<float,2>& output,std::string& error)
{
    output={0,0};
    for (std::size_t i=0;i<output.size();++i)
    {
        Set(animation,name,float(i),true);if (!animation.ApplyParameters(error)) return false;
        auto attribute=MotionGraphAttribute{name,0}.ToAnimation();bool found=false;
        if (!animation.tree.current) {error="GrindControlFade requires a current animation tree";return false;}
        if (!animation.tree.current->QueryAttribute(name,15,attribute,found,error)) return false;
        // Original ignores found, keeping partial output even on a miss.
        if (!attribute.payload[0]) {error="Grind twist query returned an uninitialized scalar";return false;}output[i]=Float(*attribute.payload[0]);
    }
    return true;
}
bool ParseGraphMotionGrindOperation(const GraphAttributes& attributes,GraphMotionGrindOperation& output,bool& recognized,std::string& error)
{
    const auto name=attributes.Text("name").value_or("");GraphMotionGrindOperation op;recognized=true;error.clear();
    if (name=="CreateGrindAttributes") op.kind=GraphMotionGrindOperation::Kind::Attributes;
    else if (name=="ControlGrindCrouch") {op.kind=GraphMotionGrindOperation::Kind::Crouch;op.height=EncodeAnimationName(attributes.Text("driveDistToCom").value_or("disttocog"));}
    else if (name=="GrindControlFade")
    {
        const auto height=attributes.Text("distBoardToCogAnimAttribute"),twist=attributes.Text("twistAnimAttribute"),intent=attributes.Text("twistMGIntent");
        if (!height || !twist || !intent) {error="GrindControlFade requires "+std::string(!height?"distBoardToCogAnimAttribute":!twist?"twistAnimAttribute":"twistMGIntent");return false;}
        op.kind=GraphMotionGrindOperation::Kind::Fade;op.height=EncodeAnimationName(*height);op.twist=EncodeAnimationName(*twist);op.intent=std::string(*intent);
    }
    else recognized=false;output=std::move(op);return true;
}
bool GraphMotionGrindOperation::Execute(MotionGraphGrindState& state,MotionAnimation& animation,const MotionGraphGrindSettings& settings,
    const std::optional<MotionGraphGrindPhysical>& physical,float dt,std::uint8_t phase,std::string& error) const
{
    using K=Kind;error.clear();if (kind==K::Unsupported) {error="Unbound MotionGraph grind operation";return false;}
    if (phase==2 || (phase==0 && kind==K::Attributes)) return true;
    if (!physical) {error="Grind graph requires completed physical grind observations";return false;}const auto& p=*physical;
    const auto mirror_needed=(phase==0 && kind==K::Fade)||(phase==1 && p.grinding && kind==K::Attributes);bool mirrored=false;
    if (mirror_needed) {if (!animation.tree.skater_animation_flags) {error="Grind graph requires live animation stance";return false;}mirrored=(*animation.tree.skater_animation_flags&0x40000000u)!=0;}
    switch (kind)
    {
    case K::Attributes:if (phase==1 && p.grinding) {animation.EmitPacket(p.grind_name,1);const auto back=MotionGraphGrindFacingBackwards(p.deck_velocity,p.effective_board_forward,p.processed_bit20,mirrored);animation.EmitPacket(EncodeAnimationName(back?"GrindFacingBackwards":"GrindFacingForwards"),1);}break;
    case K::Crouch:if (phase==0) state.height=p.animation_height;else if (phase==1) {if (!state.height) {error="ControlGrindCrouch Update before Begin";return false;}const auto next=MotionGraphGrindCrouch(*state.height,animation.MotionIntent("Crouch").value_or(0),p.physical_crouch,settings.height[0],settings.height[1],settings.height[2],dt);state.height=next;Set(animation,height,next);}break;
    case K::Fade:if (phase==0) {Set(animation,height,p.animation_height);std::array<float,2> bounds;if (!MotionGraphGrindEndpoints(animation,twist,bounds,error)) return false;MotionGraphGrindFadeState fade;const auto value=fade.Begin(bounds[0],bounds[1],MotionGraphGrindMirroredTwist(p.raw_skeleton_twist,mirrored));Set(animation,twist,value);state.fade=fade;}else if (phase==1) {if (!state.fade) {error="GrindControlFade Update before Begin";return false;}const auto value=state.fade->Update(dt,animation.MotionIntent(intent).value_or(0),settings.fade);if (value) Set(animation,twist,*value);}break;
    case K::Unsupported:break;
    }
    return true;
}
}
