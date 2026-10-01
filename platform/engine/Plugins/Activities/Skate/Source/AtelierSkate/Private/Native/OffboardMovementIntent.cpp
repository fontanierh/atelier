// SPDX-License-Identifier: Apache-2.0
#include "OffboardControllerMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void BipedIntentState::Update(const BipedIntentSettings& settings,const BipedIntentInput& input)
{
    using namespace biped_math;
    const auto minimum=!input.suppress_minimum&&(input.flags&8)!=0?.5f:0.0f;
    const auto magnitude=Select(minimum-input.magnitude,minimum,input.magnitude);
    sprint_grace=input.sprint_pressed?Bits(0x3e99999a):sprint_grace-Step();
    const auto sprint=(sprint_grace>0||input.sprint_pressed)&&!input.edge_active;
    sprint_time=Clamp(sprint_time+(sprint?Step():-Step()),0,settings.sprint_time_cap);
    const auto fast=settings.sprint_speed.Evaluate(magnitude),normal=settings.normal_speed.Evaluate(magnitude);
    const auto blend=sprint?settings.sprint_blend.Evaluate(sprint_time):0.0f;
    speed=std::fma(1.0f-blend,normal,blend*fast);secondary_speed=0;
    steering=input.steering;original_steering=input.steering;edge_aligned=false;
    if(input.obstacle&&!input.ignore_obstacle&&!(speed<=0))
    {
        const auto opposite=Mul(input.obstacle_normal,-1);
        const auto desired=WrapAngle(SignedAngle(opposite,input.direction,{0,1,0,0}));
        const auto degrees=obstacle_centered?55.0f:25.0f;
        obstacle_centered=degrees*Bits(0x3c8efa35)>std::abs(desired);
        const auto facing=WrapAngle(SignedAngle(opposite,input.forward,{0,1,0,0}));
        if(!(std::abs(facing)>=Bits(0x3fc90fdb)))
        {
            const auto value=obstacle_centered?(facing*Bits(0xbf22f983))*.5f:
                std::fma(-facing,Bits(0x3f22f983),desired<=0?-1.0f:1.0f)*.5f;
            const auto correction=Clamp(value,-1,1);
            if(!(steering*correction>=0))steering=correction;
            else {const auto sign=correction<=0?-1.0f:1.0f;const auto old=steering*sign,next=correction*sign;steering=Select(old-next,old,next)*sign;}
            if(obstacle_centered)speed=0;
        }
    }
    else
    {
        obstacle_centered=false;
        if(input.sliding)
        {
            const auto angle=WrapAngle(ProjectedAngle(input.slide_velocity,input.forward,input.up));
            const auto original=steering;speed=(1.0f-std::abs(original))*speed;
            const auto sign=Select(angle,1,-1);
            if(!(original*sign<=0))
            {
                const auto limit=45.0f*Bits(0x3c8efa35);
                const auto weight=std::fma(-angle,sign,limit)/limit;
                steering=Clamp(weight,0,1)*original;
            }
            const auto correction=settings.slide_steering.Evaluate(sign*(angle*Bits(0x3ea2f983)));
            steering=Clamp(std::fma(-correction,sign,steering),-1,1);
            if(!(std::abs(angle)>=Bits(0x3fc90fdb)))speed+=Length(input.slide_velocity);
        }
        else if(input.edge_active&&!(speed<=0))
        {
            const auto direction=input.magnitude==0?input.forward:input.direction;
            const auto tangent=Dot(input.edge_tangent,direction)>=0?input.edge_tangent:Mul(input.edge_tangent,-1);
            edge_target=Madd(tangent,.5f,input.edge_point);const auto delta=Sub(edge_target,input.position);
            if(!(Dot(Horizontal(direction),Horizontal(delta))<=Bits(0x3f666666)))
            {edge_aligned=true;steering=Clamp(Dot(UnitOr(delta,input.forward),input.right)*.5f,-1,1);}
        }
    }
}
}
