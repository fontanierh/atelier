#pragma once
#include "SkeletonDrives.h"
#include "PhysicsSkeleton.h"
#include "Settings.h"
namespace atelier::skate
{
struct WipeoutDriveSettings
{
    std::array<std::array<float,5>,24> bone{};
    std::array<float,4> root{};
    std::array<float,2> strength{};
    float hook_spring=0,hook_strength=0,hook_damping=0;
    static bool Load(const SettingsDatabase&,const PhysicsSkeleton&,WipeoutDriveSettings&,std::string&);
};
struct WipeoutDriveWeights {float start,end,controlled,upper_extra,lower_extra;};
bool UpdateWipeoutDrives(SkeletonDrives&,const std::array<Mat4,24>& actual_animation_volumes,
    const WipeoutDriveSettings&,WipeoutDriveWeights,float& residual,std::string& error);
void SetWipeoutLinearRoot(SkeletonDrives&,const WipeoutDriveSettings&,float weight);
void SetWipeoutAngularRoot(SkeletonDrives&,const WipeoutDriveSettings&,float weight);
}
