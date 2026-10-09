#pragma once
#include "SimulationMath.h"
#include <cmath>
#include <cstring>
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate::wipeout_physical_math
{
inline float Word(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
inline Vec4 FromWords(std::array<std::uint32_t,4> words){Vec4 v;std::memcpy(v.data(),words.data(),16);return v;}
inline Vec4 Add(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]+=b[i];return a;}
inline Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]-=b[i];return a;}
inline Vec4 Scale(Vec4 a,float b){for(float& v:a)v*=b;return a;}
inline Vec4 Madd(Vec4 a,float b,Vec4 c){for(std::size_t i=0;i<4;++i)a[i]=std::fma(a[i],b,c[i]);return a;}
inline Vec4 Cross(Vec4 a,Vec4 b){return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),std::fma(-a[3],b[3],a[3]*b[3])};}
inline float Length(Vec4 a){const float s=Dot3(a,a);return s==0?0:s*InverseLengthSquared(s,2);}
inline Vec4 Normalize(Vec4 a){return Scale(a,InverseLengthSquared(Dot3(a,a),2));}
inline Vec4 NormalizeOr(Vec4 a,Vec4 fallback){return Length(a)>Word(0x358637bd)?Normalize(a):fallback;}
inline float Reciprocal(float v){return RefinedReciprocal(v,2);}
inline float Clamp(float v,float low,float high){v=low-v>=0?low:v;return high-v>=0?v:high;}
inline Vec4 LimitLength(Vec4 v,float maximum){const float len=Length(v);if(!(len>=Word(0x37800000)))return v;const float cap=maximum-len>=0?len:maximum;return Scale(Scale(v,cap),Reciprocal(len));}
inline std::int32_t Increment(std::int32_t a){std::uint32_t v;std::memcpy(&v,&a,4);++v;std::memcpy(&a,&v,4);return a;}
inline std::int32_t Signed(std::uint32_t v){std::int32_t out;std::memcpy(&out,&v,4);return out;}
inline float Step(){return Word(0x3c888889);}
}
