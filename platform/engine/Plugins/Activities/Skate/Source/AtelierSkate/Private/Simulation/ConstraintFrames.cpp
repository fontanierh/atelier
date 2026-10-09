#include "ConstraintFrames.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate::constraint_frame
{
namespace
{
Vec3 InertiaTail(PackedWorldInverseInertia t,Vec3 v,Vec3 first)
{
    return {std::fma(t.full.z,v.z,std::fma(t.full.y,v.y,first.x)),
        std::fma(t.split.z,v.z,std::fma(t.split.y,v.y,first.y)),
        std::fma(t.split.x,v.z,std::fma(t.split.z,v.y,first.z))};
}
}
QuaternionRows Rows(Quat a,Quat b)
{
    const float xx=a[0]*b[0],xy=a[0]*b[1],xz=a[0]*b[2],xw=a[0]*b[3];
    const float yx=a[1]*b[0],yy=a[1]*b[1],yz=a[1]*b[2],yw=a[1]*b[3];
    const float zx=a[2]*b[0],zy=a[2]*b[1],zz=a[2]*b[2],zw=a[2]*b[3];
    const float wx=a[3]*b[0],wy=a[3]*b[1],wz=a[3]*b[2],ww=a[3]*b[3];
    return {{{Vec3{((ww+xx)-yy)-zz,((yx+xy)+wz)+zw,((xz+zx)-wy)-yw},
        Vec3{((yx+xy)-wz)-zw,((ww+yy)-zz)-xx,((yz+zy)+wx)+xw},
        Vec3{((xz+zx)+yw)+wy,((zy+yz)-wx)-xw,((ww+zz)-xx)-yy}}},
        {((wx-xw)+zy)-yz,((wy-yw)+xz)-zx,((wz-zw)+yx)-xy,((ww+zz)+yy)+xx}};
}
Quat Compose(Quat a,Quat b)
{
    const Vec3 av{a[0],a[1],a[2]},bv{b[0],b[1],b[2]};const auto cross=Cross3(av,bv);
    return {std::fma(a[0],b[3],std::fma(b[0],a[3],cross.x)),
        std::fma(a[1],b[3],std::fma(b[1],a[3],cross.y)),
        std::fma(a[2],b[3],std::fma(b[2],a[3],cross.z)),a[3]*b[3]-Dot3(av,bv)};
}
Basis3 Basis(Quat q)
{
    const std::uint32_t word=0x3fb504f3;float root_two;std::memcpy(&root_two,&word,4);
    const float x=q[0]*root_two,y=q[1]*root_two,z=q[2]*root_two,w=q[3]*root_two;
    const float dx=std::fma(-x,x,0.5f),dy=std::fma(-y,y,0.5f),dz=std::fma(-z,z,0.5f);
    const float xy=x*y,yz=y*z,zx=z*x,wz=w*z,wx=w*x,wy=w*y;
    return {{{{dy+dz,xy+wz,zx-wy},{xy-wz,dz+dx,yz+wx},{zx+wy,yz-wx,dx+dy}}}};
}
Vec3 TransformDirection(Basis3 basis,Vec3 v)
{
    const auto& c=basis.columns;
    return {std::fma(c[2][0],v.z,std::fma(c[1][0],v.y,c[0][0]*v.x)),
        std::fma(c[2][1],v.z,std::fma(c[1][1],v.y,c[0][1]*v.x)),
        std::fma(c[2][2],v.z,std::fma(c[1][2],v.y,c[0][2]*v.x))};
}
Vec3 PointRate(Vec3 linear,Vec3 angular,Vec3 arm)
{
    return {std::fma(arm.z,angular.y,std::fma(-arm.y,angular.z,linear.x)),
        std::fma(arm.x,angular.z,std::fma(-arm.z,angular.x,linear.y)),
        std::fma(arm.y,angular.x,std::fma(-arm.x,angular.y,linear.z))};
}
Vec3 MultiplyInertia(PackedWorldInverseInertia t,Vec3 v)
{return InertiaTail(t,v,{t.full.x*v.x,t.full.y*v.x,t.full.z*v.x});}
Vec3 MultiplyInertiaFromZero(PackedWorldInverseInertia t,Vec3 v)
{return InertiaTail(t,v,{std::fma(t.full.x,v.x,0.0f),std::fma(t.full.y,v.x,0.0f),std::fma(t.full.z,v.x,0.0f)});}
std::array<Vec3,3> Columns(Basis3 basis)
{const auto& c=basis.columns;return {Vec3{c[0][0],c[0][1],c[0][2]},Vec3{c[1][0],c[1][1],c[1][2]},Vec3{c[2][0],c[2][1],c[2][2]}};}
std::array<float,3> Project(Vec3 v,const std::array<Vec3,3>& axes)
{return {Dot3(v,axes[0]),Dot3(v,axes[1]),Dot3(v,axes[2])};}
}
