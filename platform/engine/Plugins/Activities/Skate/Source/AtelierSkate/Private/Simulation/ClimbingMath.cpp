// SPDX-License-Identifier: MIT
// Adapted from glam 0.32.1 (neon Mat4/Quat, Vec3 and f32 math), the arithmetic
// selected by the pinned Bevy host on AArch64. License notice follows:
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
// of the Software, and to permit persons to whom the Software is furnished to
// do so, subject to the following conditions: The above copyright notice and
// this permission notice shall be included in all copies or substantial portions
// of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY
// KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
// MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
// EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
// OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
// ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
// DEALINGS IN THE SOFTWARE.
#include "ClimbingMath.h"
#include <cmath>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::climbing_math {
namespace {
Vec4 Add4(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]+=b[i];return a;}
Vec4 Sub4(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 Mul4(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]*=b[i];return a;}
Vec4 Scale4(Vec4 a,float s){for(auto& v:a)v*=s;return a;}
float SimdDot4(Vec4 a,Vec4 b){const auto v=Mul4(a,b);return (v[0]+v[1])+(v[2]+v[3]);}
float SimdDot3(Vec3 a,Vec3 b){return (a.x*b.x+a.y*b.y)+(a.z*b.z+0.0f);}
template<unsigned A,unsigned B,unsigned C,unsigned D>Vec4 Swizzle(Vec4 a,Vec4 b){
 const std::array<float,8> v{a[0],a[1],a[2],a[3],b[0],b[1],b[2],b[3]};return {v[A],v[B],v[C],v[D]};
}
float AcosApprox(float v){const bool positive=v>=0;const auto x=std::fabs(v);auto omx=1.0f-x;if(omx<0)omx=0;const auto root=std::sqrt(omx);
 auto result=((((((-0.0012624911f*x+0.00667009f)*x-0.017088126f)*x+0.03089188f)*x-0.050174303f)*x+0.08897899f)*x-0.2145988f)*x+1.5707963f;
 result*=root;return positive?result:3.14159265358979323846f-result;
}
}
Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
Vec3 Sub(Vec3 a,Vec3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
Vec3 ScaleVector(Vec3 a,float s){return {a.x*s,a.y*s,a.z*s};}
float Dot(Vec3 a,Vec3 b){return (a.x*b.x+a.y*b.y)+a.z*b.z;}
Vec3 Cross(Vec3 a,Vec3 b){return {a.y*b.z-b.y*a.z,a.z*b.x-b.z*a.x,a.x*b.y-b.x*a.y};}
float Length(Vec3 a){return std::sqrt(Dot(a,a));}
float Distance(Vec3 a,Vec3 b){return Length(Sub(a,b));}
Vec3 Normalize(Vec3 a){return ScaleVector(a,1.0f/Length(a));}
std::optional<Vec3> TryNormalize(Vec3 a){const auto r=1.0f/Length(a);if(std::isfinite(r)&&r>0)return ScaleVector(a,r);return std::nullopt;}
Vec3 NormalizeOrZero(Vec3 a){return TryNormalize(a).value_or(Vec3{});}
Vec3 Orthonormal(Vec3 a){const auto sign=std::isnan(a.z)?a.z:std::copysign(1.0f,a.z);const auto v=-1.0f/(sign+a.z);const auto b=a.x*a.y*v;return {b,sign+a.y*a.y*v,-a.y};}
Vec3 Lerp(Vec3 a,Vec3 b,float s){return Add(ScaleVector(a,1.0f-s),ScaleVector(b,s));}
float Length4(Vec4 q){return std::sqrt(SimdDot4(q,q));}
Quat NormalizeQuat(Quat q){return Scale4(q,1.0f/Length4(q));}
Quat InverseQuat(Quat q){return Mul4(q,{-1,-1,-1,1});}
Quat MultiplyQuat(Quat lhs,Quat rhs){
 const auto a=Scale4(rhs,lhs[3]);
 const auto b=Mul4(Scale4(Swizzle<3,2,1,0>(rhs,rhs),lhs[0]),{1,-1,1,-1});
 const auto c=Mul4(Scale4(Swizzle<2,3,0,1>(rhs,rhs),lhs[1]),{1,1,-1,-1});
 const auto d=Mul4(Scale4(Swizzle<1,0,3,2>(rhs,rhs),lhs[2]),{-1,1,1,-1});
 return Add4(Add4(a,b),Add4(c,d));
}
Quat RotationAxes(Vec3 x,Vec3 y,Vec3 z){
 const auto m00=x.x,m01=x.y,m02=x.z,m10=y.x,m11=y.y,m12=y.z,m20=z.x,m21=z.y,m22=z.z;
 if(m22<=0){const auto dif10=m11-m00,omm22=1.0f-m22;if(dif10<=0){const auto four=omm22-dif10,inv=.5f/std::sqrt(four);return {four*inv,(m01+m10)*inv,(m02+m20)*inv,(m12-m21)*inv};}
 const auto four=omm22+dif10,inv=.5f/std::sqrt(four);return {(m01+m10)*inv,four*inv,(m12+m21)*inv,(m20-m02)*inv};}
 const auto sum10=m11+m00,opm22=1.0f+m22;if(sum10<=0){const auto four=opm22-sum10,inv=.5f/std::sqrt(four);return {(m02+m20)*inv,(m12+m21)*inv,four*inv,(m01-m10)*inv};}
 const auto four=opm22+sum10,inv=.5f/std::sqrt(four);return {(m12-m21)*inv,(m20-m02)*inv,(m01-m10)*inv,four*inv};
}
Quat RotationY(float angle){const auto half=angle*.5f;return {0,std::sin(half),0,std::cos(half)};}
Quat RotationArc(Vec3 from,Vec3 to){const auto dot=Dot(from,to);constexpr auto limit=1.0f-2.0f*std::numeric_limits<float>::epsilon();if(dot>limit)return {0,0,0,1};if(dot<-limit){const auto axis=Orthonormal(from);const auto half=3.14159265358979323846f*.5f;const auto s=std::sin(half);return {axis.x*s,axis.y*s,axis.z*s,std::cos(half)};}const auto c=Cross(from,to);return NormalizeQuat({c.x,c.y,c.z,1.0f+dot});}
Quat Slerp(Quat from,Quat to,float s){auto dot=SimdDot4(from,to);if(dot<0){for(auto& v:to)v=-v;dot=-dot;}if(dot>1.0f-std::numeric_limits<float>::epsilon())return NormalizeQuat(Add4(Scale4(from,1.0f-s),Scale4(to,s)));const auto theta=AcosApprox(dot);const auto a=std::sin(theta*(1.0f-s)),b=std::sin(theta*s),theta_sin=std::sin(theta);return Scale4(Add4(Scale4(from,a),Scale4(to,b)),1.0f/theta_sin);}
Vec3 Rotate(Quat q,Vec3 v){const Vec3 b{q[0],q[1],q[2]};const auto b2=SimdDot3(b,b);return Add(Add(ScaleVector(v,q[3]*q[3]-b2),ScaleVector(b,SimdDot3(v,b)*2.0f)),ScaleVector(Cross(b,v),q[3]*2.0f));}
Mat4 Matrix(const Mat4& m){auto out=m;for(unsigned i=0;i<3;++i)out[i][3]=0;out[3][3]=1;return out;}
Mat4 Simulation(const Mat4& m){auto out=m;out[3][3]=0;return out;}
Vec3 Translation(const Mat4& m){return {m[3][0],m[3][1],m[3][2]};}
Vec3 Point(const Mat4& m,Vec3 v){auto res=Scale4(m[0],v.x);res=Add4(Scale4(m[1],v.y),res);res=Add4(Scale4(m[2],v.z),res);res=Add4(m[3],res);return {res[0],res[1],res[2]};}
Vec3 Vector(const Mat4& m,Vec3 v){auto res=Scale4(m[0],v.x);res=Add4(Scale4(m[1],v.y),res);res=Add4(Scale4(m[2],v.z),res);return {res[0],res[1],res[2]};}
Mat4 Multiply(const Mat4& a,const Mat4& b){Mat4 out;for(unsigned i=0;i<4;++i){auto res=Scale4(a[0],b[i][0]);res=Add4(res,Scale4(a[1],b[i][1]));res=Add4(res,Scale4(a[2],b[i][2]));out[i]=Add4(res,Scale4(a[3],b[i][3]));}return out;}
float Determinant(const Mat4& m){const auto& a=m[0];const auto& b=m[1];const auto& c=m[2];const auto& d=m[3];const auto a2323=c[2]*d[3]-c[3]*d[2],a1323=c[1]*d[3]-c[3]*d[1],a1223=c[1]*d[2]-c[2]*d[1],a0323=c[0]*d[3]-c[3]*d[0],a0223=c[0]*d[2]-c[2]*d[0],a0123=c[0]*d[1]-c[1]*d[0];return ((a[0]*(b[1]*a2323-b[2]*a1323+b[3]*a1223)-a[1]*(b[0]*a2323-b[2]*a0323+b[3]*a0223))+a[2]*(b[0]*a1323-b[1]*a0323+b[3]*a0123))-a[3]*(b[0]*a1223-b[1]*a0223+b[2]*a0123);}
Mat4 Inverse(const Mat4& m){
 const auto factor=[&](unsigned first,unsigned second){
  const auto sw=[&](Vec4 a,Vec4 b,unsigned lane){return Vec4{a[lane],a[lane],b[lane],b[lane]};};
  const auto x=sw(m[3],m[2],first),y=sw(m[3],m[2],second);
  return Sub4(Mul4(sw(m[2],m[1],second),Swizzle<0,0,4,6>(x,x)),Mul4(Swizzle<0,0,4,6>(y,y),sw(m[2],m[1],first)));
 };
 const auto f0=factor(3,2),f1=factor(3,1),f2=factor(2,1),f3=factor(3,0),f4=factor(2,0),f5=factor(1,0);
 std::array<Vec4,4> v;for(unsigned i=0;i<4;++i){const Vec4 t{m[1][i],m[1][i],m[0][i],m[0][i]};v[i]=Swizzle<0,2,6,6>(t,t);}
 Mat4 out;
 out[0]=Mul4({1,-1,1,-1},Add4(Sub4(Mul4(v[1],f0),Mul4(v[2],f1)),Mul4(v[3],f2)));
 out[1]=Mul4({-1,1,-1,1},Add4(Sub4(Mul4(v[0],f0),Mul4(v[2],f3)),Mul4(v[3],f4)));
 out[2]=Mul4({1,-1,1,-1},Add4(Sub4(Mul4(v[0],f1),Mul4(v[1],f3)),Mul4(v[3],f5)));
 out[3]=Mul4({-1,1,-1,1},Add4(Sub4(Mul4(v[0],f2),Mul4(v[1],f4)),Mul4(v[2],f5)));
 const Vec4 row{out[0][0],out[1][0],out[2][0],out[3][0]};const auto reciprocal=1.0f/SimdDot4(m[0],row);for(auto& c:out)c=Scale4(c,reciprocal);return out;
}
float Smooth(float t){if(t<0)t=0;if(t>1)t=1;return t*t*(3.0f-2.0f*t);}
Mat4 Transform::ToMatrix() const{const auto x=rotation[0],y=rotation[1],z=rotation[2],w=rotation[3];const auto x2=x+x,y2=y+y,z2=z+z,xx=x*x2,xy=x*y2,xz=x*z2,yy=y*y2,yz=y*z2,zz=z*z2,wx=w*x2,wy=w*y2,wz=w*z2;return {Scale4({1.0f-(yy+zz),xy+wz,xz-wy,0},scale.x),Scale4({xy-wz,1.0f-(xx+zz),yz+wx,0},scale.y),Scale4({xz+wy,yz-wx,1.0f-(xx+yy),0},scale.z),Vec4{translation.x,translation.y,translation.z,1}};}
Transform Transform::FromMatrix(const Mat4& m){const auto determinant=Determinant(m);const auto sign=std::isnan(determinant)?determinant:std::copysign(1.0f,determinant);const Vec3 scale{Length4(m[0])*sign,Length4(m[1]),Length4(m[2])};const auto x=Scale4(m[0],1.0f/scale.x),y=Scale4(m[1],1.0f/scale.y),z=Scale4(m[2],1.0f/scale.z);return {Translation(m),RotationAxes({x[0],x[1],x[2]},{y[0],y[1],y[2]},{z[0],z[1],z[2]}),scale};}
Transform Blend(Transform a,Transform b,float s){return {Lerp(a.translation,b.translation,s),Slerp(a.rotation,b.rotation,s),Lerp(a.scale,b.scale,s)};}
} // namespace atelier::skate::climbing_math
