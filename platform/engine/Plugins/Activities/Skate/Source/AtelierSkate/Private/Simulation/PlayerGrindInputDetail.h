#pragma once
#include "SimulationMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::player_grind_detail
{
// Four carried lanes follow the original private grind helpers. Scalar seeds,
// dot/cross/refinements/trigonometry are shared accepted SimulationMath kernels.
inline float F(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
inline Vec4 Float4(std::array<std::uint32_t,4> raw){Vec4 v;for(std::size_t i=0;i<4;++i)v[i]=F(raw[i]);return v;}
inline std::array<std::uint32_t,4> Raw4(Vec4 v){std::array<std::uint32_t,4> raw;for(std::size_t i=0;i<4;++i)std::memcpy(&raw[i],&v[i],4);return raw;}
inline Vec4 Add(Vec4 a,Vec4 b){Vec4 r;for(std::size_t i=0;i<4;++i)r[i]=a[i]+b[i];return r;}
inline Vec4 Sub(Vec4 a,Vec4 b){Vec4 r;for(std::size_t i=0;i<4;++i)r[i]=a[i]-b[i];return r;}
inline Vec4 Scale4(Vec4 a,float s){for(auto& v:a)v*=s;return a;}
inline Vec4 Madd4(Vec4 a,float s,Vec4 b){Vec4 r;for(std::size_t i=0;i<4;++i)r[i]=std::fma(a[i],s,b[i]);return r;}
inline float SquareRoot(float value){const float result=value*InverseLengthSquared(value,2);return value==0 ? 0.0f : result;}
inline float Reciprocal(float value){return RefinedReciprocal(value,2);}
}
