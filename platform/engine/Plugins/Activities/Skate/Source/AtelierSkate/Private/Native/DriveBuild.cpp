// SPDX-License-Identifier: Apache-2.0
#include "DriveBuild.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
std::uint32_t Word(float f){std::uint32_t w;std::memcpy(&w,&f,4);return w;}
std::array<float,3> Components(Vec3 v){return {v.x,v.y,v.z};}
bool Active(const DriveBodyState& b){return (b.state&4)!=0;}
struct WorldFrame {Quat orientation;Vec3 arm,position;};
WorldFrame ToWorld(DriveBodyState body,DriveFrame frame)
{
    const auto arm=constraint_frame::TransformDirection(body.basis,frame.translation);
    const auto p=body.center_of_mass;
    return {constraint_frame::Compose(body.orientation,frame.orientation),arm,{p.x+arm.x,p.y+arm.y,p.z+arm.z}};
}
struct Coefficients {float softness;std::array<float,3> target;float maximum;};
Coefficients BuildCoefficients(DriveParams p,std::array<float,3> position,
    const std::array<float,3>& velocity,const std::array<float,3>& acceleration,float dt)
{
    const float damping=dt*p.damping;
    float position_weight,velocity_weight,acceleration_weight;
    if(p.type==DriveType::Soft)
    {
        const float spring=(dt*p.spring_or_max_velocity)*dt;
        const float inverse=RefinedReciprocal((1.0f+spring)+damping);
        position_weight=inverse*spring;velocity_weight=inverse*damping;
        acceleration_weight=inverse*(spring+damping);
    }
    else
    {
        position_weight=RefinedReciprocal(1.0f+damping)*1.0f;
        velocity_weight=1.0f;acceleration_weight=1.0f;
    }
    if(p.type==DriveType::Hard)
    {
        const Vec3 v{position[0],position[1],position[2]};
        const float squared=Dot3(v,v),maximum=dt*p.spring_or_max_velocity;
        if(squared>maximum*maximum)
        {
            const float factor=maximum*InverseLengthSquared(squared);
            for(auto& component:position)component=component*factor;
        }
    }
    Coefficients result{acceleration_weight,{},(dt*p.max_strength)*dt};
    for(std::size_t i=0;i<3;++i)
    {
        const float rate=velocity[i]*velocity_weight;
        const float position_and_rate=std::fma(position[i],position_weight,rate);
        result.target[i]=std::fma(acceleration[i],acceleration_weight,position_and_rate);
    }
    return result;
}
float LinearEffectiveMass(DriveBodyState a,DriveBodyState b,Vec3 arm_a,Vec3 arm_b,Vec3 axis)
{
    float denominator=0.0f;
    if(Active(a))
    {
        const auto angular=Cross3(arm_a,axis);
        denominator+=a.inverse_mass+Dot3(angular,constraint_frame::MultiplyInertia(a.world_inverse_inertia,angular));
    }
    if(Active(b))
    {
        const auto angular=Cross3(arm_b,axis);
        denominator+=b.inverse_mass+Dot3(angular,constraint_frame::MultiplyInertia(b.world_inverse_inertia,angular));
    }
    return denominator;
}
float AngularEffectiveMass(DriveBodyState a,DriveBodyState b,Vec3 axis)
{
    float denominator=0.0f;
    if(Active(a))denominator+=Dot3(axis,constraint_frame::MultiplyInertia(a.world_inverse_inertia,axis));
    if(Active(b))denominator+=Dot3(axis,constraint_frame::MultiplyInertia(b.world_inverse_inertia,axis));
    return denominator;
}
}
DriveDynamics TruckDriveDynamics(TruckDriveSettings s)
{
    DriveParams linear{};
    if(s.use_linear)
    {
        if(s.use_hard_linear)linear={Float(0x45bb7fff),0,Float(0x48afc7ff),DriveType::Hard};
        else
        {
            const float spring=Float(0x47c35000);
            const float damping=(spring*InverseLengthSquared(spring))*2.0f;
            linear={spring,damping,Float(0x48afc7ff),DriveType::Soft};
        }
    }
    return {linear,{s.angular_displacement*Float(0x426fffff),s.angular_damping,
        s.angular_strength*Float(0x4560fffe),DriveType::Hard}};
}
DriveDynamics WheelDriveDynamics(bool hard)
{
    return {hard?DriveParams{Float(0x45bb7fff),0,Float(0x48afc7ff),DriveType::Hard}:
        DriveParams{Float(0x45610000),Float(0x42700000),Float(0x470c9fff),DriveType::Soft},{}};
}
DriveRows BuildDriveRows(DriveBodyState a,DriveBodyState b,DriveFrames frames,DriveDynamics dynamics,float dt)
{
    const auto wa=ToWorld(a,frames.body_a),wb=ToWorld(b,frames.body_b);
    DriveRows result;result.frame_a_body=a;result.frame_b_body=b;
    result.arm_a=wa.arm;result.arm_b=wb.arm;
    result.linear_axes=constraint_frame::Columns(constraint_frame::Basis(wb.orientation));
    const auto raw=constraint_frame::Rows(wa.orientation,wb.orientation);
    std::array<float,3> squared{},inverse_lengths{},angular_position{};
    bool singular=false;
    for(std::size_t i=0;i<3;++i)
    {
        squared[i]=VectorMin(VectorMax(raw.relative[i]*raw.relative[i],0.0f),1.0f);
        singular=singular||squared[i]==1.0f;
    }
    for(std::size_t i=0;i<3;++i)
    {
        inverse_lengths[i]=singular?1.0f:InverseLengthSquared(1.0f-squared[i]);
        result.angular_axes[i]=Scale(singular?result.linear_axes[i]:raw.axes[i],inverse_lengths[i]);
        angular_position[i]=(raw.relative[i]*inverse_lengths[i])*2.0f;
        result.linear_inverse_effective_mass[i]=RefinedReciprocal(LinearEffectiveMass(a,b,wa.arm,wb.arm,result.linear_axes[i]));
        result.angular_inverse_effective_mass[i]=RefinedReciprocal(AngularEffectiveMass(a,b,result.angular_axes[i]));
    }
    const auto linear_position=Subtract(wb.position,wa.position);
    const auto linear_velocity=Subtract(
        Scale(constraint_frame::PointRate(b.linear_velocity,b.angular_velocity,wb.arm),dt),
        Scale(constraint_frame::PointRate(a.linear_velocity,a.angular_velocity,wa.arm),dt));
    const auto linear_acceleration=Subtract(
        Scale(Scale(constraint_frame::PointRate(b.force_acceleration,b.torque_acceleration,wb.arm),dt),dt),
        Scale(Scale(constraint_frame::PointRate(a.force_acceleration,a.torque_acceleration,wa.arm),dt),dt));
    const auto angular_velocity=Scale(Subtract(b.angular_velocity,a.angular_velocity),dt);
    const auto angular_acceleration=Scale(Scale(Subtract(b.torque_acceleration,a.torque_acceleration),dt),dt);
    const auto linear=BuildCoefficients(dynamics.linear,Components(linear_position),Components(linear_velocity),Components(linear_acceleration),dt);
    const auto linear_target=constraint_frame::Project({linear.target[0],linear.target[1],linear.target[2]},result.linear_axes);
    const auto angular=BuildCoefficients(dynamics.angular,angular_position,
        constraint_frame::Project(angular_velocity,result.angular_axes),constraint_frame::Project(angular_acceleration,result.angular_axes),dt);
    result.linear_softness=linear.softness;result.angular_softness=angular.softness;
    for(std::size_t i=0;i<3;++i)
    {
        result.linear_target_impulse[i]=linear_target[i]*result.linear_inverse_effective_mass[i];
        result.angular_target_impulse[i]=angular.target[i]*result.angular_inverse_effective_mass[i];
        result.linear_maximum_impulse[i]=result.linear_inverse_effective_mass[i]*linear.maximum;
        result.angular_maximum_impulse[i]=result.angular_inverse_effective_mass[i]*angular.maximum;
    }
    return result;
}
DriveConstraint PackDrive(const DriveRows& d)
{
    DriveConstraint packed;packed.reaction_a=d.frame_a_body.reaction_index;packed.reaction_b=d.frame_b_body.reaction_index;
    const auto row=[&](std::size_t index,std::array<float,3> v,float w)
    {for(std::size_t i=0;i<3;++i)packed.words[index*4+i]=Word(v[i]);packed.words[index*4+3]=Word(w);};
    row(0,Components(d.arm_a),0);row(1,Components(d.arm_b),0);
    row(2,d.accumulated_linear_impulse,d.linear_softness);row(3,d.accumulated_angular_impulse,d.angular_softness);
    for(std::size_t component=0;component<3;++component)
    {
        std::array<float,3> linear{},angular{};
        for(std::size_t r=0;r<3;++r)
        {
            linear[r]=Components(d.linear_axes[r])[component]*d.linear_inverse_effective_mass[r];
            angular[r]=Components(d.angular_axes[r])[component]*d.angular_inverse_effective_mass[r];
        }
        row(4+component*2,linear,0);row(5+component*2,angular,0);
        row(12+component,Components(d.linear_axes[component]),0);row(15+component,Components(d.angular_axes[component]),0);
    }
    row(10,d.linear_target_impulse,d.linear_maximum_impulse[2]);row(11,d.angular_target_impulse,d.angular_maximum_impulse[2]);
    packed.words[27]=Word(d.linear_maximum_impulse[0]);packed.words[31]=Word(d.linear_maximum_impulse[1]);
    packed.words[35]=Word(d.angular_maximum_impulse[0]);packed.words[39]=Word(d.angular_maximum_impulse[1]);
    for(std::size_t side=0;side<2;++side)
    {
        const auto& body=side==0?d.frame_a_body:d.frame_b_body;
        if(!Active(body))continue;
        const auto& i=body.world_inverse_inertia;
        row(18+side*3,{i.full.x,i.full.y,i.full.z},body.inverse_mass);
        row(19+side*3,{i.full.y,i.split.y,i.split.z},0);
        row(20+side*3,{i.full.z,i.split.z,i.split.x},0);
    }
    return packed;
}
}
