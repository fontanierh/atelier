#include "DriveBuild.h"
#include "JointBuild.h"
#include "JointRecords.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto w=Word();float v;std::memcpy(&v,&w,4);return v;}
Vec3 Vector(){const float x=Float(),y=Float(),z=Float();return {x,y,z};}
Quat Quaternion(){return {Float(),Float(),Float(),Float()};}
Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return b;}
DriveBodyState Body()
{
    DriveBodyState b;b.reaction_index=Word();b.state=Word();b.orientation=Quaternion();b.basis=Basis();
    b.center_of_mass=Vector();b.linear_velocity=Vector();b.angular_velocity=Vector();b.force_acceleration=Vector();b.torque_acceleration=Vector();
    b.inverse_mass=Float();b.world_inverse_inertia.full=Vector();b.world_inverse_inertia.split=Vector();return b;
}
JointBodyInput JointBody()
{
    const auto b=Body();return {static_cast<std::uint32_t>(b.reaction_index),b.state,b.orientation,b.center_of_mass,b.basis,
        b.linear_velocity,b.angular_velocity,b.force_acceleration,b.torque_acceleration,b.inverse_mass,b.world_inverse_inertia};
}
DriveFrame Frame(){const auto q=Quaternion();return {q,Vector()};}
DriveParams Params(){const float s=Float(),d=Float(),m=Float();return {s,d,m,static_cast<DriveType>(Word())};}
void Out(std::uint32_t w){const char b[4]={char(w),char(w>>8),char(w>>16),char(w>>24)};std::cout.write(b,4);}
void Out(float v){std::uint32_t w;std::memcpy(&w,&v,4);Out(w);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
template<class T,std::size_t N>void Out(const std::array<T,N>& a){for(const auto& v:a)Out(v);}
void Out(DriveParams p){Out(p.spring_or_max_velocity);Out(p.damping);Out(p.max_strength);Out(static_cast<std::uint32_t>(p.type));}
void Out(DriveDynamics d){Out(d.linear);Out(d.angular);}
void Out(const DriveRows& d)
{
    Out(d.arm_a);Out(d.arm_b);Out(d.linear_axes);Out(d.angular_axes);
    Out(d.linear_inverse_effective_mass);Out(d.angular_inverse_effective_mass);Out(d.linear_softness);Out(d.angular_softness);
    Out(d.linear_target_impulse);Out(d.angular_target_impulse);Out(d.linear_maximum_impulse);Out(d.angular_maximum_impulse);
    Out(d.accumulated_linear_impulse);Out(d.accumulated_angular_impulse);
    const auto packed=PackDrive(d);Out(packed.words);Out(static_cast<std::uint32_t>(packed.reaction_a));Out(static_cast<std::uint32_t>(packed.reaction_b));
}
}
int main()
{
    const auto count=Word();for(std::uint32_t n=0;n<count;++n)
    {
        switch(Word())
        {
        case 0:
        {
            JointBuildInput i;for(auto& w:i.parameters)w=Word();for(auto& w:i.frames)w=Word();
            i.body_a=JointBody();i.body_b=JointBody();i.time_step=Float();i.joint_address=Word();Out(BuildJoint(i));break;
        }
        case 1:
        {
            const auto a=Body(),b=Body();const DriveFrames f{Frame(),Frame()};const DriveDynamics d{Params(),Params()};const float dt=Float();
            Out(BuildDriveRows(a,b,f,d,dt));break;
        }
        case 2:
        {
            TruckDriveSettings s;s.use_linear=Word()!=0;s.use_hard_linear=Word()!=0;
            s.angular_displacement=Float();s.angular_damping=Float();s.angular_strength=Float();
            Out(TruckDriveDynamics(s));Out(WheelDriveDynamics(false));Out(WheelDriveDynamics(true));break;
        }
        case 3:
        {
            const bool stock=Word()!=0;JointSettings s{Float(),Float(),Float()};
            for(const auto& j:stock?DefaultJointRecords():JointRecords(s))
            {
                Out(static_cast<std::uint32_t>(j.definition_body_0));Out(static_cast<std::uint32_t>(j.definition_body_1));
                Out(static_cast<std::uint32_t>(j.LiveBodyA()));Out(static_cast<std::uint32_t>(j.LiveBodyB()));Out(j.parameters);Out(j.frames);
            }
            break;
        }
        default:return 2;
        }
    }
    return std::cin.peek()==std::char_traits<char>::eof()?0:2;
}
