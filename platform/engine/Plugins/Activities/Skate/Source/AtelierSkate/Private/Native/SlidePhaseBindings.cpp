// SPDX-License-Identifier: Apache-2.0
#include "SlidePhaseRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 SlideRaw(const RawVector& words)
{Vec4 value;std::memcpy(value.data(),words.data(),sizeof(value));return value;}
Vec3 SlideXyz(Vec4 value){return {value[0],value[1],value[2]};}
class LiveSlideServices final:public SlideStateServices
{
    SlidePhaseOwners owners;
public:
    explicit LiveSlideServices(SlidePhaseOwners value):owners(value){}
    bool RequireCurrentSlideToolkit(std::string& error) override
    {
        if(!owners.toolkit){error="Slide requires current BoardToolkit";return false;}
        return true;
    }
    bool UpdateSlideReckoning(std::string&) override
    {
        const auto& p=owners.processed;auto& f=owners.physical;
        f.riding.UpdateSlideReckoning(*owners.toolkit,
            {SlideXyz(SlideRaw(p.animation_com_to_deck_752)),owners.animation_input.extra.physical_body_spin},
            p.flags_2468,owners.animation_input.fields.balance,(p.flags_2476&0x40000000)!=0,
            {SlideXyz(SlideRaw(p.vectors_464_480_496_512_528[0])),
             SlideXyz(SlideRaw(p.vectors_464_480_496_512_528[4])),p.scalar_2652,
             owners.toolkit->absolute_speed,static_cast<std::int32_t>(p.wheel_count_2556)});
        return true;
    }
    bool UpdateSlideSkeletonGround(std::string& error) override
    {
        auto& f=owners.physical;
        const SkeletonInputCollision collision{f.collision_feedback.flags.compliant,
            f.collision_feedback.flags.has_impulse,f.collision_pose_error,
            f.skeleton_collision.partial_ragdoll,f.collision_feedback.drive_weight};
        Mat4 target;
        if(!owners.skeleton_input.UpdateGround(f.riding.reckoning_frames.system,owners.processed,
            {f,owners.animated,owners.ik,owners.animation_input},owners.packet.hierarchy,
            collision,target,error))return false;
        owners.skeleton_air.CapturePhysicsError(f.board,target);
        return true;
    }
    bool CaptureSlidePhysicsError(std::string&) override
    {
        //82D3A924 repeats the capture that input_phase::update_ground completed.
        // The actual unblended target is retained by the shared board frames.
        owners.skeleton_air.CapturePhysicsError(owners.physical.board,
            owners.physical.board_frames.animation_target);
        return true;
    }
    std::optional<SlideCompletedFrame> ReadCompletedSlideFrame(std::string&) override
    {
        const auto& p=owners.processed;const auto& t=*owners.toolkit;
        return SlideCompletedFrame{p.surface_mode_2540,p.state_variant_index_2528,p.flags_2468,
            p.flags_2472,p.wheel_count_2556,
            {SlideRaw(p.vectors_400_416[0]),SlideRaw(p.vectors_464_480_496_512_528[0]),
             t.deck[0],t.effective[2],t.forward,SlideRaw(p.vectors_720_784_800_816_832_864[0]),
             t.absolute_speed,p.scalar_2656,owners.animation_input.fields.slide,
             p.state_timer_2664,p.scalar_2764},
            SlideRaw(p.vectors_544_560_592_608[0]),SlideRaw(p.collision_pose_error_736),
            SlideRaw(p.vectors_400_416[1]),t.travel_direction,
            owners.physical.riding.reckoning.ground_normal,t.total_mass,p.gravity_2648,
            p.scalar_2652,p.timestep_2604};
    }
    std::optional<SlideGroundInputs> PrepareSlideGroundInput(std::uint32_t index,std::string& error) override
    {
        GroundPumpingMode mode;
        if(!owners.ground.pumping_settings.Mode(index,mode,error))return std::nullopt;
        const auto edge=owners.life.edge.value_or(GroundPhaseEdge{0,{},{},{}});
        const auto& p=owners.processed;const auto& s=owners.ground_settings;
        const auto input=PrepareGroundBoardInput(s,*owners.toolkit,p,
            owners.animation_input.fields,owners.animation_input.contacts,owners.ground.pumping,
            mode.unintentional_scalar,owners.physical.riding,owners.animated.board_at_y_delta,
            owners.physical.settings.board.step.base_truck_transforms,
            {owners.life.manual_drag_2724,p.external_physics_1616.flags,edge.flags,edge.point});
        const auto& f=input.ground_force;
        return SlideGroundInputs{input.steering,input.manual,input.contact,
            {f.argument_1_2752,f.ground_scalar_1216,f.ground_scalar_1240,f.ground_scalar_1236,
             f.balance_2720,f.surface_speed_2656,f.axis_384,f.velocity_400,f.axis_544},
            s.steering,s.manual,s.manual_mode,s.force,owners.ground_runtime.wall_ride};
    }
    bool CalculateSlideCollisionForce(RidingCollisionPhysical physical,
        std::optional<SlideCollisionForce>& applied,std::string&) override
    {
        const auto force=owners.ground_runtime.CalculateCollisionForce(physical);
        if(force)applied=SlideCollisionForce{force->force_2528,force->point_2544,force->vector_2592};
        else applied.reset();
        return true;
    }
    bool LaunchSlideTrajectory(Vec4 velocity,std::string& error) override
    {
        AirLaunchInfo launch;
        if(!BindAirLaunchInfo(BindSlidePhaseTrajectoryInput(owners),launch,error))return false;
        launch.start_velocity=velocity;launch.player_jumped=true;
        AirSelectorInput input;
        if(!BindAirSelectorInput(BindSlidePhaseTrajectoryInput(owners),owners.air_settings,input,error))return false;
        bool launched;
        if(!owners.trajectory.Launch(launch,input,owners.physical.world,launched,error))return false;
        if(!owners.toolkit){error="Slide trajectory requires current board toolkit";return false;}
        const auto context=AirTrajectoryGrindContext::FromProcessed(owners.processed,owners.toolkit->deck[3]);
        bool valid;
        return owners.trajectory.Update(input,owners.physical.world,context,valid,error);
    }
};
}
AirStateBindingInput BindSlidePhaseTrajectoryInput(SlidePhaseOwners o)
{
    const auto& p=o.processed;const auto& f=o.physical;AirStateBindingInput input{};
    input.vectors_400_416=p.vectors_400_416;input.vectors_464_480_496_512_528=p.vectors_464_480_496_512_528;
    input.vectors_544_560_592_608=p.vectors_544_560_592_608;input.prepared_jump_704=p.prepared_jump_704;
    input.flags_2468=p.flags_2468;input.flags_2472=p.flags_2472;input.flags_2476=p.flags_2476;
    input.state_2504=p.state_2504;input.state_variant_index_2528=p.state_variant_index_2528;
    input.external_physics_flags=p.external_physics_1616.flags;input.transition_2636=p.transition_2636;
    input.timestep_2604=p.timestep_2604;
    const auto gravity=f.settings.board.step.simulation.gravity_acceleration;
    input.world_gravity={gravity.x,gravity.y,gravity.z,0};
    input.reckoning_system=f.riding.reckoning_frames.system;
    input.reckoning_inverse=f.riding.reckoning_frames.inverse_system;
    input.skeleton_local_centre_of_mass=f.board_frames.local_centre_of_mass;
    input.skeleton_local_board_position=f.board_frames.local_board_position;
    if(o.toolkit)input.toolkit_deck=o.toolkit->deck;
    input.trajectory_cone_x=o.trajectory.settings.cone_x;
    input.trajectory_cone_z=o.trajectory.settings.cone_z;
    return input;
}
bool AdvanceSlidePhase(SlideState& state,const SlideStateSettings& settings,
    SlidePhaseOwners owners,std::string& error)
{
    LiveSlideServices services(owners);
    return UpdateSlideState(state,settings,
        {owners.physical.board,owners.ground.manual,owners.ground.steering,
         owners.physical.settings.board.collision.wheel_material},services,error);
}
}
