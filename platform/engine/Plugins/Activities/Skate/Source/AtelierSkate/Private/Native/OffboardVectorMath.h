// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardControllerMath.h"
#include <limits>
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_air_math
{
using biped_math::Bits;using biped_math::Step;using biped_math::Dot;using biped_math::Add;using biped_math::Sub;
using biped_math::Mul;using biped_math::Madd;using biped_math::Cross;using biped_math::Select;using biped_math::Clamp;
inline constexpr Vec4 Up{0,1,0,0};
inline float Reciprocal(float v){float r=ReciprocalEstimate(v);for(unsigned n=0;n<2;++n)r=std::fma(r,std::fma(-r,v,1.0f),r);return r;}
inline float Inverse(float q,unsigned n=2){return InverseLengthSquared(q,n);}
inline float Length(Vec4 v){const auto q=Dot(v,v);return q==0?0:q*Inverse(q);}
inline Vec4 Unit(Vec4 v){return Mul(v,Inverse(Dot(v,v)));}
inline Vec4 UnitOr(Vec4 v,Vec4 fallback){return Length(v)>Bits(0x358637bd)?Unit(v):fallback;}
inline Vec4 Flat(Vec4 v){v[1]=0;return v;}
inline Vec4 RejectSafe(Vec4 v,Vec4 axis){axis=UnitOr(axis,{});return Sub(v,Mul(axis,Dot(v,axis)));}
inline float WrapAngle(float angle){const auto turns=angle*Bits(0x3e22f983),fraction=turns-std::floor(turns);return (fraction>.5f?fraction-1:fraction)*Bits(0x40c90fdb);}
inline float SignedAngle(Vec4 a,Vec4 b,Vec4 axis)
{
    const auto aa=Dot(a,a),bb=Dot(b,b);if(!(aa>Bits(0x38d1b717)&&bb>Bits(0x38d1b717)))return 0;
    a=Mul(a,Inverse(aa,1));b=Mul(b,Inverse(bb,1));const auto angle=Acos(Clamp(Dot(a,b),-1,1));
    return Dot(Cross(a,b),axis)<0?Bits(0x40c90fdb)-angle:angle;
}
inline float ProjectedAngle(Vec4 a,Vec4 b,Vec4 axis)
{if(!(Dot(a,a)*Dot(b,b)>Bits(0x37800000)))return 0;return SignedAngle(Sub(a,Mul(axis,Dot(axis,a))),Sub(b,Mul(axis,Dot(axis,b))),axis);}
inline Vec4 LimitAngle(Vec4 target,Vec4 from,float maximum)
{
    const auto a=UnitOr(target,{}),b=UnitOr(from,{}),axis=Cross(a,b);const auto angle=Acos(VectorMin(VectorMax(Dot(a,b),-1),1));
    const auto turns=std::floor(std::fma(angle,Bits(0x3e22f983),.5f)),closest=std::fma(-turns,Bits(0x40c90fdb),angle);
    if(std::abs(closest)<maximum||Dot(axis,axis)<Bits(0x37800000))return target;
    const auto sc=SinCos(-maximum*.5f);auto q=Mul(Unit(axis),sc.first);q[3]=sc.second;
    return Mul(Madd(Cross(q,Madd(from,sc.second,Cross(q,from))),2,from),Length(target));
}
inline Vec4 ClampLength(Vec4 v,float maximum){return biped_math::ClampLength(v,maximum);}
inline Vec4 Rotate(Vec4 v,Vec4 axis,float angle)
{
    const auto x=axis[0],y=axis[1],z=axis[2];const auto sc=SinCos(angle);const auto s=sc.first,c=sc.second,t=1-c;
    const auto tx=t*x,ty=t*y,tz=t*z,sx=s*x,sy=s*y,sz=s*z;
    const Vec4 right{std::fma(tx,x,c),std::fma(tx,y,sz),tx*z-sy,0};
    const Vec4 up{ty*x-sz,std::fma(ty,y,c),std::fma(ty,z,sx),0};
    const Vec4 forward{std::fma(tz,x,sy),tz*y-sx,std::fma(tz,z,c),0};
    return Madd(forward,v[2],Madd(up,v[1],Mul(right,v[0])));
}
inline std::int32_t WrappingNeg(std::int32_t v){return static_cast<std::int32_t>(0u-static_cast<std::uint32_t>(v));}
inline std::int32_t WrappingAdd(std::int32_t a,std::int32_t b){return static_cast<std::int32_t>(static_cast<std::uint32_t>(a)+static_cast<std::uint32_t>(b));}
inline std::int32_t WrappingSub(std::int32_t a,std::int32_t b){return static_cast<std::int32_t>(static_cast<std::uint32_t>(a)-static_cast<std::uint32_t>(b));}
inline std::int32_t Integer(float v)
{if(std::isnan(v))return 0;if(v>=float(std::numeric_limits<std::int32_t>::max()))return std::numeric_limits<std::int32_t>::max();if(v<=float(std::numeric_limits<std::int32_t>::min()))return std::numeric_limits<std::int32_t>::min();return static_cast<std::int32_t>(v);}
}
