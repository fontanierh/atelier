// SPDX-License-Identifier: Apache-2.0
#include "BoardColliders.h"
#include <fstream>
#include <iterator>
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

void Primitive(const ContactPrimitive& p)
{
    Out(std::uint32_t(p.index()));
    std::visit([](const auto& s)
    {
        using T=std::decay_t<decltype(s)>;
        if constexpr(std::is_same_v<T,Sphere>){Out(s.center);Out(s.radius);}
        else if constexpr(std::is_same_v<T,Capsule>){Out(s.center);Out(s.axis);Out(s.half_length);Out(s.radius);}
        else if constexpr(std::is_same_v<T,RoundedBox>){Out(s.center);Out(s.basis);Out(s.half_extents);Out(s.radius);}
        else {Out(s.vertices);Out(s.feature.normal);Out(s.feature.edges);Out(s.feature.flags);Out(s.feature.edge_cosines);Out(s.edge_lengths);Out(s.fatness);}
    },p);
}
void Material(ContactMaterial m){Out(m.static_friction);Out(m.dynamic_friction);Out(m.restitution);}
void Parameters(DriveParams d){Out(d.spring_or_max_velocity);Out(d.damping);Out(d.max_strength);Out(std::uint32_t(d.type));}
void Settings(const BoardPhysicsSettings& s)
{
    const auto v=s.step.simulation;Out(v.time_step);Out(v.frequency);Out(v.cool_down);Out(v.minimum_energy);Out(v.gravity_acceleration);
    Out(s.step.iterations);for(const auto& t:s.step.base_truck_transforms)Out(t);Parameters(s.step.truck_dynamics.linear);Parameters(s.step.truck_dynamics.angular);Out(s.step.force_point_y_offset);
    for(const auto& t:s.authored)Out(t);Material(s.collision.truck_material);Material(s.collision.deck_material);Material(s.collision.wheel_material);Material(s.standard_wheel_material);Material(s.floor_material);
    Out(s.collision.wheel_radius);Out(std::uint32_t(s.collision.truck_collisions));Out(s.input_magnitude_threshold);
}
}
int main(int argc,char** argv)
{
    if(argc!=2)return 2;std::ifstream file(argv[1],std::ios::binary);SettingsDatabase database;std::string error;
    if(!database.Load(std::vector<std::uint8_t>(std::istreambuf_iterator<char>(file),{}),error)){std::cerr<<error;return 2;}
    const auto stock=BoardPhysicsSettings::Load(database,error);if(!stock){std::cerr<<error;return 2;}
    const auto count=Word();Out(count);
    for(std::uint32_t c=0;c<count;++c)
    {
        const auto begin=output.size();Out(0u);auto settings=*stock;const auto mode=static_cast<BoardMotion>(Word());const auto spawn=Transform();
        const auto custom=Word();if(custom)
        {
            settings.collision.truck_collisions=Word()!=0;settings.collision.deck_geometry.children.clear();
            const auto n=Word();for(std::uint32_t j=0;j<n;++j)
            {
                const auto kind=Word();DeckShape shape;
                if(kind==0)shape=DeckSphere{Float()};else if(kind==1)shape=DeckCapsule{Float(),Float()};
                else if(kind==2)shape=DeckRoundedBox{Vector(),Float()};
                else {const std::array<Vec3,3> vertices{Vector(),Vector(),Vector()};const float fat=Float();const std::array<float,3> cos{Float(),Float(),Float()};shape=DeckTriangle{vertices,fat,cos,Word()};}
                const auto transform=Transform();const bool enabled=Word()!=0;settings.collision.deck_geometry.children.push_back({shape,transform,enabled});
            }
        }
        BoardRuntime board(settings.masses,settings.authored,spawn,settings.step.simulation,mode);Settings(settings);
        for(auto& b:board.BodiesMut()){b.state_flags=Word();b.rates.linear_velocity=Vector();}
        const auto n=Word();std::vector<WorldTriangle> triangles;for(std::uint32_t j=0;j<n;++j)
        {const std::array<Vec3,3> v{Vector(),Vector(),Vector()};const float fat=Float();const auto flags=Word();const auto tag=Word();triangles.push_back({TriangleFromVolume(v,fat,{1,1,1},flags),settings.floor_material,tag});}
        WorldGeometry world(std::move(triangles));BoardWorldContacts contacts;if(Word())contacts.EnableImportedFloorSeams();
        const auto frames=Word();Out(frames);
        for(std::uint32_t t=0;t<frames;++t)
        {
            const auto start=output.size();Out(0u);settings.step.simulation=Simulation();const auto iterations=Word();settings.step.iterations=iterations;
            const std::array<float,2> targets{Float(),Float()};board.ClearForces();const auto force=Vector();const auto point=Vector();board.ForcesMut().Append({t,force,point});
            const WorldContactSettings query{Float(),Float(),Float(),Float(),Word()!=0};const ContactRetentionSettings retention{Word(),Float(),Word()!=0};
            const auto volumes=BoardWorldVolumes(board,settings.collision);Out(std::uint32_t(volumes.size()));
            for(const auto& v:volumes){Out(v.body_contact_id);Primitive(v.primitive);Out(v.linear_velocity);Material(v.material);}
            const auto& collisions=contacts.Query(world,volumes,query,retention);Out(contacts.DroppedContacts());Out(std::uint32_t(collisions.size()));
            for(const auto& c:collisions){Out(c.body_a.ContactId());Out(c.body_b.ContactId());const auto& q=c.contact;Out(q.position_on_a);Out(q.position_on_b);Out(q.normal);Out(q.restitution);Out(q.static_friction);Out(q.dynamic_friction);Out(q.tag);}
            board.Advance(collisions,targets,settings.step);for(const auto& b:board.Bodies())Out(b);Out(board.Hook().body);Out(board.Hook().drive.frames);for(const auto& pose:board.PartTransforms())Out(pose);
            Out(std::uint32_t(board.SolvedContacts().size()));for(const auto& row:board.SolvedContacts())Out(row);
            Out(std::uint32_t(board.ContactReports().size()));for(const auto& report:board.ContactReports())Out(report);
            output[start]=std::uint32_t(output.size()-start-1);
        }
        output[begin]=std::uint32_t(output.size()-begin-1);
    }
    if(std::cin.peek()!=std::char_traits<char>::eof())return 2;
    for(auto w:output)for(unsigned i=0;i<4;++i)std::cout.put(char(w>>(i*8)));
}
