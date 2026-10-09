#include "ContactBuild.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
void Out(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(bool v){Out(std::uint32_t(v));}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
template<class T,std::size_t N> void Out(const std::array<T,N>& values){for(const auto& v:values)Out(v);}
}
int main()
{
    const auto count=Word();
    for(std::uint32_t i=0;i<count;++i)
    {
        const auto kind=Word();std::array<std::uint32_t,64> record{};for(auto& w:record)w=Word();
        const float dt=Float();std::array<float,3> inverse{};for(auto& v:inverse)v=Float();
        const auto p=PrepareContact(record,dt);Out(p.arms);Out(p.axes);Out(p.active);Out(p.inverse_mass);Out(p.point_acceleration);
        Out(p.angular_response_a);Out(p.angular_response_b);Out(p.effective_mass);Out(p.separation_projection);Out(p.restitution_projection);Out(p.predicted_separation_projection);
        std::array<float,3> seen{};std::uint32_t calls=0;bool ok=true;
        if(kind==0)BuildContact(record,dt);
        else ok=BuildContactWithResponse(record,dt,[&](const std::array<float,3>& effective,std::array<float,3>& out){++calls;seen=effective;out=inverse;return kind!=2;});
        Out(ok);Out(calls);Out(seen);Out(record);
    }
    return std::cin.peek()==std::char_traits<char>::eof()?0:2;
}
