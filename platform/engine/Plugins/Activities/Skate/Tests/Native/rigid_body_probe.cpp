// SPDX-License-Identifier: Apache-2.0
#include "RigidBody.h"
#include "BodyMass.h"
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace atelier::skate;
namespace
{
std::uint32_t Word() { char b[4];if(!std::cin.read(b,4))throw std::runtime_error("truncated input");return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24); }
float Float() {auto bits=Word();float v;std::memcpy(&v,&bits,4);return v;}
void Out(std::uint32_t w) {const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Out(float v) {std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
template<class T,std::size_t N> void Out(const std::array<T,N>& values){for(const auto& v:values)Out(v);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(Basis3 b){Out(b.columns);}
Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
Quat Quaternion(){Quat q;for(auto&v:q)v=Float();return q;}
Basis3 Basis(){Basis3 b;for(auto&c:b.columns)for(auto&v:c)v=Float();return b;}
template<std::size_t N> std::array<std::uint32_t,N> Words(){std::array<std::uint32_t,N> a;for(auto&w:a)w=Word();return a;}
float Value(std::uint32_t w){float v;std::memcpy(&v,&w,4);return v;}
void Out(const BodyRateStep& step)
{
    const auto& b=step.state;Out(b.orientation);Out(b.basis);Out(b.world_inverse_inertia);Out(b.position);Out(b.linear_velocity);Out(b.angular_velocity);
    Out(b.force_acceleration);Out(b.torque_acceleration);Out(b.kinetic_energy);Out(b.cool_down);Out(step.orientation_displacement);Out(step.linear_speed_squared);Out(step.angular_speed_squared);
}
}
int main()
{
    try
    {
        const auto count=Word();
        for(std::uint32_t record=0;record<count;++record)
        {
            const auto op=Word();
            if(op==0 || op==5)
            {
                auto body=Words<44>();const auto inertia=Words<10>();
                SimulationStep sim;sim.time_step=Float();sim.frequency=Float();sim.cool_down=Word();sim.minimum_energy=Float();sim.gravity_acceleration=Vector();
                auto reactions=Words<16>();const auto steps=Word();
                if(op==0) for(std::uint32_t i=0;i<steps;++i)
                {
                    const auto result=DynamicUpdatePacked(body,inertia,sim,reactions);Out(body);Out(reactions);Out(result.orientation_displacement);Out(result.linear_speed_squared);Out(result.angular_speed_squared);
                }
                else
                {
                    const auto vec=[&](unsigned offset){return Vec3{Value(body[offset]),Value(body[offset+1]),Value(body[offset+2])};};
                    BodyRates b{};for(unsigned i=0;i<4;++i)b.orientation[i]=Value(body[i]);b.position=vec(4);b.linear_velocity=vec(8);b.angular_velocity=vec(12);
                    b.force_acceleration=vec(36);b.torque_acceleration=vec(40);b.kinetic_energy=Value(body[39]);b.cool_down=body[43];
                    InertiaDynamics data{{Value(inertia[0]),Value(inertia[1]),Value(inertia[2])},Value(inertia[4]),Value(inertia[5]),Value(inertia[6]),Value(inertia[7]),Value(inertia[8]),Value(inertia[9])};
                    const auto rv=[&](unsigned o){return Vec3{Value(reactions[o]),Value(reactions[o+1]),Value(reactions[o+2])};};
                    ReactionCorrections corrections{rv(0),rv(4),rv(8),rv(12)};
                    for(std::uint32_t i=0;i<steps;++i){auto result=IntegrateBodyRates(b,data,sim,corrections);Out(result);b=result.state;corrections={};}
                }
            }
            else if(op==1){const auto q=Quaternion();const auto v=Vector();Out(IntegrateOrientation(q,v));Out(BasisFromQuaternion(q));}
            else if(op==2){const auto b=Basis();const auto v=Vector();Out(WorldInverseInertia(b,v));}
            else if(op==3)
            {
                const auto b=Basis();const auto v=Vector();const auto packed=PackWorldInverseInertia(b);Out(packed.full);Out(packed.split);Out(MultiplyPackedWorldInverseInertia(packed,v));
            }
            else if(op==4)
            {
                const auto force_acc=Vector(),torque_acc=Vector();const auto cooldown=Word();const auto force=Vector(),point=Vector();const auto deck=Basis();const float mass=Float();const auto inertia=Basis();
                const auto out=AccumulatePointForce({force_acc,torque_acc,cooldown},force,point,deck,mass,inertia);Out(out.force_acceleration);Out(out.torque_acceleration);Out(out.cool_down);
            }
            else if(op==6){const auto cool=Word();const float energy=Float();const auto gravity=Vector();const auto s=SimulationStep::Fixed60Hz(cool,energy,gravity);Out(s.time_step);Out(s.frequency);Out(s.cool_down);Out(s.minimum_energy);Out(s.gravity_acceleration);}
            else if(op==7)
            {
                MassShape shape;shape.kind=static_cast<MassShapeKind>(Word());shape.radius=Float();shape.half_length=Float();shape.padding=Float();shape.half_extents=Vector();
                const auto result=ComputePrimitiveMass(shape);Out(std::uint32_t(bool(result)));
                if(result){Out(result->moments_per_unit_mass);Out(result->volume);}
            }
            else throw std::runtime_error("unknown operation");
        }
        if(std::cin.peek()!=std::char_traits<char>::eof())throw std::runtime_error("trailing input");
    }
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
