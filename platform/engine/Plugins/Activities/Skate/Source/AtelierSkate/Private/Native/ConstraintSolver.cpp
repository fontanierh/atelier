// SPDX-License-Identifier: Apache-2.0
#include "ConstraintSolver.h"
#include <cmath>
#include <cstring>
#include <limits>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
using Column = std::array<float,4>;
using Columns = std::array<Column,3>;
float Float(std::uint32_t word) { float value;std::memcpy(&value,&word,4);return value; }
std::uint32_t Word(float value) { std::uint32_t word;std::memcpy(&word,&value,4);return word; }
#if defined(__GNUC__)
__attribute__((noinline))
#elif defined(_MSC_VER)
__declspec(noinline)
#endif
float NegatedPositionCarry(float axis,float impulse)
{
    // The frozen arm64 reference folds this carry lane's negation into FNMADD
    // before applying inverse mass. XYZ instead subtracts its computed impulse.
    // Both the product and zero addend are negated; using -(fma(...,+0)) would
    // give a different signed zero for a negative-zero product.
    return std::fma(-axis,impulse,-0.0f);
}
template<std::size_t N> Column Read(const std::array<std::uint32_t,N>& words,std::size_t row)
{
    Column value{};for(std::size_t i=0;i<4;++i)value[i]=Float(words[row*4+i]);return value;
}
template<std::size_t N> void Write(std::array<std::uint32_t,N>& words,std::size_t row,const Column& value)
{
    for(std::size_t i=0;i<4;++i)words[row*4+i]=Word(value[i]);
}
Column PointCorrection(const Column& arm,const Column& linear,const Column& angular)
{
    Column value{};
    for(std::size_t lane=0;lane<4;++lane)
    {
        const auto next=lane==3?3:(lane+1)%3,previous=lane==3?3:(lane+2)%3;
        const float first=std::fma(angular[next],arm[previous],linear[lane]);
        value[lane]=std::fma(-angular[previous],arm[next],first);
    }
    return value;
}
struct ContactRows
{
    Column arm_a,arm_b,accumulated,target;
    Columns correction,axes,angular_a,angular_b;
    float static_friction,dynamic_friction;
    explicit ContactRows(const std::array<std::uint32_t,64>& words)
        : arm_a(Read(words,0)),arm_b(Read(words,1)),accumulated(Read(words,5)),target(Read(words,6)),
          static_friction(Float(words[15])),dynamic_friction(Float(words[19]))
    {
        for(std::size_t i=0;i<3;++i)
        {
            correction[i]=Read(words,2+i);axes[i]=Read(words,7+3*i);
            angular_a[i]=Read(words,8+3*i);angular_b[i]=Read(words,9+3*i);
        }
    }
};
struct ContactReaction
{
    Column linear,position,angular,orientation;
    explicit ContactReaction(const PackedReaction& words)
        :linear(Read(words,0)),position(Read(words,1)),angular(Read(words,2)),orientation(Read(words,3)){}
    void Apply(const ContactRows& rows,const Column& change,bool body_a)
    {
        const auto& response=body_a?rows.angular_a:rows.angular_b;
        const float inverse_mass=response[0][3];
        for(std::size_t lane=0;lane<4;++lane)
        {
            float linear_impulse=std::fma(rows.axes[0][lane],change[0],0.0f);
            linear_impulse=std::fma(rows.axes[1][lane],change[1],linear_impulse);
            linear_impulse=std::fma(rows.axes[2][lane],change[2],linear_impulse);
            const float position_impulse=std::fma(rows.axes[0][lane],change[3],0.0f);
            if(body_a)
            {
                for(std::size_t axis=0;axis<3;++axis)angular[lane]=std::fma(response[axis][lane],change[axis],angular[lane]);
                orientation[lane]=std::fma(response[0][lane],change[3],orientation[lane]);
                linear[lane]=std::fma(linear_impulse,inverse_mass,linear[lane]);
                position[lane]=std::fma(position_impulse,inverse_mass,position[lane]);
            }
            else
            {
                for(std::size_t axis=0;axis<3;++axis)angular[lane]=std::fma(-response[axis][lane],change[axis],angular[lane]);
                orientation[lane]=std::fma(-response[0][lane],change[3],orientation[lane]);
                linear[lane]=std::fma(-linear_impulse,inverse_mass,linear[lane]);
                const float negative_position=lane==3?NegatedPositionCarry(rows.axes[0][lane],change[3]):-position_impulse;
                position[lane]=std::fma(negative_position,inverse_mass,position[lane]);
            }
        }
    }
    void Publish(PackedReaction& words) const
    {
        Write(words,0,linear);Write(words,1,position);Write(words,2,angular);Write(words,3,orientation);
    }
};
void ContactPass(std::array<std::uint32_t,64>& words,PackedReaction& a,PackedReaction& b)
{
    const ContactRows rows(words);ContactReaction reaction_a(a),reaction_b(b);
    const auto position_a=PointCorrection(rows.arm_a,reaction_a.position,reaction_a.orientation);
    const auto position_b=PointCorrection(rows.arm_b,reaction_b.position,reaction_b.orientation);
    const auto velocity_a=PointCorrection(rows.arm_a,reaction_a.linear,reaction_a.angular);
    const auto velocity_b=PointCorrection(rows.arm_b,reaction_b.linear,reaction_b.angular);
    Column position_error{},total_error{},candidate{},next{},change{};
    for(std::size_t lane=0;lane<4;++lane)
    {
        position_error[lane]=position_b[lane]-position_a[lane];
        total_error[lane]=(velocity_b[lane]-velocity_a[lane])+position_error[lane];
    }
    for(std::size_t lane=0;lane<4;++lane)
    {
        const auto& error=lane==3?position_error:total_error;
        float impulse=rows.accumulated[lane]+rows.target[lane];
        for(std::size_t component=0;component<3;++component)
            impulse=std::fma(rows.correction[component][lane==3?0:lane],error[component],impulse);
        candidate[lane]=impulse;
    }
    for(std::size_t lane=0;lane<4;++lane)
    {
        const float normal=(lane==1||lane==2)?rows.accumulated[0]:0.0f;
        const float upper=(lane==0||lane==3)?std::numeric_limits<float>::max():0.0f;
        const float static_low=std::fma(-rows.static_friction,normal,0.0f);
        const float static_high=std::fma(rows.static_friction,normal,upper);
        const float dynamic_low=std::fma(-rows.dynamic_friction,normal,0.0f);
        const float dynamic_high=std::fma(rows.dynamic_friction,normal,upper);
        const float lower_selected=candidate[lane]>=static_low?candidate[lane]:dynamic_low;
        next[lane]=static_high>=candidate[lane]?lower_selected:dynamic_high;
        change[lane]=next[lane]-rows.accumulated[lane];
    }
    Write(words,5,next);reaction_a.Apply(rows,change,true);reaction_b.Apply(rows,change,false);
    reaction_a.Publish(a);reaction_b.Publish(b);
}
Column Project(const Columns& columns,const Column& correction,const Column& initial)
{
    Column result{};
    for(std::size_t component=0;component<4;++component)
    {
        const float x=std::fma(columns[0][component],correction[0],initial[component]);
        const float y=std::fma(columns[1][component],correction[1],x);
        result[component]=std::fma(columns[2][component],correction[2],y);
    }
    return result;
}
struct ReactionState
{
    Column linear,angular;
    explicit ReactionState(const PackedReaction& words):linear(Read(words,0)),angular(Read(words,2)){}
    void Publish(PackedReaction& words) const {Write(words,0,linear);Write(words,2,angular);}
};
struct Geometry
{
    Column arm_a,arm_b;
    Columns linear_projection,angular_projection,linear_axes,angular_axes,inertia_a,inertia_b;
    explicit Geometry(const std::array<std::uint32_t,96>& words):arm_a(Read(words,0)),arm_b(Read(words,1))
    {
        for(std::size_t i=0;i<3;++i)
        {
            linear_projection[i]=Read(words,4+2*i);angular_projection[i]=Read(words,5+2*i);
            linear_axes[i]=Read(words,12+i);angular_axes[i]=Read(words,15+i);
            inertia_a[i]=Read(words,18+i);inertia_b[i]=Read(words,21+i);
        }
    }
    void Relative(const ReactionState& a,const ReactionState& b,Column& point,Column& angular) const
    {
        const auto point_a=PointCorrection(arm_a,a.linear,a.angular);
        const auto point_b=PointCorrection(arm_b,b.linear,b.angular);
        for(std::size_t i=0;i<3;++i){point[i]=point_b[i]-point_a[i];angular[i]=b.angular[i]-a.angular[i];}
    }
    void Apply(ReactionState& a,ReactionState& b,const Column& linear_change,const Column& angular_change) const
    {
        const auto linear_impulse=Project(linear_axes,linear_change,{});
        const auto angular_impulse=Project(angular_axes,angular_change,{});
        // arm cross impulse + angular impulse, with the same fused order as
        // point correction (whose third argument is the left cross operand).
        const auto torque_a=PointCorrection(linear_impulse,angular_impulse,arm_a);
        const auto torque_b=PointCorrection(linear_impulse,angular_impulse,arm_b);
        for(std::size_t i=0;i<4;++i)
        {
            a.linear[i]=std::fma(linear_impulse[i],inertia_a[0][3],a.linear[i]);
            b.linear[i]=std::fma(-linear_impulse[i],inertia_b[0][3],b.linear[i]);
        }
        a.angular=Project(inertia_a,torque_a,a.angular);
        for(std::size_t i=0;i<4;++i)
        {
            const float x=std::fma(-inertia_b[0][i],torque_b[0],b.angular[i]);
            const float y=std::fma(-inertia_b[1][i],torque_b[1],x);
            b.angular[i]=std::fma(-inertia_b[2][i],torque_b[2],y);
        }
    }
};
float JointLimit(float candidate,float low,float high)
{
    const float high_error=high+candidate,low_error=low+candidate;
    const float negative=high_error<0.0f?high_error:0.0f;
    const float positive=low_error>0.0f?low_error:0.0f;
    return positive+negative;
}
float DriveLimit(float candidate,float limit)
{
    const float upper=candidate<limit?candidate:limit;
    const float negative=0.0f-limit;
    return upper>negative?upper:negative;
}
void JointDrivePass(std::array<std::uint32_t,96>& words,PackedReaction& a,PackedReaction& b,bool drive)
{
    const Geometry geometry(words);ReactionState body_a(a),body_b(b);
    Column relative_point{},relative_angular{};geometry.Relative(body_a,body_b,relative_point,relative_angular);
    const auto old_linear=Read(words,2),old_angular=Read(words,3);
    const auto linear_response=Project(geometry.linear_projection,relative_point,old_linear);
    const auto angular_response=Project(geometry.angular_projection,relative_angular,old_angular);
    const auto row10=Read(words,10),row11=Read(words,11);
    auto linear_impulse=old_linear,angular_impulse=old_angular;
    if(drive)
    {
        const Column linear_limit{Float(words[27]),Float(words[31]),row10[3],0.0f};
        const Column angular_limit{Float(words[35]),Float(words[39]),row11[3],0.0f};
        for(std::size_t i=0;i<3;++i)
        {
            linear_impulse[i]=DriveLimit(std::fma(linear_response[i],old_linear[3],row10[i]),linear_limit[i]);
            angular_impulse[i]=DriveLimit(std::fma(angular_response[i],old_angular[3],row11[i]),angular_limit[i]);
        }
    }
    else
    {
        const Column angular_low{Float(words[27]),Float(words[31]),row10[3],row10[3]};
        const Column angular_high{Float(words[35]),Float(words[39]),row11[3],row11[3]};
        for(std::size_t i=0;i<4;++i)
        {
            angular_impulse[i]=JointLimit(angular_response[i],angular_low[i],angular_high[i]);
            linear_impulse[i]=JointLimit(linear_response[i],row10[i],row11[i]);
        }
    }
    Column linear_change{},angular_change{};
    for(std::size_t i=0;i<3;++i){linear_change[i]=linear_impulse[i]-old_linear[i];angular_change[i]=angular_impulse[i]-old_angular[i];}
    // Angular-first publication for joints, linear-first for drives; both use
    // candidates computed from the same incoming reaction snapshot.
    if(drive){Write(words,2,linear_impulse);Write(words,3,angular_impulse);}
    else{Write(words,3,angular_impulse);Write(words,2,linear_impulse);}
    geometry.Apply(body_a,body_b,linear_change,angular_change);body_a.Publish(a);body_b.Publish(b);
}
template<std::size_t N> bool Valid(const std::vector<Constraint<N>>& constraints,std::size_t count)
{
    for(const auto& c:constraints)if(c.reaction_a==c.reaction_b||c.reaction_a>=count||c.reaction_b>=count)return false;
    return true;
}
}
bool SolveConstraints(std::vector<ContactConstraint>& contacts,std::vector<JointConstraint>& joints,
    std::vector<DriveConstraint>& drives,std::vector<PackedReaction>& reactions,std::uint32_t iterations)
{
    if(!Valid(contacts,reactions.size())||!Valid(joints,reactions.size())||!Valid(drives,reactions.size()))return false;
    for(std::uint32_t iteration=0;iteration<iterations;++iteration)
    {
        for(auto& c:contacts)ContactPass(c.words,reactions[c.reaction_a],reactions[c.reaction_b]);
        for(auto& c:joints)JointDrivePass(c.words,reactions[c.reaction_a],reactions[c.reaction_b],false);
        for(auto& c:drives)JointDrivePass(c.words,reactions[c.reaction_a],reactions[c.reaction_b],true);
    }
    return true;
}
}
