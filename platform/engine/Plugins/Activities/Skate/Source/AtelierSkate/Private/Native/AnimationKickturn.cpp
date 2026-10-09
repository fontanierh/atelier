#include "AnimationKickturn.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float value;std::memcpy(&value,&bits,4);return value;}
float Bound(float value,float maximum) {const auto lower=-value>=0?0.0f:value;return maximum-lower>=0?lower:maximum;}
}
void AnimationKickturnState::Begin(const AnimationKickturnSettings& settings)
{*this={};previous_height=settings.height.Evaluate(0);}
AnimationKickturnOutput AnimationKickturnState::Update(float dt,float intent,AnimationKickturnOperation op,const AnimationKickturnSettings& settings)
{
    if (!first_update) elapsed+=dt;const auto phase=Bound(elapsed/animation_length,1.0f);
    const auto spin_curve=settings.spin.Evaluate(phase),height_curve=settings.height.Evaluate(phase);
    const auto sum=std::fma(height_curve,op.max_height,previous_height),height=Bound(sum*.5f,op.max_height);previous_height=height;
    if (intent!=0) last_nonzero_intent=intent;const auto sign=last_nonzero_intent>=0?1.0f:-1.0f;
    first_update=false;return {-height,(op.spin_scale*sign)*spin_curve};
}
bool LoadAnimationKickturnSettings(const SettingsDatabase& data,AnimationKickturnSettings& output,std::string& error)
{
    AnimationKickturnSettings settings;
    const auto curve=[&](std::string_view name,PointGraph<8>& value)
    {
        const auto field=data.Field("anim_motion","kickturn",name);const std::uint32_t* words;
        if (!field) {error="Missing stock field anim_motion/kickturn/"+std::string(name);return false;}
        if (!field->Words(20,words)) {error="Expected 20 big-endian words, found "+std::to_string(field->is_text?field->text.size():field->byte_count*2)+" bytes of hex";return false;}
        for (std::size_t i=0;i<8;++i) {value.x[i]=Float(words[4+i]);value.y[i]=Float(words[12+i]);}return true;
    };
    if (!curve("kickturn_spin",settings.spin)||!curve("kickturn_balance",settings.height)) return false;output=settings;error.clear();return true;
}
bool ParseAnimationKickturnOperation(const GraphAttributes& a,AnimationKickturnOperation& output,bool& recognized,std::string& error)
{
    recognized=a.Text("name")=="KickTurnSteering";error.clear();if (!recognized) return true;
    output={Float(a.FloatBits("maxHeight",0x3f000000)),Float(a.FloatBits("spinScale",0x3f000000))};return true;
}
bool ExecuteAnimationKickturnOperation(AnimationKickturnOperation op,AnimationKickturnState& state,const AnimationKickturnSettings& settings,
    MotionAnimation& animation,float dt,std::uint8_t phase,std::string& error)
{
    if (phase==0) state.Begin(settings);
    else if (phase==1)
    {
        if (state.first_update)
        {
            if (!animation.ApplyParameters(error)) return false;float length;
            if (!animation.CurrentLength(length,error)) return false;state.animation_length=length;
        }
        const auto output=state.Update(dt,animation.MotionIntent("KickTurn").value_or(0),op,settings);
        animation.EmitPacket(EncodeAnimationName("Balance"),output.balance);animation.EmitPacket(EncodeAnimationName("Spin"),output.spin);
    }
    error.clear();return true;
}
}
