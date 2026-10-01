// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GrindForces.h"
#include "RidingCollisionResponse.h"
#include "PlayerGrindInput.h"
#include "Settings.h"
namespace atelier::skate
{
struct GrindSubstateSettings
{
    RidingCollisionResponseSettings collision;
    float animated_board_threshold;
    std::array<std::array<std::array<float,2>,3>,5> vertical;
    bool Vertical(PlayerGrindFamily,std::uint32_t mode,float strength,float& output,std::string& error) const;
};
float GrindGeometrySideJump(PlayerGrindFamily,std::uint32_t kind);
struct GrindRuntimeSettings
{
    float standard_angular_drag;
    PointGraph<4> pin_vs_slope;
    float look_ahead;
    PointGraph<4> exit_assist;
    GrindPostSettings post;
    GrindReckoningSettings reckoning;
    GrindSubstateSettings substate;
    static bool Load(const SettingsDatabase&,GrindRuntimeSettings&,std::string& error);
};
}
