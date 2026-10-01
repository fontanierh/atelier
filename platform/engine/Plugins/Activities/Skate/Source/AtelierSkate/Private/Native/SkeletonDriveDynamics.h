// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "DriveBuild.h"
namespace atelier::skate
{
struct AnimationDriveSettings {float linear_strength,linear_displacement,angular_strength,angular_displacement;};
struct DriveInterpolation {std::array<float,2> spring,strength,damping;};
struct BoneDriveSettings
{
    std::array<AnimationDriveSettings,2> animation;
    float collision_soft_displacement,collision_soft_strength,ragdoll_soft_displacement,ragdoll_soft_strength;
    DriveInterpolation transition_linear,transition_angular;
    float transition_calls;
};
struct BoneDriveDynamics
{
    std::array<DriveDynamics,2> channels{};
    std::uint32_t mode=0;
    std::array<float,2> strengths{};
    float transition_counter=0;
    bool transition_active=false;
    void Enable(std::size_t channel,float strength,BoneDriveSettings settings);
};
}
