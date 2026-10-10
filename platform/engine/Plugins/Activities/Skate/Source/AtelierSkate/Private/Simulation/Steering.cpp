#include "Steering.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
float Clamp(float value,float minimum,float maximum) {return value<minimum?minimum:value>maximum?maximum:value;}
}
float CalculateSteeringTilt(const SteeringSettings& s,SteeringInput input,float* push_scalar,float* damped_turn)
{
    const auto hard_scalar=std::fma(std::abs(input.hard_turn),s.hard_turn_increase,1.0f);auto turn=input.turn;
    if (input.hard_turn!=0) turn=turn>=0?1:-1;
    if (damped_turn) {turn=std::fma(1.0f-s.damping,*damped_turn,s.damping*turn);*damped_turn=turn;}
    const auto speed=s.speed_graph.Evaluate(Clamp(input.absolute_body_speed/s.speed_graph_max_speed,0,1)),mapped_input=s.input_graph.Evaluate(std::abs(turn));
    float push=1;if (push_scalar) {*push_scalar=Clamp(input.pushing?*push_scalar-s.push_scalar_decrement:s.push_scalar_increment+*push_scalar,s.push_scalar_min,1);push=*push_scalar;}
    const auto manual=input.balance!=0?s.manual_scalar:1,tightness=std::fma(s.tight_trucks_scalar,input.truck_tightness,1.0f)-input.truck_tightness;
    return input.flipped_controls_scalar*s.general_scalar*manual*tightness*push*mapped_input*speed*hard_scalar*turn;
}
void TruckSteeringState::Update(float target,float blend,std::uint32_t flags_2468,std::uint32_t flags_2472)
{
    deck_tilt=std::fma(1.0f-blend,deck_tilt,blend*target);std::array<bool,2> active{(flags_2472&(1u<<27))!=0,(flags_2472&(1u<<26))!=0};if (flags_2468&(1u<<20)) std::swap(active[0],active[1]);
    for (std::size_t i=0;i<2;++i)
    {
        auto& timer=activation_time[i];auto& angle=targets[i];
        if (active[i]) {if (timer<=.16500001f) {timer+=Float(0x3c888889);const auto fraction=Clamp(timer*6.060606f,0,1);angle=std::fma(1.0f-fraction,angle,fraction*deck_tilt);}else angle=deck_tilt;}
        else {if (timer==0) angle*=.983f;timer=0;}
    }
}
}
