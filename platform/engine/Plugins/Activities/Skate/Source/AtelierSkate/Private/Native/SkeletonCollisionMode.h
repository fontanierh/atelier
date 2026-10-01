// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GeometryTypes.h"
#include "SkeletonBody.h"
namespace atelier::skate
{
struct SkeletonCollisionSettings
{
    bool enabled;
    ContactMaterial normal_material;
    std::array<bool,SkeletonAnimationPartCount> compliant;
    std::array<float,SkeletonAnimationPartCount> priority;
    float effect_time;
};
struct SkeletonPartCollision {bool enabled;std::uint32_t volume_group,part_group;ContactMaterial material;};
class SkeletonCollisionFeedback;
class SkeletonCollisionMode
{
public:
    std::array<SkeletonPartCollision,SkeletonPartCount> parts;
    std::array<std::uint32_t,SkeletonAnimationPartCount> disable_count{};
    bool pending_reenable=false;
    std::uint32_t assembly_group=5;
    bool partial_ragdoll=false,is_ragdoll=false;
    SkeletonCollisionSettings settings;
    std::array<std::array<bool,SkeletonPartCount>,SkeletonPartCount> self_culling;
    SkeletonCollisionMode(SkeletonCollisionSettings settings,bool cull_all_self_pairs);
    void DisableHandplantContacts(std::uint32_t frames);
    void ResetBodyState(SkeletonCollisionFeedback& feedback);
    bool SelectDriven(std::uint32_t mode,std::string& error);
    void NormalCollision();
    void DisableAll(bool clear_counts);
    void EnableBone(std::size_t part);
    void FinishContactFrame();
    void NormalBone(std::size_t part,bool has_collision);
    void RestoreNormalProperties(SkeletonBody& skeleton);
    void ApplyRagdollProperties(SkeletonBody& skeleton,bool inverse_mass,bool inverse_inertia,
        std::array<float,2> drag,std::array<ContactMaterial,2> materials);
    void FinishRagdollRequest(std::uint32_t mode);
private:
    std::array<std::array<bool,SkeletonPartCount>,SkeletonPartCount> normal_self_culling_;
    void SetGroup(std::uint32_t group);
    void SelectBiped();
    void DisableRoot();
    void EnableEligibleBones();
};
}
