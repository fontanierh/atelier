#pragma once
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
#include "OffboardGroundGeometry.h"
#include <cstring>
namespace atelier::skate::offboard_ground_query
{
inline float Bits(std::uint32_t w){float v;std::memcpy(&v,&w,4);return v;}
inline Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline Vec3 Sub(Vec3 a,Vec3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
inline Vec3 Mul(Vec3 a,float f){return {a.x*f,a.y*f,a.z*f};}
inline Vec3 Fma(Vec3 a,float f,Vec3 b){return {std::fma(a.x,f,b.x),std::fma(a.y,f,b.y),std::fma(a.z,f,b.z)};}
inline float Dot(Vec3 a,Vec3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Vec3 Cross(Vec3 a,Vec3 b){return {std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};}
inline Vec3 Horizontal(Vec3 v){return {v.x,0,v.z};}
inline Vec3 Abs(Vec3 v){return {std::abs(v.x),std::abs(v.y),std::abs(v.z)};}
inline float InverseRoot(float q){auto r=ReciprocalSquareRootEstimate(q);for(unsigned n=0;n<2;++n)r=std::fma(r*.5f,std::fma(-q,r*r,1.0f),r);return r;}
inline float Length(Vec3 v){const auto q=Dot(v,v),length=q*InverseRoot(q);return q==0?0:length;}
inline float Reciprocal(float x){auto r=ReciprocalEstimate(x);for(unsigned n=0;n<2;++n)r=std::fma(r,std::fma(-x,r,1.0f),r);return r;}
inline Vec3 Unit(Vec3 a,Vec3 fallback){const auto q=Dot(a,a),r=InverseRoot(q),length=q==0?0:q*r;return length>Bits(0x358637bd)?Mul(a,r):fallback;}
inline Vec3 Point(OffboardGroundFrame f,Vec3 p){return Fma(f.forward,p.z,Fma(f.up,p.y,Fma(f.right,p.x,f.position)));}
inline Bounds TransformBounds(OffboardGroundFrame f,Bounds b)
{
    const auto center=Point(f,Mul(Add(b.max,b.min),.5f)),half=Mul(Sub(b.max,b.min),.5f);
    const auto extent=Fma(Abs(f.forward),half.z,Fma(Abs(f.up),half.y,Mul(Abs(f.right),half.x)));
    return {Sub(center,extent),Add(center,extent)};
}
inline bool Overlaps(Bounds a,Bounds b){return a.min.x<=b.max.x&&a.max.x>=b.min.x&&a.min.y<=b.max.y&&a.max.y>=b.min.y&&a.min.z<=b.max.z&&a.max.z>=b.min.z;}
inline bool Matches(std::int32_t a,std::int32_t b){return a==-1||b==-1||a==b;}
}
