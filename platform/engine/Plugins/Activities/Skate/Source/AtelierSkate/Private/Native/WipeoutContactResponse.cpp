// SPDX-License-Identifier: Apache-2.0
#include "WipeoutContactResponse.h"
#include "GravityScale.h"
#include "WipeoutBody.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
namespace
{
Vec4 Reject(Vec4 value,Vec4 direction){const auto normal=NormalizeOr(direction,{});return Sub(value,Scale(normal,Dot3(value,normal)));}
Vec4 RejectPositive(Vec4 value,Vec4 direction){const float projection=Dot3(value,NormalizeOr(direction,{}));return projection>0?Sub(value,Scale(direction,projection)):value;}
}
void WipeoutMaterialTenResponse::Select(bool contact)
{
    std::uint32_t next=phase;
    if(phase==0&&contact)next=-Dot3(previous_velocity,normal)>2.0f?1:4;
    else if(phase==1&&time>Word(0x3d072b02)){
        const auto twice=Scale(normal,2.0f);target_velocity=Scale(Sub(previous_velocity,Scale(twice,Dot3(previous_velocity,normal))),Word(0x3f666666));next=2;
    }else if(phase==2&&time>Word(0x3d072b02)){finished=true;next=3;}
    else if(phase==3&&!contact)next=0;
    if(next!=phase){phase=next;time=0;}
}
void WipeoutMaterialTenResponse::Update(SkeletonBody& body,Vec4 velocity,std::optional<Vec4> contact)
{
    if(contact)normal=*contact;finished=false;Select(bool(contact));
    switch(phase){
    case 0:{const auto difference=Sub(velocity,previous_velocity);previous_velocity=time>Word(0x3c75c28f)&&Dot3(difference,difference)>1?
        Madd(velocity,Word(0x3d4ccccd),Scale(previous_velocity,Word(0x3f733333))):velocity;break;}
    case 1:{const auto rejected=RejectPositive(Scale(velocity,-0.5f),normal);AddWipeoutBodyVelocity(body,Madd(normal,-1,rejected));break;}
    case 2:AddWipeoutBodyVelocity(body,Scale(Sub(target_velocity,velocity),1.0f));target_velocity=Madd({0,(Word(0xc11ccccd)*GravityScale()),0,0},Step(),target_velocity);break;
    default:break;
    }
    time+=Step();
}
void WipeoutMaterialElevenResponse::Update(SkeletonBody& body,Vec4 com_velocity,std::optional<Vec4> contact,Vec4 effective,std::array<float,2> controls)
{
    velocity=com_velocity;
    if(Dot3(velocity,velocity)>0.25f&&contact){frames_since_contact=0;contact_latched=true;normal=*contact;if(!active)previous_velocity=Reject(previous_velocity,normal);}
    active=contact_latched||frames_since_contact<3;
    if(active){ApplyResponse(body);ApplyControl(body,effective,controls);active_frames=Increment(active_frames);}
    else{previous_velocity=velocity;active_frames=0;}
    frames_since_contact=frames_since_contact<=100?Increment(frames_since_contact):100;
}
void WipeoutMaterialElevenResponse::ApplyResponse(SkeletonBody& body) const
{
    Vec4 retained_delta{};
    if(active_frames<3){const auto difference=Reject(Sub(previous_velocity,velocity),normal);if(Dot3(difference,velocity)>0)retained_delta=Scale(difference,Word(0x3f666666));}
    const auto friction=Reject(Scale(velocity,Word(0xbb03126f)),normal);Vec4 slope_delta{};
    if(normal[1]<Word(0x3f7851ec)){
        const auto across=Cross({0,1,0,0},normal);auto direction=NormalizeOr(Cross(across,normal),{});if(direction[1]>0)direction=Scale(direction,-1);
        auto horizontal=normal;horizontal[1]=0;const auto candidate=Scale(direction,Length(horizontal)*Word(0x3dcccccd));if(Dot3(candidate,velocity)>0)slope_delta=candidate;
    }
    AddWipeoutBodyVelocity(body,Add(Add(friction,retained_delta),slope_delta));
}
void WipeoutMaterialElevenResponse::ApplyControl(SkeletonBody& body,Vec4 effective,std::array<float,2> controls) const
{
    const auto planar=Reject(velocity,normal),direction=NormalizeOr(planar,{});
    if(Word(0x3f7fbe77)>Dot3({0,1,0,0},effective)){
        const float fraction=Reciprocal(10)*VectorMin(10,Length(planar));const Vec4 input{controls[0],0,controls[1],0};const auto tangent=Reject(input,normal),lateral=Reject(tangent,direction);
        AddWipeoutBodyVelocity(body,Scale(lateral,fraction*Word(0x3d4ccccd)));
    }
}
}
