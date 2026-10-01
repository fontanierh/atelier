// SPDX-License-Identifier: Apache-2.0
#include "Straighten.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {float Bound(float v,float low,float high) {const float lower=low-v>=0?low:v;return high-lower>=0?lower:high;}}
Vec4 CalculateStraighten(const StraightenSettings& s,const StraightenInput& i)
{
    const float limit=std::fma(1-s.time_scalar,i.scalar_2764,s.time_scalar)*s.heading_time_limit;
    const float strength=s.time_response.Evaluate(Bound(i.heading_time,0,limit)/limit)*s.strength;
    Vec4 forward=i.forward;if (Dot3(i.forward,i.velocity)<0) for (auto& v:forward) v=-v;
    const float error=Dot3(Cross3(forward,i.velocity),i.normal);Vec4 output;
    for (std::size_t n=0;n<4;++n) output[n]=i.normal[n]*(error*strength);
    if (i.turn*error<0)
    {
        const float scale=1-Bound(std::fabs(i.turn),0,s.opposite_turn_limit)/s.opposite_turn_limit;
        for (auto& v:output) v*=scale;
    }
    return output;
}
}
