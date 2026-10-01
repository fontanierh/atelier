// SPDX-License-Identifier: Apache-2.0
#include "GroundStateCorrections.h"
#include "GroundCorrections.h"
#include "GroundDrag.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
using namespace atelier::skate;
namespace {
std::vector<std::uint32_t> out;
std::uint32_t Word(){char b[4];if(!std::cin.read(b,4))std::exit(2);std::uint32_t w;std::memcpy(&w,b,4);return w;}
std::int32_t Signed(){const auto w=Word();std::int32_t n;std::memcpy(&n,&w,4);return n;}
float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
Vec4 Four(){return {Float(),Float(),Float(),Float()};}
void Out(std::uint32_t w){out.push_back(w);}
void Out(float f){std::uint32_t w;std::memcpy(&w,&f,4);Out(w);}
void Out(Vec4 v){for(auto f:v)Out(f);}
PhysicsGroundState State(){PhysicsGroundState s;s.collision_force_2528=Four();
s.collision_point_2544=Four();
s.word_2560=Word();
s.word_2564=Word();
s.vector_2592=Four();
s.vector_2608=Four();
s.anti_flip_torque_2624=Four();
s.steering_push_scalar_2640=Float();
s.steering_damped_turn_2644=Float();
s.elapsed_2648=Float();
s.collision_countdown_2652=Float();
s.captured_position_x_2656=Float();
s.captured_position_z_2660=Float();
s.scalar_2664=Float();
s.scalar_2668=Float();
s.straighten_scale_2672=Float();
s.vector_2688=Four();
s.scalar_2704=Float();
s.flag_2708=Word()!=0;
s.flag_2720=Word()!=0;
s.flag_2721=Word()!=0;
s.flag_2722=Word()!=0;
s.anti_flip_nudge_applied_2723=Word()!=0;
s.human_player_2724=Word()!=0;
s.controls_latched_2725=Word()!=0;
s.captured_position_valid_2726=Word()!=0;
s.pinning_2727=Word()!=0;
s.was_pinning_2728=Word()!=0;
s.flag_2729=Word()!=0;
s.push_suppressed_2730=Word()!=0;
s.flag_2731=Word()!=0;
s.manual_correction_2732=Word()!=0;
s.manual_opposition_2733=Word()!=0;
s.hang_detection_frames_2740=Signed();
s.hang_force_frames_2744=Signed();
s.hung_wipeout_frames_2748=Signed();
s.anti_flip_nudge_frames_2752=Signed();return s;}
void Out(const PhysicsGroundState& s){Out(s.collision_force_2528);
Out(s.collision_point_2544);
Out(s.word_2560);
Out(s.word_2564);
Out(s.vector_2592);
Out(s.vector_2608);
Out(s.anti_flip_torque_2624);
Out(s.steering_push_scalar_2640);
Out(s.steering_damped_turn_2644);
Out(s.elapsed_2648);
Out(s.collision_countdown_2652);
Out(s.captured_position_x_2656);
Out(s.captured_position_z_2660);
Out(s.scalar_2664);
Out(s.scalar_2668);
Out(s.straighten_scale_2672);
Out(s.vector_2688);
Out(s.scalar_2704);
Out(std::uint32_t(s.flag_2708));
Out(std::uint32_t(s.flag_2720));
Out(std::uint32_t(s.flag_2721));
Out(std::uint32_t(s.flag_2722));
Out(std::uint32_t(s.anti_flip_nudge_applied_2723));
Out(std::uint32_t(s.human_player_2724));
Out(std::uint32_t(s.controls_latched_2725));
Out(std::uint32_t(s.captured_position_valid_2726));
Out(std::uint32_t(s.pinning_2727));
Out(std::uint32_t(s.was_pinning_2728));
Out(std::uint32_t(s.flag_2729));
Out(std::uint32_t(s.push_suppressed_2730));
Out(std::uint32_t(s.flag_2731));
Out(std::uint32_t(s.manual_correction_2732));
Out(std::uint32_t(s.manual_opposition_2733));
Out(std::uint32_t(s.hang_detection_frames_2740));
Out(std::uint32_t(s.hang_force_frames_2744));
Out(std::uint32_t(s.hung_wipeout_frames_2748));
Out(std::uint32_t(s.anti_flip_nudge_frames_2752));}
struct Services final:GroundCorrectionServices {
 Vec4 start,end,deck,y,z;bool hung=false;std::uint32_t fail=0,calls=0,last_error=0;std::vector<std::uint32_t> log;
 bool Gate(std::uint32_t id,const std::vector<Vec4>& vectors,std::string& error){
  ++calls;log.push_back(id);log.push_back(std::uint32_t(vectors.size()*4));for(auto v:vectors)for(auto f:v){std::uint32_t w;std::memcpy(&w,&f,4);log.push_back(w);}
  if(calls==fail){last_error=id;error="probe ground service "+std::to_string(id);return false;}return true;
 }
 bool GroundDot3(Vec4 a,Vec4 b,float& value,std::string& error)override{if(!Gate(1,{a,b},error))return false;value=Dot3(a,b);return true;}
 bool GroundScaleToMagnitude(Vec4 v,float square,float size,Vec4& value,std::string& error)override{if(!Gate(2,{v,Vec4{square,size,0,0}},error))return false;value=atelier::skate::GroundScaleToMagnitude(v,square,size);return true;}
 bool BuildHangForce(Vec4& value,std::string& error)override{if(!Gate(3,{},error))return false;value=GroundHangForce(start,end,deck);return true;}
 bool ApplyHangForce(Vec4 v,std::string& error)override{return Gate(4,{v},error);}
 bool DetectHungUpGeometry(bool& value,std::string& error)override{if(!Gate(5,{},error))return false;value=hung;return true;}
 bool RequestHungWipeout(std::string& error)override{return Gate(6,{},error);}
 bool WheelCatchDisplacement(Vec4& value,std::string& error)override{if(!Gate(7,{},error))return false;value=GroundWheelCatchDisplacement(y,z);return true;}
 bool ApplyWheelCatchDisplacement(Vec4 v,std::string& error)override{return Gate(8,{v},error);}
 bool PinToCapturedPosition(float x,float z0,std::string& error)override{return Gate(9,{Vec4{x,z0,0,0}},error);}
};
void Fill(BoardForceQueue& q,std::uint32_t n){q.Clear();for(std::uint32_t j=0;j<n;++j)if(!q.Append({100+j,{float(j),float(j)+.25f,-float(j)},{.1f,.2f,.3f}}))std::exit(2);}
InertiaDynamics Inertia(){return {{Float(),Float(),Float()},Float(),Float(),Float(),Float(),Float(),Float()};}
void Frame(const PhysicsGroundState& s,const BoardForceQueue& q,const std::vector<std::size_t>& indices,const std::vector<InertiaDynamics>& inertias){
 Out(s);Out(std::uint32_t(q.Count()));for(std::size_t i=0;i<q.Count();++i){const auto f=q.Entries()[i];Out(f.tag);for(float v:{f.force_world.x,f.force_world.y,f.force_world.z,f.point_body.x,f.point_body.y,f.point_body.z})Out(v);}
 Out(std::uint32_t(indices.size()));for(auto i:indices)Out(std::uint32_t(i));
 Out(std::uint32_t(inertias.size()));for(auto i:inertias)for(float f:{i.inverse_tensor.x,i.inverse_tensor.y,i.inverse_tensor.z,i.inverse_mass,i.spherical,i.maximum_linear_velocity,i.maximum_angular_velocity,i.linear_drag,i.angular_drag})Out(f);
}
}
int main(){
 const auto cases=Word();for(std::uint32_t c=0;c<cases;++c){
  auto state=State();BoardForceQueue q;Fill(q,Word());Services services;services.start=Four();services.end=Four();services.deck=Four();services.y=Four();services.z=Four();
  std::vector<std::size_t> indices;std::vector<InertiaDynamics> inertias;const auto n=Word();Out(c);Out(n);const auto mark=out.size();Out(0u);Frame(state,q,indices,inertias);
  for(std::uint32_t tick=0;tick<n;++tick){
   const auto op=Word();bool ok=true;std::uint32_t a=0,b=0;std::string error;services.log.clear();services.last_error=0;
   switch(op){
   case 0:state=PhysicsGroundState::BeforeFirstEnter(Word()!=0);break;
   case 1:state.BeginEntry();break;
   case 2:state.FinishEntry(Word());break;
   case 3:{const auto count=Signed();a=state.BeginUpdate(count,Four());break;}
   case 4:state.FinishUpdate(Float());break;
   case 5:{const AntiFlipNudgeInput input{Float(),Four()};AntiFlipNudgeResult r{};ok=UpdateAntiFlipNudge(state,input,q,services,r,error);if(ok){a=r.attempted;b=r.queued;}break;}
   case 6:{const HangUpInput input{Word(),Float(),Float(),Word()!=0};ok=ManageHangUps(state,input,services,error);break;}
   case 7:{const HalfpipeWheelCatchInput input{Word(),Float(),Float(),Float(),Float()};bool applied=false;ok=ManageHalfpipeWheelCatches(input,services,applied,error);if(ok)a=applied;break;}
   case 8:{const PinningInput input{Word(),Signed(),Word()};ok=ConsiderGroundPinning(state,input,services,error);break;}
   case 9:state.anti_flip_torque_2624=Four();break;
   case 10:services.fail=Word();services.hung=Word()!=0;services.calls=0;break;
   case 11:state=State();break;
   case 12:Fill(q,Word());break;
   case 13:{indices.clear();const auto ni=Word();for(std::uint32_t j=0;j<ni;++j)indices.push_back(Word());inertias.clear();const auto nb=Word();for(std::uint32_t j=0;j<nb;++j)inertias.push_back(Inertia());break;}
   case 14:{const bool selected=Word()!=0;const auto part=Word();const float drag=Float();BodyInertias bindings{indices.data(),indices.size(),inertias.data(),inertias.size()};DragBindingError drag_error{};ok=bindings.SetLinearDrag(drag,selected?std::optional<std::size_t>(part):std::nullopt,drag_error);if(!ok)a=100+std::uint32_t(drag_error);break;}
   case 15:{const GroundDragInput input{Word(),Float(),Float(),Float(),Float()};const LinearDragSettings settings{Float(),Float(),Float(),Float()};const float drag=input.Calculate(settings);std::memcpy(&a,&drag,4);break;}
   default:return 2;
   }
   Out(op);Out(std::uint32_t(ok));Out(a);Out(b);Out(services.last_error);Out(services.calls);Out(std::uint32_t(services.log.size()));for(auto w:services.log)Out(w);Frame(state,q,indices,inertias);
  }out[mark]=std::uint32_t(out.size()-mark-1);
 }if(std::cin.peek()!=std::char_traits<char>::eof())return 2;for(auto w:out)for(unsigned i=0;i<4;++i)std::cout.put(char(w>>(8*i)));
}
