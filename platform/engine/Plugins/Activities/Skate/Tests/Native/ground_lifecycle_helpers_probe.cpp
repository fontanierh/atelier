// SPDX-License-Identifier: Apache-2.0
#include "GroundMotion.h"
#include "GroundOutput.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input {
 std::vector<std::uint32_t> words;std::size_t at=0;
 std::uint32_t Word(){assert(at<words.size());return words[at++];}
 float Float(){auto word=Word();float v;std::memcpy(&v,&word,4);return v;}
 Vec4 Four(){return {Float(),Float(),Float(),Float()};}
 Vec3 Three(){return {Float(),Float(),Float()};}
 PhysicsGroundState State(){PhysicsGroundState s;s.collision_force_2528=Four();s.collision_point_2544=Four();s.word_2560=Word();s.word_2564=Word();s.vector_2592=Four();s.vector_2608=Four();s.anti_flip_torque_2624=Four();s.steering_push_scalar_2640=Float();s.steering_damped_turn_2644=Float();s.elapsed_2648=Float();s.collision_countdown_2652=Float();s.captured_position_x_2656=Float();s.captured_position_z_2660=Float();s.scalar_2664=Float();s.scalar_2668=Float();s.straighten_scale_2672=Float();s.vector_2688=Four();s.scalar_2704=Float();s.flag_2708=Word()!=0;s.flag_2720=Word()!=0;s.flag_2721=Word()!=0;s.flag_2722=Word()!=0;s.anti_flip_nudge_applied_2723=Word()!=0;s.human_player_2724=Word()!=0;s.controls_latched_2725=Word()!=0;s.captured_position_valid_2726=Word()!=0;s.pinning_2727=Word()!=0;s.was_pinning_2728=Word()!=0;s.flag_2729=Word()!=0;s.push_suppressed_2730=Word()!=0;s.flag_2731=Word()!=0;s.manual_correction_2732=Word()!=0;s.manual_opposition_2733=Word()!=0;s.hang_detection_frames_2740=std::int32_t(Word());s.hang_force_frames_2744=std::int32_t(Word());s.hung_wipeout_frames_2748=std::int32_t(Word());s.anti_flip_nudge_frames_2752=std::int32_t(Word()); return s;}
};
struct Output {
 std::vector<std::uint32_t> words;
 void Word(std::uint32_t v){words.push_back(v);}
 void Float(float v){std::uint32_t word;std::memcpy(&word,&v,4);Word(word);}
 void Four(Vec4 v){for(auto f:v)Float(f);}
 void Three(Vec3 v){Float(v.x);Float(v.y);Float(v.z);}
 void Manual(const ManualState& s){for(float v:{s.filtered_angle_error,s.target_angle,s.measured_angle,s.angular_correction,s.elapsed})Float(v);}
 void Force(QueuedPointForce f){Word(f.tag);Three(f.force_world);Three(f.point_body);}
};
struct Services:ManualGroundBodies,ManualGroundProjection {
 std::array<Vec4,7> velocities;std::array<std::size_t,7> mapping;Output trace;unsigned fail=0,calls=0;
 Vec4 LinearVelocity(std::size_t part)override{const auto v=velocities[mapping[part]];trace.Word(0);trace.Word(part);trace.Four(v);return v;}
 void SetLinearVelocity(std::size_t part,Vec4 v)override{trace.Word(2);trace.Word(part);trace.Four(v);velocities[mapping[part]]=v;}
 bool NormalSpeed(Vec4 normal,Vec4 velocity,float& value,std::string& error)override{++calls;trace.Word(1);trace.Four(normal);trace.Four(velocity);if(calls==fail){error="projection failure";return false;}value=Dot3(normal,velocity);return true;}
};
void Observe(Output& o,const PhysicsGroundOutput& s){
 o.Word(s.skateboard_motion_4.is_push_accelerating);o.Word(s.skateboard_motion_4.is_at_pushable_speed);
 o.Word(bool(s.velocity_projection_36));if(s.velocity_projection_36){o.Four(s.velocity_projection_36->velocity_without_axis_component);o.Word(s.velocity_projection_36->active);}
 const auto& g=s.ground_32;o.Word(g.wall_ride_exit);o.Word(g.anti_flip_nudge_present);o.Word(g.is_pinning);o.Four(g.anti_flip_torque);o.Float(g.time_to_skitch);o.Float(g.skitch_spline_height);o.Float(g.processed_scalar_2720);o.Word(g.processed_flag_2484_bit_13);
 const auto& t=s.state_28;o.Word(t.grab_spline_type);o.Word(t.grab_spline_object_id);o.Word(t.flag_84);o.Word(t.has_world_grab_intent_without_object);o.Word(bool(t.manual_correction_write_78));if(t.manual_correction_write_78)o.Word(*t.manual_correction_write_78);
 o.Word(s.intents_52.has_world_grab_intent);o.Word(s.intents_52.selected_mode_below_speed_threshold_58);o.Word(s.is_grabbing_object_72_304);o.Word(s.manual_opposition_56_168);o.Word(s.push_suppressed_20_596);
}
int main(){
 const std::vector<char> bytes{std::istreambuf_iterator<char>(std::cin),{}};assert(bytes.size()%4==0);Input i;for(std::size_t at=0;at<bytes.size();at+=4){std::uint32_t w;std::memcpy(&w,bytes.data()+at,4);i.words.push_back(w);}Output all;
 const auto cases=i.Word();for(std::uint32_t c=0;c<cases;++c){const auto op=i.Word();Output o;
 switch(op){
 case 0:{const auto normal=i.Four(),angular=i.Four();o.Three(GroundEntryAngularVelocity(normal,angular));break;}
 case 1:{const auto velocity=i.Three();const auto normal=i.Four(),forward=i.Four();o.Float(GroundEntryTargetSpeed(velocity,normal,forward));break;}
 case 2:{const auto physical=i.Four(),animation=i.Four(),axis=i.Four();const auto mass=i.Float(),strength=i.Float(),point=i.Float();o.Force(GroundLandingOnDeckForce(physical,animation,axis,mass,strength,point));break;}
 case 3:{BoardForceQueue q;const auto count=i.Word();for(unsigned j=0;j<count;++j){const auto tag=i.Word();const auto force=i.Three(),point=i.Three();assert(q.Append({tag,force,point}));}const auto mass=i.Float(),dt=i.Float();const auto normal=i.Four();const bool pushing=i.Word()!=0,manual=i.Word()!=0;const auto result=GroundFutureDeckDisplacement(q,mass,dt,normal,pushing,manual);o.Word(bool(result));if(result)o.Three(*result);o.Word(q.Count());for(std::size_t j=0;j<q.Count();++j)o.Force(q.Entries()[j]);break;}
 case 4:{ManualState state{i.Float(),i.Float(),i.Float(),i.Float(),i.Float()};const auto previous=i.Word();const auto scale=i.Float();ManualGroundInput frame{i.Float(),i.Four(),i.Word(),i.Word()};Services services;for(auto& slot:services.mapping)slot=i.Word();for(auto& v:services.velocities)v=i.Four();services.fail=i.Word();const bool entry=i.Word()!=0;std::string error;const bool ok=entry?EnterManualGround(state,previous,scale,frame,services,services,error):RemoveManualVelocityIntoGround(frame,services,services,error);o.Word(ok);o.Manual(state);o.Word(services.calls);o.Word(services.trace.words.size());for(auto w:services.trace.words)o.Word(w);for(auto v:services.velocities)o.Four(v);break;}
 case 5:{const auto state=i.State();GroundOutputFrame frame{i.Four(),i.Four(),i.Float(),i.Float(),i.Float(),i.Float(),i.Word(),i.Word(),i.Word()!=0};GroundOutputSettings settings{{i.Float(),i.Float()},i.Float()};Observe(o,FillGroundPhysicsOutput(state,frame,settings));break;}
 default:return 2;
 }all.Word(c);all.Word(op);all.Word(o.words.size());for(auto w:o.words)all.Word(w);
 }assert(i.at==i.words.size());for(auto w:all.words)for(unsigned j=0;j<4;++j)std::cout.put(char(w>>(j*8)));return std::cout?0:2;
}
