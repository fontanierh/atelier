#include "BoardRuntime.h"
#include "DeckGeometry.h"
#include "JointBuild.h"
#include "JointRecords.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> output;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);return std::uint32_t(static_cast<unsigned char>(b[0]))|(std::uint32_t(static_cast<unsigned char>(b[1]))<<8)|(std::uint32_t(static_cast<unsigned char>(b[2]))<<16)|(std::uint32_t(static_cast<unsigned char>(b[3]))<<24);}
float Float(){const auto word=Word();float value;std::memcpy(&value,&word,4);return value;}
Vec3 Vector(){return {Float(),Float(),Float()};}
Basis3 Basis(){Basis3 b;for(auto& c:b.columns)for(auto& v:c)v=Float();return b;}
AffineTransform Transform(){const auto b=Basis();return {b,Vector()};}
SimulationStep Simulation(){SimulationStep s;s.time_step=Float();s.frequency=Float();s.cool_down=Word();s.minimum_energy=Float();s.gravity_acceleration=Vector();return s;}
void Out(std::uint32_t word){output.push_back(word);}
void Out(float value){std::uint32_t word;std::memcpy(&word,&value,4);Out(word);}
void Out(Vec3 value){Out(value.x);Out(value.y);Out(value.z);}
template<class T,std::size_t N>void Out(const std::array<T,N>& a){for(const auto& v:a)Out(v);}
void Out(Basis3 b){Out(b.columns);}
void Out(AffineTransform t){Out(t.basis);Out(t.translation);}
void Out(const BodySnapshot& b)
{
    const auto& r=b.rates;const auto& d=b.inertia;Out(b.state_flags);Out(r.orientation);Out(r.basis);Out(r.world_inverse_inertia);
    Out(r.position);Out(r.linear_velocity);Out(r.angular_velocity);Out(r.force_acceleration);Out(r.torque_acceleration);Out(r.kinetic_energy);Out(r.cool_down);
    Out(d.inverse_tensor);Out(d.inverse_mass);Out(d.spherical);Out(d.maximum_linear_velocity);Out(d.maximum_angular_velocity);Out(d.linear_drag);Out(d.angular_drag);
}
template<std::size_t N>void Out(const Constraint<N>& row){Out(row.words);Out(static_cast<std::uint32_t>(row.reaction_a));Out(static_cast<std::uint32_t>(row.reaction_b));}
void Out(const BoardContactReport& r)
{
    Out(static_cast<std::uint32_t>(r.part));Out(r.other.ContactId());Out(std::uint32_t(r.is_body_a));Out(r.normal);Out(r.position);Out(r.relative_linear_velocity);
    Out(std::uint32_t(r.other_surface));Out(r.normal_force_on_a);Out(r.friction_force_on_a);Out(r.tangents);
}
DriveBodyState DriveBody(const BodySnapshot& b,std::size_t id)
{
    const auto& r=b.rates;return {id,b.state_flags,r.orientation,r.basis,r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration,b.inertia.inverse_mass,PackWorldInverseInertia(r.world_inverse_inertia)};
}
JointBodyInput JointBody(const BodySnapshot& b)
{
    const auto& r=b.rates;return {0,b.state_flags,r.orientation,r.position,r.basis,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration,b.inertia.inverse_mass,PackWorldInverseInertia(r.world_inverse_inertia)};
}
ContactBodyState ContactBody(const BodySnapshot& b,std::uint32_t id)
{
    const auto& r=b.rates;const auto inertia=PackWorldInverseInertia(r.world_inverse_inertia);
    return {id,r.position,id,inertia.full,b.inertia.inverse_mass,inertia.split,b.state_flags|8u,r.force_acceleration,r.kinetic_energy,r.torque_acceleration,r.cool_down,r.linear_velocity,r.angular_velocity};
}
void Snapshot(const BoardRuntime& board,const std::vector<BodySnapshot>& attached,
    const std::vector<ContactConstraint>& contacts,const std::vector<JointConstraint>& joints,const std::vector<DriveRows>& drives)
{
    for(const auto& b:board.Bodies())Out(b);Out(board.Hook().body);Out(board.Hook().drive.frames);Out(board.Hook().drive.dynamics);
    for(const auto& t:board.PartTransforms())Out(t);for(std::size_t i=0;i<BoardBodyCount;++i)Out(board.BodyTransform(static_cast<BoardBodyId>(i)));Out(board.HookTransform());
    Out(static_cast<std::uint32_t>(board.Forces().Count()));for(std::size_t i=0;i<board.Forces().Count();++i){const auto& f=board.Forces().Entries()[i];Out(f.tag);Out(f.force_world);Out(f.point_body);}
    std::vector<float> inverse;for(const auto& b:board.Bodies())inverse.push_back(b.inertia.inverse_mass);Out(TotalBodyMass(inverse));Out(board.CollisionGroup());
    Out(static_cast<std::uint32_t>(board.SolvedContacts().size()));for(const auto& row:board.SolvedContacts())Out(row);
    Out(static_cast<std::uint32_t>(board.ContactReports().size()));for(const auto& report:board.ContactReports())Out(report);
    Out(static_cast<std::uint32_t>(attached.size()));for(const auto& b:attached)Out(b);
    Out(static_cast<std::uint32_t>(contacts.size()));for(const auto& row:contacts)Out(row);
    Out(static_cast<std::uint32_t>(joints.size()));for(const auto& row:joints)Out(row);
    Out(static_cast<std::uint32_t>(drives.size()));for(const auto& row:drives)Out(PackDrive(row));
}
}
int main()
{
    const auto cases=Word();for(std::uint32_t c=0;c<cases;++c)
    {
        const auto mode=static_cast<BoardMotion>(Word());const auto spawn=Transform();const auto simulation=Simulation();
        auto masses=DefaultSkateboardMassProperties();
        if(Word()!=0)for(auto& mass:masses){const auto t=Transform();mass.local_mass_frame={t.basis,t.translation};}
        const auto authored=AuthoredBodyTransforms(AuthoredTransformInputs::Stock());BoardRuntime board(masses,authored,spawn,simulation,mode);
        std::vector<BodySnapshot> attached;const auto attached_count=Word();
        for(std::uint32_t n=0;n<attached_count;++n){auto body=board.Bodies()[6];body.state_flags=Word();body.rates.position=Vector();attached.push_back(body);}
        std::vector<ContactConstraint> contacts;std::vector<JointConstraint> joints;std::vector<DriveRows> drives;
        const auto initial=output.size();Out(0u);Out(0u);Snapshot(board,attached,contacts,joints,drives);output[initial]=static_cast<std::uint32_t>(output.size()-initial-1);
        const auto commands=Word();for(std::uint32_t command=0;command<commands;++command)
        {
            const auto start=output.size();Out(0u);const auto op=Word();std::uint32_t result=0;
            switch(op)
            {
            case 0:{QueuedPointForce force;force.tag=Word();force.force_world=Vector();force.point_body=Vector();result=board.ForcesMut().Append(force);break;}
            case 1:board.ClearForces();break;
            case 2:board.SetTransform(Transform());break;
            case 3:board.SetHookTransform(Transform());break;
            case 4:{const auto flags=Word();const auto gravity=Vector();const auto target=Transform();board.ResetPhysical(authored,target,flags,gravity);break;}
            case 5:
            {
                const auto id=Word();auto& b=id<7?board.BodiesMut()[id]:id==7?board.HookMut().body:attached.at(id-8);
                b.state_flags=Word();b.rates.linear_velocity=Vector();b.rates.angular_velocity=Vector();b.rates.force_acceleration=Vector();b.rates.torque_acceleration=Vector();b.rates.kinetic_energy=Float();b.rates.cool_down=Word();break;
            }
            case 6:
            {
                std::uint8_t animated=static_cast<std::uint8_t>(Word());switch(Word())
                {
                    case 0:board.HookMut().drive.EnableAnimationSoft(animated);break;
                    case 1:board.HookMut().drive.EnableAngularSoft();break;
                    case 2:board.HookMut().drive.EnableAngularOnly(animated);break;
                    case 3:board.HookMut().drive.DisableAnimation(animated);break;
                    case 4:board.HookMut().drive.DisableLinear();break;
                    case 5:board.HookMut().drive.DisableAngular();break;
                    default:return 2;
                }
                result=animated;break;
            }
            case 7:
            {
                BoardStepSettings settings;settings.simulation=Simulation();settings.iterations=Word();
                settings.base_truck_transforms=CalculateTruckTransforms(TruckTransformInputs::Stock());settings.truck_dynamics=TruckDriveDynamics({});
                const std::array<float,2> targets{{Float(),Float()}};settings.force_point_y_offset=Float();std::vector<BoardCollision> collisions;
                const auto count=Word();for(std::uint32_t n=0;n<count;++n)
                {
                    const auto id=Word();const bool reverse=Word()!=0;const float gap=Float();ContactInput input;input.normal=Vector();input.restitution=Float();input.static_friction=Float();input.dynamic_friction=Float();input.tag=Word();
                    const auto& b=id<7?board.Bodies()[id]:attached.at(id-8);input.position_on_a=b.rates.position;input.position_on_a.y-=0.05f;input.position_on_b=input.position_on_a;input.position_on_b.y-=gap;
                    auto a=CollisionBody::FromContactId(id),world=CollisionBody::StaticWorld();if(reverse){std::swap(a,world);std::swap(input.position_on_a,input.position_on_b);input.normal={-input.normal.x,-input.normal.y,-input.normal.z};}
                    collisions.push_back({a,world,input});
                }
                const bool supplement=Word()!=0;contacts.clear();joints.clear();drives.clear();
                if(supplement && !attached.empty())
                {
                    const auto& a=attached[0];const auto& b=board.Bodies()[6];
                    const ContactInput input{a.rates.position,b.rates.position,{0,1,0},0.05f,0.4f,0.3f,0x12345678};
                    contacts.push_back(BuildContactJacobian(input,ContactBody(a,8),ContactBody(b,6),settings.simulation.time_step));
                    const auto record=DefaultJointRecords()[0];JointBuildInput j;j.parameters=record.parameters;j.frames=record.frames;j.body_a=JointBody(a);j.body_b=JointBody(b);j.time_step=settings.simulation.time_step;
                    joints.push_back({BuildJoint(j),8,6});drives.push_back(BuildDriveRows(DriveBody(a,8),DriveBody(b,6),{},TruckDriveDynamics({}),settings.simulation.time_step));
                }
                if(attached.empty())board.Advance(collisions,targets,settings);
                else {std::vector<BodySnapshot*> pointers;for(auto& b:attached)pointers.push_back(&b);board.AdvanceAttached(collisions,targets,settings,{pointers,contacts,joints,drives});}
                break;
            }
            case 8:board.SetCollisionGroup(Word());break;
            case 9:result=board.TakeSolverDiagnostics(Word()!=0).has_value();break;
            default:return 2;
            }
            Out(result);Snapshot(board,attached,contacts,joints,drives);output[start]=static_cast<std::uint32_t>(output.size()-start-1);
        }
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(const auto word:output){const char b[4]={char(word),char(word>>8),char(word>>16),char(word>>24)};std::cout.write(b,4);}
}
