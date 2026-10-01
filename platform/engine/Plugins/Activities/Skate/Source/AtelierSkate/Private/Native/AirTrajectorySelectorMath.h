// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "NativeMath.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::air_trajectory_detail
{
inline float Bits(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
inline constexpr Vec4 Up{0,1,0,0};
inline float Step() {return Bits(0x3c888889);}
inline Vec4 Add(Vec4 a,Vec4 b) {for (std::size_t i=0;i<4;++i) a[i]+=b[i];return a;}
inline Vec4 Sub(Vec4 a,Vec4 b) {for (std::size_t i=0;i<4;++i) a[i]-=b[i];return a;}
inline Vec4 Scale(Vec4 a,float scalar) {for (auto& value:a) value*=scalar;return a;}
inline Vec4 Madd(Vec4 a,float scalar,Vec4 b) {for (std::size_t i=0;i<4;++i) a[i]=std::fma(a[i],scalar,b[i]);return a;}
inline Vec4 Cross(Vec4 a,Vec4 b)
{
    return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),
        std::fma(-a[1],b[0],a[0]*b[1]),0};
}
inline float Length(Vec4 a) {const auto square=Dot3(a,a);return square==0?0:square*InverseLengthSquared(square,2);}
inline Vec4 Normalize(Vec4 a)
{
    const auto square=Dot3(a,a),inverse=InverseLengthSquared(square,2);
    const auto length=square==0?0:square*inverse;
    return length>Bits(0x358637bd)?Scale(a,inverse):Vec4{};
}
inline float AngleBetween(Vec4 a,Vec4 b)
{
    const auto aa=Dot3(a,a),bb=Dot3(b,b);
    if (!(aa>Bits(0x38d1b717)&&bb>Bits(0x38d1b717))) return 0;
    return Acos(VectorMin(VectorMax(Dot3(Scale(a,InverseLengthSquared(aa,1)),
        Scale(b,InverseLengthSquared(bb,1))),-1),1));
}
inline Vec4 Transform(Mat4 m,Vec4 a) {return Madd(m[2],a[2],Madd(m[1],a[1],Madd(m[0],a[0],m[3])));}
inline std::int32_t SaturatedInteger(float value)
{
    if (std::isnan(value)) return 0;
    if (value>=2147483648.0f) return std::numeric_limits<std::int32_t>::max();
    if (value<=-2147483648.0f) return std::numeric_limits<std::int32_t>::min();
    return static_cast<std::int32_t>(value);
}
}
