#include "WipeoutBody.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
void SetWipeoutBodyVelocity(SkeletonBody& body,Vec4 v){for(std::size_t i=1;i<24;++i)body.BodiesMut()[i].rates.linear_velocity={v[0],v[1],v[2]};}
void AddWipeoutBodyVelocity(SkeletonBody& body,Vec4 v){for(std::size_t i=1;i<24;++i){auto& velocity=body.BodiesMut()[i].rates.linear_velocity;velocity.x+=v[0];velocity.y+=v[1];velocity.z+=v[2];}}
void RemoveWipeoutNormalVelocity(SkeletonBody& body,Vec4 normal)
{
    for(std::size_t i=1;i<24;++i){const auto v=body.Bodies()[i].rates.linear_velocity;const Vec4 value{v.x,v.y,v.z,0};const auto projected=Scale(normal,Dot3(normal,value));const auto next=Madd(projected,i<15?0.1f:0,Sub(value,projected));body.BodiesMut()[i].rates.linear_velocity={next[0],next[1],next[2]};}
}
void BlendWipeoutBodyVelocity(SkeletonBody& body,Vec4 target)
{
    for(std::size_t i=1;i<24;++i){const auto v=body.Bodies()[i].rates.linear_velocity;const auto average=Madd(target,0.5f,{v.x*0.5f,v.y*0.5f,v.z*0.5f,0});const auto delta=Sub(average,target);const float length=Length(delta);const auto next=length<=2?average:Madd(delta,2.0f/length,target);body.BodiesMut()[i].rates.linear_velocity={next[0],next[1],next[2]};}
}
void LimitWipeoutBodyVelocity(SkeletonBody& body,float maximum)
{
    for(std::size_t i=1;i<24;++i){const auto v=body.Bodies()[i].rates.linear_velocity;const Vec4 value{v.x,v.y,v.z,0};if(Dot3(value,value)>maximum*maximum){const auto next=Scale(value,Reciprocal(Length(value))*maximum);body.BodiesMut()[i].rates.linear_velocity={next[0],next[1],next[2]};}}
}
void SetWipeoutBodyDrag(SkeletonBody& body,float linear,float angular)
{for(auto& part:body.BodiesMut()){part.inertia.linear_drag=linear*Word(0x426fffff);part.inertia.angular_drag=angular*Word(0x426fffff);}}
void SetWipeoutDrag(SkeletonBody& body,float drag)
{SetWipeoutBodyDrag(body,Clamp(drag,0,1),Clamp((drag+1.0f)*0.5f,0,1));}
void ApplyWipeoutSpecialSurface(SkeletonBody& body,float height)
{
    const float weights[]={1.7f,1.5f,1.2f,1,1,1,1.2f,1,1,1,1.2f,1,1,1,0.5f,0.5f,0.5f,0.6f,0.5f,0.5f,0.5f,0.6f,1};
    for(std::size_t i=1;i<24;++i){const float depth=(height+0.1f)-body.record.pose[i][3][1];float drag;
        if(depth>0){body.ApplyPartDisplacement(i,{0,std::fma(depth,0.6f,0.1f)*weights[i-1],0,0});drag=0.1f;}else drag=0.005f;
        body.BodiesMut()[i].inertia.angular_drag=drag*Word(0x426fffff);body.BodiesMut()[i].inertia.linear_drag=drag*Word(0x426fffff);
    }
}
Vec4 WipeoutBodyAngularVelocity(const SkeletonPhysicalRecord& record,const std::array<float,24>& fractional)
{
    Vec4 result{};for(std::size_t part=1;part<24;++part){const auto radial=Sub(record.positions[part],record.centre_of_mass),velocity=Sub(record.velocities[part],record.centre_of_mass_velocity);const float squared=Dot3(radial,radial);
        if(squared>Word(0x38d1b717)){const auto term=Scale(Cross(radial,velocity),Reciprocal(squared));result=Madd(term,fractional[part],result);}}
    return result;
}
void ApplyWipeoutTorque(SkeletonBody& body,Vec4 com,Vec4 control)
{
    const float magnitude=Length(control);for(std::size_t part=1;part<24;++part){const auto radial=Sub(body.record.pose[part][3],com);if(Dot3(radial,radial)>0.001f){const auto tangent=NormalizeOr(Cross(control,radial),{});body.ApplyPartDisplacement(part,Scale(tangent,magnitude));}}
}
}
