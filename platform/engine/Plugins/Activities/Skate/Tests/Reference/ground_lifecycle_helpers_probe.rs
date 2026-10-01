// Protocol appended to the frozen full crate root; no original producers changed.
use std::{io::{Read,Write},rc::Rc,cell::RefCell};
use crate::{math::Vector3,physics::{force_queue::{BoardForceQueue,QueuedPointForce},manual::state::ManualState},riding::{grounded::{state::{motion,output::*,data::PhysicsGroundState},manual_entry::{self,ManualGroundInput,ManualGroundBodies,ManualGroundProjection}},ground_correction_math}};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn four(&mut self)->[f32;4]{core::array::from_fn(|_|self.float())}
 fn three(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn state(&mut self)->PhysicsGroundState{PhysicsGroundState{collision_force_2528:self.four(),collision_point_2544:self.four(),word_2560:self.word(),word_2564:self.word(),vector_2592:self.four(),vector_2608:self.four(),anti_flip_torque_2624:self.four(),steering_push_scalar_2640:self.float(),steering_damped_turn_2644:self.float(),elapsed_2648:self.float(),collision_countdown_2652:self.float(),captured_position_x_2656:self.float(),captured_position_z_2660:self.float(),scalar_2664:self.float(),scalar_2668:self.float(),straighten_scale_2672:self.float(),vector_2688:self.four(),scalar_2704:self.float(),flag_2708:self.word()!=0,flag_2720:self.word()!=0,flag_2721:self.word()!=0,flag_2722:self.word()!=0,anti_flip_nudge_applied_2723:self.word()!=0,human_player_2724:self.word()!=0,controls_latched_2725:self.word()!=0,captured_position_valid_2726:self.word()!=0,pinning_2727:self.word()!=0,was_pinning_2728:self.word()!=0,flag_2729:self.word()!=0,push_suppressed_2730:self.word()!=0,flag_2731:self.word()!=0,manual_correction_2732:self.word()!=0,manual_opposition_2733:self.word()!=0,hang_detection_frames_2740:self.word() as i32,hang_force_frames_2744:self.word() as i32,hung_wipeout_frames_2748:self.word() as i32,anti_flip_nudge_frames_2752:self.word() as i32}}
}
struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,v:u32){self.0.push(v);}
 fn float(&mut self,v:f32){self.word(v.to_bits());}
 fn four(&mut self,v:[f32;4]){self.0.extend(v.map(f32::to_bits));}
 fn three(&mut self,v:Vector3){for f in [v.x,v.y,v.z]{self.float(f);}}
 fn manual(&mut self,s:&ManualState){for f in [s.filtered_angle_error,s.target_angle,s.measured_angle,s.angular_correction,s.elapsed]{self.float(f);}}
 fn force(&mut self,f:QueuedPointForce){self.word(f.tag);self.three(f.force_world);self.three(f.point_body);}
}
struct Bodies{velocities:[[f32;4];7],mapping:[usize;7],trace:Rc<RefCell<Output>>}
impl ManualGroundBodies for Bodies{
 fn linear_velocity(&mut self,part:usize)->[f32;4]{let v=self.velocities[self.mapping[part]];let mut log=self.trace.borrow_mut();log.word(0);log.word(part as u32);log.four(v);v}
 fn set_linear_velocity(&mut self,part:usize,v:[f32;4]){let mut log=self.trace.borrow_mut();log.word(2);log.word(part as u32);log.four(v);self.velocities[self.mapping[part]]=v;}
}
struct Projection{fail:u32,calls:u32,trace:Rc<RefCell<Output>>}
impl ManualGroundProjection for Projection{type Error=();
 fn normal_speed(&mut self,normal:[f32;4],velocity:[f32;4])->Result<f32,()>{self.calls+=1;let mut log=self.trace.borrow_mut();log.word(1);log.four(normal);log.four(velocity);if self.calls==self.fail{Err(())}else{Ok(ground_correction_math::dot_product(normal,velocity))}}
}
fn observe(o:&mut Output,s:PhysicsGroundOutput){
 o.word(s.skateboard_motion_4.is_push_accelerating as u32);o.word(s.skateboard_motion_4.is_at_pushable_speed as u32);
 o.word(s.velocity_projection_36.is_some() as u32);if let Some(p)=s.velocity_projection_36{o.four(p.velocity_without_axis_component);o.word(p.active as u32);}
 let g=s.ground_32;o.word(g.wall_ride_exit as u32);o.word(g.anti_flip_nudge_present as u32);o.word(g.is_pinning as u32);o.four(g.anti_flip_torque);o.float(g.time_to_skitch);o.float(g.skitch_spline_height);o.float(g.processed_scalar_2720);o.word(g.processed_flag_2484_bit_13 as u32);
 let t=s.state_28;o.word(t.grab_spline_type);o.word(t.grab_spline_object_id);o.word(t.flag_84 as u32);o.word(t.has_world_grab_intent_without_object as u32);o.word(t.manual_correction_write_78.is_some() as u32);if let Some(v)=t.manual_correction_write_78{o.word(v as u32);}
 o.word(s.intents_52.has_world_grab_intent as u32);o.word(s.intents_52.selected_mode_below_speed_threshold_58 as u32);o.word(s.is_grabbing_object_72_304 as u32);o.word(s.manual_opposition_56_168 as u32);o.word(s.push_suppressed_20_596 as u32);
}
fn main(){let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut all=Output(Vec::new());let cases=i.word();for c in 0..cases{let op=i.word();let mut o=Output(Vec::new());match op{
 0=>{let normal=i.four();let angular=i.four();o.three(motion::entry_angular_velocity(normal,angular));},
 1=>{let velocity=i.three();let normal=i.four();let forward=i.four();o.float(motion::entry_target_speed(velocity,normal,forward));},
 2=>{let physical=i.four();let animation=i.four();let axis=i.four();let mass=i.float();let strength=i.float();let point=i.float();o.force(motion::landing_on_deck_force(physical,animation,axis,mass,strength,point));},
 3=>{let mut q=BoardForceQueue::default();let count=i.word();for _ in 0..count{let tag=i.word();let force_world=i.three();let point_body=i.three();assert!(q.append(QueuedPointForce{tag,force_world,point_body}));}let mass=i.float();let dt=i.float();let normal=i.four();let pushing=i.word()!=0;let manual=i.word()!=0;let result=motion::future_deck_displacement(&q,mass,dt,normal,pushing,manual);o.word(result.is_some() as u32);if let Some(v)=result{o.three(v);}o.word(q.entries().len() as u32);for f in q.entries(){o.force(*f);}},
 4=>{let mut state=ManualState{filtered_angle_error:i.float(),target_angle:i.float(),measured_angle:i.float(),angular_correction:i.float(),elapsed:i.float()};let previous=i.word();let scale=i.float();let frame=ManualGroundInput{balance:i.float(),ground_normal:i.four(),flags_2468:i.word(),flags_2472:i.word()};let mapping=core::array::from_fn(|_|i.word() as usize);let velocities=core::array::from_fn(|_|i.four());let fail=i.word();let entry=i.word()!=0;let trace=Rc::new(RefCell::new(Output(Vec::new())));let mut bodies=Bodies{velocities,mapping,trace:trace.clone()};let mut projection=Projection{fail,calls:0,trace:trace.clone()};let result=if entry{manual_entry::enter_ground(&mut state,previous,scale,frame,&mut bodies,&mut projection)}else{manual_entry::remove_velocity_into_ground(frame,&mut bodies,&mut projection)};o.word(result.is_ok() as u32);o.manual(&state);o.word(projection.calls);let log=trace.borrow();o.word(log.0.len() as u32);o.0.extend(&log.0);for v in bodies.velocities{o.four(v);}},
 5=>{let state=i.state();let frame=GroundOutputFrame{axis_464:i.four(),velocity_608:i.four(),absolute_body_speed_2616:i.float(),deck_speed_2652:i.float(),state_timer_2664:i.float(),scalar_2720:i.float(),flags_2476:i.word(),flags_2484:i.word(),selected_mode_flag_109:i.word()!=0};let settings=GroundOutputSettings{pushable_speed_terms_4_8:[i.float(),i.float()],mode_speed_threshold_0:i.float()};observe(&mut o,fill_physics_output(&state,frame,settings));},
 _=>panic!("Ground lifecycle helper opcode")};all.word(c);all.word(op);all.word(o.0.len() as u32);all.0.extend(o.0);}assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in all.0{stdout.write_all(&w.to_le_bytes()).unwrap();}}
