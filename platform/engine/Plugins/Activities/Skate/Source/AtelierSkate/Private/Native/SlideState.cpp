// SPDX-License-Identifier: Apache-2.0
#include "SlideState.h"
#include "RidingAngles.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
Vec4 Scale4(Vec4 v,float s) {for (auto& value:v) value*=s;return v;}
Vec4 Madd4(Vec4 v,float s,Vec4 b) {for (std::size_t i=0;i<4;++i) v[i]=std::fma(v[i],s,b[i]);return v;}
Vec4 Reject(Vec4 v,Vec4 n) {const auto d=Dot3(v,n);for (std::size_t i=0;i<4;++i) v[i]-=n[i]*d;return v;}
Vec4 NormalizeSafe(Vec4 v)
{
    const auto d=Dot3(v,v),inverse=InverseLengthSquared(d,2),length=d==0?0:d*inverse;
    return length>Float(0x358637bd)?Scale4(v,inverse):Vec4{};
}
Vec3 Three(Vec4 v) {return {v[0],v[1],v[2]};}
float Fsel(float test,float positive,float negative) {return test>=-0.0f?positive:negative;}
}
Vec4 CalculateSlideAngularCorrection(const SlideSettings& s,const SlideSurface& surface,SlideInput p)
{
    const auto remap=s.input_remap.Evaluate(std::abs(p.slide));auto age=p.elapsed-.5f;age=Fsel(-age,0,age);age=Fsel(1.0f-age,age,1);
    const auto weight=s.remap_vs_speed.Evaluate(p.surface_speed)*age,pi=Float(0x40490fdb),signed_remap=Fsel(p.slide,remap,-remap);
    const auto angle=std::fma(p.slide*pi,1.0f-weight,(signed_remap*pi)*weight);
    const auto velocity=Normalize3(p.velocity,2),side=Normalize3(Cross3(p.normal,velocity),2),desired=Madd4(velocity,Cos(angle),Scale4(side,Sin(angle)));
    auto error=Cross3(p.reference_forward,desired);if (Dot3(p.reference_forward,desired)<0) {const auto negate=error[1]<0;error=p.normal;if (negate) for (auto& value:error) value=-value;}
    const auto strength=std::fma(1.0f-s.softest_wheel_spin,p.wheel_hardness,s.softest_wheel_spin)*surface.yaw_strength;
    const auto displacement=Scale4(Madd4(error,strength,Scale4(p.angular_velocity,surface.yaw_damping)),s.angular_force);
    return Scale4(p.normal,Dot3(displacement,p.normal));
}
QueuedPointForce CalculateSlidingForce(const SlideSettings& s,const SlideSurface& surface,SlideInput p)
{
    const auto tangent=Reject(p.velocity,p.normal),lateral=Scale4(p.side,Dot3(tangent,p.side));const auto response=surface.speed_to_force.Evaluate(p.absolute_speed),hardness=response>0?p.wheel_hardness:1;
    const auto strength=std::fma(1.0f-s.softest_wheel_force,hardness,s.softest_wheel_force)*response;
    const auto side=NormalizeSafe(Cross3(p.normal,p.velocity)),longitudinal=Reject(Scale4(lateral,strength),NormalizeSafe(side));
    const auto angle=Dot3(p.velocity,p.velocity)*Dot3(p.effective_forward,p.effective_forward)>Float(0x37800000)?RidingSignedAngle(Three(Reject(p.velocity,p.normal)),Three(Reject(p.effective_forward,p.normal)),Three(p.normal)):0;
    const auto degrees=RidingFractionWrappedAngle(angle)*Float(0x42652ee1),sign=degrees>0?1.0f:-1.0f;
    const auto angular=Scale4(Scale4(side,s.force_vs_angle.Evaluate(std::abs(degrees))),s.force_vs_speed.Evaluate(p.surface_speed)),force=Madd4(angular,sign,longitudinal);
    const auto y=Dot3(force,p.velocity)<0?-s.force_y_offset:s.force_y_offset;return {9,Three(force),{0,y,0}};
}
}
