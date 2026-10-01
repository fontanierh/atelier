// SPDX-License-Identifier: Apache-2.0
#include "ReckoningFrames.h"
#include "RidingAngles.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
Vec4 Normalize(Vec4 value){const float inverse=InverseLengthSquared(Dot3(value,value),2);for(auto& lane:value)lane*=inverse;return value;}
Vec3 XYZ(Vec4 value){return {value[0],value[1],value[2]};}
Mat4 Inverse(const Mat4& frame)
{
    Mat4 result{};for(std::size_t axis=0;axis<3;++axis)result[axis]={frame[0][axis],frame[1][axis],frame[2][axis],0};
    Vec4 position;for(std::size_t i=0;i<4;++i)position[i]=0.0f-frame[3][i];
    for(std::size_t i=0;i<4;++i)
    {
        const float z=result[2][i]*position[2];
        const float y=std::fma(result[1][i],position[1],z);
        result[3][i]=std::fma(result[0][i],position[0],y);
    }
    return result;
}
}
void ReckoningFrames::CalculateTransform(Vec4 up,Vec4 normal)
{
    const auto right=Cross3(up,heading),forward=Cross3(right,up);
    heading=Normalize(forward);system[0]=Normalize(right);system[1]=up;system[2]=heading;
    unflipped=system;system=ComposeSkeletonAffine(body_flip,system);inverse_system=Inverse(system);
    const auto ground_right=Cross3(normal,heading),ground_forward=Cross3(ground_right,normal);
    ground[0]=Normalize(ground_right);ground[1]=normal;ground[2]=Normalize(ground_forward);
}
void ReckoningFrames::CalculateDynamicLean(Vec4 up,Vec4 dynamic_up)
{
    const auto axis=system[2];
    const auto project=[&](Vec4 value){const float amount=Dot3(value,axis);for(std::size_t i=0;i<4;++i)value[i]-=axis[i]*amount;return value;};
    const auto from=project(up),to=project(dynamic_up);const float epsilon=Float(0x3727c5ac);
    target_lean_angle=Dot3(from,from)>epsilon && Dot3(to,to)>epsilon?
        RidingFractionWrappedAngle(RidingSignedAngle(XYZ(from),XYZ(to),XYZ(axis))):0.0f;
}
void ReckoningFrames::CalculateTilt(bool reversed,const PointGraph<8>& angle_curve,const PointGraph<8>& up_curve)
{
    const auto axis=unflipped[1];const Vec4 world_up{0,1,0,0};const float dot=Dot3(axis,world_up);
    Vec4 parallel,projected;for(std::size_t i=0;i<4;++i){parallel[i]=axis[i]*dot;projected[i]=world_up[i]-parallel[i];}
    if(Dot3(projected,projected)<=Float(0x3a03126f))return;
    const float angle=world_up==parallel?0.0f:RidingSignedAngle(XYZ(unflipped[2]),XYZ(Normalize(projected)),XYZ(axis));
    const float half_pi=Float(0x3fc90fdb),scale=Float(0x3f22f983);
    float normalized=((std::abs(RidingFractionWrappedAngle(angle-half_pi))-half_pi)*-1.0f)*scale;
    if(reversed)normalized=-normalized;
    const float up_angle=(half_pi-Asin(axis[1]))*scale;
    const float tilt=angle_curve.Evaluate(std::abs(normalized)),up_tilt=up_curve.Evaluate(std::abs(up_angle));
    const float signed_tilt=normalized>=-0.0f?tilt:-tilt;lateral_tilt={up_tilt*signed_tilt,0,0,0};
}
}
