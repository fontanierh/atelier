// SPDX-License-Identifier: Apache-2.0
#include "GroundOutput.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float FlushSubnormal(float value)
{
    std::uint32_t bits;std::memcpy(&bits,&value,4);
    if ((bits&0x7f800000)==0&&(bits&0x007fffff)!=0)
    {bits&=0x80000000;std::memcpy(&value,&bits,4);}
    return value;
}
Vec4 RejectAxis(Vec4 velocity,Vec4 axis)
{
    const auto projection=Dot3(velocity,axis);
    for (std::size_t i=0;i<4;++i)
    {
        const auto scaled=FlushSubnormal(axis[i]*projection);
        velocity[i]=FlushSubnormal(velocity[i]-scaled);
    }
    return velocity;
}
}
PhysicsGroundOutput FillGroundPhysicsOutput(const PhysicsGroundState& state,GroundOutputFrame frame,
    GroundOutputSettings settings)
{
    const auto grab=(frame.flags_2476&0x00400000)!=0;
    std::optional<GroundVelocityProjectionOutput> projection;
    if (frame.state_timer_2664==0)
        projection=GroundVelocityProjectionOutput{RejectAxis(frame.velocity_608,frame.axis_464),true};
    return {
        {state.flag_2721,frame.absolute_body_speed_2616<settings.pushable_speed_terms_4_8[0]+settings.pushable_speed_terms_4_8[1]},
        projection,
        {state.flag_2720,state.anti_flip_nudge_applied_2723,state.pinning_2727,state.anti_flip_torque_2624,
            state.scalar_2664,state.scalar_2668,frame.scalar_2720,(frame.flags_2484&0x00002000)!=0},
        {state.word_2560,state.word_2564,state.flag_2731,grab&&!state.flag_2729,
            state.manual_correction_2732?std::optional<bool>(true):std::nullopt},
        {grab,frame.selected_mode_flag_109&&frame.deck_speed_2652<settings.mode_speed_threshold_0},
        state.flag_2729,state.manual_opposition_2733,state.push_suppressed_2730
    };
}
}
