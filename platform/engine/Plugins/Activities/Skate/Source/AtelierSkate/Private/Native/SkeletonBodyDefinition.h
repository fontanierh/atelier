// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AggregateMass.h"
#include "SkeletonAnimationRecord.h"

namespace atelier::skate
{
struct BoneSettings
{
    float mass_factor,ragdoll_mass_factor;
    bool has_collision,use_root_drive;
    std::uint32_t volume_type;
    float volume_scalar;
    std::uint32_t num_parents;
};
struct SkeletonBodySettings
{
    float density,root_radius,root_half_length,capsule_radius_scalar,capsule_length_scalar;
    float ragdoll_inverse_mass_factor;
    std::uint32_t inertia_multiply_type;
    float inertia_factor;
};
struct HatGeometry
{
    float radius,half_length;
    Basis3 basis;
    Vec3 translation;
    static HatGeometry FromOffsets(float radius,float thickness,Vec3 angles,Vec3 translation);
};
struct SkeletonPart
{
    MassShape shape;
    std::optional<HatGeometry> hat;
    BodyMassProperties animated,ragdoll;
    float inverse_mass_animated,inverse_mass_ragdoll;
};
struct SkeletonBodyDefinition
{
    std::array<SkeletonPart,SkeletonPartCount> parts;
    std::array<BoneSettings,SkeletonAnimationPartCount> bones;
    SkeletonAnimationMasses animation_masses;
    static std::optional<SkeletonBodyDefinition> Build(
        std::array<Vec3,SkeletonAnimationPartCount> sizes,
        std::array<BoneSettings,SkeletonAnimationPartCount> bones,
        SkeletonBodySettings settings,std::optional<HatGeometry> hat,std::string& error);
};
}
