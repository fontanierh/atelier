#pragma once
#include "SkeletonController.h"
#include "SkeletonCollisionFeedback.h"
#include "SkeletonJoints.h"
#include "PhysicsSkeleton.h"
#include "Settings.h"
namespace atelier::skate
{
struct WipeoutRagdollSettings
{
    std::array<std::array<std::uint32_t,4>,22> normal_limits{},ragdoll_limits{};
    bool inverse_mass=false,inverse_inertia=false;
    std::array<float,2> drag{};
    std::array<ContactMaterial,2> materials{};
    static bool Load(const SettingsDatabase&,const PhysicsSkeleton&,WipeoutRagdollSettings&,std::string&);
};
class WipeoutRagdollSetup
{
public:
    WipeoutRagdollSettings settings;
    bool Load(const SettingsDatabase&,const PhysicsSkeleton&,std::string&);
    bool Request(SkeletonControllerState&,std::uint32_t requested,SkeletonBody&,SkeletonJoints&,SkeletonCollisionMode&,std::string&) const;
    void RestoreNormal(SkeletonBody&,SkeletonJoints&,SkeletonCollisionMode&,SkeletonCollisionFeedback&) const;
};
}
