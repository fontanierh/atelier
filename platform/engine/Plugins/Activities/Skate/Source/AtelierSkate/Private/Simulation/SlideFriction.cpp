#include "SlideFriction.h"
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
std::array<float,8> CalculateSlideFriction(const SlideFrictionSettings& s,const SlideFrictionInput& i)
{
    float y=-1.0f>i.normal[1]?-1.0f:i.normal[1];y=1.0f<y?1.0f:y;
    const float angle=1-s.angle_response.Evaluate(Bound(Acos(y)*Word(0x3f22f983),0,1));
    const float speed=1-s.speed_response.Evaluate(i.surface_speed*0.1f);
    const float time=s.time_response.Evaluate(Bound(i.heading_time,0,s.heading_time_limit)/s.heading_time_limit);
    const float blend=std::fma(1-s.scalar_516,i.scalar_2764,s.scalar_516),response=angle-speed>=0?angle:speed;
    const float scalar=-(((time*blend)*response)*s.friction),normal_speed=Dot3(i.velocity,i.normal);
    Vec4 tangent;for (std::size_t n=0;n<4;++n) tangent[n]=i.velocity[n]-i.normal[n]*normal_speed;
    const float side_speed=Dot3(tangent,i.side_axis);std::array<float,8> output{};
    for (std::size_t n=0;n<4;++n) output[n]=(i.side_axis[n]*side_speed)*scalar;return output;
}
}
