// SPDX-License-Identifier: Apache-2.0
#include "SkeletonBody.h"
#include <cstdlib>
#include <cstring>
#include <utility>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
std::uint32_t Bits(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
PoseMatrix Words(Mat4 m){PoseMatrix result;for(std::size_t i=0;i<16;++i)result[i]=Bits(m[i/4][i%4]);return result;}
Mat4 Floats(PoseMatrix w){Mat4 result;for(std::size_t i=0;i<16;++i)result[i/4][i%4]=Float(w[i]);return result;}
PoseMatrix MassWords(LocalMassFrame frame)
{
    auto m=SkeletonIdentity;
    for(std::size_t column=0;column<3;++column)for(std::size_t lane=0;lane<3;++lane)m[column][lane]=frame.basis.columns[column][lane];
    m[3]={frame.translation.x,frame.translation.y,frame.translation.z,0};return Words(m);
}
std::array<std::uint32_t,10> InertiaWords(InertiaDynamics d)
{
    return {Bits(d.inverse_tensor.x),Bits(d.inverse_tensor.y),Bits(d.inverse_tensor.z),0,Bits(d.inverse_mass),Bits(d.spherical),
        Bits(d.maximum_linear_velocity),Bits(d.maximum_angular_velocity),Bits(d.linear_drag),Bits(d.angular_drag)};
}
std::array<std::uint32_t,44> BodyWords(const BodyRates& r)
{
    std::array<std::uint32_t,44> w{};for(std::size_t i=0;i<4;++i)w[i]=Bits(r.orientation[i]);
    w[4]=Bits(r.position.x);w[5]=Bits(r.position.y);w[6]=Bits(r.position.z);
    for(std::size_t axis=0;axis<3;++axis)for(std::size_t lane=0;lane<3;++lane)w[16+axis*4+lane]=Bits(r.basis.columns[axis][lane]);return w;
}
}
SkeletonBody::SkeletonBody(SkeletonBodyDefinition input,
    const std::array<Mat4,SkeletonAnimationPartCount>& input_authored,Mat4 spawn,SimulationStep simulation):definition(std::move(input))
{
    std::array<Mat4,SkeletonAnimationPartCount> authored;
    for(std::size_t i=0;i<authored.size();++i)authored[i]=Floats(OrthonormalizePartBasis(Words(input_authored[i])));
    animation_to_world=ComposeSkeletonAffine(spawn,InverseSkeletonRigid(authored[0]));
    for(std::size_t i=0;i<bodies_.size();++i)
    {
        const auto desired=i<SkeletonAnimationPartCount ? ComposeSkeletonAffine(animation_to_world,authored[i]):spawn;
        const auto mass=definition.parts[i].animated;auto inertia=mass.dynamics;
        if(i>=1 && i<SkeletonAnimationPartCount)inertia.inverse_mass=definition.parts[i].inverse_mass_animated;
        PartPose part{Words(desired),MassWords(mass.local_mass_frame),std::array<std::uint32_t,44>{},InertiaWords(inertia)};
        atelier::skate::SetPartTransform(part,Words(desired));bodies_[i]=InitializeBody(part,inertia,simulation,BoardMotion::Active);
    }
    const auto pose=PartTransforms();record.Update(pose,pose[0],definition.animation_masses.fractional);
    record.Update(pose,pose[0],definition.animation_masses.fractional);
}
void SkeletonBody::SetPartTransform(std::size_t part,Mat4 frame)
{
    if(part>=bodies_.size())std::abort();auto& body=bodies_[part];auto& r=body.rates;
    PartPose pose{Words(frame),MassWords(definition.parts[part].animated.local_mass_frame),BodyWords(r),InertiaWords(body.inertia)};
    atelier::skate::SetPartTransform(pose,Words(frame));const auto& w=*pose.body;
    for(std::size_t i=0;i<4;++i)r.orientation[i]=Float(w[i]);r.position={Float(w[4]),Float(w[5]),Float(w[6])};
    for(std::size_t axis=0;axis<3;++axis)for(std::size_t lane=0;lane<3;++lane)r.basis.columns[axis][lane]=Float(w[16+axis*4+lane]);
    r.world_inverse_inertia.columns={{{Float(w[28]),Float(w[29]),Float(w[30])},
        {Float(w[29]),Float(w[33]),Float(w[34])},{Float(w[30]),Float(w[34]),Float(w[32])}}};record.pose[part]=frame;
}
std::array<Mat4,SkeletonPartCount> SkeletonBody::PartTransforms() const
{
    std::array<Mat4,SkeletonPartCount> result;
    for(std::size_t i=0;i<result.size();++i)
    {
        const PartPose part{Words(SkeletonIdentity),MassWords(definition.parts[i].animated.local_mass_frame),BodyWords(bodies_[i].rates),std::nullopt};
        result[i]=Floats(PartTransform(part));
    }
    return result;
}
void SkeletonBody::PublishPhysicalRecord(Mat4 board){record.Update(PartTransforms(),board,definition.animation_masses.fractional);}
void SkeletonBody::ApplyPartDisplacement(std::size_t part,Vec4 displacement)
{
    const float step=Float(0x3c888889),inverse_step=RefinedReciprocal(step,2);
    if(part>=bodies_.size())std::abort();auto& body=bodies_[part];Vec4 value;
    for(std::size_t lane=0;lane<4;++lane)value[lane]=(displacement[lane]*inverse_step)*body.inertia.inverse_mass;
    body.rates.force_acceleration.x+=value[0];body.rates.force_acceleration.y+=value[1];body.rates.force_acceleration.z+=value[2];body.rates.cool_down=0;
}
}
