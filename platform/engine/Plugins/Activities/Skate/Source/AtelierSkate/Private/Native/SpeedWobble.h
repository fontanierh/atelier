#pragma once
#include "NativeMath.h"
#include "Settings.h"
namespace atelier::skate
{
struct SpeedWobbleSettings
{
    PointGraph<8> frequency_time,frequency_speed,amplitude_time,amplitude_speed;
    float tightness_threshold,time_range,speed_range,frequency_scale,amplitude_scale,crouch_threshold,height_min,height_max;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct SpeedWobbleMode
{
    float activation_threshold,amplitude_multiplier;
    bool Load(const SettingsDatabase&,std::string_view mode,std::string& error);
};
struct SpeedWobbleState
{
    std::array<std::uint32_t,8> words{};
    void Reset();
    bool IsActive() const {return words[7]>>24!=0;}
};
struct SpeedWobbleInput {float tilt,speed,center_of_mass_height,truck_tightness,activation_threshold,amplitude_multiplier;};
float CalculateSpeedWobble(SpeedWobbleState&,const SpeedWobbleSettings&,SpeedWobbleInput);
}
