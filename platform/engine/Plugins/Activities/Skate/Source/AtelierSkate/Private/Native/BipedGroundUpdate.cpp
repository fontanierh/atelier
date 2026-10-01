// SPDX-License-Identifier: Apache-2.0
#include "BipedGroundRuntime.h"
#include "OffboardAirMath.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{Vec4 Value(RawVector w){Vec4 v;std::memcpy(v.data(),w.data(),16);return v;}}
bool BipedGroundRuntime::PrepareAir(const OffboardAirLaunchInput& p,float elapsed,Vec4 point,std::optional<OffboardAirLaunchPacket>& out,std::string& error)
{
    if(!result){error="Ground Sync requires completed Ground job";return false;}const auto motion=*result;const auto flags=contact.flags_176;
    bool launch=(flags&1)==0&&elapsed>offboard_air_math::Bits(0x3d4ccccd);launch=launch||motion.alternate;
    if((flags&8)==0&&(p.flags_2480&0x20180)==0&&!state.flags_144_to_150[6])launch=launch||(p.flags_2476&0x80000)!=0;
    state.flags_144_to_150[2]=launch;
    if(!launch){out.reset();error.clear();return true;}
    auto packet=OffboardAirLaunchPacket::Initialized(0);
    if(!ProduceOffboardAirLaunch(packet,controller.state,controller.settings.movement_velocity.turn_vs_speed,air_launch,p,false,error))return false;
    const auto frame=motion.animation_frame;
    for(unsigned n=0;n<4;++n)packet.position_32[n]=std::fma(frame[2][n],point[2],std::fma(frame[1][n],point[1],std::fma(frame[0][n],point[0],frame[3][n])));
    out=packet;error.clear();return true;
}
void BipedGroundRuntime::UpdatePossession(BipedRuntimeOwners v)
{
    auto& physical=v.physical;auto& fields=physical.controller_fields;const auto current=fields.state_448;std::uint32_t target;
    if((v.processed.flags_2484&1)!=0){if(current==2||current==3||current==4)return;target=5;}
    else{if(current!=5)return;target=1;}
    fields.word_444=0;if(current==target)return;const auto& p=v.processed;
    const Mat4 board_frame=v.toolkit?v.toolkit->deck:physical.DeckFrame();Mat4 player_frame;for(unsigned n=0;n<4;++n)player_frame[n]=Value(p.effective_anim_transform_192[n]);
    const BoardPossessionProcessed processed{board_frame,player_frame,Value(p.vectors_544_560_592_608[2]),Value(p.vectors_880_896_912_928_944[2]),Value(p.vectors_400_416[0]),Value(p.vectors_464_480_496_512_528[0]),p.flags_2476,p.flags_2480,p.flags_2488};
    const BoardPossessionObserveInput input{processed,v.toolkit?std::optional<Mat4>{v.toolkit->deck}:std::nullopt,physical.riding.ground,physical.riding.wheel_lines,physical.skeleton.record,physical.collision_feedback,physical.drive_frames,physical.roots.animation_to_world};
    const auto observation=ObserveBoardPossession(physical.board,input);
    LiveBoardPossessionEffects effects(physical.board,v.life.board_animated_290,physical.board_wiping_out,physical.possession_live,physical.settings.board.collision,p.timestep_2604);
    if(target==5)physical.possession.Stop(fields,observation,effects);else physical.possession.Hold(fields,observation,effects);
    fields.state_448=target;physical.possession_live.PublishVolumes(physical.settings.board.collision);
}
bool BipedGroundRuntime::UpdateSkeleton(BipedRuntimeOwners v,Mat4 frame,Vec4 com,std::string& error)
{
    auto& f=v.physical;auto& p=v.processed;const float body_spin=v.animation_input.extra.physical_body_spin;
    const auto collision=BipedRuntimeCollision(f);
    const auto target=PrepareBipedSkeletonGroundFrames(f.roots,f.board_frames,f.animation_record.pose[0],f.drive_frames[0],skeleton_state,{frame,com},p.flags_2476,p.flags_2484,p.flags_2468);
    if((p.flags_2480&0x8000)!=0||(p.flags_2484&1)!=0)f.board_frames.physical_board=v.skeleton_air.ApplyBoard(f.board,target,true);
    std::array<Mat4,24> drives;if(!v.skeleton_input.GeneralUpdate(p,v.SkeletonOwners(),v.hierarchy,collision,drives,error))return false;
    v.animated.FinishGround();const auto root=f.roots.animation_to_world;
    // The active host callback only publishes this original call-local packet.
    // Skeleton's processed flag publication precedes the deferred finish.
    const std::optional<BipedReckoningUpdate> update{{root[1],root[2],.5f}};
    v.animation_input.fields.flags2468=p.flags_2468;
    if(update)FinishBipedReckoning(skeleton_state,*update,f.riding,v.air_reckoning,p,body_spin);
    error.clear();return true;
}
bool BipedGroundRuntime::Update(BipedRuntimeOwners v,BipedGroundContactSnapshot snapshot,OffboardToolkitInput& out,std::string& error)
{
    const auto p=v.processed;const auto fields=v.animation_input.fields;const auto extra=v.animation_input.extra;const auto frame=state.frame_80;
    const auto controls=CalculateBipedGroundInput({p.flags_2472,extra.offboard_magnitude,extra.offboard_turn,extra.biped_world_x,extra.biped_world_z,fields.magnitude_scale,fields.turn_scale,{frame[2][0],frame[2][1],frame[2][2]}},movement_vs_stick_angle,turn_vs_stick_angle);
    const auto line=p.line_tests_960_1008_1056[2];
    const auto prepared=PrepareBipedGroundJob(contact,state.distance_164,{snapshot,frame,p.state_2504,line.valid?std::optional<Vec4>{Value(line.position)}:std::nullopt,p.frames_since_teleport_2584,Value(p.vectors_544_560_592_608[2]),Value(p.vectors_544_560_592_608[3]),controls,v.physical.collision_extra_errors,fields.animation_translation,v.animated.motion.velocity_world,fields.animation_time,fields.cadence_end_percent,fields.animation_physics_blend_seconds,p.flags_2472,p.flags_2476,p.flags_2480,p.flags_2484,p.flags_2488},geometry);
    geometry_adjustment=prepared.geometry;const auto motion=Run(prepared.job);
    UpdateBipedGroundFeet(v.feet,MakeBipedFeetInput(v.processed,v.physical.animation_record,v.physical.roots),v.ik.state);
    v.ground.steering.Update(0,v.air_settings.steering_blend,p.flags_2468,p.flags_2472);UpdatePossession(v);
    OffboardAirLaunchInput launch;if(!BipedRuntimeLaunchInput(v,std::nullopt,"Ground launch requires the completed BoardToolkit",launch,error))return false;
    std::optional<OffboardAirLaunchPacket> packet;if(!PrepareAir(launch,v.processed.state_timer_2664,v.physical.animation_record.centre_of_mass,packet,error))return false;
    if(packet&&!v.selector.Launch(v.physical.world,*packet,BipedRuntimeGravity(v.physical),BipedRuntimeAirContext(v.processed),error))return false;
    state.flags_144_to_150[0]=false;const auto animation=SyncBipedGroundFrames(state,contact,motion);
    if(!UpdateSkeleton(v,animation,motion.position,error))return false;SyncGrab(v);
    out={state.frame_80[3],motion.surface_frame[2],motion.surface_frame[1],motion.surface_frame[0],motion.velocity,animation[1],animation[0]};error.clear();return true;
}
bool BipedGroundRuntime::SubmitGeometry(BipedRuntimeOwners v,std::string& error)
{
    if(!result){error="Ground geometry submission requires completed motion";return false;}
    return geometry.Submit(v.physical.world,state.frame_80,result->velocity,{v.processed.actor_query_2948,static_cast<std::int32_t>(v.processed.actor_query_2952)},v.processed.flags_2488,error);
}
}
