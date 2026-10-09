#pragma once
#include "GroundForce.h"
namespace atelier::skate
{
struct PumpingSettings
{
    PointGraph<8> pump_vs_speed,pump_vs_time,min_crouch_vs_ground_angle,compression_vs_ground_angle,compression_vs_deck_angle;
    float height_change_damping,minimum_height_change,maximum_height_change;
    float ground_compression_scale,deck_compression_scale,angular_speed_damping;
};
struct PumpingMode
{
    float maximum_absorption_per_second,maximum_acceleration_per_second,absorption_factor,acceleration_factor;
};
struct GroundPumpingMode {PumpingMode controller;float unintentional_scalar;};
struct PumpingConfiguration
{
    PumpingSettings settings;
    std::array<GroundPumpingMode,5> modes;
    bool Load(const SettingsDatabase&,std::string& error);
    bool Mode(std::uint32_t index,GroundPumpingMode& output,std::string& error) const;
};
struct PumpingOutput
{
    float compression,absorption,ground_normal_absorption,minimum_crouch,deck_angle_absorption,pump_acceleration;
    std::uint8_t intentional_pumping;
};
struct PumpingState
{
    Vec4 previous_position{},previous_normal{};
    float smoothed_height_change=0,pumping_time=0,previous_height=0;
    float pumping=0,pump_acceleration=0,angular_speed=0;
    float absorption=0,ground_normal_absorption=0,minimum_crouch=0,deck_angle_absorption=0,reset_only_scalar=0;
    bool record_valid=false;
    std::uint8_t intentional_pumping=0;
    // These fields describe the reset output, not a memory overlay.
    void Reset() {*this=PumpingState{};}
    PumpingOutput PhysicsOutput() const;
};
struct PumpingSample {Vec4 position,normal,com_to_deck_world;float deck_angle;std::uint8_t intentional_pumping;};
float PumpingHeight(const Vec4& normal,const Vec4& com_to_deck);
float PumpingSpeed(const Vec4& previous,const Vec4& current,float dt);
float PumpingAngularSpeed(const Vec4& previous_position,const Vec4& previous_normal,const PumpingSample&,float dt);
float CalculatePumping(PumpingState&,const PumpingSettings&,const PumpingSample&,float dt);
void UpdatePumping(PumpingState&,const PumpingSettings&,PumpingMode,const PumpingSample&,float dt);
// Ground's controller timestep is independent of the processed force timestep.
void UpdateGroundPumping(PumpingState&,const PumpingSettings&,PumpingMode,const PumpingSample&);
struct PumpForceInput
{
    std::uint32_t flags_2476;
    float mode_multiplier,pumping_scalar,input_scalar_2660,timestep;
    Vec4 direction_432,normal_threshold;
};
std::array<float,8> CalculatePumpForce(const PumpForceInput&);
}
