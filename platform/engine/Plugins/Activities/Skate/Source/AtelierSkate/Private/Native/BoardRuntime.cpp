// SPDX-License-Identifier: Apache-2.0
#include "BoardRuntime.h"
#include <cstdlib>
#include <cstring>
#include <limits>

namespace atelier::skate
{
namespace
{
std::uint32_t Bits(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
PoseMatrix PoseWords(AffineTransform transform)
{
    PoseMatrix words{};
    for(std::size_t axis=0;axis<3;++axis)
        for(std::size_t lane=0;lane<3;++lane)words[axis*4+lane]=Bits(transform.basis.columns[axis][lane]);
    words[12]=Bits(transform.translation.x);words[13]=Bits(transform.translation.y);words[14]=Bits(transform.translation.z);return words;
}
PoseMatrix MassFrameWords(LocalMassFrame frame){return PoseWords({frame.basis,frame.translation});}
std::array<std::uint32_t,10> InertiaWords(InertiaDynamics inertia)
{
    return {Bits(inertia.inverse_tensor.x),Bits(inertia.inverse_tensor.y),Bits(inertia.inverse_tensor.z),0,
        Bits(inertia.inverse_mass),Bits(inertia.spherical),Bits(inertia.maximum_linear_velocity),
        Bits(inertia.maximum_angular_velocity),Bits(inertia.linear_drag),Bits(inertia.angular_drag)};
}
std::array<std::uint32_t,44> BodyPoseWords(const BodyRates& rates)
{
    std::array<std::uint32_t,44> words{};
    for(std::size_t i=0;i<4;++i)words[i]=Bits(rates.orientation[i]);
    words[4]=Bits(rates.position.x);words[5]=Bits(rates.position.y);words[6]=Bits(rates.position.z);
    for(std::size_t axis=0;axis<3;++axis)
        for(std::size_t lane=0;lane<3;++lane)words[16+axis*4+lane]=Bits(rates.basis.columns[axis][lane]);
    return words;
}
AffineTransform RatesTransform(const BodyRates& rates){return {rates.basis,rates.position};}
AffineTransform TransformFromWords(const PoseMatrix& words)
{
    AffineTransform result;
    for(std::size_t axis=0;axis<3;++axis)
        for(std::size_t lane=0;lane<3;++lane)result.basis.columns[axis][lane]=Float(words[axis*4+lane]);
    result.translation={Float(words[12]),Float(words[13]),Float(words[14])};return result;
}
void CopyPose(const PartPose& part,BodyRates& rates)
{
    if(!part.body)std::abort();const auto& w=*part.body;
    for(std::size_t i=0;i<4;++i)rates.orientation[i]=Float(w[i]);
    rates.position={Float(w[4]),Float(w[5]),Float(w[6])};
    for(std::size_t axis=0;axis<3;++axis)
        for(std::size_t lane=0;lane<3;++lane)rates.basis.columns[axis][lane]=Float(w[16+axis*4+lane]);
}
}
BodySnapshot InitializeBody(const PartPose& part,InertiaDynamics inertia,SimulationStep simulation,BoardMotion mode)
{
    const bool is_static=mode==BoardMotion::Static;if(is_static)inertia={};
    BodyRates rates{};rates.orientation={0,0,0,1};rates.basis=AffineTransform{}.basis;
    rates.force_acceleration=is_static?Vec3{}:simulation.gravity_acceleration;
    rates.kinetic_energy=is_static?0.0f:std::numeric_limits<float>::max();
    rates.cool_down=mode==BoardMotion::Active?0:simulation.cool_down;
    CopyPose(part,rates);rates.world_inverse_inertia=WorldInverseInertia(rates.basis,inertia.inverse_tensor);
    return {mode==BoardMotion::Active?4u:mode==BoardMotion::Frozen?2u:1u,rates,inertia};
}
BoardRuntime::BoardRuntime(std::array<BodyMassProperties,BoardBodyCount> masses,
    std::array<AffineTransform,BoardBodyCount> authored,AffineTransform spawn,SimulationStep simulation,BoardMotion mode)
{
    std::array<PartPose,BoardBodyCount> parts;
    for(std::size_t i=0;i<parts.size();++i)
    {
        parts[i]={PoseWords(authored[i]),MassFrameWords(masses[i].local_mass_frame),std::array<std::uint32_t,44>{},std::nullopt};
        if(mode!=BoardMotion::Static)parts[i].inertia=InertiaWords(masses[i].dynamics);
        SetPartTransform(parts[i],PoseWords(authored[i]));
    }
    PartPose hook_part{PoseWords(AffineTransform{}),std::nullopt,std::array<std::uint32_t,44>{},std::nullopt};
    SetBoardTransform(parts,hook_part,PoseWords(spawn));
    for(std::size_t i=0;i<bodies_.size();++i)
    {
        bodies_[i]=InitializeBody(parts[i],masses[i].dynamics,simulation,mode);
        mass_frames_[i]=masses[i].local_mass_frame;
    }
    hook_={InitializeBody(hook_part,InertiaDynamics{},simulation,BoardMotion::Static),HookDriveState::Initial()};
}
std::optional<BoardSolverDiagnostics> BoardRuntime::TakeSolverDiagnostics(bool enabled)
{
    step_.diagnostic_capture=enabled;auto snapshot=std::move(step_.diagnostic_snapshot);step_.diagnostic_snapshot.reset();return snapshot;
}
void BoardRuntime::ResetPhysical(std::array<AffineTransform,BoardBodyCount> authored,AffineTransform target,
    std::uint32_t processed_flags,Vec3 gravity)
{
    std::array<PartPose,BoardBodyCount> parts;
    for(std::size_t i=0;i<parts.size();++i)
        parts[i]={PoseWords(authored[i]),MassFrameWords(mass_frames_[i]),BodyPoseWords(bodies_[i].rates),InertiaWords(bodies_[i].inertia)};
    for(const std::size_t i:{6,0,1,2,3,4,5})SetPartTransform(parts[i],PoseWords(authored[i]));
    if((processed_flags&0x00100000u)!=0)
        for(const std::size_t i:{0,2})for(auto& v:target.basis.columns[i])v=-v;
    PartPose hook{PoseWords(HookTransform()),std::nullopt,BodyPoseWords(hook_.body.rates),std::nullopt};
    SetBoardTransform(parts,hook,PoseWords(target));
    for(std::size_t i=0;i<bodies_.size();++i)
    {
        auto& body=bodies_[i];CopyPose(parts[i],body.rates);
        body.rates.linear_velocity={};body.rates.angular_velocity={};body.rates.force_acceleration=gravity;body.rates.torque_acceleration={};
        body.rates.world_inverse_inertia=WorldInverseInertia(body.rates.basis,body.inertia.inverse_tensor);
    }
    CopyPose(hook,hook_.body.rates);forces_.Clear();step_=BoardStep{};
}
void BoardRuntime::SetTransform(AffineTransform target)
{
    const auto authored=PartTransforms();std::array<PartPose,BoardBodyCount> parts;
    for(std::size_t i=0;i<parts.size();++i)
        parts[i]={PoseWords(authored[i]),MassFrameWords(mass_frames_[i]),BodyPoseWords(bodies_[i].rates),InertiaWords(bodies_[i].inertia)};
    PartPose hook{PoseWords(HookTransform()),std::nullopt,BodyPoseWords(hook_.body.rates),std::nullopt};
    SetBoardTransform(parts,hook,PoseWords(target));
    for(std::size_t i=0;i<bodies_.size();++i)
    {
        auto& body=bodies_[i];CopyPose(parts[i],body.rates);
        body.rates.world_inverse_inertia=WorldInverseInertia(body.rates.basis,body.inertia.inverse_tensor);
    }
    CopyPose(hook,hook_.body.rates);
}
AffineTransform BoardRuntime::BodyTransform(BoardBodyId id) const
{
    const auto index=static_cast<std::size_t>(id);if(index>=bodies_.size())std::abort();return RatesTransform(bodies_[index].rates);
}
std::array<AffineTransform,BoardBodyCount> BoardRuntime::PartTransforms() const
{
    std::array<AffineTransform,BoardBodyCount> result;
    for(std::size_t i=0;i<result.size();++i)
    {
        const PartPose part{PoseWords(RatesTransform(bodies_[i].rates)),MassFrameWords(mass_frames_[i]),BodyPoseWords(bodies_[i].rates),std::nullopt};
        result[i]=TransformFromWords(PartTransform(part));
    }
    return result;
}
AffineTransform BoardRuntime::HookTransform() const {return RatesTransform(hook_.body.rates);}
void BoardRuntime::SetHookTransform(AffineTransform requested)
{
    PartPose part{PoseWords(HookTransform()),std::nullopt,BodyPoseWords(hook_.body.rates),std::nullopt};
    SetPartTransform(part,PoseWords(requested));CopyPose(part,hook_.body.rates);
}
void BoardRuntime::Advance(const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,BoardStepSettings settings)
{step_.Advance(bodies_,hook_,forces_,collisions,truck_targets,settings);}
void BoardRuntime::AdvanceAttached(const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,
    BoardStepSettings settings,AttachedStep attached)
{step_.AdvanceAttached(bodies_,hook_,forces_,collisions,truck_targets,settings,std::move(attached));}
}
