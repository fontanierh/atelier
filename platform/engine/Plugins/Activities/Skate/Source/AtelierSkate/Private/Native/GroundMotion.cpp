// SPDX-License-Identifier: Apache-2.0
#include "GroundMotion.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Words(Vec3 v) {return {v.x,v.y,v.z,0};}
Vec3 Three(Vec4 v) {return {v[0],v[1],v[2]};}
float Float(std::uint32_t word) {float value;std::memcpy(&value,&word,4);return value;}
float Reciprocal(float value)
{
    auto r=ReciprocalEstimate(value);
    for (unsigned i=0;i<2;++i) r=std::fma(r,std::fma(-value,r,1.0f),r);
    return r;
}
bool RemovePart(std::size_t part,Vec4 normal,ManualGroundBodies& bodies,
    ManualGroundProjection& projection,std::string& error)
{
    const auto velocity=bodies.LinearVelocity(part);float speed;
    if (!projection.NormalSpeed(normal,velocity,speed,error)) return false;
    auto remaining=velocity;
    for (std::size_t i=0;i<3;++i) {const auto component=normal[i]*speed;remaining[i]=velocity[i]-component;}
    bodies.SetLinearVelocity(part,remaining);return true;
}
}
Vec3 GroundEntryAngularVelocity(Vec4 normal,Vec4 angular)
{
    const auto speed=Dot3(normal,angular);for (auto& v:normal) v*=speed;return Three(normal);
}
float GroundEntryTargetSpeed(Vec3 velocity,Vec4 normal,Vec4 forward)
{
    const auto v=Words(velocity);const auto along_normal=Dot3(v,normal);Vec4 tangent;
    for (std::size_t i=0;i<4;++i) tangent[i]=v[i]-normal[i]*along_normal;
    const auto raw=std::abs(Dot3(v,forward)),planar=std::abs(Dot3(tangent,forward));
    return raw-planar>=0?planar:raw;
}
QueuedPointForce GroundLandingOnDeckForce(Vec4 physical,Vec4 animation,Vec4 axis,
    float mass,float strength,float point_y)
{
    Vec4 delta;for (std::size_t i=0;i<4;++i) delta[i]=animation[i]-physical[i];
    const auto projected=Dot3(delta,axis),inverse_step=Reciprocal(Float(0x3c888889));Vec4 force;
    for (std::size_t i=0;i<4;++i) force[i]=((delta[i]-axis[i]*projected)*strength)*mass*inverse_step;
    return {19,Three(force),{0,point_y,0}};
}
std::optional<Vec3> GroundFutureDeckDisplacement(const BoardForceQueue& forces,float mass,float dt,
    Vec4 normal,bool pushing,bool manual_correction)
{
    if (pushing||manual_correction) return std::nullopt;
    Vec4 sum{};
    for (std::size_t j=0;j<forces.Count();++j)
    {
        const auto v=Words(forces.Entries()[j].force_world);
        for (std::size_t i=0;i<4;++i) sum[i]+=v[i];
    }
    const auto scale=Reciprocal(mass)*dt;Vec4 delta;
    for (std::size_t i=0;i<4;++i) delta[i]=sum[i]*scale;
    const auto projection=Dot3(delta,normal);
    for (std::size_t i=0;i<4;++i) delta[i]=(delta[i]-normal[i]*projection)*dt;
    return Three(delta);
}
bool RemoveManualVelocityIntoGround(ManualGroundInput input,ManualGroundBodies& bodies,
    ManualGroundProjection& projection,std::string& error)
{
    if (input.balance==0) return true;
    if (!RemovePart(6,input.ground_normal,bodies,projection,error)) return false;
    const auto reversed=(input.flags_2468&(1u<<20))!=0;
    const auto contact26=(input.flags_2472&(1u<<26))!=0,contact27=(input.flags_2472&(1u<<27))!=0;
    const auto first=reversed?contact26:contact27,second=reversed?contact27:contact26;
    if (first) for (const std::size_t part:{0u,1u,4u}) if (!RemovePart(part,input.ground_normal,bodies,projection,error)) return false;
    if (second) for (const std::size_t part:{2u,3u,5u}) if (!RemovePart(part,input.ground_normal,bodies,projection,error)) return false;
    return true;
}
bool EnterManualGround(ManualState& state,std::uint32_t previous_category,float scale,
    ManualGroundInput input,ManualGroundBodies& bodies,ManualGroundProjection& projection,std::string& error)
{
    if (state.EnterGround(previous_category,scale)==ManualEntryContinuation::RemoveVelocityIntoGround)
        return RemoveManualVelocityIntoGround(input,bodies,projection,error);
    return true;
}
}
