#include "BoardAssembly.h"
#include "DrivePreparation.h"
#include "JointBuild.h"
#include "JointRecords.h"
#include "TruckDriveFrames.h"
#include <cstring>

namespace atelier::skate
{
namespace
{
std::uint32_t Bits(float value){std::uint32_t word;std::memcpy(&word,&value,4);return word;}
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
JointBodyInput JointBody(const BodySnapshot& body)
{
    const auto& r=body.rates;
    return {0,body.state_flags,r.orientation,r.position,r.basis,r.linear_velocity,r.angular_velocity,
        r.force_acceleration,r.torque_acceleration,body.inertia.inverse_mass,
        PackWorldInverseInertia(r.world_inverse_inertia)};
}
DriveBodyState DriveBody(const BodySnapshot& body,std::size_t reaction)
{
    const auto& r=body.rates;
    return {reaction,body.state_flags,r.orientation,r.basis,r.position,r.linear_velocity,r.angular_velocity,
        r.force_acceleration,r.torque_acceleration,body.inertia.inverse_mass,
        PackWorldInverseInertia(r.world_inverse_inertia)};
}
DriveFrames UnpackFrames(const std::array<std::uint32_t,16>& words)
{
    const auto frame=[&](std::size_t offset)->DriveFrame
    {
        return {{Float(words[offset]),Float(words[offset+1]),Float(words[offset+2]),Float(words[offset+3])},
            {Float(words[offset+4]),Float(words[offset+5]),Float(words[offset+6])}};
    };
    return {frame(0),frame(8)};
}
}
BoardConstraints BoardConstraints::Build(const std::array<BodySnapshot,BoardBodyCount>& bodies,
    const BoardHook& hook,std::array<DriveFrames,3> frames,DriveDynamics truck_dynamics,float time_step)
{
    BoardConstraints result;
    for(const auto& record:DefaultJointRecords())
    {
        const auto a=static_cast<std::size_t>(record.LiveBodyA());
        const auto b=static_cast<std::size_t>(record.LiveBodyB());
        if(((bodies[a].state_flags|bodies[b].state_flags)&4u)==0)continue;
        JointBuildInput input;
        input.parameters=record.parameters;input.frames=record.frames;
        input.body_a=JointBody(bodies[a]);input.body_b=JointBody(bodies[b]);input.time_step=time_step;
        result.joints.push_back({BuildJoint(input),a,b});
    }
    constexpr auto deck=static_cast<std::size_t>(BoardBodyId::Deck);
    constexpr std::array<std::size_t,2> trucks{{static_cast<std::size_t>(BoardBodyId::FrontTruck),
        static_cast<std::size_t>(BoardBodyId::BackTruck)}};
    for(std::size_t i=0;i<trucks.size();++i)
    {
        const auto truck=trucks[i];
        if(((bodies[truck].state_flags|bodies[deck].state_flags)&4u)==0)continue;
        result.drives.push_back(BuildDriveRows(DriveBody(bodies[truck],truck),DriveBody(bodies[deck],deck),
            frames[i],truck_dynamics,time_step));
    }
    if(((hook.body.state_flags|bodies[deck].state_flags)&4u)!=0)
        result.drives.push_back(BuildDriveRows(DriveBody(hook.body,HookReaction),DriveBody(bodies[deck],deck),
            frames[2],hook.drive.SolverDynamics(),time_step));
    return result;
}
std::array<DriveFrames,3> PrepareDriveFrames(std::array<AffineTransform,2> base,
    std::array<float,2> targets,BoardHook& hook)
{
    const auto trucks=SteeringDriveFrames(base,targets);
    std::array<DriveFrames,3> result;
    for(std::size_t i=0;i<trucks.size();++i)
    {
        std::array<std::uint32_t,16> raw{};
        const std::array<DriveFrame,2> frames{{trucks[i].body_a,trucks[i].body_b}};
        for(std::size_t side=0;side<frames.size();++side)
        {
            const auto& f=frames[side];const auto offset=side*8;
            const std::array<float,8> values{{f.orientation[0],f.orientation[1],f.orientation[2],f.orientation[3],
                f.translation.x,f.translation.y,f.translation.z,0.0f}};
            for(std::size_t lane=0;lane<values.size();++lane)raw[offset+lane]=Bits(values[lane]);
        }
        NormalizeDriveFrames(raw);result[i]=UnpackFrames(raw);
    }
    NormalizeDriveFrames(hook.drive.frames);result[2]=UnpackFrames(hook.drive.frames);
    return result;
}
}
