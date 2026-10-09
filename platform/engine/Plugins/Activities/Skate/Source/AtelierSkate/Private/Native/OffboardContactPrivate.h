#pragma once
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
#include "OffboardContactToolkit.h"
#include <algorithm>
#include <cmath>
#include <cstring>
namespace atelier::skate::offboard_contact
{
inline float Bits(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
inline float Dot(Vec4 a,Vec4 b){return Dot3(a,b);}
inline Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t n=0;n<4;++n)a[n]-=b[n];return a;}
inline Vec4 Scale(Vec4 a,float f){for(auto& v:a)v*=f;return a;}
inline Vec4 Madd(Vec4 a,float f,Vec4 b){for(std::size_t n=0;n<4;++n)b[n]=std::fma(a[n],f,b[n]);return b;}
inline Vec4 Cross(Vec4 a,Vec4 b){return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1]),0};}
inline float Inverse(float q,unsigned stages=2){auto r=ReciprocalSquareRootEstimate(q);for(unsigned n=0;n<stages;++n)r=std::fma(r*.5f,std::fma(-q,r*r,1.0f),r);return r;}
inline float Length(Vec4 v){const auto q=Dot(v,v);if(q==0)return 0;return q*Inverse(q);}
inline float Reciprocal(float v){auto r=ReciprocalEstimate(v);for(unsigned n=0;n<2;++n)r=std::fma(r,std::fma(-r,v,1.0f),r);return r;}
inline Vec4 Normalize(Vec4 v,Vec4 fallback){const auto l=Length(v);return l>Bits(0x358637bd)?Scale(v,Reciprocal(l)):fallback;}
inline bool Valid(const AirTrajectoryQueryResult& r){return r.contact_time>=0;}
inline std::optional<Vec4> PlaneSegment(Vec4 p,Vec4 n,Vec4 a,Vec4 b)
{const auto da=Dot(n,Sub(a,p)),db=Dot(n,Sub(b,p));if(da*db>=0)return std::nullopt;const auto aa=std::abs(da),bb=std::abs(db),sum=aa+bb;return Madd(a,bb/sum,Scale(b,aa/sum));}
inline Vec4 ClampNormal(Vec4 a,Vec4 b,Vec4 normal)
{
    a=Normalize(a,{});b=Normalize(b,{});const auto axis=Normalize(Cross(a,b),{}),projected=Normalize(Sub(normal,Scale(axis,Dot(axis,normal))),{});
    if(((Dot(axis,axis)*Dot(projected,projected))*Dot(a,a))*Dot(b,b)<.1f)return normal;
    if(Dot(Cross(a,projected),axis)>0&&Dot(Cross(projected,b),axis)>0)return projected;
    return Dot(projected,a)>Dot(projected,b)?a:b;
}
inline float Intersection(std::array<float,2> a,std::array<float,2> b,std::array<float,2> c,std::array<float,2> d)
{
    const std::array<float,2> u{b[0]-a[0],b[1]-a[1]},v{d[0]-c[0],d[1]-c[1]};const auto denominator=v[1]*u[0]-v[0]*u[1];
    if(std::abs(denominator)<.00001f)return 1.0e10f;return (1.0f/denominator)*(v[0]*(a[1]-c[1])-v[1]*(a[0]-c[0]));
}
float Tangent(float);
void Sort(std::vector<OffboardContactSample>&);
OffboardContactSamples Collect(const OffboardQueryBatch&,const OffboardProbeLayout&,const OffboardQueryResults&);
void InsertObstacles(OffboardToolkitInput,OffboardContactSamples&);void CorrectNormals(OffboardToolkitInput,OffboardContactSamples&);
struct Segment{std::uint32_t kind;Vec4 start,end,direction,normal;float length;};
struct Profile{std::vector<Segment> segments;std::size_t last_ground=0;};
std::pair<float,std::size_t> Simplify(OffboardToolkitInput,std::vector<OffboardContactSample>&);
Profile BuildProfile(OffboardToolkitInput,const std::vector<OffboardContactSample>&,std::size_t count);
std::vector<OffboardContactCandidate> Generate(OffboardToolkitInput,const Profile&,const OffboardContactPrefix&,float obstruction,std::uint32_t retained_flags);
void Publish(OffboardToolkitInput,const Profile&,const OffboardContactSamples&,std::vector<OffboardContactCandidate>&,float obstruction,OffboardContactCandidate&,OffboardContactHistory&,OffboardContactPrefix&);
}
