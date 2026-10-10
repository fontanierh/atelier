#pragma once
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
#include "OffboardController.h"
#include <cmath>
#include <cstring>
namespace atelier::skate::biped_math
{
inline float Bits(std::uint32_t w){float v;std::memcpy(&v,&w,4);return v;}
inline float Step(){return Bits(0x3c888889);}
inline float Select(float test,float positive,float negative){return test>=0?positive:negative;}
inline float Clamp(float v,float low,float high){v=Select(low-v,low,v);return Select(high-v,v,high);}
inline float Dot(Vec4 a,Vec4 b){return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2];}
inline Vec4 Add(Vec4 a,Vec4 b){for(std::size_t n=0;n<4;++n)a[n]+=b[n];return a;}
inline Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t n=0;n<4;++n)a[n]-=b[n];return a;}
inline Vec4 Mul(Vec4 a,float s){for(auto& n:a)n*=s;return a;}
inline Vec4 Madd(Vec4 a,float s,Vec4 b){for(std::size_t n=0;n<4;++n)b[n]=std::fma(a[n],s,b[n]);return b;}
inline Vec4 Cross(Vec4 a,Vec4 b){return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),std::fma(-a[3],b[3],a[3]*b[3])};}
inline float Inverse(float q,unsigned steps=2){float r=ReciprocalSquareRootEstimate(q);for(unsigned n=0;n<steps;++n)r=std::fma(r*.5f,std::fma(-q,r*r,1.0f),r);return r;}
inline float Root(float q){const auto value=q*Inverse(q);return q==0?0:value;}
inline float Length(Vec4 v){return Root(Dot(v,v));}
inline Vec4 Unit(Vec4 v){return Mul(v,Inverse(Dot(v,v)));}
inline Vec4 UnitOr(Vec4 v,Vec4 fallback){const auto q=Dot(v,v),r=Inverse(q),length=q==0?0:q*r;return length>Bits(0x358637bd)?Mul(v,r):fallback;}
inline float Reciprocal(float d){float r=ReciprocalEstimate(d);for(unsigned n=0;n<2;++n)r=std::fma(r,std::fma(-d,r,1.0f),r);return r;}
inline Vec4 Reject(Vec4 v,Vec4 axis){return Sub(v,Mul(axis,Dot(axis,v)));}
inline float WrapAngle(float angle){const auto t=angle*Bits(0x3e22f983),f=t-std::floor(t);return (f-(f>.5f?1.0f:0.0f))*Bits(0x40c90fdb);}
inline float UnsignedAngle(Vec4 a,Vec4 b){const auto aa=Dot(a,a),bb=Dot(b,b),gate=Bits(0x38d1b717);if(!(aa>gate&&bb>gate))return 0;return Acos(VectorMin(VectorMax(Dot(Mul(a,Inverse(aa,1)),Mul(b,Inverse(bb,1))),-1),1));}
inline float SignedAngle(Vec4 a,Vec4 b,Vec4 axis){const auto aa=Dot(a,a),bb=Dot(b,b),gate=Bits(0x38d1b717);if(!(aa>gate&&bb>gate))return 0;a=Mul(a,Inverse(aa,1));b=Mul(b,Inverse(bb,1));const auto angle=Acos(VectorMin(VectorMax(Dot(a,b),-1),1));return Dot(Cross(a,b),axis)<0?Bits(0x40c90fdb)-angle:angle;}
inline float ProjectedAngle(Vec4 a,Vec4 b,Vec4 axis){if(!(Dot(a,a)*Dot(b,b)>Bits(0x37800000)))return 0;return SignedAngle(Reject(a,axis),Reject(b,axis),axis);}
inline Vec4 Horizontal(Vec4 v){return UnitOr({v[0],0,v[2],v[0]},{});}
inline Vec4 TransformVector(Vec4 v,const Mat4& f){return Madd(f[2],v[2],Madd(f[1],v[1],Mul(f[0],v[0])));}
inline Vec4 TransformPoint(Vec4 v,const Mat4& f){return Madd(f[2],v[2],Madd(f[1],v[1],Madd(f[0],v[0],f[3])));}
inline Mat4 Compose(const Mat4& a,const Mat4& b){return {{TransformVector(a[0],b),TransformVector(a[1],b),TransformVector(a[2],b),TransformPoint(a[3],b)}};}
inline Vec4 LimitAngle(Vec4 target,Vec4 from,float maximum)
{
    const auto a=UnitOr(target,{}),b=UnitOr(from,{}),axis=Cross(a,b);
    const auto angle=Acos(VectorMin(VectorMax(Dot(a,b),-1),1));const auto turns=std::floor(std::fma(angle,Bits(0x3e22f983),.5f));
    const auto closest=std::fma(-turns,Bits(0x40c90fdb),angle);
    if(std::abs(closest)<maximum||Dot(axis,axis)<Bits(0x37800000))return target;
    const auto sc=SinCos((-maximum)*.5f);auto q=Mul(Unit(axis),sc.first);q[3]=sc.second;
    const auto middle=Madd(from,sc.second,Cross(q,from));return Mul(Madd(Cross(q,middle),2,from),Length(target));
}
inline Vec4 ClampLength(Vec4 v,float maximum)
{
    const auto length=Length(v);if(!(length>=Bits(0x37800000)))return v;
    const auto bounded=Select(maximum-length,length,maximum);float inverse=ReciprocalEstimate(length);
    for(unsigned n=0;n<2;++n)inverse=std::fma(inverse,std::fma(-inverse,length,1.0f),inverse);
    for(auto& x:v)x=(x*bounded)*inverse;return v;
}
inline BipedVector3 XYZ(Vec4 v){return {v[0],v[1],v[2]};}
}
