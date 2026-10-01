// SPDX-License-Identifier: Apache-2.0
#include "GameplayRuntime.h"
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
template<class T> bool Adopt(std::optional<T> value,std::unique_ptr<T>& destination)
{
    if(!value)return false;
    destination=std::make_unique<T>(std::move(*value));return true;
}
}
bool GameplayRuntime::Create(std::shared_ptr<const GameplayResources> source,WorldGeometry world,
    std::shared_ptr<const PlayerGrindStaticProvider> grind_world,AffineTransform spawn,
    std::string_view mode,std::unique_ptr<GameplayRuntime>& output,std::string& error)
{
    if(!source || !source->animation || !source->animation->evaluator || !grind_world)
    {error="Gameplay construction requires native resources and a grind world";return false;}
    auto result=std::unique_ptr<GameplayRuntime>(new GameplayRuntime);
    result->resources=std::move(source);result->grind_world=std::move(grind_world);
    const auto& data=result->resources->settings;
    const auto& rig=result->resources->animation->evaluator->frames.rig;
    const auto& definition=result->resources->physical_skeleton;
    if(!result->profile.Load(data,mode,error))return false;
    if(!SkaterAnimation::FromSource(data,result->resources->graphs,"",result->resources->animation,result->animation,error))return false;
    if(!result->animation->EvaluateInitialPose(result->render_pose,error))return false;
    auto animated_settings=AnimatedSkeletonSettings::Load(data,definition,rig,false,error);
    if(!animated_settings)return false;
    result->animated=std::make_unique<AnimatedSkeleton>(std::move(*animated_settings));
    auto physical_settings=PhysicalSimulationSettings::Load(data,definition,rig,error);
    if(!physical_settings)return false;
    if(!Adopt(PhysicalSimulationRuntime::Initialize(std::move(*physical_settings),data,
        result->render_pose,std::move(world),spawn,error),result->physical))return false;
    result->grind_materials=std::make_unique<PlayerGrindMaterials>(result->physical->settings.board);
    auto registry=OffboardGrabRegistry::Create(result->physical->world,{},{},error);
    if(!registry)return false;
    result->grab_registry=std::move(*registry);
    if(!result->animation_input.Load(data,rig,mode,error))return false;
    if(!Adopt(FootIk::Load(data,rig,*result->animated,error),result->ik))return false;
    if(!Adopt(SkeletonOutputRuntime::Load(data,rig,*result->animated,error),result->skeleton_output))return false;
    if(!result->ragdoll.Load(data,definition,error))return false;
    const auto deck=result->physical->DeckFrame();
    if(!Adopt(RespawnRuntime::Load(data,deck,result->animation->CheckpointStance(),error),result->respawn))return false;
    if(!result->trajectory.Load(data,error))return false;
    result->trajectory.BindGrindWorld(result->grind_world);
    if(!Adopt(SkeletonInputRuntime::Load(data,error),result->skeleton_input))return false;
    if(!result->scoring.Load(data,error))return false;
    std::vector<std::string> bone_names;bone_names.reserve(rig.bones.size());
    for(const auto& bone:rig.bones)bone_names.push_back(bone.name);
    if(!result->climbing.Load(result->resources->climbing,bone_names,error))return false;
    if(!Adopt(SkeletonAir::Load(data,error),result->skeleton_air))return false;
    if(!result->air_reckoning.Load(data,error) || !result->air_settings.Load(data,error)
        || !result->known_air.Load(data,error) || !result->biped_air.Load(data,error)
        || !result->landing_on_deck.Load(data,error) || !result->landing_deck.Load(data,error)
        || !result->ground_animation_settings.Load(data,error) || !result->revert.Load(data,error)
        || !result->slide.Load(data,error) || !result->grind.Load(data,error)
        || !result->footplant.Load(data,error) || !result->boneless.Load(data,error)
        || !result->handplant.Load(data,error) || !result->wipeout.Load(data,error))return false;
    result->teleport=std::make_unique<TeleportStateRuntime>(TeleportCheckpoint{deck,true});
    if(!Adopt(FootPhysicalOutputs::Load(data,error),result->foot_physical))return false;
    if(!Adopt(PlayerInputRuntime::Load(data,error),result->input))return false;
    if(!Adopt(PlayerStateRuntime::Load(data,mode,error),result->player_state))return false;
    if(!result->player_state->conditioning.Load(data,error))return false;
    if(!result->ground.Load(data,true,error) || !result->ground_runtime.Load(data,error)
        || !result->ground_profiles.Load(data,error) || !result->ground_settings.Load(data,mode,"smooth",error))return false;
    if(!Adopt(BipedGroundRuntime::Load(data,result->resources->animation->metadata,error),result->biped_ground))return false;
    OffboardAirSelectorSettings selector_settings;
    if(!selector_settings.Load(data,error))return false;
    result->offboard_air_selector=std::make_unique<OffboardAirSelector>(std::move(selector_settings));
    if(!result->feedback.Load(data,error))return false;
    if(!Adopt(PlayerControls::Load(data,result->resources->gestures,error),result->controls))return false;
    if(!result->camera.Load(data,result->resources->camera_graph,result->resources->camera_data,error))return false;
    result->input_teleport=std::make_unique<PlayerTeleportRuntime>(PlayerTeleportLifecycle{
        result->ground,result->ground_lifecycle.skeleton_controller,*result->skeleton_air,
        result->footplant,result->handplant,result->grab_cache,result->wipeout.state,result->wobble,
        result->ground_lifecycle.skeleton_elapsed_16505,result->ground_lifecycle.board_animated_290});
    result->stock_spin_speed_=result->air_settings.state.body_spin_scale_428;
    output=std::move(result);error.clear();return true;
}
GameplayFrameOwners GameplayRuntime::BorrowFrame()
{
    auto& f=*physical;auto& i=*input;auto& a=*animated;auto& k=*ik;auto& si=*skeleton_input;
    auto& sa=*skeleton_air;auto& state=*player_state;auto& anim=*animation;
    const PlayerStateCoordinatorOwners shared{f,i,state,ground_lifecycle,si,animation_input,k,wipeout.state,grab,exchange};
    const GroundPhaseOwners ground_owners{f,i.processed,i.toolkit,ground,ground_runtime,ground_lifecycle,a,k,
        animation_input,air_reckoning,wobble,grab_cache,wipeout.state,handplant,*grind_world,trajectory,air_settings};
    const AirPhaseOwners air_owners{f,i.processed,i.toolkit,ground,ground_runtime,ground_lifecycle,a,k,
        animation_input,si,sa,air_reckoning,footplant,wipeout,*grind_world,trajectory,air_settings,
        {state.post.jump_reference,state.post.jump_fix_frames},anim.packet};
    const GroundAnimationOwners animation_ground_owners{f,i.processed,i.toolkit,ground,ground_runtime,
        ground_lifecycle,a,k,animation_input,si,sa,wipeout.state,trajectory,air_settings,anim.packet,trainer};
    const BipedRuntimeOwners biped_owners{f,i.processed,i.physical,i.toolkit,a,k,animation_input,si,sa,
        anim.packet.hierarchy,ground,ground_lifecycle,air_settings,air_reckoning,wipeout,offboard_contact,
        *offboard_air_selector,offboard_feet,landing_deck,grab};
    const LandingOnDeckOwners landing_owners{biped_owners,*biped_ground,anim.packet,wobble};
    const GrindRuntimeOwners grind_owners{f,i,ground,ground_runtime,ground_lifecycle,a,k,animation_input,si,sa,
        air_reckoning,wipeout.state,trajectory,ground_settings,air_settings,trainer,anim.packet.hierarchy};
    const WipeoutPhysicalOwners wipeout_owners{f,i,ground,ground_lifecycle,a,k,animation_input,si,wipeout,
        air_settings,anim.packet.hierarchy};
    const SlidePhaseOwners slide_owners{f,i.processed,i.toolkit,ground,ground_runtime,ground_lifecycle,a,k,
        animation_input,si,sa,air_reckoning,wipeout,trajectory,air_settings,ground_settings,anim.packet,state.post.jump_fix_frames};
    const PlayerStatePhaseOwners phases{shared,ground_owners,air_owners,animation_ground_owners,biped_owners,
        landing_owners,grind_owners,wipeout_owners,slide_owners,ground_settings,ground_animation_settings,anim,
        *respawn,*teleport,revert,air,known_air,boneless,ground_animation,*biped_ground,biped_air,landing_on_deck,grind,ragdoll,slide};
    const RenderPoseOwners render{f,a,i.processed,i.physical,k,wipeout,anim,ground.steering,wobble,
        *skeleton_output,*foot_physical,render_pose,pose_generation};
    const PlayerInputOwners input_owners{f,ground_runtime,si,a,k,animation_input,*grind_materials};
    const PlayerInputHostPhaseOwners host_input{shared,input_owners,offboard_contact,*offboard_air_selector,
        landing_deck,trajectory,*input_teleport,*grind_world};
    const PlayerStatePublicationOwners publication{shared,air_owners,biped_owners,landing_owners,grind_owners,
        wipeout_owners,air,known_air,*biped_ground,biped_air,landing_on_deck,grind,ragdoll,revert,slide.state,
        handplant,ground_animation,*teleport};
    const AnimationPhaseOwners animation_phase{f,i,state.conditioning,state.state_flags,k,handplant,
        air_reckoning,centre_of_mass_output,biped_ground->controller,trainer,physical_feedback,feedback,anim,*teleport};
    const AnimationFeedbackOwners animation_feedback{f,i,ground,animation_input,anim,state.conditioning,
        air_reckoning,feedback,physical_feedback};
    const ClimbingFrame climb{f,i,a,k,animation_input,centre_of_mass_filter,centre_of_mass_output,render_pose,
        pose_generation,state.lifecycle,*offboard_air_selector,offboard_feet};
    return {{phases,render},host_input,publication,animation_phase,animation_feedback,ground_profiles,
        ground_settings,grab_registry,climbing,climb,*controls,resources->graphs,profile,camera,clock,
        network_active,scoring,centre_of_mass_filter,centre_of_mass_output};
}
bool GameplayRuntime::Advance(const TickInput& packet,std::string& error)
{
    if(!controls->Sample(packet,input->physical,physical->settings,profile,camera,error))return false;
    auto actions=packet.Actions();
    return AdvanceGameplayFrame(BorrowFrame(),actions,packet.ControllerAvailable(),error);
}
bool GameplayRuntime::TravelTo(Mat4 transform,std::string& error)
{
    if(!input->RequestTeleport(transform,error))return false;
    teleport->RequestManual(transform,true);error.clear();return true;
}
bool GameplayRuntime::InstallWorld(WorldGeometry world,std::shared_ptr<const PlayerGrindStaticProvider> grind,
    std::string& error)
{
    if(!grind){error="World installation requires its grind provider";return false;}
    auto registry=OffboardGrabRegistry::Create(world,{},{},error);if(!registry)return false;
    grab_registry=std::move(*registry);physical->ReplaceWorld(std::move(world));
    grind_world=std::move(grind);trajectory.BindGrindWorld(grind_world);error.clear();return true;
}
bool GameplayRuntime::Tune(float pop,float spin,float push_speed,float push_power,float vert_assist,std::string& error)
{
    if(!std::isfinite(pop) || !std::isfinite(spin) || pop<0.5f || pop>2.0f || spin<0.5f || spin>3.0f
        || !std::isfinite(push_speed) || push_speed<0.5f || push_speed>2.0f
        || !std::isfinite(push_power) || push_power<0.5f || push_power>3.0f
        || !(vert_assist>=0.0f && vert_assist<=1.0f))
    {error="Invalid skating tuning";return false;}
    trajectory.vert_assist=vert_assist;
    trainer.pop=pop;trainer.push_speed=push_speed;trainer.push_power=push_power;
    air_settings.state.body_spin_scale_428=stock_spin_speed_*spin;
    known_air.SetSpinSpeed(stock_spin_speed_*spin);air_reckoning.SetSpinScale(spin);
    error.clear();return true;
}
void GameplayRuntime::Launch(Vec3 velocity)
{
    for(auto& body:physical->board.BodiesMut())body.rates.linear_velocity=velocity;
    for(auto& body:physical->skeleton.BodiesMut())body.rates.linear_velocity=velocity;
}
}
