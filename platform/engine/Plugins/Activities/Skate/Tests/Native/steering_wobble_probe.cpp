// SPDX-License-Identifier: Apache-2.0
#include "Steering.h"
#include "SpeedWobble.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
std::uint32_t Word()
{
    unsigned char bytes[4];if (!std::cin.read(reinterpret_cast<char*>(bytes),4)) std::exit(2);
    return std::uint32_t(bytes[0])|(std::uint32_t(bytes[1])<<8)|(std::uint32_t(bytes[2])<<16)|(std::uint32_t(bytes[3])<<24);
}
float Float() {const auto word=Word();float value;std::memcpy(&value,&word,4);return value;}
PointGraph<8> Curve() {PointGraph<8> value;for (auto& v:value.x) v=Float();for (auto& v:value.y) v=Float();return value;}
SteeringSettings Steering() {return {Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float(),Curve(),Curve(),Float()};}
SpeedWobbleSettings Wobble() {return {Curve(),Curve(),Curve(),Curve(),Float(),Float(),Float(),Float(),Float(),Float(),Float(),Float()};}
std::vector<std::uint32_t> output;
void Out(std::uint32_t value) {output.push_back(value);}
void Out(float value) {std::uint32_t word;std::memcpy(&word,&value,4);Out(word);}
void Out(const PointGraph<8>& value) {for (auto v:value.x) Out(v);for (auto v:value.y) Out(v);}
void Out(const SteeringSettings& s) {for (auto v:{s.hard_turn_increase,s.damping,s.speed_graph_max_speed,s.push_scalar_increment,s.push_scalar_decrement,s.push_scalar_min,s.manual_scalar,s.general_scalar,s.tight_trucks_scalar}) Out(v);Out(s.speed_graph);Out(s.input_graph);Out(s.tilt_blending);}
void Out(const SpeedWobbleSettings& s) {Out(s.frequency_time);Out(s.frequency_speed);Out(s.amplitude_time);Out(s.amplitude_speed);for (auto v:{s.tightness_threshold,s.time_range,s.speed_range,s.frequency_scale,s.amplitude_scale,s.crouch_threshold,s.height_min,s.height_max}) Out(v);}
void Out(const TruckSteeringState& s) {Out(s.deck_tilt);for (auto v:s.targets) Out(v);for (auto v:s.activation_time) Out(v);}
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;std::ifstream stream(argv[1],std::ios::binary);const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(stream)),{});SettingsDatabase data;std::string error;
    SteeringSettings stock_steering{};SpeedWobbleSettings stock_wobble{};std::array<SpeedWobbleMode,5> modes{};const std::array<std::string_view,5> names{"easy","normal","hardcore","motorized","test"};
    if (!data.Load(bytes,error)||!stock_steering.Load(data,error)||!stock_wobble.Load(data,error)) {std::cerr<<error;return 2;}
    for (std::size_t i=0;i<modes.size();++i) if (!modes[i].Load(data,names[i],error)) {std::cerr<<error;return 2;}
    char magic[8];if (!std::cin.read(magic,8)||std::memcmp(magic,"ATSTWB01",8)) return 2;const auto count=Word();
    for (std::uint32_t c=0;c<count;++c)
    {
        const auto op=Word();Out(c);Out(op);const auto mark=output.size();Out(0u);
        switch (op)
        {
            case 0:Out(stock_steering);Out(stock_wobble);for (const auto& mode:modes) {Out(mode.activation_threshold);Out(mode.amplitude_multiplier);}break;
            case 1:
            {
                const auto settings=Word()?stock_steering:Steering();auto push=Float(),damped=Float();const auto steps=Word();
                for (std::uint32_t n=0;n<steps;++n) {const auto mask=Word();const SteeringInput input{Float(),Float(),Float(),Float(),Float(),Float(),Word()!=0};Out(CalculateSteeringTilt(settings,input,mask&1?&push:nullptr,mask&2?&damped:nullptr));Out(push);Out(damped);}break;
            }
            case 2:
            {
                TruckSteeringState state{Float(),{Float(),Float()},{Float(),Float()}};const auto steps=Word();
                for (std::uint32_t n=0;n<steps;++n) {const auto target=Float(),blend=Float();const auto flags_a=Word(),flags_b=Word();state.Update(target,blend,flags_a,flags_b);Out(state);}break;
            }
            case 3:
            {
                const auto settings=Word()?stock_wobble:Wobble();SpeedWobbleState state;for (auto& word:state.words) word=Word();const auto steps=Word();
                for (std::uint32_t n=0;n<steps;++n) {if (Word()) state.Reset();const SpeedWobbleInput input{Float(),Float(),Float(),Float(),Float(),Float()};Out(CalculateSpeedWobble(state,settings,input));for (auto word:state.words) Out(word);}break;
            }
            default:return 2;
        }
        output[mark]=std::uint32_t(output.size()-mark-1);
    }
    if (std::cin.peek()!=std::char_traits<char>::eof()) return 2;for (auto word:output) for (unsigned i=0;i<4;++i) std::cout.put(char(word>>(8*i)));
}
