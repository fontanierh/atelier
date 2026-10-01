// SPDX-License-Identifier: Apache-2.0
#include "RidingAngles.h"
#include "BoardGroundAngle.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace {float Float(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}}
float RidingSignedAngle(Vec3 a,Vec3 b,Vec3 up)
{
    const float sa=Dot3(a,a),sb=Dot3(b,b);
    if(!(sa>0.0001f && sb>0.0001f))return 0;
    const float angle=BoardGroundAngleBetween(a,b);
    a=Scale(a,InverseLengthSquared(sa,1));b=Scale(b,InverseLengthSquared(sb,1));
    const Vec3 cross{std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};
    return Dot3(cross,up)<0.0f?Float(0x40c90fdb)-angle:angle;
}
float RidingFractionWrappedAngle(float angle)
{
    const float turns=angle*Float(0x3e22f983);
    const float fraction=turns-std::floor(turns);
    const float centered=fraction-(fraction>0.5f?1.0f:0.0f);
    return centered*Float(0x40c90fdb);
}
}
