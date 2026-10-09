#include "WipeoutOrientation.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits) {float v;std::memcpy(&v,&bits,4);return v;}
Vec4 Scale(Vec4 v,float s) {for (auto& x:v) x*=s;return v;}
Vec4 Sub(Vec4 a,Vec4 b) {for (std::size_t i=0;i<4;++i) a[i]-=b[i];return a;}
float Clamp(float v,float low,float high) {v=low-v>=0?low:v;return high-v>=0?v:high;}
}
float WipeoutSignedAngle(Vec4 left,Vec4 right,Vec4 axis)
{
    const auto a=Dot3(left,left),b=Dot3(right,right);if (!(a>Float(0x38d1b717)&&b>Float(0x38d1b717))) return 0;
    left=Scale(left,InverseLengthSquared(a,1));right=Scale(right,InverseLengthSquared(b,1));const auto angle=Acos(Clamp(Dot3(left,right),-1,1));return Dot3(Cross3(left,right),axis)<0?Float(0x40c90fdb)-angle:angle;
}
float WipeoutProjectedAngle(Vec4 left,Vec4 right,Vec4 axis)
{
    if (!(Dot3(left,left)*Dot3(right,right)>Float(0x37800000))) return 0;
    return WipeoutSignedAngle(Sub(left,Scale(axis,Dot3(axis,left))),Sub(right,Scale(axis,Dot3(axis,right))),axis);
}
float WipeoutWrapAngle(float angle)
{
    const auto turns=angle*Float(0x3e22f983),fraction=turns-std::floor(turns),centered=fraction>.5f?fraction-1.0f:fraction;return centered*Float(0x40c90fdb);
}
}
