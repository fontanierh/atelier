// SPDX-License-Identifier: Apache-2.0
#include "AnimationAirborne.h"
#include "GraphMotionName.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
float Maximum(float a,float b) {return a-b>=0?a:b;}
float Minimum(float a,float b) {return b-a>=0?a:b;}
float Clamp(float value,float low,float high) {const auto lower=low-value>=0?low:value;return high-lower>=0?lower:high;}
constexpr std::string_view Front="IA_BODYSPIN_OLLIE_FS_0_N",Back="IA_BODYSPIN_OLLIE_BS_0_N";
void Influence(float& value,float& delta,float target,float blend,const AnimationBodySpinSettings& s)
{
    const auto desired=std::fma(blend,target,(1.0f-blend)*value)-value;
    delta=Clamp(desired,delta-s.maximum_acceleration,delta+s.maximum_acceleration);
    const auto next=Clamp(value+delta,value-s.maximum_delta,value+s.maximum_delta);value=Clamp(next,0,1);
}
}
std::array<float,2> AnimationAirLegState::Update(AnimationAirLegBone bone,const AnimationAirLegPhysical& p,
    const AnimationAirLegSettings& s,float dt,const std::optional<AnimationAttribute>& initial,bool prepare)
{
    const bool ascending=p.com_velocity[1]>0;
    if (mode==0)
    {
        mode=ascending?1:2;
        if (initial) {if (initial->kind==0) height=Float(initial->payload[0].value_or(0));}
        else
        {
            const Vec4* toe=p.offboard_316||bone==AnimationAirLegBone::RightToe?&p.right_toe:bone==AnimationAirLegBone::LeftToe?&p.left_toe:nullptr;
            if (toe) {Vec4 delta;for (std::size_t i=0;i<4;++i) delta[i]=p.com_position[i]-(*toe)[i];height=Dot3(delta,p.system_up);}
            else height=p.animation_height;
        }
    }
    else if (mode==1&&p.com_velocity[1]>=0) height=Maximum(std::fma(-dt,s.going_up_speed,height),s.minimum_height);
    else if (mode==1||mode==2)
    {
        mode=2;
        if (prepare) {mode=3;height=std::fma(dt,s.preland_velocity,height);if (bone!=AnimationAirLegBone::Board) height*=s.offboard_multiplier;}
        else
        {
            const auto closing=-Dot3(p.com_velocity,p.system_up),vertical=std::abs(Dot3(p.system_up,Vec4{0,1,0,0}));
            auto speed=std::fma(Maximum(closing,0),vertical,(1.0f-vertical)*s.going_down_speed);speed=Minimum(speed,s.going_down_speed);
            height=Maximum(std::fma(-speed,dt,height),s.minimum_height);
        }
    }
    else if (mode==3) {height=std::fma(dt,s.preland_velocity,height);if (bone!=AnimationAirLegBone::Board) height*=s.offboard_multiplier;}
    descending_time=ascending?0:descending_time+dt;return {height,s.arm_extension.Evaluate(descending_time)};
}
bool AnimationAirLegPrepareToLand(bool query,const std::optional<AnimationAttribute>& full,
    const AnimationAirLegPhysical& p,const AnimationAirLegSettings& s)
{
    if (!query) return false;if (!full) return true;
    const auto extension=full->kind==0?Float(full->payload[0].value_or(0)):0.0f;
    if (extension<s.preland_final_height-Float(0x3dcccccd)) return true;
    const auto required=(extension-p.animation_height)/s.preland_velocity;return p.remaining_air_time-Float(0x3d75c28f)<required;
}
bool AnimationNearLanding(const MotionGraphPrelandingInputs& p,const AnimationBodySpinSettings& s)
{
    if (MotionGraphOverridePrelanding(p,s.prelanding)||p.com_velocity_y>=0) return false;
    if (p.offboard_316) return p.offboard_time_32<(s.final_height-s.on_deck_height)/s.height_velocity;
    if (p.air_437)
    {
        auto time=(s.final_height-p.animation_height_72)/s.height_velocity;time*=s.landing_distance.Evaluate(Clamp(p.air_normal_36,0,1));return p.air_remaining_184<time;
    }
    return p.offboard_319&&p.offboard_time_32<Float(0x3f99999a);
}
bool AnimationBodySpinState::Update(MotionAnimation& animation,std::uint32_t category,std::uint32_t physical_state,
    bool doing_trick,std::array<std::uint32_t,2> hands,bool mirrored,const std::optional<MotionGraphPrelandingInputs>& p,
    const AnimationBodySpinSettings& s,std::string& error)
{
    const bool biped_air=physical_state==503,air=category==2||biped_air,active=air||doing_trick,busy=hands[0]!=0||hands[1]!=0;
    auto spin=animation.MotionIntent("BodySpin").value_or(0);if (mirrored) spin=-spin;const auto mapped=s.map.Evaluate(std::abs(spin));const auto influence=spin>=0?mapped:-mapped;
    bool near=false;if (air) {if (!p) {error="BodySpin airborne branch requires actual prelanding physical outputs";return false;}near=AnimationNearLanding(*p,s);}
    auto next_mode=mode;
    switch (next_mode)
    {
    case 0:if (category==3) next_mode=4;if (active) next_mode=busy?4:1;break;
    case 1:if (!active) next_mode=0;if (busy) next_mode=4;if (std::abs(spin)>Float(0x3e99999a)) next_mode=2;break;
    case 2:if (!active) next_mode=0;if (busy) next_mode=4;if (air) next_mode=3;break;
    case 3:if (busy||(near&&biped_air)) next_mode=4;if (!air) next_mode=0;break;
    case 4:if (!active&&category==1) next_mode=0;break;
    default:break;
    }
    switch (next_mode)
    {
    case 0:case 4:for (const auto name:{Front,Back}) animation.channels.EndWith(name,Float(0x3e4ccccd),false);break;
    case 1:front=0;front_delta=0;back=0;back_delta=0;break;
    case 2:case 3:
        if (next_mode==2)
        {
            const ChannelSettings channel{0,false,false,1,Float(0x3e4ccccd),false,Float(0x3e99999a),false,false};
            if (spin>Float(0x3e99999a))
            {
                if (!animation.channels.Has(Front)&&!near) {bool created;if (!animation.NewChannel(Front,Front,channel,created,error)) return false;}
                animation.channels.EndWith(Back,Float(0x3e19999a),false);
            }
            if (spin<Float(0xbe99999a))
            {
                if (!animation.channels.Has(Back)&&!near) {bool created;if (!animation.NewChannel(Back,Back,channel,created,error)) return false;}
                animation.channels.EndWith(Front,Float(0x3e19999a),false);
            }
        }
        if (animation.channels.Has(Front)) {const auto target=Clamp(influence,0,1),blend=target<front?s.blend_out:s.blend_in;Influence(front,front_delta,target,blend,s);animation.channels.Influence(Front,front);}
        if (animation.channels.Has(Back)) {const auto target=-Clamp(influence,-1,0),blend=target>back?s.blend_out:s.blend_in;Influence(back,back_delta,target,blend,s);animation.channels.Influence(Back,back);}
        break;
    default:break;
    }
    mode=next_mode;previous_spin=spin;error.clear();return true;
}
bool ParseGraphMotionAirborneOperation(const GraphAttributes& a,GraphMotionAirborneOperation& output,bool& recognized,std::string& error)
{
    const auto raw=a.Text("name");recognized=false;if (!raw) {error="MotionGraph operation has no name";return false;}
    const auto name=TrimMotionGraphName(*raw);GraphMotionAirborneOperation operation;
    if (name=="BodySpin") operation.kind=GraphMotionAirborneOperation::Kind::BodySpin;
    else if (name=="ControlAirLegExtension")
    {
        operation.kind=GraphMotionAirborneOperation::Kind::AirLeg;operation.height=EncodeAnimationName(a.Text("driveDistToCom").value_or("disttocog"));
        const auto bone=a.Text("bone").value_or("Skateboard_Root");operation.bone=bone=="LeftToeBase"?AnimationAirLegBone::LeftToe:bone=="RightToeBase"?AnimationAirLegBone::RightToe:AnimationAirLegBone::Board;
    }
    else {error.clear();return true;}
    output=operation;recognized=true;error.clear();return true;
}
GraphMotionAirborneInstance CreateGraphMotionAirborneInstance(const GraphMotionAirborneOperation& operation)
{
    using K=GraphMotionAirborneOperation::Kind;switch (operation.kind) {case K::AirLeg:return AnimationAirLegState{};case K::BodySpin:return AnimationBodySpinState{};default:return std::monostate{};}
}
bool ExecuteGraphMotionAirborneOperation(const GraphMotionAirborneOperation& operation,GraphMotionAirborneInstance& instance,
    std::uint8_t phase,float dt,GraphMotionAirborneContext context,std::string& error)
{
    using K=GraphMotionAirborneOperation::Kind;
    if (operation.kind==K::AirLeg)
    {
        auto* state=std::get_if<AnimationAirLegState>(&instance);if (!state) {error="Airborne MotionGraph operation/instance mismatch";return false;}
        if (phase==1)
        {
            if (!context.air_leg) {error="Air leg extension requires completed physical output";return false;}const auto& physical=*context.air_leg;
            std::optional<AnimationAttribute> initial;if (state->NeedsInitialAttribute()&&!context.animation.LastAttribute(operation.height,initial,error)) return false;
            bool prepare=false;if (state->NeedsPrelandingQuery(physical))
            {
                if (!context.prelanding) {error="Air leg extension requires actual prelanding output";return false;}
                const auto query=AnimationNearLanding(*context.prelanding,context.settings.spin);std::optional<AnimationAttribute> full;
                if (query&&!context.animation.LastAttribute(EncodeAnimationName("FullExtension"),full,error)) return false;
                prepare=AnimationAirLegPrepareToLand(query,full,physical,context.settings.air_leg);
            }
            const auto output=state->Update(operation.bone,physical,context.settings.air_leg,dt,initial,prepare);
            context.animation.SetAttribute({operation.height,output[0],false,-1});context.animation.SetAttribute({EncodeAnimationName("extend"),output[1],false,-1});
        }
    }
    else if (operation.kind==K::BodySpin)
    {
        auto* state=std::get_if<AnimationBodySpinState>(&instance);if (!state) {error="Airborne MotionGraph operation/instance mismatch";return false;}
        if (phase==1)
        {
            if (!context.category) {error="BodySpin requires physicalcategory";return false;}if (!context.physical_state) {error="BodySpin requires physicalstate";return false;}if (!context.mirrored) {error="BodySpin requires animstance";return false;}
            return state->Update(context.animation,*context.category,*context.physical_state,context.doing_trick,context.busy_hands,*context.mirrored,context.prelanding,context.settings.spin,error);
        }
    }
    else {error="Airborne MotionGraph operation/instance mismatch";return false;}
    error.clear();return true;
}
}
