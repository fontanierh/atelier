// SPDX-License-Identifier: Apache-2.0
#include "RidingCollisionResponse.h"
#include "RidingAngles.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
std::int32_t TruncatedInteger(float value)
{
    if(std::isnan(value))return 0;
    if(value>=2147483648.0f)return std::numeric_limits<std::int32_t>::max();
    if(value<=-2147483648.0f)return std::numeric_limits<std::int32_t>::min();
    return std::int32_t(value);
}
float WrapAngle(float angle)
{
    const float pi=Float(0x40490fdb),tau=Float(0x40c90fdb);
    if(angle<-pi || !(angle<pi))
    {
        const auto turns=TruncatedInteger(angle*Float(0x3e22f983));
        angle=std::fma(-float(turns),tau,angle);
        if(!(angle<pi))angle-=tau;else if(angle<-pi)angle+=tau;
    }
    return angle;
}
Vec3 XYZ(Vec4 value){return {value[0],value[1],value[2]};}
}
std::optional<RidingCollisionResponse> CalculateRidingCollisionResponse(
    const RidingCollisionResponseSettings& settings,RidingCollisionPhysical input)
{
    if((input.flags&0x20000u)==0)return std::nullopt;
    const float projection=Dot3(XYZ(input.collision_displacement),XYZ(input.ground_normal));
    Vec4 displaced;for(std::size_t i=0;i<4;++i)displaced[i]=input.collision_displacement[i]-input.ground_normal[i]*projection;
    const float distance=Length3(XYZ(displaced));if(distance<Float(0x37800000))return std::nullopt;
    const float inverse_distance=1.0f/distance;Vec4 direction,tangent,target,delta,force;
    for(std::size_t i=0;i<4;++i)direction[i]=displaced[i]*inverse_distance;
    const float toward=Dot3(XYZ(input.velocity),XYZ(direction));
    for(std::size_t i=0;i<4;++i)
    {
        tangent[i]=input.velocity[i]-direction[i]*toward;
        target[i]=std::fma(direction[i],settings.target_displacement_velocity,tangent[i]);
        delta[i]=(target[i]-input.velocity[i])*settings.force_scalar;
    }
    if(toward>settings.target_displacement_velocity)delta={};
    const float magnitude=Length3(XYZ(delta)),inverse_dt=RefinedReciprocal(input.time_step,2);
    for(std::size_t i=0;i<4;++i)force[i]=(delta[i]*input.mass)*inverse_dt;
    const bool applied=magnitude>=0.01f;
    if(applied)
    {
        const float clamp=magnitude<=settings.maximum_velocity_delta?1.0f:settings.maximum_velocity_delta/magnitude;
        for(auto& lane:force)lane*=clamp;
    }
    else force={};
    const float angle=WrapAngle(RidingSignedAngle(XYZ(input.forward),XYZ(direction),XYZ(input.up)));
    const float torque=settings.torque_vs_angle.Evaluate(std::abs(angle)*Float(0x3ea2f983));
    const float signed_torque=angle>=0.0f?torque:-torque;Vec4 angular;
    for(std::size_t i=0;i<4;++i)angular[i]=input.up[i]*signed_torque;
    return RidingCollisionResponse{applied,force,{0,settings.force_y_offset,0,0},angular,target};
}
}
