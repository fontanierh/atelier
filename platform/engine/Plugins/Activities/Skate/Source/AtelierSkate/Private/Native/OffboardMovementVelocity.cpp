// SPDX-License-Identifier: Apache-2.0
#include "OffboardControllerMath.h"
#include "GravityScale.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float VelocityInverse(float square)
{
    float rescale=1;
    if(square>0&&std::fpclassify(square)==FP_SUBNORMAL){square*=16777216.0f;rescale=4096;}
    auto inverse=ReciprocalSquareRootEstimate(square);
    for(unsigned n=0;n<2;++n)inverse=std::fma(inverse*.5f,std::fma(-square,inverse*inverse,1.0f),inverse);
    return inverse*rescale;
}
float VelocityLength(Vec4 v){const auto square=biped_math::Dot(v,v),length=square*VelocityInverse(square);return square==0?0:length;}
Vec4 VelocityUnitOr(Vec4 v,Vec4 fallback)
{
    const auto square=biped_math::Dot(v,v),inverse=VelocityInverse(square),length=square==0?0:square*inverse;
    return length>biped_math::Bits(0x358637bd)?biped_math::Mul(v,inverse):fallback;
}
Vec4 VelocityRemovePositive(Vec4 value,Vec4 direction)
{
    const auto projection=biped_math::Dot(value,VelocityUnitOr(direction,{}));
    return projection>0?biped_math::Sub(value,biped_math::Mul(direction,projection)):value;
}
}
void BipedVelocityState::Update(const BipedVelocitySettings& settings,const BipedVelocityInput& input)
{
    using namespace biped_math;
    const auto direction=VelocityUnitOr(Sub(input.forward,Mul(input.plane_normal,Dot(input.forward,input.plane_normal))),input.forward);
    const auto slope_degrees=Asin(direction[1])*Bits(0x42652ee1);
    float target_speed;
    if(input.slope_mode)target_speed=settings.slope_mode_speed.Evaluate(std::abs(slope_degrees));
    else
    {
        auto target=settings.slope_speed_scalar.Evaluate(slope_degrees)*input.desired_speed;
        if(!(input.desired_speed<=.5f)&&!(target>=speed))
        {
            const auto gravity_delta=velocity[1]>0?((Bits(0xc11ccccd)*GravityScale())*Step())*Select(-direction[1],0,direction[1]):0;
            const auto delta=target-speed,limited_delta=Select(delta- -2.0f,delta,-2)*Step();
            target=speed+Select(gravity_delta-limited_delta,limited_delta,gravity_delta);
        }
        target_speed=target;
    }
    const auto original=velocity;auto target=Madd(original,0,Mul(direction,target_speed));
    const auto radians=Bits(0x3c8efa35);
    const auto turn_error=std::fma(settings.turn_vs_speed.Evaluate(speed)*input.steering,radians,-turn);
    auto maximum_delta=input.slope_mode?.5f:Bits(0x3e4ccccd);
    if(!(input.override_gate<0)&&!input.slope_mode)
    {
        const auto first=override_remaining<0;if(first)override_remaining=input.override_duration;
        const auto ratio=input.override_duration<Bits(0x3a83126f)?0:override_remaining/input.override_duration;
        const auto amount=ratio*1.25f;auto blend=Select(1.0f-amount,amount,1);
        if(!first&&!(VelocityLength(input.override_velocity)<=VelocityLength(original)*Bits(0x3f8ccccd)))blend=Select(blend-.5f,.5f,blend);
        target=Madd(original,blend,Mul(input.override_velocity,1.0f-blend));maximum_delta=100;
        if((input.flags&8)!=0)
        {
            const auto target_length=VelocityLength(target);
            if(!(target_length>=Bits(0x3c23d70a)))target=Mul(direction,1);
            else if(!(target_length>=1))target=Mul(target,1.0f/target_length);
        }
        const auto remaining=override_remaining-Step();override_remaining=Select(-remaining,0,remaining);
    }
    else override_remaining=-1;
    const auto turn_delta=settings.turn_delta_vs_speed.Evaluate(speed)*radians;
    const auto delta=Sub(target,original);const auto magnitude=VelocityLength(delta);
    auto next=maximum_delta>=magnitude?target:Madd(delta,maximum_delta/magnitude,original);
    turn+=Clamp(turn_error,-turn_delta,turn_delta);
    if(input.obstacle){const auto opposite=Mul(input.obstacle_normal,-1);target=VelocityRemovePositive(target,opposite);next=VelocityRemovePositive(next,opposite);}
    right_delta=Dot(Sub(next,original),input.right);forward_delta=Dot(Sub(target,original),input.forward);
    velocity=next;speed=VelocityLength(next);
}
}
