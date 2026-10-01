// SPDX-License-Identifier: Apache-2.0
#include "GrindRuntimeInternal.h"
#include "PlayerStateSelector.h"
#include "AntiFlip.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace grind_detail;
namespace
{
Vec4 Launch(GrindRuntimeOwners o,GrindLaunchInput input)
{
    const auto output=CalculateGrindLaunch(o.input.grind->jumper,input);
    const auto velocity=Xyz(output.velocity);
    for(auto& body:o.physical.board.BodiesMut())body.rates.linear_velocity=velocity;
    o.input.grind->jumper=output.jumper;
    o.input.processed.flags_2476|=output.flags_2476_to_or;
    return output.velocity;
}
}
bool GrindRuntime::CollisionForce(GrindRuntimeOwners o,std::optional<Vec4>& output,std::string& error)
{
    if(!o.input.toolkit){error="Grind collision requires current BoardToolkit";return false;}
    const auto& p=o.input.processed;const auto& toolkit=*o.input.toolkit;
    const auto response=CalculateRidingCollisionResponse(settings.substate.collision,{p.flags_2472,FloatVector(p.collision_pose_error_736),FloatVector(p.vectors_400_416[1]),
        toolkit.travel_direction,FloatVector(p.vectors_544_560_592_608[0]),Lanes(o.physical.riding.reckoning.ground_normal),p.timestep_2604,toolkit.total_mass});
    if(!response||!response->applied){output.reset();return true;}
    o.physical.board.ForcesMut().Append({15,Xyz(response->force),Xyz(response->point)});output=response->target_velocity;return true;
}
bool GrindRuntime::Execute(GrindRuntimeOwners o,const PlayerGrindObservation& observed,std::string& error)
{
    if(!active){error="Grind substate requires active physical family";return false;}
    const auto family=*active;const auto index=std::size_t(family);const auto state=states[index];bool jumped_now=false;
    std::optional<Vec4> prediction_velocity;if(!CollisionForce(o,prediction_velocity,error))return false;
    if(!prediction_velocity){
        auto& p=o.input.processed;
        if(p.flags_2468&0x00400000){
            if(!o.input.toolkit){error="Grind pop requires current BoardToolkit";return false;}
            const auto position=o.input.toolkit->deck[3];float vertical;
            if(!settings.substate.Vertical(family,p.state_variant_index_2528,o.animation_input.extra.jump_strength,vertical,error))return false;
            vertical*=o.trainer.grind_pop;const float side=GrindGeometrySideJump(family,p.grind.geometry_kind_1464);
            if(!o.input.grind){error="Grind pop requires actual input jumper";return false;}
            const auto velocity=Launch(o,{FloatVector(p.vectors_400_416[0]),position,FloatVector(p.grind.point_1120),o.animation_input.extra.grind_stability_nudge,side,vertical});
            auto& next=states[index];next.already_jumped=true;next.just_jumped=true;next.jump_velocity=velocity;jumped_now=true;prediction_velocity=velocity;
        }else if(!state.already_jumped){
            if(p.grind.flags_1516&0x40000000){const auto velocity=FloatVector(p.grind.entry_velocity_1184);o.ground_runtime.SetAnimatedVelocity(o.physical.board,velocity);prediction_velocity=velocity;}
            else if(state.substate==1){if(!Contact(o,observed,error))return false;}
            else if(state.substate==2){if(!Involuntary(o,observed,error))return false;}
        }
    }
    if(prediction_velocity){
        if(!o.input.toolkit){error="Grind prediction requires current BoardToolkit";return false;}
        const auto position=o.input.toolkit->deck[3];const float dt=o.input.processed.timestep_2604;Vec4 prediction;
        for(std::size_t i=0;i<4;++i)prediction[i]=std::fma((*prediction_velocity)[i],dt,position[i]);
        o.physical.roots.predicted_board_position=prediction;o.physical.roots.supplied_prediction=prediction;
    }
    Mat4 target;if(jumped_now)return Animated(o,target,error);
    if(!Ground(o,target,error))return false;o.skeleton_air.CapturePhysicsError(o.physical.board,target);return true;
}
bool GrindRuntime::ExecuteNonspecific(GrindRuntimeOwners o,std::string& error)
{
    nonspecific_jumped=false;auto& p=o.input.processed;
    if(p.flags_2468&0x00400000){
        if(!o.input.toolkit){error="Nonspecific pop requires current BoardToolkit";return false;}
        const auto position=o.input.toolkit->deck[3];float vertical;
        if(!settings.substate.Vertical(PlayerGrindFamily::FiftyFifty,p.state_variant_index_2528,o.animation_input.extra.jump_strength,vertical,error))return false;
        if(!o.input.grind){error="Nonspecific pop requires actual input jumper";return false;}
        const auto velocity=Launch(o,{FloatVector(p.vectors_400_416[0]),position,FloatVector(p.grind.point_1120),o.animation_input.extra.grind_stability_nudge,Float(0x3f333333),vertical*o.trainer.grind_pop});
        nonspecific_jump_velocity=velocity;nonspecific_jumped=true;Mat4 target;if(!Animated(o,target,error))return false;
        o.ground_runtime.SetAnimatedVelocity(o.physical.board,velocity);
    }else{
        const bool animated=StateIsSkateboardAnimated({o.skeleton_input.force_mode,o.physical.drive_frames[0][2][1],settings.substate.animated_board_threshold});
        Mat4 target;if(animated&&(p.flags_2472&0x00400000)){if(!Animated(o,target,error))return false;}else if(!Ground(o,target,error))return false;
        o.ground.steering.Update(0,o.ground_settings.Board().steering.tilt_blending,p.flags_2468,p.flags_2472);
        o.skeleton_air.CapturePhysicsError(o.physical.board,target);
        if(!o.input.toolkit){error="Nonspecific board update requires current BoardToolkit";return false;}
        const auto& toolkit=*o.input.toolkit;const auto up=FloatVector(p.vectors_544_560_592_608[0]);
        const auto correction=CalculateAntiFlip(o.ground_settings.Board().anti_flip,{p.flags_2468,o.animation_input.fields.balance,toolkit.deck[2],toolkit.deck[0],up});
        o.ground_runtime.ApplyAngularDisplacement(o.physical.board,correction);ApplyGrindWorldForce(o.physical.board,Scale(up,-40),toolkit.deck[3]);
        std::optional<Vec4> ignored;if(!CollisionForce(o,ignored,error))return false;
    }
    return true;
}
}
