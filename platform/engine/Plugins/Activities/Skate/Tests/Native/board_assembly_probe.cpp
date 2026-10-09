#include "BoardAssembly.h"
#include "DeckGeometry.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> output;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Vector(){return {Float(),Float(),Float()};}
Quat Quaternion(){return {Float(),Float(),Float(),Float()};}
Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return b;}
BodySnapshot Body()
{
    BodySnapshot b;b.state_flags=Word();auto& r=b.rates;r.orientation=Quaternion();r.basis=Basis();r.world_inverse_inertia=Basis();
    r.position=Vector();r.linear_velocity=Vector();r.angular_velocity=Vector();r.force_acceleration=Vector();r.torque_acceleration=Vector();
    r.kinetic_energy=Float();r.cool_down=Word();auto& d=b.inertia;d.inverse_tensor=Vector();d.inverse_mass=Float();d.spherical=Float();
    d.maximum_linear_velocity=Float();d.maximum_angular_velocity=Float();d.linear_drag=Float();d.angular_drag=Float();return b;
}
void Out(std::uint32_t v){output.push_back(v);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(Quat q){for(const auto v:q)Out(v);}
template<class T,std::size_t N>void Out(const std::array<T,N>& a){for(const auto& v:a)Out(v);}
void Out(Basis3 b){Out(b.columns);}
void Out(const BodyRates& r)
{
    Out(r.orientation);Out(r.basis);Out(r.world_inverse_inertia);Out(r.position);Out(r.linear_velocity);Out(r.angular_velocity);
    Out(r.force_acceleration);Out(r.torque_acceleration);Out(r.kinetic_energy);Out(r.cool_down);
}
void Out(DriveFrame f){Out(f.orientation);Out(f.translation);}
void Out(DriveFrames f){Out(f.body_a);Out(f.body_b);}
template<std::size_t N>void Out(const Constraint<N>& row){Out(row.words);Out(static_cast<std::uint32_t>(row.reaction_a));Out(static_cast<std::uint32_t>(row.reaction_b));}
void Out(const DriveBodyState& b)
{
    Out(static_cast<std::uint32_t>(b.reaction_index));Out(b.state);Out(b.orientation);Out(b.basis);Out(b.center_of_mass);
    Out(b.linear_velocity);Out(b.angular_velocity);Out(b.force_acceleration);Out(b.torque_acceleration);Out(b.inverse_mass);
    Out(b.world_inverse_inertia.full);Out(b.world_inverse_inertia.split);
}
void Out(const DriveRows& d)
{
    Out(d.frame_a_body);Out(d.frame_b_body);Out(d.arm_a);Out(d.arm_b);Out(d.linear_axes);Out(d.angular_axes);
    Out(d.linear_inverse_effective_mass);Out(d.angular_inverse_effective_mass);Out(d.linear_softness);Out(d.angular_softness);
    Out(d.linear_target_impulse);Out(d.angular_target_impulse);Out(d.linear_maximum_impulse);Out(d.angular_maximum_impulse);
    Out(d.accumulated_linear_impulse);Out(d.accumulated_angular_impulse);Out(PackDrive(d));
}
ReactionCorrections Unpack(const PackedReaction& words)
{
    const auto vector=[&](std::size_t offset)->Vec3
    {std::array<float,3> v;for(std::size_t n=0;n<3;++n)std::memcpy(&v[n],&words[offset+n],4);return {v[0],v[1],v[2]};};
    return {vector(0),vector(4),vector(8),vector(12)};
}
std::array<BodySnapshot,BoardBodyCount> StockBodies()
{
    const auto transforms=DefaultLiveBodyTransforms();const auto orientations=DefaultLiveBodyOrientations();
    const auto mass=DefaultSkateboardMassProperties();std::array<BodySnapshot,BoardBodyCount> result;
    for(std::size_t n=0;n<result.size();++n)
    {
        auto& b=result[n];b.state_flags=4;b.inertia=mass[n].dynamics;b.rates.orientation=orientations[n];
        b.rates.basis=BasisFromQuaternion(orientations[n]);b.rates.position=transforms[n].translation;
        b.rates.world_inverse_inertia=WorldInverseInertia(b.rates.basis,b.inertia.inverse_tensor);
    }
    return result;
}
}
int main()
{
    const auto cases=Word();for(std::uint32_t c=0;c<cases;++c)
    {
        const auto start=output.size();Out(0u);const bool stock=Word()!=0;
        std::array<BodySnapshot,BoardBodyCount> bodies;BoardHook hook;
        if(stock){bodies=StockBodies();hook.body=bodies[6];for(auto& b:bodies)b.state_flags=Word();hook.body.state_flags=Word();}
        else {for(auto& b:bodies)b=Body();hook.body=Body();}
        for(auto& w:hook.drive.frames)w=Word();for(auto& w:hook.drive.dynamics)w=Word();
        std::array<AffineTransform,2> base;for(auto& b:base){b.basis=Basis();b.translation=Vector();}
        const std::array<float,2> targets{{Float(),Float()}};
        TruckDriveSettings settings;settings.use_linear=Word()!=0;settings.use_hard_linear=Word()!=0;
        settings.angular_displacement=Float();settings.angular_damping=Float();settings.angular_strength=Float();
        const float dt=Float();const auto calls=Word(),iterations=Word();
        std::array<DriveFrames,3> frames;
        for(std::uint32_t n=0;n<calls;++n){frames=PrepareDriveFrames(base,targets,hook);for(const auto& f:frames)Out(f);Out(hook.drive.frames);Out(hook.drive.dynamics);}
        auto constraints=BoardConstraints::Build(bodies,hook,frames,TruckDriveDynamics(settings),dt);
        Out(static_cast<std::uint32_t>(constraints.joints.size()));for(const auto& j:constraints.joints)Out(j);
        Out(static_cast<std::uint32_t>(constraints.drives.size()));for(const auto& d:constraints.drives)Out(d);
        std::vector<DriveConstraint> drives;for(const auto& d:constraints.drives)drives.push_back(PackDrive(d));
        std::vector<ContactConstraint> contacts;std::vector<PackedReaction> reactions(BoardBodyCount+1);
        if(!SolveConstraints(contacts,constraints.joints,drives,reactions,iterations))return 3;
        for(const auto& j:constraints.joints)Out(j);for(const auto& d:drives)Out(d);
        for(const auto& r:reactions)
        {
            // The typed Rust facade retains xyz of each packed reaction row.
            const auto typed=Unpack(r);Out(typed.linear_displacement);Out(typed.position_displacement);
            Out(typed.angular_displacement);Out(typed.orientation_displacement);
        }
        const auto simulation=SimulationStep::Fixed60Hz(5,0.0001f,{0,-9.81f,0});
        for(std::size_t n=0;n<bodies.size();++n)
        {
            const auto step=IntegrateBodyRates(bodies[n].rates,bodies[n].inertia,simulation,Unpack(reactions[n]));
            Out(step.state);Out(step.orientation_displacement);Out(step.linear_speed_squared);Out(step.angular_speed_squared);
        }
        output[start]=static_cast<std::uint32_t>(output.size()-start-1);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(const auto w:output){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
}
