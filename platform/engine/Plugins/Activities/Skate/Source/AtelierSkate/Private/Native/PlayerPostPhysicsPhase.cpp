// SPDX-License-Identifier: Apache-2.0
#include "PlayerPostPhysicsPhase.h"
#include <cassert>
#include <cstring>
namespace atelier::skate
{
namespace
{
Vec4 Value(RawVector words){Vec4 value;std::memcpy(value.data(),words.data(),16);return value;}
Vec3 Xyz(Vec4 value){return {value[0],value[1],value[2]};}
template<std::size_t N>std::array<Vec4,N> Values(const std::array<RawVector,N>& input)
{std::array<Vec4,N> output;for(std::size_t i=0;i<N;++i)output[i]=Value(input[i]);return output;}
}
bool CheckPlayerWipeoutAfterPhysics(PlayerStatePhaseOwners o,std::string& error)
{
    const auto observations=AirPhaseWipeoutObservations(o.air);
    const auto current=o.player.state.Current();using S=PhysicalStateId;
    switch(current)
    {
    case S::HandPlant:case S::FootPlant:
    {
        WipeoutFrame frame;if(!observations.Frame(frame,error))return false;
        if(current==S::HandPlant)
        {if(!o.air.wipeout.CheckAir(observations,false,error))return false;}
        else CheckWipeoutPlant(o.air.wipeout.state,o.air.wipeout.settings,frame);
        if(current==S::FootPlant)o.air.footplant.PostPhysics(o.player.input.processed,o.air.wipeout.state);
        break;
    }
    case S::PhysicsGround:case S::SlideGround:case S::RevertGround:
        return o.air.wipeout.CheckGround(observations,error);
    case S::GroundAnimation:return o.air.wipeout.CheckGroundAnimation(observations,1.0f,error);
    case S::PhysicsAir:return o.air.wipeout.CheckAir(observations,false,error);
    default:break;
    }
    error.clear();return true;
}
bool AdvancePlayerOffboardPostPhysics(PlayerStatePhaseOwners o,std::string& error)
{
    const auto current=o.player.state.Current();using S=PhysicalStateId;
    if(current!=S::BipedGround && current!=S::OffBoardPushing && current!=S::BipedAir && current!=S::LandingOnDeck)
    {error.clear();return true;}
    WipeoutFrame frame;if(!AirPhaseWipeoutObservations(o.air).Frame(frame,error))return false;
    if(current==S::LandingOnDeck)return o.landing_on_deck.PostPhysics(o.landing,frame,error);
    if(current==S::BipedAir)return o.biped_air.PostPhysics(o.biped,frame,error);
    o.biped_ground.PostPhysics(o.biped,frame);error.clear();return true;
}
bool FinishPlayerPostPhysics(PlayerPostPhysicsOwners owners,std::string& error)
{
    auto& o=owners.states;auto& f=o.player.physical;const auto& p=o.player.input.processed;
    assert(&f==&owners.render.physical && &p==&owners.render.processed);
    assert(&owners.render.publication==&o.player.input.physical);
    assert(&owners.render.ik==&o.player.ik && &owners.render.animated==&o.air.animated);
    assert(&owners.render.animation==&o.animation && &owners.render.wipeout==&o.air.wipeout);
    assert(&owners.render.wobble==&o.ground.wobble);
    assert(&owners.render.steering==&o.ground.ground.steering);
    if(!o.player.input.toolkit)
    {error="Postphysics wall probe requires the current board toolkit";return false;}
    f.FinishBoardOutputs({p.state_2508,Xyz(Value(p.vectors_464_480_496_512_528[0])),
        Xyz(Value(p.vectors_544_560_592_608[0])),Xyz(o.player.input.toolkit->deck[3]),p.time_on_ground_2752});
    f.PublishFeedback({p.state_2508,p.category_2512,p.flags_2472,p.flags_2480,
        Values(p.vectors_464_480_496_512_528),Values(p.vectors_880_896_912_928_944)});
    const auto current=o.player.state.Current();
    if(current==PhysicalStateId::WipeoutGround)o.ragdoll.PostPhysics(o.wipeout);
    if(current==PhysicalStateId::PhysicsAir)o.physics_air.UpdateApex(f.board);
    if(current==PhysicalStateId::KnownAir && !o.known_air.PostPhysics(o.air,error))return false;
    if((IsGrindState(current)||current==PhysicalStateId::Nonspecific) && !o.grinding.Post(o.grind,o.player.state.post.jump_fix_frames,error))return false;
    if(!CheckPlayerWipeoutAfterPhysics(o,error))return false;
    if(!AdvancePlayerOffboardPostPhysics(o,error))return false;
    const auto compression=owners.render.skeleton_output.AverageCompressions(f.board);
    if(!PublishRenderPose(owners.render,compression,error))return false;
    return f.FinishFrame(error);
}
}
