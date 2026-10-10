#pragma once
#include "SkeletonBody.h"
namespace atelier::skate
{
void SetWipeoutBodyVelocity(SkeletonBody&,Vec4);
void AddWipeoutBodyVelocity(SkeletonBody&,Vec4);
void RemoveWipeoutNormalVelocity(SkeletonBody&,Vec4 normal);
void BlendWipeoutBodyVelocity(SkeletonBody&,Vec4 target);
void LimitWipeoutBodyVelocity(SkeletonBody&,float maximum);
void SetWipeoutBodyDrag(SkeletonBody&,float linear,float angular);
void SetWipeoutDrag(SkeletonBody&,float drag);
void ApplyWipeoutSpecialSurface(SkeletonBody&,float height);
Vec4 WipeoutBodyAngularVelocity(const SkeletonPhysicalRecord&,const std::array<float,24>& fractional);
void ApplyWipeoutTorque(SkeletonBody&,Vec4 physical_com,Vec4 control);
}
