// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardAirMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::biped_air_math
{
// Height, times and Post use the source's nested Z/Y FMA reduction. The
// orientation/collision kernels use air_launch::math::dot instead.
inline float HeightDot(Vec4 a,Vec4 b){return std::fma(a[2],b[2],std::fma(a[1],b[1],a[0]*b[0]));}
inline Vec4 HeightSub(Vec4 a,Vec4 b){for(unsigned n=0;n<4;++n)a[n]-=b[n];return a;}
inline Vec4 HeightMadd(Vec4 a,float b,Vec4 c){for(unsigned n=0;n<4;++n)a[n]=std::fma(a[n],b,c[n]);return a;}
inline float HeightSelect(float test,float positive,float negative){return test>=0?positive:negative;}
}
