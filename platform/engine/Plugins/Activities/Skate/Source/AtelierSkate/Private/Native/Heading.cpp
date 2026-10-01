// SPDX-License-Identifier: Apache-2.0
#include "Heading.h"
#include "GroundForce.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}
float Bound(float v,float low,float high) {const float lower=low-v>=0?low:v;return high-lower>=0?lower:high;}
}
Vec4 CalculateHeading(const HeadingSettings& s,const HeadingInput& i,float& previous)
{
    Vec4 output;
    if (i.balance!=0&&i.manual_turn!=0)
    {
        const bool wrong=((i.flags_2472&0x08000000)!=0&&i.balance<0)||((i.flags_2472&0x04000000)!=0&&i.balance>0);
        const float turn=wrong?i.manual_turn*s.manual_wrong_wheel_scalar:i.manual_turn;
        const float target=s.manual_response.Evaluate(i.manual_curve_input)*Word(0x3c8efa35);
        previous=std::fma(1-s.manual_damping,previous,target*s.manual_damping);const float scalar=(i.timestep*previous)*turn;
        for (std::size_t n=0;n<4;++n) output[n]=i.normal[n]*scalar;return output;
    }
    previous=0;std::array<Vec4,3> rows;
    for (std::size_t n=0;n<3;++n) rows[n]={i.transform[0][n],i.transform[1][n],i.transform[2][n],0};
    const float cosine=Bound(rows[1][1],-1,1);float angle=Acos(cosine)*Word(0x3f22f983);if (angle>1.2f) angle=0;
    Vec4 downhill;
    for (std::size_t n=0;n<4;++n) {const float first=rows[0][n]*0;const float second=std::fma(rows[1][n],-1.0f,first);downhill[n]=std::fma(rows[2][n],0.0f,second);}
    downhill[1]=0;const float inclination=s.inclination_response.Evaluate(angle);downhill=NormalizeRidingForceVector(downhill,s.normal_threshold);for (auto& v:downhill) v*=inclination;
    Vec4 velocity;
    for (std::size_t n=0;n<4;++n) {const float first=rows[0][n]*i.velocity[0];const float second=std::fma(rows[1][n],i.velocity[1],first);velocity[n]=std::fma(rows[2][n],i.velocity[2],second);}
    velocity[1]=0;const float cross_y=std::fma(-velocity[0],downhill[2],velocity[2]*downhill[0]);
    const float speed=Bound(std::fabs(i.signed_speed),0,s.speed_max),heading=(cross_y*s.heading_strength)*s.speed_response.Evaluate(speed/s.speed_max);
    float opposing=Dot3(i.angular_velocity,i.normal)*-i.turn_2712;opposing=opposing>=0?opposing:0;
    const float turn=((s.angular_response.Evaluate(opposing)*i.scalar_2740)*s.turn_strength)*i.turn_2712;
    const float scalar=!(heading*turn<0)&&!(std::fabs(turn)>std::fabs(heading))?heading:turn;
    for (std::size_t n=0;n<4;++n) output[n]=i.normal[n]*scalar;return output;
}
}
