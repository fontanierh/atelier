#include "OffboardAirMath.h"
#include "GravityScale.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_air_math
{
std::pair<Vec4,Vec4> Jump(const BipedControllerState& state,const PointGraph<8>& turn,OffboardAirLaunchSettings settings,const OffboardAirLaunchInput& p,Vec4 forward)
{
    const auto reference_up=state.frame_output.frame[1];const auto blend=Madd(reference_up,1,Mul(state.motion.frame_0[1],0));
    const auto up=UnitOr(blend,reference_up),planar=Sub(p.velocity_912,Mul(up,Dot(up,p.velocity_912)));
    const auto backward=Dot(planar,forward),amount=Select(-backward,0,backward)-backward;
    auto base=Madd(forward,amount,planar),secondary=base;const auto speed_squared=Dot(base,base);
    if((p.flags_2472&0x10000000)==0)
    {
        const Vec4 control{p.raw_x_2692,0,p.raw_z_2688,0};
        if(!(speed_squared>=1)){base=ClampLength(Madd(control,1,base),1);secondary=base;}
        else if(state.contact.active&&Dot(control,control)>Bits(0x3f4f5c28))
        {
            const auto angle=WrapAngle(ProjectedAngle(control,base,up));
            if(45*Bits(0x3c8efa35)>angle)secondary=Mul(Unit(RejectSafe(control,up)),speed_squared*Inverse(speed_squared));
            else if(90*Bits(0x3c8efa35)>angle)secondary=Mul(LimitAngle(Unit(RejectSafe(control,up)),base,45),speed_squared*Inverse(speed_squared));
        }
    }
    const auto q=settings.jump_height*(Bits(0x419ccccd)*GravityScale()),value=q*Inverse(q),launch_speed=q==0?0:value;
    const auto v=up[1]*launch_speed,vertical=Select(-v,0,v);secondary=UnitOr(Flat(secondary),{});
    const auto requested=(turn.Evaluate(state.motion.speed_704)*state.intent.steering)*Bits(0x3c8efa35),center=state.motion.angular_velocity_688,window=Bits(0x3fdf66f3);
    const auto angle=Clamp(Clamp(requested,center-window,center+window)*.4f,Bits(0xbe860a92),Bits(0x3e860a92));
    return {Rotate(Madd(base,settings.jump_speed_scalar,Mul(up,vertical)),up,angle),secondary};
}
}
