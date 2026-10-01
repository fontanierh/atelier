// SPDX-License-Identifier: Apache-2.0
#include "WipeoutPhysicalRuntime.h"
#include "WipeoutControls.h"
#include "WipeoutPhysicalMath.h"
#include "GroundCorrections.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
bool WipeoutPhysicalRuntime::Advance(WipeoutPhysicalOwners o,std::string& error)
{
    auto& physical=o.physical;auto& body=physical.skeleton;const auto& p=o.input.processed;
    const bool actual_contact=physical.collision_feedback.flags.any||state.below_surface;state.airborne_frames=actual_contact?-1:Increment(state.airborne_frames);
    if(!state.special_surface&&(p.flags_2488&0x40000000)){
        state.special_surface=true;state.surface_height=p.collision_scalar_2924;
        if(!ragdoll.Request(o.life.skeleton_controller,10,body,physical.skeleton_joints,physical.skeleton_collision,error))return false;
    }
    const auto velocity=FromWords(p.vectors_544_560_592_608[3]);if(velocity[1]>5&&velocity[1]-state.velocity[1]>5)LimitWipeoutBodyVelocity(body,5);
    state.velocity=velocity;const float speed=Length(velocity);UpdateWipeoutRetainedVelocity(state,body,physical.skeleton_drives,drives,actual_contact,p.flags_2468,velocity);
    const auto position=FromWords(p.vectors_544_560_592_608[2]);if(state.special_surface){state.below_surface=position[1]-state.surface_height<0;ApplyWipeoutSpecialSurface(body,state.surface_height);}
    Mat4 effective;for(unsigned i=0;i<4;++i)effective[i]=FromWords(p.effective_anim_transform_192[i]);const auto controls=o.animation_input.extra.wipeout_control,gesture=o.animation_input.extra.wipeout_gesture;
    if(!state.below_surface){
        if(!UpdateContact(o,actual_contact,velocity,effective[2],controls,error))return false;
        const float drag=state.slow&&actual_contact?(state.over?Clamp(state.settled_time*0.15f+0.05f,0,0.5f):0.05f):0;SetWipeoutDrag(body,drag);
    }
    state.time+=Step();state.response_time+=Step();state.extra_weight_zero_time+=Step();if(state.extra_weight>0)state.extra_weight_zero_time=0;
    state.response_scalar=0;state.slow_time+=Step();state.maximum_speed=speed-state.maximum_speed>=0?speed:state.maximum_speed;if(speed>2)state.slow_time=0;
    UpdateWipeoutResponseCounter(state,actual_contact);const auto com=physical.board_frames.centre_of_mass;bool applied=false;
    if(state.below_surface||state.imminent_surface_twelve)ControlWipeoutAir(state,body,com,controls,true);
    else if((p.flags_2484&0x100)&&state.response_time>=0.1f){
        const auto& f=physical.collision_feedback;const auto normal=WipeoutResponseNormal(f.flags.compliant?std::optional<Vec4>(f.highest_normal):std::nullopt,
            prediction.result.contact_time>=0?std::optional<Vec4>(prediction.result.landing_normal):std::nullopt);TriggerWipeoutResponse(state,body,normal,controls);
    }else if(state.airborne_frames>15&&!state.over){
        PrepareWipeoutProfile(state,profiles,gesture,controls);if(state.profile>=profiles.size()){error="Wipeout profile is outside the original five controls";return false;}
        const auto& profile=profiles[state.profile];ControlWipeoutProfileAir(state,body,com,effective,controls,profile);ApplyWipeoutProfileDrift(state,body,profile);applied=true;
    }else if((!actual_contact&&state.airborne_frames>15)||state.over)applied=ControlWipeoutAir(state,body,com,controls,actual_contact);
    else{
        PrepareWipeoutProfile(state,profiles,gesture,controls);if(state.profile>=profiles.size()){error="Wipeout profile is outside the original five controls";return false;}
        ControlWipeoutGround(state,body,com,effective,state.predicted_position,profiles[state.profile],physical.roots.animation_to_world,physical.animation_record.pose);applied=true;
    }
    const auto weight=UpdateWipeoutWeights(state,settings,actual_contact,applied,p.flags_2472,gesture);
    o.ground.steering.Update(0,o.air_settings.steering_blend,p.flags_2468,p.flags_2472);SetWipeoutAngularRoot(physical.skeleton_drives,drives,weight.target_weight);
    float residual;if(!UpdateSkeleton(o,weight.start,weight.end,weight.controlled,weight.extra,state.retained_velocity_active,residual,error))return false;
    if(state.move_board&&Signed(state.board_move_frames)<21){
        const auto deck=physical.board.PartTransforms()[6].translation;if(!o.input.toolkit){error="Wipeout board force requires the current BoardToolkit";return false;}
        const auto point=o.input.toolkit->deck[3];GroundApplyWorldForce(physical.board.BodiesMut()[6],deck,{state.board_offset[0],state.board_offset[1],state.board_offset[2]},{point[0],point[1],point[2]});++state.board_move_frames;
    }
    state.ManageRecovery(p.flags_2468,p.flags_2472,p.flags_2484,p.timestep_2604,settings.recovery);const auto gravity=physical.settings.board.step.simulation.gravity_acceleration;
    return prediction.Advance(state,physical.world,position,{gravity.x,gravity.y,gravity.z,0},error);
}
}
