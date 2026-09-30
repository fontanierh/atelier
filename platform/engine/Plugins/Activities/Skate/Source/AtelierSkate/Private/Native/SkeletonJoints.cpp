// SPDX-License-Identifier: Apache-2.0
#include "SkeletonJoints.h"
#include "JointBuild.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t Bits(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
float MinimumAngle(float value){const float minimum=Float(0x3c23d70a);return value-minimum>=0.0f ? value:minimum;}
void PackFrame(std::uint32_t* words,Mat4 frame,Vec4 anchor)
{
    Basis3 basis;for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)basis.columns[i][j]=frame[i][j];
    const auto q=QuaternionFromBasis(basis);
    for(std::size_t i=0;i<4;++i){words[i]=Bits(q[i]);words[4+i]=Bits(anchor[i]);}
}
JointBodyInput JointBody(const BodySnapshot& body)
{
    const auto& r=body.rates;
    return {0,body.state_flags,r.orientation,r.position,r.basis,r.linear_velocity,r.angular_velocity,
        r.force_acceleration,r.torque_acceleration,body.inertia.inverse_mass,PackWorldInverseInertia(r.world_inverse_inertia)};
}
}
std::optional<SkeletonJoints> SkeletonJoints::FromDefinition(
    const std::array<Mat4,SkeletonAnimationPartCount>& initial_bones,
    const std::array<std::optional<std::size_t>,SkeletonAnimationPartCount>& parents,
    const std::array<SkeletonJointBone,SkeletonAnimationPartCount>& bones,
    const std::array<SkeletonJointBoneSettings,SkeletonJointCount>& settings,SkeletonJointSettings global,std::string& error)
{
    SkeletonJoints result;std::size_t count=0;
    for(std::size_t child=0;child<SkeletonAnimationPartCount;++child)
    {
        if(!parents[child])continue;const auto parent=*parents[child];
        if(parent>=SkeletonAnimationPartCount || parent==child){error="Invalid physical skeleton joint parent";return std::nullopt;}
        if(count>=settings.size()){error="Too many physical skeleton joints";return std::nullopt;}
        const auto setting=settings[count];const auto bone=bones[child];
        const auto inverse_child_volume=InverseSkeletonRigid(bone.volume_frame);
        const auto inverse_parent_volume=InverseSkeletonRigid(bones[parent].volume_frame);
        const auto parent_orientation=PhysicsBoneFrame(bone.parent_orientation,{});
        const auto joint_orientation=PhysicsBoneFrame(bone.joint_orientation,{});
        const auto parent_joint=ComposeSkeletonAffine(inverse_parent_volume,InverseSkeletonRigid(parent_orientation));
        const auto relative_bones=ComposeSkeletonAffine(InverseSkeletonRigid(initial_bones[parent]),initial_bones[child]);
        const auto parent_anchor=ComposeSkeletonAffine(inverse_parent_volume,relative_bones)[3];
        const auto child_frame=ComposeSkeletonAffine(inverse_child_volume,joint_orientation);
        const auto parent_frame=ComposeSkeletonAffine(parent_joint,joint_orientation);
        SkeletonJoint record{parent,child,{}, {}};PackFrame(record.frames.data(),child_frame,inverse_child_volume[3]);
        PackFrame(record.frames.data()+8,parent_frame,parent_anchor);record.frames[19]=Bits(1.0f);
        const float frequency=RefinedReciprocal(Float(0x3c888889),2);
        for(std::size_t i=0;i<4;++i)record.parameters[4+i]=Bits(global.displacement_limit[i]*frequency);
        record.parameters[8]=Bits(global.twist_displacement_limit*Float(0x426fffff));
        record.parameters[9]=Bits(global.swing_displacement_limit*Float(0x426fffff));
        record.parameters[14]=setting.ball_joint || global.enforce_swing_free ? 4u:1u;
        record.parameters[15]=setting.ball_joint || global.enforce_twist_free ? 2u:1u;
        const float swing=MinimumAngle(bone.swing_limit*setting.swing_angle),twist=MinimumAngle(bone.twist_limit*setting.twist_angle);
        record.parameters[10]=Bits(swing);record.parameters[11]=Bits(twist);record.parameters[12]=Bits(Cos(swing));record.parameters[13]=Bits(Cos(twist));
        result.records[count++]=record;
    }
    if(count!=SkeletonJointCount){error="Physical skeleton requires22 joints";return std::nullopt;}
    error.clear();return result;
}
std::vector<JointConstraint> SkeletonJoints::Build(const std::array<BodySnapshot,SkeletonPartCount>& bodies,
    std::size_t reaction_base,float time_step) const
{
    std::vector<JointConstraint> rows;
    for(const auto& record:records)
    {
        if(record.child>=bodies.size() || record.parent>=bodies.size())std::abort();
        const auto& a=bodies[record.child];const auto& b=bodies[record.parent];if(((a.state_flags|b.state_flags)&4u)==0)continue;
        JointBuildInput input;input.parameters=record.parameters;input.frames=record.frames;
        input.body_a=JointBody(a);input.body_b=JointBody(b);input.time_step=time_step;
        rows.push_back({BuildJoint(input),reaction_base+record.child,reaction_base+record.parent});
    }
    return rows;
}
}
