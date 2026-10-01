// SPDX-License-Identifier: Apache-2.0
#include "ClimbingRuntime.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace climbing_math;
bool EqualAscii(std::string_view a,std::string_view b){
  if(a.size()!=b.size())return false;const auto lower=[](unsigned char c){return c>='A'&&c<='Z'?c+('a'-'A'):c;};
  for(std::size_t i=0;i<a.size();++i)if(lower(a[i])!=lower(b[i]))return false;
  return true;
}
Vec4 NativePoint(Vec3 p){return {p.x,p.y,p.z,0};}
RawVector Words(Vec4 v){RawVector out;for(unsigned i=0;i<4;++i)std::memcpy(&out[i],&v[i],4);return out;}
RawMatrix Words(Mat4 m){RawMatrix out;for(unsigned i=0;i<4;++i)out[i]=Words(m[i]);return out;}
float Float(std::uint32_t word){float v;std::memcpy(&v,&word,4);return v;}
void ZeroRates(BodyRates& rates){rates.linear_velocity={};rates.angular_velocity={};rates.force_acceleration={};rates.torque_acceleration={};}
bool Pressed(ClimbingControls controls,unsigned bit){const auto& w=controls.controller.Words();return (w[13]&(1u<<bit))!=0&&(w[6]&(1u<<bit))==0;}
}
bool ClimbingRuntime::Load(const std::optional<ClimbingClipFile>& file,const std::vector<std::string>& names,std::string& error){
  ClimbingRuntime loaded;
  if(file){ClimbingClips clips;if(!ClimbingClips::FromConverted(*file,clips,error))return false;loaded.clips=std::move(clips);
    for(const auto& name:loaded.clips->reach.names){const auto found=std::find_if(names.begin(),names.end(),[&](const auto& n){return EqualAscii(n,name);});if(found==names.end()){error="Climbing rig bone "+name+" missing from skater";return false;}loaded.indices.push_back(std::size_t(found-names.begin()));}
  }
  *this=std::move(loaded);error.clear();return true;
}
bool ClimbingRuntime::Advance(ClimbingFrame f,ClimbingControls controls,camera::CameraRuntime& camera,ClimbingGlobalStages& stages,bool& handled,std::string& error){
  using namespace climbing_math;auto& physics=f.physical;const auto dt=physics.settings.board.step.simulation.time_step;
  if(f.player.PendingTeleport()){active.reset();approach.reset();cooldown=.3f;handled=false;error.clear();return true;}
  cooldown=std::fmax(cooldown-dt,0.0f);
  if(!clips||!active){handled=false;error.clear();return true;}
  const auto& c=clips->reach;auto& a=*active;
  if(a.phase==ClimbingPhase::Hang&&Pressed(controls,23)&&ClearClimbingLedge(physics.world,a.ledge)){a.phase=ClimbingPhase::Mantle;a.time=0;}
  a.time+=dt;
  const auto yaw=RotationY(std::atan2(a.ledge.forward.x,a.ledge.forward.z));
  const auto hang=c.Sample(c.Duration());const auto hang_globals=c.Globals(hang);
  const auto hang_root=Add(Sub(a.ledge.anchor,Rotate(yaw,c.Hands(hang_globals))),Rotate(yaw,ClimbingContactClearance(c,hang_globals)));
  const auto mantle_end=clips->mantle.Sample(clips->mantle.Duration());
  const auto sample_phase=a.phase;const auto sample_time=a.time;
  std::vector<Transform> locals;Vec3 translation;Quat rotation;bool complete=false;
  switch(a.phase){
  case ClimbingPhase::Catch:{
    const auto duration=std::fmin(.22f+Distance(a.start_root.translation,hang_root)*.18f,.5f);
    const auto t=std::fmin(a.time/duration,1.0f);const auto weight=Smooth(t);locals=hang;
    for(std::size_t i=0;i<std::min(locals.size(),a.entry.size());++i)locals[i]=Blend(a.entry[i],locals[i],weight);
    translation=Lerp(a.start_root.translation,hang_root,weight);rotation=Slerp(a.start_root.rotation,yaw,weight);
    if(t>=1){a.phase=ClimbingPhase::Hang;a.time=0;}break;
  }
  case ClimbingPhase::Hang:locals=hang;translation=hang_root;rotation=yaw;break;
  case ClimbingPhase::Mantle:{
    locals=clips->mantle.Sample(a.time);const auto weight=Smooth(a.time/.22f);
    for(std::size_t i=0;i<std::min(locals.size(),hang.size());++i)locals[i]=Blend(hang[i],locals[i],weight);
    const auto g=c.Globals(locals);const auto attached=Add(Sub(a.ledge.anchor,Rotate(yaw,c.Hands(g))),Rotate(yaw,ClimbingContactClearance(c,g)));
    const auto end_attached=Sub(a.ledge.anchor,Rotate(yaw,c.Hands(c.Globals(clips->mantle.Sample(clips->mantle.Duration()*.55f)))));
    const auto release=Smooth((a.time/clips->mantle.Duration()-.55f)/.45f);
    const auto final_root=Sub(a.ledge.landing,Rotate(yaw,c.Feet(c.Globals(mantle_end))));
    translation=release>0?Lerp(end_attached,final_root,release):attached;rotation=yaw;
    if(a.time>=clips->mantle.Duration()){a.phase=ClimbingPhase::Settle;a.time=0;}break;
  }
  case ClimbingPhase::Settle:{
    const auto weight=Smooth(a.time/.25f);locals.reserve(std::min(mantle_end.size(),ground_entry.size()));
    for(std::size_t i=0;i<std::min(mantle_end.size(),ground_entry.size());++i)locals.push_back(Blend(mantle_end[i],ground_entry[i],weight));
    translation=Sub(a.ledge.landing,Rotate(yaw,c.Feet(c.Globals(locals))));rotation=yaw;complete=a.time>=.25f;break;
  }
  }
  const Transform root{translation,rotation,{1,1,1}};const auto root_matrix=root.ToMatrix();
  float contact_weight;
  switch(sample_phase){case ClimbingPhase::Catch:case ClimbingPhase::Hang:contact_weight=1;break;case ClimbingPhase::Mantle:contact_weight=1.0f-Smooth((sample_time/clips->mantle.Duration()-.50f)/.05f);break;case ClimbingPhase::Settle:contact_weight=0;break;}
  if(contact_weight>0&&!ApplyClimbingHands(c,locals,root_matrix,a.ledge,contact_weight,error))return false;
  auto globals=c.Globals(locals);const auto board_index=c.Index("SKATEBOARD_ROOT");Mat4 board_world;
  if(a.carry_board){
    const auto hips=Point(root_matrix,Translation(globals[c.Index("HIPS")])),chest=Point(root_matrix,Translation(globals[c.Index("SPINE3")]));
    const auto up=Normalize(Sub(chest,hips));const auto shoulder_delta=Sub(Translation(globals[c.Index("LEFTARM")]),Translation(globals[c.Index("RIGHTARM")]));
    const auto shoulders=Vector(root_matrix,shoulder_delta);
    const auto forward=Normalize(Cross(shoulders,up)),right=Normalize(Cross(up,forward));
    const Transform stowed{Sub(ScaleVector(Add(hips,chest),.5f),ScaleVector(forward,.20f)),RotationAxes(right,ScaleVector(forward,-1),up),{1,1,1}};
    auto board=Blend(Transform::FromMatrix(a.board_world),stowed,std::fmax(Smooth(a.time/.2f),a.phase!=ClimbingPhase::Catch?1.0f:0.0f));
    if(sample_phase==ClimbingPhase::Settle){const auto hand_carry=Multiply(root_matrix,c.Globals(ground_entry)[board_index]);board=Blend(board,Transform::FromMatrix(hand_carry),Smooth(sample_time/.25f));}
    board_world=board.ToMatrix();
  }else{
    if(!physics.AdvanceClimbingBoardOnly(dt,error))return false;
    board_world=Multiply(Multiply(Matrix(physics.DeckFrame()),Inverse(a.physical_board_world)),a.board_world);
  }
  const auto board_delta=Multiply(Multiply(Inverse(root_matrix),board_world),Inverse(globals[board_index]));
  for(std::size_t i=0;i<globals.size();++i){auto parent=std::int32_t(i);while(parent>=0&&parent!=std::int32_t(board_index))parent=c.parents[std::size_t(parent)];if(parent==std::int32_t(board_index))globals[i]=Multiply(board_delta,globals[i]);}
  auto pose=a.fallback;
  for(std::size_t i=0;i<std::min(indices.size(),globals.size());++i){if(indices[i]>=pose.size()){error="Climbing remap is outside the render pose (source index assertion)";return false;}pose[indices[i]]=Native(globals[i]);}
  const auto actual_board=Multiply(Multiply(board_world,Inverse(a.board_world)),a.physical_board_world);
  if(a.carry_board){AffineTransform transform;for(unsigned i=0;i<3;++i)for(unsigned j=0;j<3;++j)transform.basis.columns[i][j]=actual_board[i][j];transform.translation=Translation(actual_board);physics.board.SetTransform(transform);for(auto& b:physics.board.BodiesMut())ZeroRates(b.rates);}
  if(!PublishPose(f,root_matrix,std::move(pose),error))return false;
  const auto& w=controls.controller.Words();f.animation_input.extra.look_x=Float(w[9]);f.animation_input.extra.look_y=Float(w[10]);
  if(!stages.AdvanceCamera(f,camera,error))return false;
  ++physics.ticks;stages.FinishClockTick();
  if(complete){if(!stages.ResumeAfterClimb(f,error))return false;active.reset();cooldown=.3f;}
  handled=true;error.clear();return true;
}
bool ClimbingRuntime::PublishPose(ClimbingFrame f,const Mat4& root,std::vector<Mat4> pose,std::string& error){
  using namespace climbing_math;auto& p=f.physical;auto& s=f.animated;
  std::array<Mat4,24> parts;if(!MapAnimationParts(pose,s.settings.bone_indices,s.settings.physics_frames,parts,error))return false;
  p.roots.animation_to_world=Native(root);p.roots.world_to_animation=Native(Inverse(root));
  p.animation_record.Update(parts,p.roots.animation_to_board,s.settings.masses);s.animation_hips=parts[23];s.animation_board=parts[0];
  const auto com=Point(root,{p.animation_record.centre_of_mass[0],p.animation_record.centre_of_mass[1],p.animation_record.centre_of_mass[2]});
  p.board_frames.UpdateComLift(Native(root),NativePoint(com),.24f);p.board_frames.centre_of_mass=NativePoint(com);p.board_frames.previous_centre_of_mass=NativePoint(com);p.board_frames.com_velocity={};
  for(std::size_t i=0;i<parts.size();++i)p.skeleton.SetPartTransform(i,Native(Multiply(root,Matrix(parts[i]))));
  p.skeleton.SetPartTransform(24,p.board_frames.lifted_com_frame);p.skeleton.SetPartTransform(25,p.board_frames.com_frame);
  p.skeleton_drives.targets.Reset(Native(Multiply(root,Matrix(parts[23]))),Native(Multiply(root,Matrix(parts[0]))));
  const auto targets=p.skeleton_drives.targets.UpdateExtraTargets(p.skeleton,p.board_frames.com_frame,p.board_frames.lifted_com_frame);
  p.extra_target_positions={targets.com,targets.lifted_com,targets.following_com};p.pose_errors.SetTargets(targets);p.drive_frames=parts;
  for(auto& b:p.skeleton.BodiesMut())ZeroRates(b.rates);
  p.skeleton.animation_to_world=Native(root);p.previous_root_position=NativePoint(Translation(root));p.root_velocity={};p.correction={};
  p.skeleton.PublishPhysicalRecord(Native(Multiply(root,Matrix(parts[0]))));
  auto& processed=f.player.processed;processed.effective_anim_transform_192=Words(Native(root));processed.vectors_544_560_592_608[2]=Words(NativePoint(com));processed.vectors_544_560_592_608[3]={};processed.flags_2472&=~(1u<<10);
  auto& physical=f.player.physical;physical.skeleton.anim_to_world_11920=Words(Native(root));physical.reckoning.vector_64=Words(NativePoint(com));physical.reckoning.vector_16={};physical.reckoning.vector_96=Words(Vec4{0,1,0,0});physical.air.flag_441=0;physical.air.use_air_reckoning_452=0;
  f.centre_of_mass_output=f.centre_of_mass_filter.Update(NativePoint(com),{});f.render_pose=std::move(pose);++f.pose_generation;++f.player.player.update_count_1316;
  error.clear();return true;
}
} // namespace atelier::skate
