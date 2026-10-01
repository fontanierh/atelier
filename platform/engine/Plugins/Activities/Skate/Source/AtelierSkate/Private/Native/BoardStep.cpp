// SPDX-License-Identifier: Apache-2.0
#include "BoardStep.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>

namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
ReactionCorrections UnpackReaction(const PackedReaction& words)
{
    const auto v=[&](std::size_t offset)->Vec3{return {Float(words[offset]),Float(words[offset+1]),Float(words[offset+2])};};
    return {v(0),v(4),v(8),v(12)};
}
void ApplyDeckForces(std::array<BodySnapshot,BoardBodyCount>& bodies,const BoardForceQueue& forces,float y_offset)
{
    auto& deck=bodies[static_cast<std::size_t>(BoardBodyId::Deck)];auto& r=deck.rates;
    const auto result=forces.ApplyToDeck({r.force_acceleration,r.torque_acceleration,r.cool_down},r.basis,
        deck.inertia.inverse_mass,r.world_inverse_inertia,y_offset);
    r.force_acceleration=result.force_acceleration;r.torque_acceleration=result.torque_acceleration;r.cool_down=result.cool_down;
}
ContactBodyState ContactBody(CollisionBody id,const std::array<BodySnapshot,BoardBodyCount>& bodies,
    const std::vector<BodySnapshot*>& attached,std::size_t world_reaction)
{
    ContactBodyState result{};
    if(id.kind==CollisionBody::Kind::StaticWorld)
    {
        result.contact_body_id=0xffffffffu;result.reaction_id=static_cast<std::uint32_t>(world_reaction);return result;
    }
    result.contact_body_id=id.ContactId();result.reaction_id=result.contact_body_id;
    if(id.kind==CollisionBody::Kind::Attached && id.index>=attached.size())std::abort();
    const auto& body=id.kind==CollisionBody::Kind::Board?bodies[id.index]:*attached[id.index];
    const auto& r=body.rates;const auto inertia=PackWorldInverseInertia(r.world_inverse_inertia);
    result.center_of_mass=r.position;result.inverse_inertia_full=inertia.full;result.inverse_inertia_split=inertia.split;
    result.inverse_mass=body.inertia.inverse_mass;result.state=body.state_flags|8u;
    result.force_acceleration=r.force_acceleration;result.torque_acceleration=r.torque_acceleration;
    result.linear_velocity=r.linear_velocity;result.angular_velocity=r.angular_velocity;
    result.kinetic_energy=r.kinetic_energy;result.cool_down=r.cool_down;return result;
}
}
void BoardStep::Advance(std::array<BodySnapshot,BoardBodyCount>& bodies,BoardHook& hook,const BoardForceQueue& forces,
    const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,BoardStepSettings settings)
{
    std::vector<ContactConstraint> contacts;std::vector<JointConstraint> joints;std::vector<DriveRows> drives;
    AdvanceAttached(bodies,hook,forces,collisions,truck_targets,settings,{{},contacts,joints,drives});
}
void BoardStep::AdvanceAttached(std::array<BodySnapshot,BoardBodyCount>& bodies,BoardHook& hook,const BoardForceQueue& forces,
    const std::vector<BoardCollision>& collisions,std::array<float,2> truck_targets,BoardStepSettings settings,AttachedStep attached)
{
    auto simulation=settings.simulation;
    if(!std::isfinite(simulation.time_step) || !(simulation.time_step>0.0f))std::abort();
    simulation.frequency=1.0f/simulation.time_step;
    for(const auto& collision:collisions)if(collision.body_a==collision.body_b)std::abort();
    for(std::size_t i=0;i<attached.bodies.size();++i)
    {
        const auto body=attached.bodies[i];if(!body || body==&hook.body)std::abort();
        for(const auto& part:bodies)if(body==&part)std::abort();
        for(std::size_t previous=0;previous<i;++previous)if(body==attached.bodies[previous])std::abort();
    }
    ApplyDeckForces(bodies,forces,settings.force_point_y_offset);
    const auto frames=PrepareDriveFrames(settings.base_truck_transforms,truck_targets,hook);
    const auto world_reaction=attached.WorldReaction();
    reactions_.assign(world_reaction+1,PackedReaction{});contacts_.clear();reports_.clear();
    bool any_active=(hook.body.state_flags&4u)!=0;
    for(const auto& body:bodies)any_active=any_active || (body.state_flags&4u)!=0;
    for(const auto body:attached.bodies)any_active=any_active || (body->state_flags&4u)!=0;
    if(!any_active)return;
    for(const auto& collision:collisions)
    {
        // The copied workspaces include this frame's applied point forces.
        contacts_.push_back(BuildContactJacobian(collision.contact,
            ContactBody(collision.body_a,bodies,attached.bodies,world_reaction),
            ContactBody(collision.body_b,bodies,attached.bodies,world_reaction),simulation.time_step));
    }
    auto constraints=BoardConstraints::Build(bodies,hook,frames,settings.truck_dynamics,simulation.time_step);
    const auto board_contacts=contacts_.size(),board_joints=constraints.joints.size(),board_drives=constraints.drives.size();
    contacts_.insert(contacts_.end(),attached.contacts.begin(),attached.contacts.end());
    constraints.joints.insert(constraints.joints.end(),attached.joints.begin(),attached.joints.end());
    constraints.drives.insert(constraints.drives.end(),attached.drives.begin(),attached.drives.end());
    std::vector<DriveConstraint> drives;drives.reserve(constraints.drives.size());
    for(const auto& drive:constraints.drives)drives.push_back(PackDrive(drive));
    if(!SolveConstraints(contacts_,constraints.joints,drives,reactions_,settings.iterations))std::abort();
    for(std::size_t i=0;i<drives.size();++i)
        for(std::size_t lane=0;lane<3;++lane)
        {
            constraints.drives[i].accumulated_linear_impulse[lane]=Float(drives[i].words[8+lane]);
            constraints.drives[i].accumulated_angular_impulse[lane]=Float(drives[i].words[12+lane]);
        }
    ++diagnostic_tick_;
    if(diagnostic_capture && diagnostic_tick_%6==0)
    {
        constexpr auto deck=static_cast<std::size_t>(BoardBodyId::Deck);
        BoardSolverDiagnostics snapshot{diagnostic_tick_,bodies[deck],hook,UnpackReaction(reactions_[deck]),{}, {}};
        for(std::size_t i=0;i<constraints.joints.size();++i)
            if(constraints.joints[i].reaction_a==deck || constraints.joints[i].reaction_b==deck)
                snapshot.joints.push_back({i,constraints.joints[i]});
        for(std::size_t i=0;i<constraints.drives.size();++i)
            if(constraints.drives[i].frame_a_body.reaction_index==deck || constraints.drives[i].frame_b_body.reaction_index==deck)
                snapshot.drives.push_back({i,constraints.drives[i]});
        diagnostic_snapshot=std::move(snapshot);
    }
    // Finish every solver family before integrating any assembly's body.
    const auto integrate=[&](BodySnapshot& body,std::size_t index)
    {
        if((body.state_flags&4u)!=0)
            body.rates=IntegrateBodyRates(body.rates,body.inertia,simulation,UnpackReaction(reactions_[index])).state;
        reactions_[index]={};
    };
    for(std::size_t i=0;i<bodies.size();++i)integrate(bodies[i],i);
    integrate(hook.body,HookReaction);
    for(std::size_t i=0;i<attached.bodies.size();++i)integrate(*attached.bodies[i],AttachedReactionBase+i);
    CollectBoardContactReports(reports_,contacts_,bodies,simulation.frequency);
    std::copy(contacts_.begin()+board_contacts,contacts_.end(),attached.contacts.begin());
    std::copy(constraints.joints.begin()+board_joints,constraints.joints.end(),attached.joints.begin());
    std::copy(constraints.drives.begin()+board_drives,constraints.drives.end(),attached.drives.begin());
}
}
