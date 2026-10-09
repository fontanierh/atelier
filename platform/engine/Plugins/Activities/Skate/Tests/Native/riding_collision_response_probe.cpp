#include "RidingCollisionResponse.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace {
std::vector<std::uint32_t> out;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec4 Four(){return {Float(),Float(),Float(),Float()};}
PointGraph<8> Curve(){PointGraph<8> c;for(auto& v:c.x)v=Float();for(auto& v:c.y)v=Float();return c;}
void Out(std::uint32_t w){out.push_back(w);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(Vec4 v){for(auto w:v)Out(w);}
}
int main(){const auto cases=Word();for(std::uint32_t c=0;c<cases;++c){const auto op=Word();if(op!=0)return 2;Out(c);Out(op);const auto size=out.size();Out(0u);
 RidingCollisionResponseSettings settings;settings.maximum_velocity_delta=Float();settings.force_y_offset=Float();settings.force_scalar=Float();settings.target_displacement_velocity=Float();settings.torque_vs_angle=Curve();
 RidingCollisionPhysical input;input.flags=Word();input.collision_displacement=Four();input.velocity=Four();input.forward=Four();input.up=Four();input.ground_normal=Four();input.time_step=Float();input.mass=Float();
 const auto result=CalculateRidingCollisionResponse(settings,input);Out(std::uint32_t(bool(result)));if(result){Out(std::uint32_t(result->applied));Out(result->force);Out(result->point);Out(result->angular_displacement);Out(result->target_velocity);}out[size]=std::uint32_t(out.size()-size-1);}
 if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:out)for(unsigned i=0;i<4;++i)std::cout.put(char(w>>(8*i)));
}
