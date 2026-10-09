#pragma once
#include "PhysicsSkeleton.h"
#include "Settings.h"
#include "SkeletonCollisionFeedback.h"
#include "SkeletonJoints.h"
#include "SkeletonDrives.h"
namespace atelier::skate
{
// The caller supplies the validated native PHYS_TPOSE bank record. These
// bindings preserve original collection lookup and initial hierarchy order.
std::optional<SkeletonBodyDefinition> LoadSkeletonBodyDefinition(const SettingsDatabase&,const PhysicsSkeleton&,
    std::optional<std::string_view> hat_collection,std::string& error);
std::optional<SkeletonBody> LoadSkeletonBody(const SettingsDatabase&,const PhysicsSkeleton&,
    const std::array<Mat4,SkeletonAnimationPartCount>& initial_mapped,Mat4 spawn,SimulationStep,
    std::optional<std::string_view> hat_collection,std::string& error);
std::optional<SkeletonCollisionSettings> LoadSkeletonCollisionSettings(const SettingsDatabase&,const PhysicsSkeleton&,std::string& error);
std::optional<SkeletonFeedbackSettings> LoadSkeletonFeedbackSettings(const SettingsDatabase&,SkeletonCollisionSettings,std::string& error);
std::optional<BoneDriveSettings> LoadBoneDriveSettings(const SettingsDatabase&,std::string& error);
std::optional<SkeletonJoints> LoadSkeletonJoints(const SettingsDatabase&,const PhysicsSkeleton&,
    const std::vector<Mat4>& initial_hierarchy,const std::vector<std::int32_t>& hierarchy_parents,
    const std::array<std::size_t,SkeletonAnimationPartCount>& bone_indices,std::string& error);
std::optional<SkeletonDrives> LoadSkeletonDrives(const SettingsDatabase&,const PhysicsSkeleton&,
    const std::vector<Mat4>& initial_hierarchy,const std::array<std::size_t,SkeletonAnimationPartCount>& bone_indices,
    const std::array<Mat4,SkeletonAnimationPartCount>& initial_mapped,const SkeletonJoints&,
    Mat4 animation_to_world,Mat4 spawn,SimulationStep,std::string& error);
}
