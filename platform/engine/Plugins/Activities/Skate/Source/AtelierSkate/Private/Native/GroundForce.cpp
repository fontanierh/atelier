// SPDX-License-Identifier: Apache-2.0
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
Vec4 NormalizeRidingForceVector(const Vec4& v,const Vec4& thresholds)
{
    const float squared=Dot3(v,v),inverse=InverseLengthSquared(squared,2);
    const float length=squared==0?0:squared*inverse;
    Vec4 result;for (std::size_t i=0;i<4;++i) result[i]=length>thresholds[i]?v[i]*inverse:0;
    return result;
}
std::array<float,8> CalculateGroundForce(const GroundForceSettings& s,const GroundForceInput& i)
{
    const float fraction=Bound(i.argument_1/s.range_1220,0,1);
    const float zero_scalar=i.argument_1!=0||i.balance!=0?1:0;
    const float speed=(i.surface_speed*0.125f)*s.speed_scale_1224;
    const float remainder=((1-fraction)*s.scale_1228)*zero_scalar;
    const float magnitude=-(std::fma(speed,fraction,remainder)*i.argument_4);
    Vec4 force;for (std::size_t n=0;n<4;++n) force[n]=std::fma(i.axis_544[n],magnitude,(-i.axis_384[n])*i.argument_3);
    const auto direction=NormalizeRidingForceVector(i.velocity_400,s.normal_threshold);const float projected=Dot3(direction,force);
    std::array<float,8> result{};for (std::size_t n=0;n<4;++n) result[n]=force[n]-direction[n]*projected;
    result[6]=i.application_z;return result;
}
bool LoadGroundForceSettings(const SettingsDatabase& data,GroundForceSettings& output,std::string& error)
{
    GroundForceSettings s;
    const auto scalar=[&](std::string_view name,float& value)
    {
        const auto field=data.Field("physics_feet","default",name);
        if (!field) {error="Missing stock field physics_feet/default/"+std::string(name);return false;}
        const auto v=field->Float();if (!v) {error="Expected finite stock float physics_feet/default/"+std::string(name);return false;}
        value=*v;return true;
    };
    if (!scalar("LandingForceTime",s.range_1220)||!scalar("MinForce",s.speed_scale_1224)||!scalar("MaxLandingForce",s.scale_1228)) return false;
    s.normal_threshold.fill(Word(0x358637bd));output=s;error.clear();return true;
}
}
