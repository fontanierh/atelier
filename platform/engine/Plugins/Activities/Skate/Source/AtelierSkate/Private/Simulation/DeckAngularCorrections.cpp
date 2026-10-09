#include "DeckAngularCorrections.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
Vec3 DeckScale(Vec3 v,float x){return {v.x*x,v.y*x,v.z*x};}
Vec3 DeckSubtract(Vec3 a,Vec3 b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
Vec3 DeckCross(Vec3 a,Vec3 b)
{return {std::fma(-a.z,b.y,a.y*b.z),std::fma(-a.x,b.z,a.z*b.x),std::fma(-a.y,b.x,a.x*b.y)};}
Vec3 DeckMultiply(Basis3 m,Vec3 v)
{
    const auto lane=[&](unsigned i){return std::fma(m.columns[2][i],v.z,std::fma(m.columns[1][i],v.y,m.columns[0][i]*v.x));};
    return {lane(0),lane(1),lane(2)};
}
Basis3 DeckInvert(Basis3 tensor)
{
    const auto& a=tensor.columns[0];const auto& b=tensor.columns[1];const auto& c=tensor.columns[2];
    const Vec3 av{a[0],a[1],a[2]};const auto first=DeckCross({b[0],b[1],b[2]},{c[0],c[1],c[2]}),second=DeckCross({c[0],c[1],c[2]},av),third=DeckCross(av,{b[0],b[1],b[2]});
    const float inverse=RefinedReciprocal(Dot3(av,first),2);Basis3 result;
    result.columns={{{first.x*inverse,second.x*inverse,third.x*inverse},{first.y*inverse,second.y*inverse,third.y*inverse},{first.z*inverse,second.z*inverse,third.z*inverse}}};return result;
}
Vec3 DeckExisting(BodyRates& body,Vec3 requested)
{
    const float squared=Dot3(requested,requested),inverse=InverseLengthSquared(squared,2),length=squared==0.0f?0.0f:squared*inverse;
    const auto direction=length>Scalar(0x358637bd)?DeckScale(requested,inverse):Vec3{};
    return DeckScale(direction,Dot3(direction,DeckScale(body.angular_velocity,Scalar(0x3c888889))));
}
float GroundTorqueScalar()
{
    const float x=.25f,square=x*x,cube=x*square,fourth=square*square;
    const float log[]={Scalar(0x3fb8aa0e),Scalar(0xbf389e52),Scalar(0x3ef5162d),Scalar(0xbeb1d204),Scalar(0x3e77adbd),Scalar(0xbe0cd4fb),Scalar(0x3d5541c6),Scalar(0xbc188b0b)};
    const float low=std::fma(cube,log[3],std::fma(square,log[2],std::fma(x,log[1],log[0])));
    const float high=std::fma(cube,log[7],std::fma(square,log[6],std::fma(x,log[5],log[4])));
    const float exponent=std::fma(-x,std::fma(fourth,high,low),-3.0f),integral=std::floor(exponent),fraction=exponent-integral;
    const float s=fraction*fraction,c=fraction*s,f=s*s;
    const float exp[]={Scalar(0x3f800000),Scalar(0xbf317218),Scalar(0x3e75fded),Scalar(0xbd6357ca),Scalar(0x3c1d8c54),Scalar(0xbaae1854),Scalar(0x391aa7d7),Scalar(0xb7364261)};
    const float l=std::fma(c,exp[3],std::fma(s,exp[2],std::fma(fraction,exp[1],exp[0])));
    const float h=std::fma(c,exp[7],std::fma(s,exp[6],std::fma(fraction,exp[5],exp[4])));
    const float polynomial=std::fma(f,h,l),power=Scalar(static_cast<std::uint32_t>(127+static_cast<int>(integral))<<23);
    return (power*RefinedReciprocal(polynomial,2))*Scalar(0xc0c1999a);
}
}
void ApplyDeckAxisDisplacement(BodyRates& body,Vec3 requested)
{ApplyDeckAngularDisplacement(body,DeckSubtract(requested,DeckExisting(body,requested)));}
void ApplyDeckLimitedDisplacement(BodyRates& body,Vec3 requested)
{
    const auto existing=DeckExisting(body,requested);auto remainder=DeckSubtract(requested,existing);
    if(Dot3(remainder,requested)<0.0f)remainder={};const auto selected=Dot3(existing,requested)<0.0f?requested:remainder;
    ApplyDeckAngularDisplacement(body,selected);
}
void ApplyDeckAngularDisplacement(BodyRates& body,Vec3 displacement)
{
    const auto tensor=body.world_inverse_inertia,inverse=DeckInvert(tensor);const float step=Scalar(0x3c888889);
    const auto target=DeckScale(displacement,RefinedReciprocal(step,2)),momentum=DeckMultiply(inverse,target),torque=DeckScale(momentum,RefinedReciprocal(step,2)),acceleration=DeckMultiply(tensor,torque);
    body.torque_acceleration={body.torque_acceleration.x+acceleration.x,body.torque_acceleration.y+acceleration.y,body.torque_acceleration.z+acceleration.z};body.cool_down=0;
}
void ApplyGroundBodyTorque(BodyRates& body)
{
    const auto world=DeckMultiply(body.basis,{0.0f,GroundTorqueScalar(),0.0f}),acceleration=DeckMultiply(body.world_inverse_inertia,world);
    body.torque_acceleration={acceleration.x+body.torque_acceleration.x,acceleration.y+body.torque_acceleration.y,acceleration.z+body.torque_acceleration.z};body.cool_down=0;
}
}
