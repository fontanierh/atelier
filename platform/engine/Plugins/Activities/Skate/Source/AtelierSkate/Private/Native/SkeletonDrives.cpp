#include "SkeletonDrives.h"
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
Mat4 NormalizePart(Mat4 frame)
{
    PoseMatrix words;for(std::size_t i=0;i<16;++i)std::memcpy(&words[i],&frame[i/4][i%4],4);
    words=OrthonormalizePartBasis(words);for(std::size_t i=0;i<16;++i)frame[i/4][i%4]=Float(words[i]);return frame;
}
DriveBodyState DriveBody(const BodySnapshot& body,std::size_t index)
{
    const auto& r=body.rates;
    return {index,body.state_flags,r.orientation,r.basis,r.position,r.linear_velocity,r.angular_velocity,
        r.force_acceleration,r.torque_acceleration,body.inertia.inverse_mass,PackWorldInverseInertia(r.world_inverse_inertia)};
}
}
std::optional<SkeletonDrives> SkeletonDrives::FromDefinition(
    const std::array<Mat4,SkeletonAnimationPartCount>& initial_bones,
    const std::array<Mat4,SkeletonAnimationPartCount>& initial_mapped,
    const std::array<std::optional<std::size_t>,SkeletonAnimationPartCount>& parents,
    Mat4 animation_to_world,Mat4 spawn,SimulationStep simulation,SkeletonDriveSettings settings,std::string& error)
{
    bool invalid=parents[0].has_value() || parents[23].has_value();
    for(const auto p:parents)invalid=invalid || (p && *p>=SkeletonAnimationPartCount);
    for(std::size_t i=1;i<23;++i)invalid=invalid || !parents[i];
    if(invalid){error="Skeleton drives require22 bone pairs and two roots";return std::nullopt;}
    std::array<Mat4,SkeletonAnimationPartCount> inverses;
    for(std::size_t i=0;i<inverses.size();++i)inverses[i]=InverseSkeletonRigid(initial_bones[i]);
    SkeletonDrives result(simulation,settings);
    for(std::size_t part=0;part<parents.size();++part)
    {
        if(!parents[part])continue;const std::array<std::size_t,2> parent{{*parents[part],23}};
        const std::array<DriveFrames,2> frames{{BoneDriveFrames(initial_bones[part],inverses[part],inverses[parent[0]]),
            BoneDriveFrames(initial_bones[part],inverses[part],inverses[parent[1]])}};
        BoneDriveDynamics dynamics;dynamics.mode=2;dynamics.Enable(0,1,settings.bone);dynamics.mode=0;dynamics.Enable(1,1,settings.bone);
        result.bones[part]=BoneDrives{parent,{true,true},frames,dynamics};
    }
    const auto hips=NormalizePart(initial_mapped[23]);result.targets.Reset(ComposeSkeletonAffine(animation_to_world,hips),spawn);
    error.clear();return result;
}
void SkeletonDrives::Update(const std::array<Mat4,SkeletonAnimationPartCount>& pose,bool partial,float collision_weight)
{
    std::array<Mat4,SkeletonAnimationPartCount> inverses;for(std::size_t i=0;i<pose.size();++i)inverses[i]=InverseSkeletonRigid(pose[i]);
    const auto base=settings.enabled ? settings.strength:std::array<float,2>{};
    targets.dynamics[0].linear={Float(0x4415ffff),0,Float(0x470c9fff),DriveType::Hard};
    for(std::size_t part=1;part<23;++part)
    {
        if(!bones[part])continue;auto& bone=*bones[part];const bool selected=!partial || part<=5 || (part>=7 && part<=9);
        std::array<float,2> strengths;
        if(!(collision_weight>=1.0f) && selected)
        {
            bone.dynamics.mode=3;
            for(std::size_t channel=0;channel<2;++channel)
            {const float c=settings.collision_strength[part][channel];strengths[channel]=std::fma(1.0f-c,collision_weight,c)*settings.strength[channel];}
        }
        else {bone.dynamics.mode=0;strengths=base;}
        bone.dynamics.strengths=strengths;
        for(std::size_t channel=0;channel<2;++channel)
        {
            if(!bone.active[channel])continue;
            if(bone.parent[channel]>=inverses.size())std::abort();
            bone.frames[channel]=BoneDriveFrames(pose[part],inverses[part],inverses[bone.parent[channel]]);
            bone.dynamics.Enable(channel,strengths[channel],settings.bone);
        }
    }
}
SkeletonDriveBatch SkeletonDrives::Build(const std::array<BodySnapshot,SkeletonPartCount>& bodies,
    std::size_t reaction_base,std::size_t target_reaction_base,float time_step)
{
    SkeletonDriveBatch batch;batch.rows.reserve(48);batch.identities.reserve(48);batch.spy.reserve(48);
    for(std::size_t target=0;target<SkeletonTargetCount;++target)
    {
        targets.frames[target]=PrepareBoneDriveFrames(targets.frames[target]);const auto part=SkeletonTargetParts[target];
        const auto& a=bodies[part];const auto& b=targets.bodies[target];if(((a.state_flags|b.state_flags)&4u)==0)continue;
        batch.rows.push_back(BuildDriveRows(DriveBody(a,reaction_base+part),DriveBody(b,target_reaction_base+target),targets.frames[target],targets.dynamics[target],time_step));
        batch.identities.push_back({SkeletonDriveIdentity::Kind::Target,target,0});batch.spy.push_back(target>=2);
    }
    for(std::size_t part=1;part<23;++part)
    {
        if(!bones[part])continue;auto& bone=*bones[part];
        for(std::size_t channel=0;channel<2;++channel)
        {
            if(!bone.active[channel])continue;bone.frames[channel]=PrepareBoneDriveFrames(bone.frames[channel]);
            const auto parent=bone.parent[channel];if(parent>=bodies.size())std::abort();
            const auto& a=bodies[part];const auto& b=bodies[parent];if(((a.state_flags|b.state_flags)&4u)==0)continue;
            batch.rows.push_back(BuildDriveRows(DriveBody(a,reaction_base+part),DriveBody(b,reaction_base+parent),bone.frames[channel],bone.dynamics.channels[channel],time_step));
            batch.identities.push_back({SkeletonDriveIdentity::Kind::Bone,part,channel});batch.spy.push_back(true);
        }
    }
    return batch;
}
}
