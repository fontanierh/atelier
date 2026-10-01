// SPDX-License-Identifier: Apache-2.0
#include "AirPhaseRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float AirPhaseFloat(std::uint32_t word){float value;std::memcpy(&value,&word,4);return value;}
Vec4 AirPhaseVector(const RawVector& words)
{return {AirPhaseFloat(words[0]),AirPhaseFloat(words[1]),AirPhaseFloat(words[2]),AirPhaseFloat(words[3])};}
Vec3 AirPhaseXYZ(Vec4 value){return {value[0],value[1],value[2]};}
}
AirStateBindingInput BindAirPhaseInput(AirPhaseOwners o)
{
    const auto& p=o.processed;const auto& f=o.physical;const auto g=f.settings.board.step.simulation.gravity_acceleration;
    AirStateBindingInput b{};b.vectors_400_416=p.vectors_400_416;b.vectors_464_480_496_512_528=p.vectors_464_480_496_512_528;
    b.vectors_544_560_592_608=p.vectors_544_560_592_608;b.prepared_jump_704=p.prepared_jump_704;b.jump_reference=o.post.jump_reference;
    b.flags_2468=p.flags_2468;b.flags_2472=p.flags_2472;b.flags_2476=p.flags_2476;b.state_2504=p.state_2504;b.category_2516=p.category_2516;
    b.state_variant_index_2528=p.state_variant_index_2528;b.jump_fix_frames=o.post.jump_fix_frames;b.external_physics_flags=p.external_physics_1616.flags;
    b.timestep_2604=p.timestep_2604;b.transition_2636=p.transition_2636;b.gravity_2648=p.gravity_2648;b.state_timer_2664=p.state_timer_2664;b.body_spin=o.animation_input.fields.body_spin;
    b.world_gravity={g.x,g.y,g.z,0};b.reckoning_system=f.riding.reckoning_frames.system;b.reckoning_inverse=f.riding.reckoning_frames.inverse_system;
    b.skeleton_local_centre_of_mass=f.board_frames.local_centre_of_mass;b.skeleton_local_board_position=f.board_frames.local_board_position;
    if (o.toolkit) b.toolkit_deck=o.toolkit->deck;
    b.trajectory_cone_x=o.trajectory.settings.cone_x;b.trajectory_cone_z=o.trajectory.settings.cone_z;return b;
}
SkeletonInputCollision AirPhaseCollisionInput(const PhysicalSimulationRuntime& f)
{return {f.collision_feedback.flags.compliant,f.collision_feedback.flags.has_impulse,f.collision_pose_error,f.skeleton_collision.partial_ragdoll,f.collision_feedback.drive_weight};}
WipeoutObservations AirPhaseWipeoutObservations(AirPhaseOwners o)
{
    auto& f=o.physical;
    return {o.processed,f.riding.ground,f.collision_feedback,f.DeckFrame(),f.board_frames.animation_target,f.roots.world_to_animation,
        f.collision_pose_error,f.collision_maximum_error,o.post.jump_fix_frames,o.air_reckoning.state,f.riding.reckoning_frames.system[1][1],
        o.trajectory.selector.GrindLockedToMiddle(),o.trajectory.selector.GrindNormal()};
}
bool AirPhaseRuntime::Enter(AirPhaseOwners o,std::string& error)
{
    const auto frame=BindPhysicsAirFrame(BindAirPhaseInput(o));auto& f=o.physical;
    o.life.skeleton_controller.flag_18=true;
    if (!o.life.skeleton_controller.Request(7,f.skeleton_collision,error)) return false;
    o.ik.EnableFeet(true);
    if (!o.life.skeleton_controller.Request(6,f.skeleton_collision,error)) return false;
    f.board.HookMut().drive.EnableAngularOnly(o.life.board_animated_290);
    o.footplant.enabled=false;o.footplant.Reset();state.selector_latch_174=false;state.reached_apex=false;
    state.trajectory_query_countdown=0;state.landing_normal={0,1,0,0};state.time_in_state=0;
    state.max_y=f.board.PartTransforms()[6].translation.y;state.start_y=frame.ground_position_y_500;
    bool use_com,heading;
    if (frame.previous_physics_category_2516==400||frame.previous_physics_state_2504==701)
    {use_com=(frame.flags_2468&0x4000)==0;heading=false;}
    else
    {const bool selected=frame.previous_physics_state_2504!=100&&frame.previous_physics_state_2504!=103&&frame.previous_physics_state_2504!=201;use_com=selected;heading=selected;}
    state.use_centre_of_mass_velocity=use_com;
    if (use_com)
    {
        auto velocity=frame.trajectory_velocity_608;AirMath math;
        if (frame.previous_physics_state_2504==500) velocity[1]=math.Minimum(velocity[1]*AirPhaseFloat(0x3f266666),3);
        if (frame.frames_since_jump_correction_2576<12) velocity=CalculateAirVelocityFromJump(frame,frame.frames_since_jump_correction_2576,math);
        state.centre_of_mass_trajectory={frame.trajectory_position_592,velocity,PhysicsAirHostComAcceleration(),-1};
    }
    if (heading) f.roots.initialize_heading=true;
    error.clear();return true;
}
void AirPhaseRuntime::Exit(AirReckoning& reckoning)
{state.use_centre_of_mass_velocity=false;reckoning.state.ResetSpin();}
bool AirPhaseRuntime::Advance(AirPhaseOwners o,std::string& error)
{
    const auto frame=BindPhysicsAirFrame(BindAirPhaseInput(o));auto& f=o.physical;auto& p=o.processed;
    if (!o.life.skeleton_controller.UpdateAir(p.flags_2472,frame.current_velocity_400[1],f.skeleton_collision,error)) return false;
    std::uint32_t countdown;std::memcpy(&countdown,&state.trajectory_query_countdown,4);--countdown;std::memcpy(&state.trajectory_query_countdown,&countdown,4);
    if (state.trajectory_query_countdown<=0&&(frame.flags_2468&0x8000)==0&&frame.previous_physics_state_2504!=0&&!o.trajectory.selector.Pending())
    {
        AirLaunchInfo info;if (!BindAirLaunchInfo(BindAirPhaseInput(o),info,error)) return false;
        if (frame.frames_since_jump_correction_2576<12)
        {AirMath math;info.start_velocity=CalculateAirVelocityFromJump(frame,frame.frames_since_jump_correction_2576,math);}
        else if (state.use_centre_of_mass_velocity)
        {
            const auto acceleration=PhysicsAirHostComAcceleration();const auto velocity=state.centre_of_mass_trajectory.velocity;
            for (std::size_t i=0;i<4;++i) info.start_velocity[i]=std::fma(acceleration[i],AirPhaseFloat(0x3c888889),velocity[i]);
            info.start_position_override=info.animation_com_position;info.start_position_override[1]+=AirPhaseFloat(0xbf266666);
            info.board_position_override=info.animation_com_position;info.board_position_override[1]+=AirPhaseFloat(0xbf4ccccd);
            info.use_position_override=true;info.trajectory_count=5;info.cone_angle_x*=AirPhaseFloat(0x3ecccccd);info.cone_angle_z*=AirPhaseFloat(0x3ecccccd);
        }
        info.player_jumped=false;AirSelectorInput input;
        if (!BindAirSelectorInput(BindAirPhaseInput(o),o.settings,input,error)) return false;
        bool launched;if (!o.trajectory.Launch(info,input,f.world,launched,error)) return false;
        state.trajectory_query_countdown=7;
    }
    AirSelectorInput input;if (!BindAirSelectorInput(BindAirPhaseInput(o),o.settings,input,error)) return false;
    if (!o.toolkit) {error="Air trajectory requires current board toolkit";return false;}
    const auto grind_context=AirTrajectoryGrindContext::FromProcessed(p,o.toolkit->deck[3]);bool valid;
    if (!o.trajectory.Update(input,f.world,grind_context,valid,error)) return false;
    const auto current=o.air_reckoning.Fields(f.riding).current_landing_normal_1152;
    const auto normal=o.trajectory.selector.SuggestedNormal().value_or(current);state.landing_normal=normal;const auto& settings=o.settings.state;
    float blend=WrapAirSignedAngle(AirAngleBetweenVectors(normal,current))<=settings.landing_normal_angle_limit_444?settings.landing_normal_blend_388:0;
    if (!state.use_centre_of_mass_velocity)
    {
        if (!state.selector_latch_174) state.selector_latch_174=o.trajectory.selector.AllPredictionsMissed();
        if (state.selector_latch_174)
        {state.use_centre_of_mass_velocity=true;state.centre_of_mass_trajectory={frame.trajectory_position_592,frame.trajectory_velocity_608,PhysicsAirHostComAcceleration(),-1};}
    }
    if (frame.state_timer_2664<=0) blend=0;
    else if (frame.flags_2468&0x4000) state.use_centre_of_mass_velocity=false;
    const auto spin=(frame.body_spin_input_2640*settings.body_spin_scale_428)*AirPhaseFloat(0x3c8efa35);
    const auto target_spin=settings.body_spin_over_time_320.Evaluate(state.time_in_state*2)*spin;PhysicsAirReckoningFields fields;
    if (!o.air_reckoning.Update(f.riding,p,o.animation_input.extra.physical_body_spin,normal,blend,target_spin,0,fields,error)) return false;
    const auto collision=AirPhaseCollisionInput(f);Mat4 target;
    if (state.use_centre_of_mass_velocity)
    {
        IntegrateAirTrajectoryFixedStep(state.centre_of_mass_trajectory);
        if (!UpdateKnownSkeletonAir(o.skeleton_input,o.skeleton_air,f.riding.reckoning_frames.system,state.centre_of_mass_trajectory.position,
            o.packet,p,o.SkeletonOwners(),o.packet.hierarchy,collision,target,error)) return false;
    }
    else if (!UpdateAnimatedSkeletonAir(o.skeleton_input,o.skeleton_air,f.riding.reckoning_frames.system,p,o.SkeletonOwners(),o.packet.hierarchy,collision,false,target,error)) return false;
    o.ground.steering.Update(0,o.settings.steering_blend,p.flags_2468,p.flags_2472);
    if (!o.toolkit) {error="Air collision requires the actual BoardToolkit";return false;}
    const auto& t=*o.toolkit;const auto ground_normal=f.riding.reckoning.ground_normal;
    const auto force=o.ground_runtime.CalculateCollisionForce({p.flags_2472,AirPhaseVector(p.collision_pose_error_736),AirPhaseVector(p.vectors_400_416[1]),
        t.travel_direction,AirPhaseVector(p.vectors_544_560_592_608[0]),{ground_normal.x,ground_normal.y,ground_normal.z,0},p.timestep_2604,t.total_mass});
    if (force) f.board.ForcesMut().Append({15,AirPhaseXYZ(force->force_2528),AirPhaseXYZ(force->point_2544)});
    else if (!state.use_centre_of_mass_velocity&&frame.frames_since_jump_correction_2576<12)
    {AirMath math;o.ground_runtime.SetAnimatedVelocity(f.board,CalculateAirVelocityFromJump(frame,frame.frames_since_jump_correction_2576,math));}
    f.correction.pending=true;const auto height=f.board.PartTransforms()[6].translation.y;
    if (!(state.max_y>height)) state.max_y=height;
    state.time_in_state+=frame.delta_time_2604;error.clear();return true;
}
void AirPhaseRuntime::UpdateApex(const BoardRuntime& board)
{if (!state.reached_apex&&board.Bodies()[6].rates.linear_velocity.y<0) state.reached_apex=true;}
bool AirPhaseRuntime::PostPhysics(AirPhaseOwners o,std::string& error)
{UpdateApex(o.physical.board);return o.wipeout.CheckAir(AirPhaseWipeoutObservations(o),false,error);}
void AirPhaseRuntime::Fill(AirOutputFields& physical) const
{
    const auto output=FillPhysicsAirOutput(state);
    for (std::size_t i=0;i<4;++i) std::memcpy(&physical.landing_normal_144[i],&output.landing_normal[i],4);
    physical.jump_height_200=output.jump_height;physical.reached_apex_436=output.is_at_apex;
    if (output.scalar_184_write) physical.scalar_184=*output.scalar_184_write;
}
}
