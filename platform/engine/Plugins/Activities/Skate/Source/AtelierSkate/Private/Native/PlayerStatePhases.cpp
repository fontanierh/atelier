// SPDX-License-Identifier: Apache-2.0
#include "PlayerStatePhases.h"
#include "OffboardStaticScene.h"
#include "SkeletonLineQueries.h"
#include <cassert>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Value(RawVector raw){Vec4 v;std::memcpy(v.data(),raw.data(),16);return v;}
Vec3 Xyz(Vec4 v){return {v[0],v[1],v[2]};}
}
PlayerStatePhases::PlayerStatePhases(PlayerStatePhaseOwners o):owners_(o)
{
    const auto* f=&o.player.physical;const auto* p=&o.player.input.processed;
    assert(&o.ground.physical==f && &o.air.physical==f && &o.ground_animation.physical==f);
    assert(&o.biped.physical==f && &o.landing.shared.physical==f && &o.grind.physical==f && &o.wipeout.physical==f && &o.slide.physical==f);
    assert(&o.ground.processed==p && &o.air.processed==p && &o.ground_animation.processed==p && &o.biped.processed==p && &o.slide.processed==p);
    assert(&o.landing.shared.processed==p && &o.grind.input==&o.player.input && &o.wipeout.input==&o.player.input);
    assert(&o.ground.life==&o.player.ground_lifecycle && &o.air.life==&o.ground.life && &o.biped.life==&o.ground.life);
    assert(&o.landing.biped==&o.biped_ground && &o.landing.pose.hierarchy==&o.biped.hierarchy);
    assert(&o.air.packet==&o.landing.pose && &o.ground_animation.packet==&o.landing.pose && &o.slide.packet==&o.landing.pose);
}
bool PlayerStatePhases::Exit(PhysicalStateId previous,PhysicalStateId requested,std::string& error)
{
    auto& o=owners_;using S=PhysicalStateId;
    switch(previous)
    {
    case S::RevertGround:case S::Boneless:case S::Sleeping:case S::Teleporting:break;
    case S::HandPlant:o.ground.handplant.Reset();break;
    case S::FootPlant:o.air.footplant.Reset();break;
    case S::PhysicsGround:o.ground.ground.Exit(o.ground.runtime,o.player.physical,o.player.input.processed);break;
    case S::PhysicsAir:o.physics_air.Exit(o.air.air_reckoning);break;
    case S::KnownAir:return o.known_air.Exit(o.air,std::uint32_t(requested),error);
    case S::BipedAir:o.biped_air.Exit(o.biped.selector);break;
    case S::BipedGround:case S::OffBoardPushing:o.biped_ground.Exit(o.biped.contact);break;
    case S::GroundAnimation:o.animation_ground.Exit(o.ground_animation);break;
    case S::LandingOnDeck:o.landing_on_deck.Exit(o.landing);break;
    case S::SlideGround:o.sliding.Exit(o.slide);break;
    case S::WipeoutGround:o.ragdoll.Exit(o.wipeout);break;
    default:
        if(IsGrindState(previous)||previous==S::Nonspecific)return o.grinding.Exit(o.grind,error);
        error="Selected "+std::string(PhysicalStateName(previous))+" requires its physical exit";return false;
    }
    error.clear();return true;
}
bool PlayerStatePhases::Enter(PhysicalStateId requested,std::string& error)
{
    auto& o=owners_;using S=PhysicalStateId;
    switch(requested)
    {
    case S::RevertGround:o.revert.Enter(o.ground);break;
    case S::HandPlant:return o.ground.handplant.Enter(o.player.physical,o.player.input.processed,o.ground.life.board_animated_290,o.air.trajectory,error);
    case S::FootPlant:return o.air.footplant.GroundEnter(o.player.physical,o.player.input.processed,o.ground.life.board_animated_290,error);
    case S::Boneless:o.boneless.Enter(o.player.physical,o.ground.life,o.player.input.processed);break;
    case S::PhysicsGround:return EnterGroundPhase(o.ground,error);
    case S::PhysicsAir:return o.physics_air.Enter(o.air,error);
    case S::KnownAir:return o.known_air.Enter(o.air,error);
    case S::BipedAir:return o.biped_air.Enter(o.biped,o.biped_ground,error);
    case S::BipedGround:case S::OffBoardPushing:return o.biped_ground.Enter(o.biped,error);
    case S::GroundAnimation:return o.animation_ground.Enter(o.ground_animation,error);
    case S::LandingOnDeck:return o.landing_on_deck.Enter(o.landing,error);
    case S::SlideGround:o.sliding.Enter(o.slide);break;
    case S::WipeoutGround:return o.ragdoll.Enter(o.wipeout,error);
    case S::Teleporting:o.teleport.Enter();break;
    default:
        if(IsGrindState(requested)||requested==S::Nonspecific)return o.grinding.Enter(requested,o.grind,error);
        error="Selected "+std::string(PhysicalStateName(requested))+" requires its physical entry";return false;
    }
    error.clear();return true;
}
bool PlayerStatePhases::Update(PhysicalStateId current,std::string& error)
{
    auto& o=owners_;auto& f=o.player.physical;auto& p=o.player.input.processed;using S=PhysicalStateId;
    const PlantSkeletonFrame plant{p,o.air.SkeletonOwners(),o.air.skeleton_input,o.air.packet.hierarchy,o.air.skeleton_air};
    switch(current)
    {
    case S::RevertGround:return o.revert.Update({o.ground,o.air.skeleton_input,o.air.skeleton_air,o.air.packet.hierarchy},o.ground_settings,error);
    case S::HandPlant:return o.ground.handplant.Update(plant,o.air.air_reckoning,error);
    case S::FootPlant:return o.air.footplant.GroundUpdate(plant,o.air.toolkit,o.air.settings,o.air.trajectory,o.air.animation_input.extra.body_adjust,error);
    case S::Boneless:return o.boneless.Update({o.air,o.air.packet.hierarchy},error);
    case S::PhysicsGround:
    {
        PhysicalGroundPacket packet{Xyz(Value(p.vectors_464_480_496_512_528[0])),Xyz(Value(p.vectors_464_480_496_512_528[4])),p.scalar_2652,p.scalar_2616,0};
        std::memcpy(&packet.wheel_count,&p.wheel_count_2556,4);
        f.riding.UpdateGroundReckoning(f.board,{Xyz(Value(p.animation_com_to_deck_752)),o.air.animation_input.extra.physical_body_spin},p.flags_2468,o.air.animation_input.fields.balance,(p.flags_2476&0x40000000)!=0,packet);
        o.ground.ground.state.push_suppressed_2730=false;
        if(!AdvanceGroundPhase(o.ground,o.ground_settings,error))return false;
        if(!o.ground.handplant.GroundUpdate(f,p,o.ground.animated,o.ground.ik,error))return false;
        return UpdateGroundSkeletonInput(o.ground,o.air.skeleton_input,o.air.skeleton_air,o.air.packet.hierarchy,error);
    }
    case S::PhysicsAir:return o.physics_air.Advance(o.air,error);
    case S::KnownAir:return o.known_air.Update(o.air,error);
    case S::BipedAir:return o.biped_air.Update(o.biped,o.biped_ground,error);
    case S::BipedGround:case S::OffBoardPushing:
    {
        const BipedGroundContactSnapshot contact{static_cast<std::int32_t>(o.biped.contact.readiness),o.biped.contact.prefix};
        OffboardToolkitInput input;if(!o.biped_ground.Update(o.biped,contact,input,error))return false;
        auto scene=OffboardStaticScene::Create(f.world,error);if(!scene)return false;
        if(!o.biped.contact.Submit(input,static_cast<std::int32_t>(p.actor_query_2952),*scene,error))return false;
        return o.biped_ground.SubmitGeometry(o.biped,error);
    }
    case S::GroundAnimation:return o.animation_ground.Advance(o.ground_animation,o.ground_settings,o.ground_animation_settings,error);
    case S::LandingOnDeck:return o.landing_on_deck.Advance(o.landing,error);
    case S::SlideGround:return o.sliding.Advance(o.slide,error);
    case S::WipeoutGround:return o.ragdoll.Advance(o.wipeout,error);
    case S::Teleporting:
        if(o.teleport.Update(p))return o.respawn.Request(f.world,o.animation,o.teleport,error);
        break;
    default:
        if(IsGrindState(current)||current==S::Nonspecific)return o.grinding.Advance(o.grind,error);
        error="Selected "+std::string(PhysicalStateName(current))+" requires its physical update";return false;
    }
    error.clear();return true;
}
bool PlayerStatePhases::EnterAfterTeleport(std::string& error)
{
    const auto on=owners_.teleport.TakeManualOnBoard();
    return SetPlayerPhysicalState(owners_.player,on&&!*on?PhysicalStateId::BipedGround:PhysicalStateId::PhysicsGround,*this,error);
}
bool PlayerStatePhases::ApplyVehicleEjection(bool& applied,std::string& error)
{
    auto& o=owners_;const auto ejection=o.teleport.TakeVehicleEjection();applied=false;
    if(!ejection){error.clear();return true;}
    if(!SetPlayerPhysicalState(o.player,PhysicalStateId::WipeoutGround,*this,error))return false;
    const auto linear=ejection->first,angular=ejection->second;const Vec3 v{linear[0],linear[1],linear[2]},w{angular[0],angular[1],angular[2]};
    for(auto& body:o.player.physical.skeleton.BodiesMut()){body.rates.linear_velocity=v;body.rates.angular_velocity=w;}
    for(auto& body:o.player.physical.board.BodiesMut()){body.rates.linear_velocity=v;body.rates.angular_velocity=w;}
    const Vec4 motion{v.x,v.y,v.z,0};o.ground.animated.motion.velocity_world=motion;
    std::memcpy(o.player.input.processed.vectors_544_560_592_608[3].data(),motion.data(),16);
    o.ragdoll.state.velocity=motion;applied=true;error.clear();return true;
}
bool PlayerStatePhases::ResumeAfterClimb(std::string& error)
{
    auto& o=owners_;o.biped_ground.Exit(o.biped.contact);o.biped.selector.Reset();
    o.player.physical.collision_extra_errors={Vec4{},Vec4{}};o.ground.animated.motion.velocity_world={};
    o.player.input.processed.vectors_544_560_592_608[3]={};
    if(o.player.state.Current()==PhysicalStateId::BipedGround)
    {if(!o.biped_ground.Enter(o.biped,error))return false;}
    else if(!SetPlayerPhysicalState(o.player,PhysicalStateId::BipedGround,*this,error))return false;
    SkeletonLineTests queries;if(!QuerySkeletonLines(o.player.physical.world,o.player.physical.skeleton,queries,error))return false;queries.Publish(o.player.input.player);
    const auto frame=o.biped_ground.state.frame_80;auto scene=OffboardStaticScene::Create(o.player.physical.world,error);if(!scene)return false;
    return o.biped.contact.Submit({frame[3],frame[2],frame[1],frame[0],{},frame[1],frame[0]},static_cast<std::int32_t>(o.player.input.processed.actor_query_2952),*scene,error);
}
}
