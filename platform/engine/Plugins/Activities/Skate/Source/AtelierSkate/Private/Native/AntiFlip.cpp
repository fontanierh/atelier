#include "AntiFlip.h"
#include "GroundForce.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {float Word(std::uint32_t w) {float f;std::memcpy(&f,&w,4);return f;}}
Vec4 CalculateAntiFlip(const AntiFlipSettings& s,const AntiFlipInput& i)
{
    if ((i.flags_2468&0x20000000)!=0) return {};
    const auto project=[&](const Vec4& axis)
    {
        const float dot=Dot3(i.projection_axis_544,axis);Vec4 projected;
        for (std::size_t n=0;n<4;++n) projected[n]=axis[n]-i.projection_axis_544[n]*dot;
        return NormalizeRidingForceVector(projected,s.normal_threshold);
    };
    const auto a=project(i.axis_96),b=project(i.axis_64);
    const auto angle=[&](const Vec4& axis,const Vec4& projected)
    {float d=Dot3(axis,projected);d=0>d?0:d;d=1<d?1:d;return Acos(d)*Word(0x3f22f983);};
    const float sign_a=Dot3(i.axis_64,Cross3(i.axis_96,a))>=0?1:-1,sign_b=Dot3(i.axis_96,Cross3(i.axis_64,b))>=0?1:-1;
    const float b_strength=s.axis_64_response.Evaluate(angle(i.axis_64,b))*sign_b;
    const float a_strength=(s.axis_96_response.Evaluate(angle(i.axis_96,a))*sign_a)*(i.balance==0?1:0);Vec4 output;
    for (std::size_t n=0;n<4;++n) output[n]=std::fma(i.axis_64[n],a_strength,i.axis_96[n]*b_strength);return output;
}
}
