#include "GroundBoard.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
bool Service(GroundBoardStage stage,bool succeeded,GroundBoardError& error)
{
    if (!succeeded) {error.kind=GroundBoardError::Kind::Service;error.stage=stage;}
    return succeeded;
}
QueuedPointForce ForceRecord(std::uint32_t tag,const std::array<float,8>& value)
{return {tag,{value[0],value[1],value[2]},{value[4],value[5],value[6]}};}
Vec4 Vector4(Vec3 value) {return {value.x,value.y,value.z,0};}
std::array<std::array<float,8>,2> GroundForces(const GroundForceSettings& settings,const GroundForceFrame& frame)
{
    float side=0;
    if (frame.processed_2776==0||frame.processed_2780<0)
    {
        const float value=frame.ground_scalar_1232*frame.previous_state_scalar_56;
        side=-value>=0?0:value;
    }
    const auto common=[&](float z,float third,float fourth)
    {return GroundForceInput{frame.argument_1_2752,z,third,fourth,frame.balance_2720,frame.surface_speed_2656,frame.axis_384,frame.velocity_400,frame.axis_544};};
    const float balance=frame.balance_2720;
    const float first=balance<=0?(balance>=-0.0f?1:2):0;
    const float nonnegative=balance<=0?1:2;
    const float second=balance>=-0.0f?nonnegative:0;
    return {CalculateGroundForce(settings,common(frame.ground_scalar_1216,side,first)),
        CalculateGroundForce(settings,common(-frame.ground_scalar_1240,frame.ground_scalar_1236*side,second))};
}
bool BodyVectors(PhysicsGroundState& state,float collision_scale,float timestep,Vec4 straighten,
    Vec4 heading,Vec4 anti_flip,Vec4 manual,GroundBoardServices& services,GroundBoardError& error)
{
    if (state.collision_countdown_2652>0)
    {
        state.collision_countdown_2652-=timestep;
        for (auto& lane:state.vector_2592) lane*=collision_scale;
        if (!Service(GroundBoardStage::ApplyCollisionDecay,services.ApplyVector(state.vector_2592,error.source),error)) return false;
    }
    if (!Service(GroundBoardStage::ApplyStraighten,services.ApplyVector(straighten,error.source),error)) return false;
    if (!Service(GroundBoardStage::ApplyHeading,services.ApplyVector(heading,error.source),error)) return false;
    if (!Service(GroundBoardStage::ApplyAntiFlip,services.ApplyAngularDisplacement(anti_flip,error.source),error)) return false;
    return Service(GroundBoardStage::ApplyManual,services.ApplyAngularDisplacement(manual,error.source),error);
}
std::optional<GroundBoardOutcome> Animated(PhysicsGroundState& state,GroundBoardComponents components,
    GroundBoardServices& services,GroundBoardError& error)
{
    if (!Service(GroundBoardStage::SetAnimatedVelocity,services.SetAnimatedVelocity(state.vector_2688,error.source),error)) return std::nullopt;
    if (!Service(GroundBoardStage::WriteProcessedVelocity,services.WriteProcessedVelocity(state.vector_2688,error.source),error)) return std::nullopt;
    if (!components.inertias.SetLinearDrag(0,std::nullopt,error.drag)) {error.kind=GroundBoardError::Kind::Drag;return std::nullopt;}
    GroundLaunchInfo pose;
    if (!Service(GroundBoardStage::BuildAnimatedPose,services.BuildAnimatedPose(pose,error.source),error)) return std::nullopt;
    if (!Service(GroundBoardStage::PublishAnimatedPose,services.PublishAnimatedPose(pose,error.source),error)) return std::nullopt;
    if (!Service(GroundBoardStage::UpdateExternalPlayer,services.UpdateExternalPlayer(pose,state.vector_2688,error.source),error)) return std::nullopt;
    if (!Service(GroundBoardStage::CommitExternalPlayer,services.CommitExternalPlayer(error.source),error)) return std::nullopt;
    if (!Service(GroundBoardStage::FinalizeAnimatedBoard,services.FinalizeAnimatedBoard(error.source),error)) return std::nullopt;
    state.flag_2720=true;
    return GroundBoardOutcome{GroundBoardOutcome::Kind::Animated};
}
std::optional<OrdinaryGroundResult> Ordinary(PhysicsGroundState& state,GroundBoardComponents c,
    GroundBoardSettings s,GroundBoardInput i,QueuedPointForce contact_force,GroundBoardServices& services,GroundBoardError& error)
{
    std::uint8_t suppressed=0;
    const auto propulsion=CalculateGroundPropulsion(i.propulsion,s.propulsion,suppressed);
    state.push_suppressed_2730=suppressed!=0;
    const auto ground=GroundForces(s.ground_force,i.ground_force);
    i.speed_model.manual_state_276=c.manual.angular_correction;
    const auto speed_force=UpdateSpeedModel(c.speed_model,s.speed_model,i.speed_model);
    i.slide_friction.heading_time=state.elapsed_2648;
    const auto slide_force=CalculateSlideFriction(s.slide_friction,i.slide_friction);
    const auto pump_force=CalculatePumpForce(i.pump_force);
    i.straighten.heading_time=state.elapsed_2648;
    auto straighten=CalculateStraighten(s.straighten,i.straighten);
    for (auto& lane:straighten) lane*=state.straighten_scale_2672;
    const auto heading=CalculateHeading(s.heading,i.heading,c.heading_previous);
    const auto anti_flip=CalculateAntiFlip(s.anti_flip,i.anti_flip);
    state.anti_flip_torque_2624=anti_flip;
    i.manual.powersliding=false;
    const auto manual=CalculateManual(c.manual,s.manual,s.manual_mode,i.manual,services,error.manual);
    if (!manual) {error.kind=GroundBoardError::Kind::Manual;return std::nullopt;}
    state.manual_correction_2732=manual->correction_active;
    state.manual_opposition_2733=manual->opposing_motion_without_correction;
    const float drag=i.ground_drag.Calculate(s.linear_drag);
    bool terminal=false;
    if (manual->correction_active) terminal=propulsion.Submit(*manual,c.force_queue).appended[0];
    else
    {
        const auto push=Vector4(propulsion.push.vector);float squared;
        if (!Service(GroundBoardStage::PushForceSquared,services.GroundDot3(push,push,squared,error.source),error)) return std::nullopt;
        if (squared>1) state.flag_2721=true;
        AntiFlipNudgeResult nudge;
        if (!Service(GroundBoardStage::AntiFlipNudge,UpdateAntiFlipNudge(state,i.anti_flip_nudge,c.force_queue,services,nudge,error.source),error)) return std::nullopt;
        if (i.contact_time_2756<s.ground_force_contact_time_limit)
        {
            c.force_queue.Append(ForceRecord(4,ground[0]));
            c.force_queue.Append(ForceRecord(5,ground[1]));
        }
        propulsion.Submit(*manual,c.force_queue);
        if (!BodyVectors(state,s.collision_response_scale,i.propulsion.timestep,straighten,heading,anti_flip,manual->angular_displacement,services,error)) return std::nullopt;
        if ((i.trajectory_state_1776_bits&0x80000000)==0) c.force_queue.Append(ForceRecord(6,speed_force));
        c.force_queue.Append(ForceRecord(1,slide_force));
        c.force_queue.Append(ForceRecord(8,pump_force));
        contact_force.tag=16;
        terminal=c.force_queue.Append(contact_force);
    }
    if (!c.inertias.ApplyGroundDrag(drag,error.drag)) {error.kind=GroundBoardError::Kind::Drag;return std::nullopt;}
    const auto brake=propulsion.braking.force_world,push=propulsion.push.vector;
    const Vec4 combined{(push.x+brake.x)+pump_force[0],(push.y+brake.y)+pump_force[1],(push.z+brake.z)+pump_force[2],pump_force[3]};
    float squared;
    if (!Service(GroundBoardStage::StrongForceSquared,services.GroundDot3(combined,combined,squared,error.source),error)) return std::nullopt;
    const bool reset=squared>s.speed_model_reset_force_squared;
    if (reset) c.speed_model.flags_1360|=0x80000000;
    if (!Service(GroundBoardStage::HangUps,ManageHangUps(state,i.hang_up,services,error.source),error)) return std::nullopt;
    bool caught;
    if (!Service(GroundBoardStage::HalfpipeWheelCatch,ManageHalfpipeWheelCatches(i.halfpipe_wheel_catch,services,caught,error.source),error)) return std::nullopt;
    if (!Service(GroundBoardStage::Pinning,ConsiderGroundPinning(state,i.pinning,services,error.source),error)) return std::nullopt;
    return OrdinaryGroundResult{manual->correction_active,manual->correction_active?7u:16u,terminal,reset};
}
}
QueuedPointForce GroundBoardCollisionResponse::TaggedForce() const
{return {15,{force_2528[0],force_2528[1],force_2528[2]},{point_2544[0],point_2544[1],point_2544[2]}};}
std::optional<GroundBoardOutcome> UpdateGroundBoard(PhysicsGroundState& state,GroundBoardComponents c,
    GroundBoardSettings s,GroundBoardInput i,GroundBoardServices& services,GroundBoardError& error)
{
    const float tilt=CalculateSteeringTilt(s.steering,i.steering,&state.steering_push_scalar_2640,&state.steering_damped_turn_2644);
    i.speed_wobble.tilt=tilt;
    if (!Service(GroundBoardStage::CenterOfMassHeight,services.CenterOfMassHeight(i.speed_wobble.center_of_mass_height,error.source),error)) return std::nullopt;
    const float wobble=CalculateSpeedWobble(c.speed_wobble,s.speed_wobble,i.speed_wobble);
    c.truck_steering.Update(wobble,s.steering.tilt_blending,i.truck_flags_2468,i.truck_flags_2472);
    if (!Service(GroundBoardStage::SetWheelMaterials,services.SetContactWheelMaterials(error.source),error)) return std::nullopt;
    GroundBoardContactResponse contact;
    if (!Service(GroundBoardStage::ContactResponse,services.ContactResponse(i.contact,state.vector_2688,contact,error.source),error)) return std::nullopt;
    state.flag_2731=contact.active_2731;
    state.vector_2688=contact.vector_2688;
    state.scalar_2704=contact.scalar_2704;
    state.flag_2708=contact.animated_board_2708;
    state.flag_2720=false;
    if (!Service(GroundBoardStage::UpdateBodyAccumulator,services.UpdateBodyAccumulator(error.source),error)) return std::nullopt;
    if (state.flag_2708) return Animated(state,c,services,error);
    std::optional<GroundBoardCollisionResponse> collision;
    if (!Service(GroundBoardStage::CollisionForce,services.CollisionForce(i.ground_vector_1216,collision,error.source),error)) return std::nullopt;
    if (collision)
    {
        state.collision_force_2528=collision->force_2528;
        state.collision_point_2544=collision->point_2544;
        state.vector_2592=collision->vector_2592;
        state.collision_countdown_2652=s.collision_response_duration;
        if (!Service(GroundBoardStage::ApplyCollisionVector,services.ApplyVector(collision->vector_2592,error.source),error)) return std::nullopt;
        c.speed_model.flags_1360|=0x80000000;
        const bool queued=c.force_queue.Append(collision->TaggedForce());float projection;
        if (!Service(GroundBoardStage::CollisionProjection,services.CollisionForceDotVelocity(collision->force_2528,i.ground_force.velocity_400,projection,error.source),error)) return std::nullopt;
        state.flag_2722=projection<-0.75f;
        GroundBoardOutcome result{GroundBoardOutcome::Kind::Collision};result.tag_15_queued=queued;return result;
    }
    const auto ordinary=Ordinary(state,c,s,i,contact.tag_16_force,services,error);
    if (!ordinary) return std::nullopt;
    GroundBoardOutcome result{GroundBoardOutcome::Kind::Ordinary};result.ordinary=*ordinary;return result;
}
}
