// SPDX-License-Identifier: Apache-2.0
#include "AirStateRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t word) {float f;std::memcpy(&f,&word,4);return f;}
bool Launch(const PhysicsAirState& state,const PhysicsAirFrame& frame,Vec4 acceleration,PhysicsAirRuntime& runtime,std::string& error)
{
    std::unique_ptr<PhysicsAirLaunchInfo> info;
    if (!runtime.ConstructTrajectoryLaunchInfo(info,error)) return false;
    if (!info) {error="PhysicsAir requires constructed trajectory launch info";return false;}
    if (!runtime.FillSkeletonLaunchInfo(*info,error)) return false;
    if (frame.frames_since_jump_correction_2576<12)
        info->SetStartVelocity(CalculateAirVelocityFromJump(frame,frame.frames_since_jump_correction_2576,runtime));
    else if (state.use_centre_of_mass_velocity)
    {
        if (!runtime.FillSkeletonLaunchInfo(*info,error)) return false;
        Vec4 velocity;for (std::size_t i=0;i<4;++i) velocity[i]=std::fma(acceleration[i],Word(0x3c888889),state.centre_of_mass_trajectory.velocity[i]);
        info->SetStartVelocity(velocity);info->SetPlayerJumped(true);
        const auto position=info->CentreOfMassAnimationPosition();Vec4 trajectory,board;
        const Vec4 trajectory_offset{0,Word(0xbf266666),0,0},board_offset{0,Word(0xbf4ccccd),0,0};
        for (std::size_t i=0;i<4;++i) {trajectory[i]=position[i]+trajectory_offset[i];board[i]=position[i]+board_offset[i];}
        info->SetTrajectoryStartPositionOverride(trajectory);info->SetBoardPositionOverride(board);
        info->SetUseTrajectoryStartPositionOverride(true);info->SetTrajectoryCount(5);
        auto angles=info->ConeAngles();for (auto& a:angles) a*=Word(0x3ecccccd);info->SetConeAngles(angles);
    }
    info->SetPlayerJumped(false);return runtime.LaunchTrajectory(*info,error);
}
}
Vec4 CalculateAirVelocityFromJump(const PhysicsAirFrame& f,std::int32_t frames,PhysicsAirMath& math)
{
    const float seconds=f.delta_time_2604*static_cast<float>(frames),gravity=seconds*f.gravity_y_2648;
    auto predicted=f.jump_velocity_848;predicted[0]+=0;predicted[1]+=gravity;predicted[2]+=0;predicted[3]+=0;
    Vec4 error;for (std::size_t i=0;i<4;++i) error[i]=f.current_velocity_400[i]-predicted[i];auto output=predicted;
    if (!(error[1]>Word(0xc0400000))) output[1]=f.current_velocity_400[1];
    error[1]=0;
    if (!(math.LengthSquared(error)<Word(0x41100000)))
    {
        auto horizontal=output;horizontal[1]=0;const float maximum=math.Length(horizontal);
        auto current=f.current_velocity_400;current[1]=0;const auto clamped=math.ClampLength(current,maximum);
        output[0]=clamped[0];output[2]=clamped[2];
    }
    return output;
}
float WrapAirSignedAngle(float angle)
{
    const float turns=angle*Word(0x3e22f983),fraction=turns-std::floor(turns);
    const float signed_fraction=fraction>Word(0x3f000000)?fraction-1:fraction;
    return signed_fraction*Word(0x40c90fdb);
}
void IntegrateAirTrajectoryFixedStep(AirTrajectory& t)
{
    const float step=Word(0x3c888889),squared=step*step,half=1.0f*Word(0x3f000000);Vec4 position,velocity;
    for (std::size_t i=0;i<4;++i)
    {
        const float linear=std::fma(t.velocity[i],step,t.position[i]),acceleration=t.acceleration[i]*half;
        velocity[i]=std::fma(t.acceleration[i],step,t.velocity[i]);position[i]=std::fma(acceleration,squared,linear);
    }
    t.position=position;t.velocity=velocity;
}
bool EnterPhysicsAir(PhysicsAirState& s,const PhysicsAirFrame& f,Vec4 acceleration,PhysicsAirRuntime& r,std::string& error)
{
    error.clear();
    if (!r.SetAirCollisionUpdateEnabled(true,error)||!r.SetSkeletonCollisionState(7,error)||!r.SetSkeletonInverseKinematicsEnabled(true,error)||
        !r.SetSkeletonCollisionState(6,error)||!r.EnableBoardAngularDriveOnly(error)||!r.SetFootplantFlag240(false,error)||!r.ResetFootplants(error)) return false;
    s.selector_latch_174=false;s.reached_apex=false;s.trajectory_query_countdown=0;s.landing_normal={0,1,0,0};s.time_in_state=0;
    s.max_y=r.BoardTransformHeight();s.start_y=f.ground_position_y_500;
    bool selected,heading;
    if (f.previous_physics_category_2516==400||f.previous_physics_state_2504==701) {selected=(f.flags_2468&0x4000)==0;heading=false;}
    else {selected=f.previous_physics_state_2504!=100&&f.previous_physics_state_2504!=103&&f.previous_physics_state_2504!=201;heading=selected;}
    s.use_centre_of_mass_velocity=selected;
    if (selected)
    {
        auto velocity=f.trajectory_velocity_608;
        if (f.previous_physics_state_2504==500) velocity[1]=r.Minimum(velocity[1]*Word(0x3f266666),Word(0x40400000));
        if (f.frames_since_jump_correction_2576<12) velocity=CalculateAirVelocityFromJump(f,f.frames_since_jump_correction_2576,r);
        s.centre_of_mass_trajectory={f.trajectory_position_592,velocity,acceleration,-1};
    }
    return !heading||r.RequestSkeletonHeadingUpdate(error);
}
void ExitPhysicsAir(PhysicsAirState& state,PhysicsAirReckoningFields& reckoning)
{state.use_centre_of_mass_velocity=false;reckoning.body_spin_speed_1572=0;reckoning.body_spin_angle_1568=0;}
PhysicsAirOutput FillPhysicsAirOutput(const PhysicsAirState& s)
{return {s.reached_apex,s.max_y-s.start_y,s.landing_normal,s.selector_latch_174?std::optional<float>(4):std::nullopt};}
bool UpdatePhysicsAirBoard(const PhysicsAirState& s,const PhysicsAirFrame& f,const PhysicsAirReckoningFields& reckoning,PhysicsAirRuntime& r,std::string& error)
{
    error.clear();if (!r.UpdateBoardSteeringTilt(0,error)) return false;
    AirBoardForce force{};bool created;
    if (!r.CalculateAirCollisionForce(reckoning.collision_reference_normal_1216,force,created,error)) return false;
    if (created) return r.EnqueueBoardForce(15,force,error);
    if (!s.use_centre_of_mass_velocity&&f.frames_since_jump_correction_2576<12)
        return r.SetBoardVelocity(CalculateAirVelocityFromJump(f,f.frames_since_jump_correction_2576,r),error);
    return true;
}
bool UpdatePhysicsAir(PhysicsAirState& s,const PhysicsAirFrame& f,const PhysicsAirSettings& settings,PhysicsAirReckoningFields& reckoning,Vec4 acceleration,PhysicsAirRuntime& r,std::string& error)
{
    error.clear();if (!r.UpdateAirCollision(error)) return false;
    std::uint32_t countdown;std::memcpy(&countdown,&s.trajectory_query_countdown,4);--countdown;std::memcpy(&s.trajectory_query_countdown,&countdown,4);
    if (s.trajectory_query_countdown<=0&&(f.flags_2468&0x8000)==0&&f.previous_physics_state_2504!=0&&!r.TrajectoryQueryJustStarted())
    {if (!Launch(s,f,acceleration,r,error)) return false;s.trajectory_query_countdown=7;}
    if (!r.UpdateTrajectorySelector(error)) return false;
    const auto current=reckoning.current_landing_normal_1152,normal=r.SelectorLandingNormal().value_or(current);s.landing_normal=normal;
    const float angle=WrapAirSignedAngle(r.AngleBetweenVectors(normal,current));
    float blend=angle<=settings.landing_normal_angle_limit_444?settings.landing_normal_blend_388:0;
    if (!s.use_centre_of_mass_velocity)
    {
        if (!s.selector_latch_174) s.selector_latch_174=r.SelectorCentreOfMassTrajectoryReady();
        if (s.selector_latch_174) {s.use_centre_of_mass_velocity=true;s.centre_of_mass_trajectory={f.trajectory_position_592,f.trajectory_velocity_608,acceleration,-1};}
    }
    if (f.state_timer_2664<=0) blend=0;
    else if ((f.flags_2468&0x4000)!=0) s.use_centre_of_mass_velocity=false;
    const float scaled=f.body_spin_input_2640*settings.body_spin_scale_428,spin=scaled*Word(0x3c8efa35);
    const float curve=settings.body_spin_over_time_320.Evaluate(s.time_in_state*Word(0x40000000)),target=curve*spin;
    PhysicsAirReckoningFields completed;
    if (!r.UpdateReckoningAirStates(normal,blend,target,0,completed,error)) return false;
    reckoning=completed;
    if (s.use_centre_of_mass_velocity)
    {IntegrateAirTrajectoryFixedStep(s.centre_of_mass_trajectory);if (!r.UpdateKnownAirSkeleton(s.centre_of_mass_trajectory.position,error)) return false;}
    else if (!r.UpdateAnimatedSkateboardSkeleton(false,error)) return false;
    if (!UpdatePhysicsAirBoard(s,f,reckoning,r,error)||!r.EnableSkateboardErrorOnSkeleton(error)) return false;
    const float height=r.BoardTransformHeight();if (!(s.max_y>height)) s.max_y=height;s.time_in_state+=f.delta_time_2604;return true;
}
bool UpdatePhysicsAirPost(PhysicsAirState& s,PhysicsAirRuntime& r,std::string& error)
{
    error.clear();if (!s.reached_apex&&r.BoardBodyVelocity()[1]<0) s.reached_apex=true;
    return r.CheckForAirWipeout(false,error);
}
}
