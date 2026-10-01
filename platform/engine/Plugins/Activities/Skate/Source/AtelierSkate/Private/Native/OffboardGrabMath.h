// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "OffboardGrabScene.h"
#include <cmath>
#include <cstring>
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_grab_math
{
inline float Bits(std::uint32_t w){float v;std::memcpy(&v,&w,4);return v;}
inline std::uint32_t Word(float v){std::uint32_t w;std::memcpy(&w,&v,4);return w;}
inline float Dot(Vec4 a,Vec4 b){return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2];}
inline Vec4 Sub(Vec4 a,Vec4 b){for(unsigned n=0;n<4;++n)a[n]-=b[n];return a;}
inline Vec4 Mul(Vec4 a,float k){for(auto& n:a)n*=k;return a;}
inline Vec4 Madd(Vec4 a,float k,Vec4 b){for(unsigned n=0;n<4;++n)b[n]=std::fma(a[n],k,b[n]);return b;}
inline Vec4 Cross(Vec4 a,Vec4 b){return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),std::fma(-a[3],b[3],a[3]*b[3])};}
inline float Inverse(float q,unsigned steps=2){auto r=ReciprocalSquareRootEstimate(q);for(unsigned n=0;n<steps;++n)r=std::fma(r*.5f,std::fma(-q,r*r,1.0f),r);return r;}
inline float Length(Vec4 v){const auto q=Dot(v,v),r=Inverse(q);return q==0?0:q*r;}
inline Vec4 Unit(Vec4 v){const auto q=Dot(v,v),r=Inverse(q),length=q==0?0:q*r;return length>Bits(0x358637bd)?Mul(v,r):Vec4{};}
inline Vec4 Flat(Vec4 v){v[1]=0;return v;}
// Record/query and qualification use distinct original fused operands.
inline float RecordReciprocal(float value){float r=1.0f/value;for(unsigned n=0;n<2;++n)r=std::fma(r,std::fma(-r,value,1.0f),r);return r;}
inline float QualifyReciprocal(float value){float r=1.0f/value;for(unsigned n=0;n<2;++n)r=std::fma(r,std::fma(-value,r,1.0f),r);return r;}
inline Vec4 Point(const Mat4& f,Vec4 v){return Madd(f[2],v[2],Madd(f[1],v[1],Madd(f[0],v[0],f[3])));}
inline Vec4 Direction(const Mat4& f,Vec4 v){return Madd(f[2],v[2],Madd(f[1],v[1],Mul(f[0],v[0])));}
inline Vec4 InversePoint(const Mat4& f,Vec4 p)
{
    Vec4 out{};for(unsigned n=0;n<3;++n){const auto translation=std::fma(f[n][0],-f[3][0],std::fma(f[n][1],-f[3][1],f[n][2]*(-f[3][2])));out[n]=std::fma(f[n][2],p[2],std::fma(f[n][1],p[1],std::fma(f[n][0],p[0],translation)));}return out;
}
inline float Angle(Vec4 a,Vec4 b)
{const auto aa=Dot(a,a),bb=Dot(b,b);if(!(aa>Bits(0x38d1b717)&&bb>Bits(0x38d1b717)))return 0;return Acos(VectorMin(VectorMax(Dot(Mul(a,Inverse(aa,1)),Mul(b,Inverse(bb,1))),-1),1));}
inline bool Same(OffboardGrabDescriptor a,OffboardGrabDescriptor b){return a.kind==b.kind&&a.id==b.id;}
inline Mat4 Frame(const OffboardGrabRecord& r){return {{GrabRecordVector(r,0),GrabRecordVector(r,16),GrabRecordVector(r,32),GrabRecordVector(r,48)}};}
inline bool Reversed(const OffboardGrabRecord& r){return ((r.words[50]>>24)&0x20)!=0;}
inline bool SphereSegment(Vec4 center,float radius,Vec4 start,Vec4 end)
{
    const auto c=Sub(center,start);const auto rr=radius*radius;if(Dot(c,c)<rr)return true;const auto d=Sub(end,start);const auto projection=Dot(c,d);if(!(projection>0))return false;const auto dd=Dot(d,d);const Vec4 cross{std::fma(-c[2],d[1],c[1]*d[2]),std::fma(-c[0],d[2],c[2]*d[0]),std::fma(-c[1],d[0],c[0]*d[1]),0};const auto discriminant=dd*rr-Dot(cross,cross),beyond=projection-dd;return !(discriminant<0||(beyond>0&&beyond*beyond>discriminant));
}
float NearestPolylineDistance(const OffboardGrabRecord&,Vec4);
Vec4 PolylineAtDistance(const OffboardGrabRecord&,float);
}
