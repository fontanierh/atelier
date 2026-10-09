#pragma once
#include "NativeMath.h"
#include "Settings.h"
namespace atelier::skate
{
struct SteeringSettings
{
    float hard_turn_increase,damping,speed_graph_max_speed;
    float push_scalar_increment,push_scalar_decrement,push_scalar_min;
    float manual_scalar,general_scalar,tight_trucks_scalar;
    PointGraph<8> speed_graph,input_graph;
    float tilt_blending;
    bool Load(const SettingsDatabase&,std::string& error);
};
struct SteeringInput
{
    float turn=0,hard_turn=0,absolute_body_speed=0,flipped_controls_scalar=0,balance=0,truck_tightness=0;
    bool pushing=false;
};
float CalculateSteeringTilt(const SteeringSettings&,SteeringInput,float* push_scalar=nullptr,float* damped_turn=nullptr);
struct TruckSteeringState
{
    float deck_tilt=0;
    std::array<float,2> targets{},activation_time{};
    void Update(float target,float blend,std::uint32_t flags_2468,std::uint32_t flags_2472);
};
}
