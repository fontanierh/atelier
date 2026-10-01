// SPDX-License-Identifier: Apache-2.0
#include "DeckGeometry.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Decode(std::uint32_t w){float v;std::memcpy(&v,&w,4);return v;}
float Float(){return Decode(Word());}
Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
AffineTransform Frame(){AffineTransform f;for(auto& c:f.basis.columns)for(auto& v:c)v=Float();f.translation=Vector();return f;}
DeckGeometrySettings Settings(){DeckGeometrySettings s{Float(),Float(),Float(),Float(),Float(),Float(),0,false,false};const auto w=Word();std::memcpy(&s.end_capsule_count,&w,4);s.enable_deck_volume_collisions=Word()!=0;s.enable_end_volume_collisions=Word()!=0;return s;}
DeckChild Child(){const auto kind=Word();std::array<std::uint32_t,14> p{};for(auto& w:p)w=Word();const auto f=[&](std::size_t n){return Decode(p[n]);};DeckChild c;
 if(kind==0)c.shape=DeckRoundedBox{{f(0),f(1),f(2)},f(3)};
 else if(kind==1)c.shape=DeckCapsule{f(0),f(1)};
 else if(kind==2)c.shape=DeckSphere{f(0)};
 else if(kind==3)c.shape=DeckTriangle{{Vec3{f(0),f(1),f(2)},Vec3{f(3),f(4),f(5)},Vec3{f(6),f(7),f(8)}},f(9),{f(10),f(11),f(12)},p[13]};
 else std::exit(2);
 c.transform=Frame();c.collision_enabled=Word()!=0;return c;}
void Out(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(Vec3 v);
void Out(const BodyMassProperties& b);
template<class T,std::size_t N> void Out(const std::array<T,N>& values){for(const auto& v:values)Out(v);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(const BodyMassProperties& b){Out(b.local_mass_frame.basis.columns);Out(b.local_mass_frame.translation);const auto& d=b.dynamics;Out(d.inverse_tensor);for(float v:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag})Out(v);}
void Out(const MassMoments& m){Out(m.columns);}
void Out(const DeckChild& c)
{
    Out(std::uint32_t(c.shape.index()));std::size_t count=0;
    if(const auto* s=std::get_if<DeckRoundedBox>(&c.shape)){Out(s->half_extents);Out(s->radius);count=4;}
    else if(const auto* s=std::get_if<DeckCapsule>(&c.shape)){Out(s->radius);Out(s->half_length);count=2;}
    else if(const auto* s=std::get_if<DeckSphere>(&c.shape)){Out(s->radius);count=1;}
    else{const auto& t=std::get<DeckTriangle>(c.shape);Out(t.vertices);Out(t.fatness);Out(t.edge_cosines);Out(t.volume_flags);count=14;}
    for(;count<14;++count)Out(std::uint32_t(0));
    Out(c.transform.basis.columns);Out(c.transform.translation);Out(std::uint32_t(c.collision_enabled));Out(c.ComputeMassMoments());
}
}
int main()
{
    const auto count=Word();
    for(std::uint32_t n=0;n<count;++n)
    {
        const auto op=Word();
        if(op==0)
        {
            const bool stock=Word()!=0;auto s=Settings();if(stock)s=DeckGeometrySettings::Stock();const float mass=Float(),drag=Float();
            for(float v:{s.width,s.mid_length,s.thickness,s.back_end_size,s.front_end_angle_degrees,s.back_end_angle_degrees})Out(v);
            Out(static_cast<std::uint32_t>(s.end_capsule_count));Out(std::uint32_t(s.enable_deck_volume_collisions));Out(std::uint32_t(s.enable_end_volume_collisions));
            const DeckGeometry d(s);Out(std::uint32_t(d.children.size()));for(const auto& c:d.children)Out(c);Out(d.ComputeMassMoments());Out(DeckMassProperties(d,mass,drag));
        }
        else if(op==1)Out(Child());
        else if(op==2)Out(DefaultSkateboardMassProperties());
        else return 2;
    }
    return std::cin.peek()==std::char_traits<char>::eof()?0:2;
}
