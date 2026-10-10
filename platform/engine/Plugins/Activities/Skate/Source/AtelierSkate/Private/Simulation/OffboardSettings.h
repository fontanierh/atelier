#pragma once
#include "OffboardController.h"
#include "AnimationMetadata.h"
#include "Settings.h"
namespace atelier::skate
{
struct OffboardBoardSettings
{
    Vec4 extent_0{},extent_16{},offset_32{};
    float angle_436=0,angle_440=0,margin_444=0,angle_452=0,angle_456=0;
};
struct OffboardAirLaunchSettings {float jump_speed_scalar=0,jump_height=0;};
struct OffboardSettings
{
    BipedControllerSettings controller;OffboardBoardSettings board;
    std::array<std::optional<BipedClipMetric>,3> metrics;
    PointGraph<8> movement_vs_stick_angle,turn_vs_stick_angle;OffboardAirLaunchSettings air_launch;
    bool Load(const SettingsDatabase&,const AnimationMetadata&,std::string& error);
};
}
