// SPDX-License-Identifier: Apache-2.0
#include "AggregateMass.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return b;}
MassMoments Moments(){MassMoments m;for(auto& c:m.columns)for(auto& v:c)v=Float();return m;}
MassShape Shape(){MassShape s;s.kind=static_cast<MassShapeKind>(Word());s.radius=Float();s.half_length=Float();s.padding=Float();s.half_extents=Vector();return s;}
void Out(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
template<class T,std::size_t N> void Out(const std::array<T,N>& values){for(const auto& v:values)Out(v);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(const LocalMassFrame& f){Out(f.basis.columns);Out(f.translation);}
void Out(const BodyMassProperties& b){Out(b.local_mass_frame);const auto& d=b.dynamics;Out(d.inverse_tensor);for(float v:{d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag})Out(v);}
void Out(const MassMoments& m){Out(m.columns);}
}
int main()
{
    const auto count=Word();
    for(std::uint32_t n=0;n<count;++n)
    {
        const auto op=Word();
        if(op==0)
        {
            PartMassInput input;input.shape=Shape();input.requested_mass=Float();const float velocity=Float(),drag=Float();
            const auto p=ComputeForwardMassProperties(input);Out(std::uint32_t(bool(p)));
            if(p){Out(p->primitive.moments_per_unit_mass);Out(p->primitive.volume);Out(p->mass);Out(p->principal_moments);}
            const auto b=ComputePrimitiveMassProperties(input,velocity,drag);Out(std::uint32_t(bool(b)));if(b)Out(*b);
        }
        else if(op==1)
        {
            MassMoments total;const auto children=Word();
            for(std::uint32_t child=0;child<children;++child)
            {
                const auto shape=Shape();const auto basis=Basis();const auto translation=Vector();auto m=MassMoments::FromPrimitive(*ComputePrimitiveMass(shape));Out(m);
                m.Transform(basis,translation);Out(m);total.Add(m);Out(total);
            }
            const float mass=Float(),velocity=Float(),drag=Float();auto reduced=total;const auto p=reduced.PrincipalProperties();
            Out(reduced);Out(p.volume);Out(p.local_mass_frame);Out(p.moments_per_unit_mass);Out(ComputeAggregateMassProperties(total,mass,velocity,drag));
        }
        else if(op==2){auto m=Moments();const auto basis=Basis();const auto translation=Vector();const auto child=Moments();m.Transform(basis,translation);Out(m);m.Add(child);Out(m);}
        else if(op==3)
        {
            const bool stock=Word()!=0;WheelMassSettings w{Float(),Float(),Float()};TruckMassSettings t{Float(),Float(),Float(),Float(),Float(),Float()};
            if(stock){w=WheelMassSettings::Stock();t=TruckMassSettings::Stock();}
            for(float v:{w.radius,w.mass,w.mass_factor,t.wheel_radius,t.wheel_x_distance,t.radius_scalar,t.half_height_scalar,t.mass,t.mass_factor})Out(v);
            const auto wi=WheelMassInput(w),ti=TruckMassInput(t);Out(wi.shape.radius);Out(wi.requested_mass);Out(ti.shape.radius);Out(ti.shape.half_length);Out(ti.requested_mass);
            Out(WheelMassProperties(w));Out(TruckMassProperties(t));
        }
        else return 2;
    }
    return std::cin.peek()==std::char_traits<char>::eof()?0:2;
}
