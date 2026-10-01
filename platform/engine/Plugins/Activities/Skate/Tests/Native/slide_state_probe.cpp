// SPDX-License-Identifier: Apache-2.0
#include "SlideStateSettings.h"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
std::uint32_t Word() {unsigned char b[4];if (!std::cin.read(reinterpret_cast<char*>(b),4)) std::exit(2);return std::uint32_t(b[0])|(std::uint32_t(b[1])<<8)|(std::uint32_t(b[2])<<16)|(std::uint32_t(b[3])<<24);}
float Float() {const auto word=Word();float value;std::memcpy(&value,&word,4);return value;}
Vec4 Four() {return {Float(),Float(),Float(),Float()};}
PointGraph<8> Curve() {PointGraph<8> value;for (auto& v:value.x) v=Float();for (auto& v:value.y) v=Float();return value;}
SlideSettings Settings() {return {Curve(),Curve(),Curve(),Curve(),Float(),Float(),Float(),Float()};}
SlideSurface Surface() {return {Curve(),Float(),Float()};}
SlideInput Frame() {return {Four(),Four(),Four(),Four(),Four(),Four(),Float(),Float(),Float(),Float(),Float()};}
std::vector<std::uint32_t> output;
void Out(std::uint32_t v) {output.push_back(v);}
void Out(float v) {std::uint32_t word;std::memcpy(&word,&v,4);Out(word);}
void Out(Vec4 v) {for (auto value:v) Out(value);}
void Out(Vec3 v) {Out(v.x);Out(v.y);Out(v.z);}
void Out(const PointGraph<8>& v) {for (auto value:v.x) Out(value);for (auto value:v.y) Out(value);}
void Out(const SlideState& s) {Out(s.start_speed);Out(s.steering_push);Out(s.damped_turn);Out(std::uint32_t(s.flag48));Out(std::uint32_t(s.wall_riding));}
void Out(const SlideSettings& s) {Out(s.input_remap);Out(s.remap_vs_speed);Out(s.force_vs_angle);Out(s.force_vs_speed);Out(s.softest_wheel_force);Out(s.softest_wheel_spin);Out(s.angular_force);Out(s.force_y_offset);}
void Out(const SlideSurface& s) {Out(s.speed_to_force);Out(s.yaw_strength);Out(s.yaw_damping);}
}
int main(int argc,char** argv)
{
    if (argc!=2) return 2;std::ifstream file(argv[1],std::ios::binary);const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(file),{}};SettingsDatabase data;SlideStateSettings stock;std::string error;
    if (!data.Load(bytes,error)||!stock.Load(data,error)) {std::cerr<<error;return 2;}const auto count=Word();
    for (std::uint32_t c=0;c<count;++c)
    {
        const auto op=Word();Out(c);Out(op);const auto mark=output.size();Out(0u);
        switch (op)
        {
            case 0:Out(SlideState{});Out(stock.settings);for (const auto& profile:stock.surfaces) {Out(profile.surface);Out(profile.material.static_friction);Out(profile.material.dynamic_friction);Out(profile.material.restitution);}Out(stock.manual_scalar);break;
            case 1:
            {
                const auto speed=Float(),push=Float(),turn=Float();const auto flag=Word(),wall=Word();SlideState state{speed,push,turn,flag!=0,wall!=0};const auto steps=Word();
                for (std::uint32_t n=0;n<steps;++n) {const auto action=Word();const auto value=Float();if (action==0) state=SlideState{};else if (action==1) state.Enter(value);else if (action==2) state.Exit();else return 2;Out(state);}break;
            }
            case 2:
            {
                const auto selected=Word();const auto settings=selected?stock.settings:Settings();const auto surface=selected?stock.surfaces.at(selected-1).surface:Surface();const auto steps=Word();
                for (std::uint32_t n=0;n<steps;++n) {const auto input=Frame();Out(CalculateSlideAngularCorrection(settings,surface,input));const auto force=CalculateSlidingForce(settings,surface,input);Out(force.tag);Out(force.force_world);Out(force.point_body);}break;
            }
            default:return 2;
        }
        output[mark]=std::uint32_t(output.size()-mark-1);
    }
    if (std::cin.peek()!=std::char_traits<char>::eof()) return 2;for (auto word:output) for (unsigned i=0;i<4;++i) std::cout.put(char(word>>(8*i)));
}
