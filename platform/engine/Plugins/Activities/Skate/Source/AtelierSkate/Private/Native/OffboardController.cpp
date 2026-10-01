// SPDX-License-Identifier: Apache-2.0
#include "OffboardControllerMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
BipedControllerState::BipedControllerState(std::array<std::optional<BipedClipMetric>,3> metrics)
{
    std::array<float,3> speeds{};for(std::size_t n=0;n<3;++n)if(metrics[n])speeds[n]=(-1.0f/metrics[n]->end_time)*metrics[n]->translation_z;
    thresholds={biped_math::Bits(0x3c23d70a),(speeds[1]+speeds[0])*.5f,(speeds[2]+speeds[1])*.5f,biped_math::Bits(0x501502f9)};
}
void BipedControllerState::Reset()
{
    const auto retained=motion.correction_576;motion={};motion.correction_576=retained;
    intent={};surface={};contact={};special={};sliding={};frame_output={};position_368={};forward_delta_692=0;right_delta_696=0;velocity_override_remaining_772=-1;alternate_709=false;
}
void BipedControllerState::Place(BipedPlacementInput i)
{
    using namespace biped_math;
    const auto clear=[&]{motion.correction_576={};correction_target_592={};motion.correction_enabled_711=false;};
    if(i.current_state==500)
    {
        Reset();const auto delta=Sub(correction_target_592,i.previous_frame[3]);
        const auto eligible=i.previous_state==501&&!(Dot(i.frame[2],delta)<=0)&&!(Dot(i.frame[2],i.previous_frame[2])<=Bits(0x3f666666));
        if(eligible){const auto difference=Sub(i.previous_frame[3],correction_target_592);const auto amount=Dot(i.previous_frame[2],difference);motion.correction_576=Mul(i.previous_frame[2],amount);motion.correction_enabled_711=true;}
        else clear();
    }
    else if(i.current_state==501)clear();
    motion.frame_0=i.frame;motion.published_frame_64=i.frame;frame_output.frame=i.frame;position_368=i.body_position;
    motion.velocity_480=i.velocity;motion.speed_704=Length(i.velocity);surface.spring_normal=i.frame[1];surface.spring_delta={};
}
Mat4 BipedBuildSurfaceFrame(Vec4 up,Vec4 forward)
{
    using namespace biped_math;auto right=Cross(up,forward);const auto q=Dot(right,right),length=Root(q);
    if(!(length>Bits(0x37800000)))return SkeletonIdentity;
    auto inverse=ReciprocalEstimate(length);for(unsigned n=0;n<2;++n)inverse=std::fma(inverse,std::fma(-inverse,length,1.0f),inverse);
    right=Mul(right,inverse);up=Unit(up);forward=Unit(Cross(right,up));return {{right,up,forward,{0,0,0,0}}};
}
BipedGroundResult OffboardController::Output() const
{
    const auto& s=state;return {s.motion.published_frame_64,s.frame_output.frame,BipedBuildSurfaceFrame(s.surface.spring_normal,s.motion.frame_0[2]),s.frame_output.velocity,s.position_368,s.motion.angular_velocity_688,s.alternate_709,s.sliding.active_710};
}
namespace
{
bool SelectBipedAlternate(const BipedControllerState& s,const BipedGroundJob& j)
{
    const auto velocity=s.motion.velocity_480[1]>s.frame_output.velocity[1]?s.frame_output.velocity:s.motion.velocity_480;
    if(j.suppress_lean||(j.flags&2)==0)return false;
    const auto delta=biped_math::Sub(j.target_position,s.motion.frame_0[3]);if(Dot3(delta,delta)<=biped_math::Bits(0x3b23d70b))return false;
    const auto normal=biped_math::Cross(delta,s.motion.frame_0[0]);const auto square=Dot3(normal,normal),inverse=biped_math::Inverse(square),length=biped_math::Root(square);
    const auto unit=length>biped_math::Bits(0x358637bd)?biped_math::Mul(normal,inverse):Vec4{};return Dot3(velocity,unit)>4;
}
}
BipedGroundResult OffboardController::StepGround(const BipedGroundJob& j)
{
    using namespace biped_math;auto& s=state;const auto& c=settings;s.intent.speed=0;s.intent.steering=0;
    s.special.Update(j.movement,j.flags,s.motion.frame_0[2][1]);
    s.contact.Update({j.collision_displacements,s.surface.spring_normal,s.motion.frame_0[1]});
    s.sliding.Update({s.special.enabled_714,s.surface.source_normal,s.motion.velocity_480,s.contact.active?std::optional<Vec4>(s.contact.direction):std::nullopt},c.slide_vs_slope,c.slide_vs_speed);
    s.intent.Update(c.movement_intent,{j.flags,j.suppress_minimum,j.movement,j.steering,j.sprint_pressed,j.edge_active,j.ignore_obstacle,j.desired_direction,j.target_frame[2],j.target_frame[3],s.motion.frame_0[0],s.motion.frame_0[1],s.motion.frame_0[2],s.motion.frame_0[3],s.contact.active,s.contact.direction,s.sliding.active_710,s.sliding.velocity_528});
    s.alternate_709=SelectBipedAlternate(s,j);
    if(s.alternate_709)
    {
        const auto forward=s.motion.frame_0[2];s.motion.velocity_480=Madd({0,Bits(0xc11ccccd),0,0},Step(),s.motion.velocity_480);
        s.motion.speed_704=Root(Dot3(s.motion.velocity_480,s.motion.velocity_480));s.motion.frame_0[3]=Madd(s.motion.velocity_480,Step(),s.motion.frame_0[3]);
        s.frame_output.Update(forward,s.surface.final_up,s.surface.spring_normal,s.motion.frame_0[3]);return Output();
    }
    BipedVelocityState velocity{s.motion.velocity_480,s.motion.angular_velocity_688,s.forward_delta_692,s.right_delta_696,s.motion.speed_704,s.velocity_override_remaining_772};
    velocity.Update(c.movement_velocity,{s.motion.frame_0[2],s.motion.frame_0[0],s.surface.surface_normal,s.intent.speed,s.intent.steering,s.special.enabled_714,s.contact.active,s.contact.direction,j.requested_phase,j.override_duration,j.animation_velocity,j.flags});
    s.motion.velocity_480=velocity.velocity;s.motion.angular_velocity_688=velocity.turn;s.motion.speed_704=velocity.speed;s.forward_delta_692=velocity.forward_delta;s.right_delta_696=velocity.right_delta;s.velocity_override_remaining_772=velocity.override_remaining;
    s.surface.UpdateSurface({j.flags,j.contact_normal,j.contact_position,j.edge_position,j.edge_normal});
    s.surface.UpdateSpring({s.motion.velocity_480,s.motion.frame_0[1],s.motion.frame_0[0],s.motion.frame_0[2],s.frame_output.frame[0],s.frame_output.frame[2],s.right_delta_696,s.forward_delta_692,j.suppress_lean});
    UpdateBipedGroundMotion(s.motion,{j.contact_position,j.support_frame,j.target_position,j.target_normal,j.flags,j.support_id,j.animation_motion,j.animation_velocity,j.requested_duration,j.mirrored,j.animation_directed,j.target_frame_present,j.target_frame,s.frame_output.frame,s.contact.displacement,s.sliding.velocity_528,s.surface.surface_normal,s.correction_target_592,s.intent.edge_target,s.intent.edge_aligned});
    s.frame_output.Update(s.motion.frame_0[2],s.surface.final_up,s.surface.spring_normal,s.motion.frame_0[3]);
    UpdateBipedPosition(s.position_368,{s.motion.published_frame_64[3],s.correction_target_592,s.motion.correction_enabled_711,s.surface.spring_normal,j.flags,j.contact_position,j.target_position,s.frame_output.frame[3],j.animation_position});
    s.cadence.Update({XYZ(s.frame_output.velocity),XYZ(s.motion.predicted_support_velocity_272),XYZ(s.contact.direction),s.contact.active,XYZ(s.frame_output.frame[1]),{XYZ(s.motion.frame_0[0]),XYZ(s.motion.frame_0[1]),XYZ(s.motion.frame_0[2])},XYZ(s.motion.frame_0[3]),XYZ(j.animation_motion),j.requested_duration,j.requested_phase,j.edge_active,j.flags,XYZ(j.target_position)},s.thresholds);
    return Output();
}
}
