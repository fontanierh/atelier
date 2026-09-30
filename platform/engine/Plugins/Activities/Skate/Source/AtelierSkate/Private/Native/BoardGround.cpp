// SPDX-License-Identifier: Apache-2.0
#include "BoardGround.h"
#include <cstdlib>
#include <cstring>
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
Vec3 Add(Vec3 a,Vec3 b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
}
std::array<WheelLine,4> WheelLines(const BoardRuntime& board,Vec3 up)
{
    const auto poses=board.PartTransforms();const auto delta=Scale(up,WheelLineLength);
    std::array<WheelLine,4> lines;
    for(std::size_t i=0;i<4;++i)lines[i]={poses[i].translation,Subtract(poses[i].translation,delta)};
    return lines;
}
void WheelLineState::Publish(const std::array<std::optional<WheelLineHit>,4>& hits)
{
    minimum_distance=WheelLineLength;
    for(std::size_t i=0;i<4;++i)
    {
        physics_surfaces[i]=0;
        if(hits[i])
        {
            const auto& hit=*hits[i];const float distance=hit.fraction*WheelLineLength;
            minimum_distance=distance-minimum_distance>=-0.0f?minimum_distance:distance;
            normals[i]=hit.normal;distances[i]=distance;physics_surfaces[i]=(hit.surface_tag>>7)&31u;
        }
    }
}
void BoardGroundState::SampleAccelerations(const std::array<Vec3,BoardBodyCount>& velocities,float dt)
{
    const float inverse_dt=1.0f/dt;
    for(std::size_t i=0;i<velocities.size();++i)
    {accelerations[i]=Scale(Subtract(velocities[i],previous_velocities[i]),inverse_dt);previous_velocities[i]=velocities[i];}
}
void BoardGroundState::AdvanceContactTime(float dt)
{time_without_wheel_contact=wheel_contact_count==0?time_without_wheel_contact+dt:0.0f;}
void BoardGroundState::Update(const std::vector<BoardContactReport>& reports,const WheelLineState& lines,
    Vec3 up,float maximum_angle,bool wiping)
{
    parts.fill(PartGroundContact{});closing_velocity={};maximum_closing_speed=0;surface_twelve_height=0;
    collision_flags&=0x01ffffffu;overall_normal={0,1,0};valid_wheel_normals.fill(true);
    float highest_y=-2.0f;std::optional<std::size_t> highest_part;
    float minimum_projection=1.0f,maximum_projection=-1.0f;
    std::array<std::uint32_t,BoardBodyCount> surfaces{};
    for(std::size_t i=0;i<4;++i)surfaces[i]=lines.physics_surfaces[i];
    for(const auto& report:reports)
    {
        if(!(report.other==CollisionBody::StaticWorld()))std::abort();
        const auto i=static_cast<std::size_t>(report.part);if(i>=parts.size())std::abort();
        if(report.part==BoardBodyId::Deck)
        {
            const float projection=Dot3(report.normal,up);
            minimum_projection=minimum_projection-projection>=0.0f?projection:minimum_projection;
            maximum_projection=maximum_projection-projection>=0.0f?maximum_projection:projection;
        }
        const float closing=-Dot3(report.normal,previous_velocities[i]);
        if(!(closing<=maximum_closing_speed)){maximum_closing_speed=closing;closing_velocity=Scale(report.normal,-closing);}
        const auto surface=(std::uint32_t(report.other_surface)>>7)&31u;
        if(surface==12){collision_flags|=1u<<25;surface_twelve_height=report.position.y;}
        if(i>=4)surfaces[i]=surface;
        auto& contact=parts[i];
        if(!contact.in_contact || report.normal.y>contact.normal.y)
        {contact.normal=report.normal;contact.point=report.position;contact.relative_velocity=report.relative_linear_velocity;}
        if(contact.normal.y>highest_y){highest_y=contact.normal.y;highest_part=i;}
        contact.in_contact=true;
    }
    const float range=maximum_projection-minimum_projection;opposing_contact=-range>=0.0f?0.0f:range;
    for(std::size_t i=0;i<parts.size();++i)if(parts[i].in_contact && surfaces[i]==8)collision_flags|=1u<<31;
    const auto reference=highest_part?parts[*highest_part].normal:wheel_normal;
    for(std::size_t i=0;i<4;++i)
    {
        if(!parts[i].in_contact)
        {
            if(lines.distances[i]<Float(0x3d8f5c29))parts[i].normal=lines.normals[i];
            else valid_wheel_normals[i]=false;
        }
    }
    part_contact_count=0;wheel_contact_count=0;
    for(std::size_t i=0;i<parts.size();++i)if(parts[i].in_contact){++part_contact_count;if(i<4)++wheel_contact_count;}
    const float minimum_up=Cos(maximum_angle*Float(0x3c8efa35));Vec3 sum{};
    for(std::size_t i=0;i<4;++i)
    {
        const auto& contact=parts[i];
        if(valid_wheel_normals[i] && Dot3(contact.normal,up)>minimum_up &&
            BoardGroundAngleBetween(reference,contact.normal)<Float(0x3f490fdb))sum=Add(sum,contact.normal);
        const float drag=contact.in_contact?(wiping?Float(0x3d23d70a):0.0f):Float(0x3bc49ba6);
        wheel_angular_drag[i]=drag*Float(0x426fffff);
    }
    const float squared=Dot3(sum,sum);
    if(wheel_contact_count>0 && squared>Float(0x37800000))
    {overall_normal=Scale(sum,InverseLengthSquared(squared,2));wheel_normal=overall_normal;}
    else
    {
        Vec3 support{};
        for(const std::size_t i:{6,4,5})if(parts[i].in_contact)support=Add(support,parts[i].normal);
        const float magnitude=Length3(support);
        if(magnitude>Float(0x3c23d70a))overall_normal=Scale(support,RefinedReciprocal(magnitude,2));
    }
}
}
