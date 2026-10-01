// SPDX-License-Identifier: Apache-2.0
#include "BipedGroundState.h"
#include "OffboardControllerMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
Mat4 EffectiveBipedRoot(Mat4 frame,std::uint32_t flags)
{
    if((flags&4)!=0)for(const auto axis:{0u,2u})for(auto& value:frame[axis])value*=-1.0f;return frame;
}
BipedGroundPlacement BipedGroundState::Enter(const BipedGroundEntryInput& input)
{
    using namespace biped_math;*this=BipedGroundState{};flags_144_to_150[4]=input.previous_state_2504==502;
    const auto up=input.animation_frame[1],velocity=input.processed_velocity_608,planar=Sub(velocity,Mul(up,Dot(up,velocity)));auto frame=input.animation_frame;
    if((input.processed_flags_2484&0x4000)!=0)
    {
        flags_144_to_150[6]=true;duration_180=input.requested_duration_2896;auto angle=input.requested_angle_2936;
        if((input.processed_flags_2476&4)!=0)angle*=-1.0f;const auto direction=Length(planar)<Bits(0x3dcccccd)?input.animation_frame[2]:planar;
        const auto basis=BipedBuildSurfaceFrame(up,direction);for(unsigned axis=0;axis<3;++axis)frame[axis]=basis[axis];
        const auto sc=SinCos(angle*.5f);auto q=Mul(up,sc.first);q[3]=sc.second;
        const auto rotated=Madd(Cross(q,Madd(input.animation_frame[2],sc.second,Cross(q,input.animation_frame[2]))),2,input.animation_frame[2]);
        angle_172=WrapAngle(SignedAngle(direction,rotated,up));auto original=WrapAngle(SignedAngle(input.animation_frame[2],direction,up));
        if(!(std::abs(angle)<=Bits(0x3fc90fdb))&&!(original*angle>=0))original+=original>0?-Bits(0x40c90fdb):Bits(0x40c90fdb);
        angular_velocity_176=(angle_172+original)/duration_180;
    }
    frame_80=frame;flags_144_to_150[5]=true;
    if(input.previous_state_2504==501)flags_144_to_150[1]=Bits(0x3f35c28f)>input.previous_frame_up_208[1];
    return {frame,planar,input.body_position_15872};
}
}
