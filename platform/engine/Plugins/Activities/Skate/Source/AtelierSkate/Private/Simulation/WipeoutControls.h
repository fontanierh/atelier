#pragma once
#include "WipeoutPhysicalSettings.h"
#include "WipeoutBody.h"
namespace atelier::skate
{
void PrepareWipeoutProfile(WipeoutPhysicalState&,const std::array<WipeoutControlProfile,5>&,
    std::array<float,2> gesture,std::array<float,2> input);
void ApplyWipeoutProfileDrift(const WipeoutPhysicalState&,SkeletonBody&,const WipeoutControlProfile&);
bool ControlWipeoutAir(WipeoutPhysicalState&,SkeletonBody&,Vec4 physical_com,std::array<float,2> input,bool contact);
void ControlWipeoutProfileAir(WipeoutPhysicalState&,SkeletonBody&,Vec4 physical_com,const Mat4& effective,
    std::array<float,2> input,const WipeoutControlProfile&);
void ControlWipeoutGround(WipeoutPhysicalState&,SkeletonBody&,Vec4 physical_com,const Mat4& effective,
    Vec4 ground_axis,const WipeoutControlProfile&,const Mat4& animation_to_world,const std::array<Mat4,24>& animation_pose);
Vec4 WipeoutResponseNormal(std::optional<Vec4> support,std::optional<Vec4> prediction);
void TriggerWipeoutResponse(WipeoutPhysicalState&,SkeletonBody&,Vec4 normal,std::array<float,2> input);
void UpdateWipeoutResponseCounter(WipeoutPhysicalState&,bool contact);
void UpdateWipeoutRetainedVelocity(WipeoutPhysicalState&,SkeletonBody&,SkeletonDrives&,const WipeoutDriveSettings&,
    bool contact,std::uint32_t flags2468,Vec4 com_velocity);
struct WipeoutWeightOutput {float target_weight,start,end,controlled,extra;};
WipeoutWeightOutput UpdateWipeoutWeights(WipeoutPhysicalState&,const WipeoutPhysicalSettings&,bool contact,bool control_applied,
    std::uint32_t flags2472,std::array<float,2> gesture);
}
