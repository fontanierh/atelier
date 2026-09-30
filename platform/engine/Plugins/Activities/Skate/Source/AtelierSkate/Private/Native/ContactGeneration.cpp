// SPDX-License-Identifier: Apache-2.0
#include "ContactGeneration.h"
#include "ContactBuild.h"
#include <cassert>
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits) {float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Word(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);return bits;}
Vec3 PointVelocity(Vec3 linear,Vec3 omega,Vec3 arm)
{return {std::fma(arm.z,omega.y,std::fma(-arm.y,omega.z,linear.x)),std::fma(arm.x,omega.z,std::fma(-arm.z,omega.x,linear.y)),std::fma(arm.y,omega.x,std::fma(-arm.x,omega.y,linear.z))};}
Vec3 ContactCross(Vec3 a,Vec3 b)
{return {std::fma(a.y,b.z,std::fma(-a.z,b.y,0.0f)),std::fma(a.z,b.x,std::fma(-a.x,b.z,0.0f)),std::fma(a.x,b.y,std::fma(-a.y,b.x,0.0f))};}
float ContactSquared(Vec3 a) {return std::fma(a.z,a.z,std::fma(a.y,a.y,std::fma(a.x,a.x,0.0f)));}
Vec3 ContactScale(Vec3 a,float scale) {return {std::fma(a.x,scale,0.0f),std::fma(a.y,scale,0.0f),std::fma(a.z,scale,0.0f)};}
std::pair<Vec3,float> Fallback(Vec3 n)
{
    const Vec3 x={std::fma(-n.x,n.x,1.0f),std::fma(-n.y,n.x,0.0f),std::fma(-n.z,n.x,0.0f)};
    const Vec3 z={std::fma(-n.x,n.z,0.0f),std::fma(-n.y,n.z,0.0f),std::fma(-n.z,n.z,1.0f)};
    if (std::fma(-n.x,n.x,Scalar(0x3f000000))>=-0.0f) return {x,x.x};
    return {{-z.x,-z.y,-z.z},z.z};
}
void Put(ContactRecord& row,unsigned offset,Vec3 value,std::uint32_t w)
{row[offset]=Word(value.x);row[offset+1]=Word(value.y);row[offset+2]=Word(value.z);row[offset+3]=w;}
void Workspace(ContactRecord& row,unsigned offset,const ContactBodyState& body)
{
    Put(row,offset,body.center_of_mass,body.reaction_id);Put(row,offset+8,body.inverse_inertia_full,Word(body.inverse_mass));
    Put(row,offset+16,body.inverse_inertia_split,body.state);Put(row,offset+24,body.force_acceleration,Word(body.kinetic_energy));Put(row,offset+32,body.torque_acceleration,body.cool_down);
}
}
ContactRecord GenerateContact(ContactInput input,ContactBodyState body_a,ContactBodyState body_b)
{
    const auto arm_a=Subtract(input.position_on_a,body_a.center_of_mass),arm_b=Subtract(input.position_on_b,body_b.center_of_mass);
    const auto point_a=PointVelocity(body_a.linear_velocity,body_a.angular_velocity,arm_a),point_b=PointVelocity(body_b.linear_velocity,body_b.angular_velocity,arm_b);
    const auto relative=Subtract(point_b,point_a),velocity_tangent=ContactCross(relative,input.normal);const float squared=ContactSquared(velocity_tangent);
    const auto selected=squared>=Scalar(0x00800000) ? std::pair<Vec3,float>{velocity_tangent,squared}:Fallback(input.normal);
    const float inverse=ReciprocalSquareRootEstimate(selected.second);const auto tangent_0=ContactScale(selected.first,inverse);const auto n=input.normal,t=selected.first;
    const auto tangent_1=ContactScale({std::fma(-t.y,n.z,std::fma(t.z,n.y,0.0f)),std::fma(-t.z,n.x,std::fma(t.x,n.z,0.0f)),std::fma(-t.x,n.y,std::fma(t.y,n.x,0.0f))},inverse);
    ContactRecord row{};Put(row,0,input.position_on_a,body_a.contact_body_id);Put(row,4,input.position_on_b,body_b.contact_body_id);Put(row,8,input.normal,Word(input.restitution));
    Put(row,12,tangent_0,Word(input.static_friction));Put(row,16,tangent_1,Word(input.dynamic_friction));Put(row,20,relative,input.tag);Workspace(row,24,body_a);Workspace(row,28,body_b);return row;
}
ContactConstraint BuildContactJacobian(ContactRecord contact,float time_step)
{
    if (!(std::isfinite(time_step) && time_step>0.0f)) {assert(false && "Contact timestep must be positive and finite");std::abort();}
    ContactConstraint result;result.reaction_a=contact[27];result.reaction_b=contact[31];result.words=contact;BuildContact(result.words,time_step);return result;
}
ContactConstraint BuildContactJacobian(ContactInput input,ContactBodyState body_a,ContactBodyState body_b,float time_step)
{return BuildContactJacobian(GenerateContact(input,body_a,body_b),time_step);}
}
