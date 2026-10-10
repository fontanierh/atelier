#include "WipeoutPhysicalState.h"
#include "WipeoutPhysicalMath.h"
#include "WipeoutOrientation.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
float WipeoutPhysicalState::ResponseStrength() const
{
    const float speed=maximum_speed*0.1f;
    const float count=float(Signed(4u-response_count));
    const float remaining=(count+1.0f)*0.5f;
    const float result=speed-remaining>=0?speed:remaining;
    return slow_time>1.0f||result<=0.2f||special_surface||below_surface?0:result;
}
void WipeoutPhysicalState::ManageRecovery(std::uint32_t f2468,std::uint32_t f2472,std::uint32_t f2484,float timestep,const WipeoutRecoverySettings& s)
{
    prevent_manual|=(f2468&1)!=0;ignore_reset|=(f2472&0x80000000)!=0;reset_ever|=(f2472&0x00100000)!=0;
    ever_settled|=over;recovery_eligible|=ever_settled||time>1.6f;settled_time=over?settled_time+Step():0;
    if(teleport_countdown<0&&ShouldTeleport(f2472,f2484,timestep,s))teleport_countdown=2;
    if(teleport_countdown==0)request_teleport=true;else if(teleport_countdown>0)--teleport_countdown;
}
bool WipeoutPhysicalState::ShouldTeleport(std::uint32_t f2472,std::uint32_t f2484,float timestep,const WipeoutRecoverySettings& s)
{
    if(ever_impaled)impaled_time+=Step();
    if(f2484&0x00400000){ever_impaled=true;if(impaled_time>0.5f)return true;}
    if(prevent_manual)return false;
    if(recovery_eligible&&reset_ever&&!ignore_reset)return true;
    if(teleport_pending){time_until_teleport-=timestep;return time_until_teleport<=0;}
    const bool automatic=(f2472&0x10000000)?time>8.0f:
        (time>s.maximum_time&&response_time>s.maximum_time)||(time>s.minimum_time&&settled_time>s.minimum_settled&&response_time>s.minimum_settled);
    if(automatic){teleport_pending=true;time_until_teleport=s.fade_time;}return false;
}
void WipeoutPhysicalState::PostPhysics(Vec4 hips,Vec4 neck,bool support,const WipeoutRecoverySettings& s)
{
    const bool bypass=extra_weight_zero_time>0.5f;const float speed=bypass?s.over_speed*2.0f:s.over_speed;
    const bool minimum=time>s.over_minimum_time;const float hs=Dot3(hips,hips),ns=Dot3(neck,neck);
    over=hs<speed*speed&&(ns<speed*speed||bypass)&&minimum&&ResponseStrength()==0;
    slow=hs<1.0f&&minimum;no_support_time=support?0:no_support_time+Step();
}
WipeoutPhysicalOutput WipeoutPhysicalState::Output(const Mat4& hips,Vec4 normal) const
{
    const auto right=hips[0],projected=Sub(normal,Scale(right,Dot3(normal,right)));
    const float right_angle=WipeoutSignedAngle(right,normal,{});
    const float up_angle=WipeoutWrapAngle(WipeoutSignedAngle(projected,hips[1],right)+Word(0x40490fdb));
    return {over,orientation,no_support_time,recovery_eligible&&!prevent_manual&&!ignore_reset,special_surface,below_surface,surface_height,true,
        predicted_time,std::uint32_t(profile),response_scalar,extra_weight,time_until_teleport,teleport_pending,material_ten_response,material_eleven_response,
        imminent_surface_twelve,predicted_position,retained_velocity_active?std::optional<Vec4>(retained_velocity):std::nullopt,
        response_finished?std::optional<float>(response_change):std::nullopt,teleport_countdown>=0,request_teleport,right_angle,up_angle};
}
}
