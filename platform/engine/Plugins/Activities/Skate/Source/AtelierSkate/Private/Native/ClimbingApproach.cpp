// SPDX-License-Identifier: Apache-2.0
#include "ClimbingRuntime.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace climbing_math;
Vec3 Vector(const RawVector& words){Vec4 f;for(unsigned i=0;i<4;++i)std::memcpy(&f[i],&words[i],4);return {f[0],f[1],f[2]};}
}
float ClimbingReachGain(float distance,bool airborne){return climbing_math::Smooth((2.6f-distance)/1.8f)*(airborne?1.0f:.45f);}
bool ClimbingRuntime::Approach(ClimbingFrame f,ClimbingControls controls,std::string& error){
  using namespace climbing_math;if(!clips){error.clear();return true;}const auto& c=clips->reach;const auto root=Matrix(f.physical.roots.animation_to_world);
  std::vector<Mat4> globals;globals.reserve(indices.size());for(auto i:indices){if(i>=f.render_pose.size()){error="Climbing remap is outside the render pose (source index assertion)";return false;}globals.push_back(Matrix(f.render_pose[i]));}
  std::vector<Transform> locals;locals.reserve(globals.size());for(std::size_t i=0;i<globals.size();++i)locals.push_back(Transform::FromMatrix(c.parents[i]<0?globals[i]:Multiply(Inverse(globals[std::size_t(c.parents[i])]),globals[i])));
  const auto state=f.selected_state.Active().state;const auto ground_velocity=Vector(f.player.physical.reckoning.vector_16);const auto ground_speed=Length(ground_velocity);
  if(state==PhysicalStateId::BipedGround&&(ground_entry.empty()||ground_speed<.3f)){ground_entry=locals;const auto height=c.Feet(globals).y;for(std::size_t i=0;i<ground_entry.size();++i)if(c.parents[i]<0)ground_entry[i].translation.y-=height;}
  const bool airborne=state==PhysicalStateId::BipedAir;
  if((!airborne&&state!=PhysicalStateId::BipedGround)||cooldown>0){approach.reset();error.clear();return true;}
  const auto feet=Point(root,c.Feet(globals));const auto velocity=ground_velocity;Vec3 direction;
  if(controls.offboard_direction){const Vec3 candidate{(*controls.offboard_direction)[0],0,(*controls.offboard_direction)[2]};if(Dot(candidate,candidate)>.04f)direction=candidate;else direction=ScaleVector({root[2][0],root[2][1],root[2][2]},(f.player.processed.flags_2476&4)!=0?-1.0f:1.0f);}
  else direction=ScaleVector({root[2][0],root[2][1],root[2][2]},(f.player.processed.flags_2476&4)!=0?-1.0f:1.0f);
  const bool controller_moving=controls.offboard_direction&&((*controls.offboard_direction)[0]*(*controls.offboard_direction)[0]+(*controls.offboard_direction)[2]*(*controls.offboard_direction)[2])>.04f;
  const bool moving=airborne||ground_speed>.15f||controller_moving;
  const auto found=moving?FindAirClimbingLedge(f.physical.world,feet,direction):std::nullopt;
  if(!airborne&&approach&&found&&Distance(approach->ledge.anchor,found->anchor)<.5f)approach->ledge=*found;
  if(!approach&&found&&Dot(velocity,found->forward)>=-.1f)approach=ClimbingApproach{*found,0};
  if(!approach){error.clear();return true;}auto& a=*approach;
  const auto separation=Sub(a.ledge.anchor,feet);const auto distance=std::sqrt(separation.x*separation.x+separation.z*separation.z);
  const bool valid=moving&&separation.y>.35f&&separation.y<2.75f&&distance<2.7f&&Dot(separation,a.ledge.forward)>0&&Dot(NormalizeOrZero(direction),a.ledge.forward)>.65f&&Dot(velocity,a.ledge.forward)>=-.3f&&ClearClimbingLedge(f.physical.world,a.ledge);
  const auto desired=valid?ClimbingReachGain(distance,airborne):0.0f;const auto dt=f.physical.settings.board.step.simulation.time_step;
  a.weight+=(desired-a.weight)*(1.0f-std::exp(-dt/.10f));
  if(a.weight<.001f&&!valid){approach.reset();error.clear();return true;}const auto weight=a.weight;
  const auto authored=c.Sample(c.Duration());for(const char* side: {"LEFT","RIGHT"})for(const char* suffix: {"SHOULDER","ARM","FOREARM","HAND"}){const auto i=c.Index(std::string(side)+suffix);locals[i].rotation=Slerp(locals[i].rotation,authored[i].rotation,weight*.75f);}
  const auto before_ik=c.Globals(locals);bool reachable=true;const char* sides[]={"LEFT","RIGHT"};
  for(unsigned i=0;i<2&&reachable;++i){const std::string side=sides[i];const auto shoulder=Point(root,Translation(before_ik[c.Index(side+"ARM")])),elbow=Point(root,Translation(before_ik[c.Index(side+"FOREARM")])),hand=Point(root,Translation(before_ik[c.Index(side+"HAND")]));reachable=Distance(shoulder,ClimbingWrist(a.ledge,i).first)<=Distance(shoulder,elbow)+Distance(elbow,hand)-.015f;}
  if(!ApplyClimbingHands(c,locals,root,a.ledge,weight,error))return false;
  const auto output=c.Globals(locals);for(std::size_t i=0;i<std::min(indices.size(),output.size());++i)f.render_pose[indices[i]]=Native(output[i]);
  if(airborne&&valid&&reachable&&a.weight>=.95f&&!ground_entry.empty()){
    const auto deck=Matrix(f.physical.DeckFrame());active=ClimbingAttached{ClimbingPhase::Catch,0,a.ledge,Transform::FromMatrix(root),std::move(locals),f.render_pose,Multiply(root,output[c.Index("SKATEBOARD_ROOT")]),deck,f.physical.controller_fields.state_448==1};approach.reset();f.offboard_air_selector.Reset();f.offboard_feet.Reset();f.ik.EnableFeet(false);
  }
  error.clear();return true;
}
} // namespace atelier::skate
