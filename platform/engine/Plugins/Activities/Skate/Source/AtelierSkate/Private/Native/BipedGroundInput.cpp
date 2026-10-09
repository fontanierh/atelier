#include "BipedGroundState.h"
#include "OffboardControllerMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
using ControlVector=std::array<float,3>;
float ControlDot(ControlVector a,ControlVector b){return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2];}
ControlVector ControlCross(ControlVector a,ControlVector b){return {std::fma(-a[2],b[1],a[1]*b[2]),std::fma(-a[0],b[2],a[2]*b[0]),std::fma(-a[1],b[0],a[0]*b[1])};}
ControlVector ControlNormalize(ControlVector v){const auto inverse=InverseLengthSquared(ControlDot(v,v),2);for(auto& x:v)x*=inverse;return v;}
ControlVector ControlInverseFrame(ControlVector right,ControlVector up,ControlVector forward,ControlVector v)
{
    const std::array<ControlVector,3> columns{{ControlCross(up,forward),ControlCross(forward,right),ControlCross(right,up)}};
    const auto determinant=ControlDot(right,columns[0]);float reciprocal=1.0f/determinant;
    for(unsigned n=0;n<2;++n)reciprocal=std::fma(reciprocal,std::fma(-determinant,reciprocal,1.0f),reciprocal);
    ControlVector result;for(unsigned n=0;n<3;++n){const auto x=columns[n][0]*reciprocal,y=columns[n][1]*reciprocal,z=columns[n][2]*reciprocal;result[n]=std::fma(z,v[2],std::fma(y,v[1],x*v[0]));}return result;
}
float ControlSignedAngle(float x,float y)
{
    const float seed=1.0f/y,reciprocal=std::fma(seed,std::fma(-y,seed,1.0f),seed);float angle=Atan(std::fma(x,reciprocal,0.0f));
    if(y<0)angle+=std::copysign(biped_math::Bits(0x40490fdb),x);if(y==0)angle=std::copysign(biped_math::Bits(0x3fc90fdb),x);return angle;
}
}
BipedGroundControlOutput CalculateBipedGroundInput(const BipedGroundControlInput& input,const PointGraph<8>& movement,const PointGraph<8>& turn)
{
    if((input.processed_flags_2472&0x10000000)!=0)return {input.processed_direct_2684,input.processed_direct_2680,{}};
    const ControlVector raw{{input.processed_stick_2692,0,input.processed_stick_2688}},up{{0,1,0}};ControlVector right{{1,0,0}},forward{{0,0,1}};
    if(ControlDot(input.frame_forward_112,up)<biped_math::Bits(0x3f7fbe77)){right=ControlNormalize(ControlCross(up,input.frame_forward_112));forward=ControlNormalize(ControlCross(right,up));}
    const auto local=ControlInverseFrame(right,up,forward,raw);const float angle=ControlSignedAngle(local[0],-local[2])*biped_math::Bits(0x3ea2f983),sign=angle>=0?1.0f:-1.0f;
    const float square=ControlDot(local,local),result=square*InverseLengthSquared(square,2),magnitude=square==0?0:result,absolute=angle*sign;
    return {(movement.Evaluate(absolute)*magnitude)*input.processed_scale_2912,((turn.Evaluate(absolute)*magnitude)*sign)*input.processed_scale_2908,{raw[0],raw[1],raw[2],0}};
}
}
