// SPDX-License-Identifier: Apache-2.0
#include "SlideStateRuntime.h"
#include "DeckAngularCorrections.h"
#include "RidingAngles.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec3 Three(Vec4 v) {return {v[0],v[1],v[2]};}
class Angle final:public ManualAngleMeasurement
{
    bool AngleBetween(Vec4 a,Vec4 b,Vec4 c,float& output,std::string&) override {output=RidingSignedAngle(Three(a),Three(b),Three(c));return true;}
};
QueuedPointForce PointForce(std::uint32_t tag,const std::array<float,8>& force) {return {tag,{force[0],force[1],force[2]},{force[4],force[5],force[6]}};}
float Fsel(float test,float positive,float negative) {return test>=-0.0f?positive:negative;}
}
void EnterSlideState(SlideState& state,BoardRuntime& board,SlideLifecycleTargets t,std::uint32_t category,float speed)
{
    t.skeleton_elapsed_16505=true;t.air_spin_angle=0;t.air_spin_speed=0;board.HookMut().drive.DisableAnimation(t.board_animated_290);board.BodiesMut()[6].rates.angular_velocity={};
    for (auto& body:board.BodiesMut()) body.inertia.linear_drag=0;
    if (category!=100) t.manual.Reset();if (t.wipeout_mode!=1) {t.wipeout_balance=0;t.wipeout_mode=1;}state.Enter(speed);
}
void ExitSlideState(SlideState& state,ContactMaterial& material,const ContactMaterial& standard) {state.Exit();material=standard;}
bool UpdateSlideState(SlideState& state,const SlideStateSettings& configuration,SlideRuntimeTargets t,SlideStateServices& services,std::string& error)
{
    if (!services.RequireCurrentSlideToolkit(error)||!services.UpdateSlideReckoning(error)||!services.UpdateSlideSkeletonGround(error)||!services.CaptureSlidePhysicsError(error)) return false;
    const auto completed=services.ReadCompletedSlideFrame(error);if (!completed) return false;const auto& p=*completed;const SlideSurfaceProfile* selected=nullptr;if (!configuration.Surface(p.surface_mode,selected,error)) return false;t.wheel_material=selected->material;
    auto prepared=services.PrepareSlideGroundInput(p.pumping_mode,error);if (!prepared) return false;auto& input=*prepared;
    const auto tilt=CalculateSteeringTilt(input.steering_settings,input.steering,&state.steering_push,&state.damped_turn);t.steering.Update(tilt,input.steering_settings.tilt_blending,p.flags_2468,p.flags_2472);
    input.manual.powersliding=true;Angle geometry;ManualError manual_error;const auto manual=CalculateManual(t.manual,input.manual_settings,input.manual_mode,input.manual,geometry,manual_error);
    if (!manual) {error=manual_error.kind==ManualError::Kind::Angle?"Slide manual controller: Angle(IntegerConversionUnavailable)":"Slide manual controller: unexpected measurement failure";return false;}
    auto contact=input.contact;contact.scalar_2756=0;const auto response=CalculateWallRideResponse(input.wall_settings,{p.slide.normal,p.up,p.slide.velocity,p.total_mass,p.gravity,p.scalar_2652,std::int32_t(p.wheel_count)},contact,{});state.wall_riding=response.active_2731;
    if (response.animated_board_2708)
    {
        for (auto& body:t.board.BodiesMut()) body.rates.linear_velocity=Three(response.vector_2688);for (auto& body:t.board.BodiesMut()) body.inertia.linear_drag=0;
        return services.LaunchSlideTrajectory(response.vector_2688,error);
    }
    const auto displacement=CalculateSlideAngularCorrection(configuration.settings,selected->surface,p.slide);ApplyDeckAngularDisplacement(t.board.BodiesMut()[6].rates,Three(displacement));auto manual_displacement=manual->angular_displacement;for (auto& value:manual_displacement) value*=configuration.manual_scalar;ApplyDeckAngularDisplacement(t.board.BodiesMut()[6].rates,Three(manual_displacement));
    const auto& f=input.force;const auto balance=f.balance_2720,front_factor=balance>0?0:Fsel(balance,1,2),rear_factor=Fsel(balance,balance>0?2:1,0);
    const auto front=CalculateGroundForce(input.force_settings,{f.argument_1_2752,f.ground_scalar_1216,0,front_factor,balance,f.surface_speed_2656,f.axis_384,f.velocity_400,f.axis_544});
    const auto rear=CalculateGroundForce(input.force_settings,{f.argument_1_2752,-f.ground_scalar_1240,f.ground_scalar_1236*0.0f,rear_factor,balance,f.surface_speed_2656,f.axis_384,f.velocity_400,f.axis_544});
    const auto sliding=CalculateSlidingForce(configuration.settings,selected->surface,p.slide);std::optional<SlideCollisionForce> collision;
    if (!services.CalculateSlideCollisionForce({p.flags_2472,p.collision_displacement,p.collision_velocity,p.travel_direction,p.up,{p.ground_normal.x,p.ground_normal.y,p.ground_normal.z,0},p.processed_timestep,p.total_mass},collision,error)) return false;
    auto& queue=t.board.ForcesMut();if (collision) queue.Append({15,Three(collision->force_2528),Three(collision->point_2544)});else {queue.Append(PointForce(4,front));queue.Append(PointForce(5,rear));queue.Append(response.tag_16_force);queue.Append(sliding);}error.clear();return true;
}
}
