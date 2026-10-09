#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct ReckoningFrames
{
    Mat4 ground=SkeletonIdentity,system=SkeletonIdentity,unflipped=SkeletonIdentity;
    Mat4 inverse_system=SkeletonIdentity,body_flip=SkeletonIdentity;
    Vec4 heading{1,0,0,0};
    float target_lean_angle=0;
    Vec4 lateral_tilt{};
    void CalculateTransform(Vec4 up,Vec4 ground_normal);
    void CalculateDynamicLean(Vec4 up,Vec4 dynamic_up);
    void CalculateTilt(bool reverse_stance,const PointGraph<8>& tilt_vs_angle,const PointGraph<8>& tilt_vs_up);
};
}
