// Appended to the frozen full crate root. Original producers stay unchanged.
use std::io::{Read,Write};
use crate::{math::Vector3,physics::{force_queue::{BoardForceQueue,QueuedPointForce},rigid_body::RetailInertiaDynamics},
 riding::{ground_correction_math as geometry,grounded::{drag::{BodyInertias,DragSelection,DragBindingError,GroundDragInput},
 state::{data::PhysicsGroundState,corrections::*}},braking::LinearDragSettings}};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn four(&mut self)->[f32;4]{std::array::from_fn(|_|self.float())}
 fn three(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn state(&mut self)->PhysicsGroundState{PhysicsGroundState{collision_force_2528:self.four(),collision_point_2544:self.four(),word_2560:self.word(),word_2564:self.word(),vector_2592:self.four(),vector_2608:self.four(),anti_flip_torque_2624:self.four(),steering_push_scalar_2640:self.float(),steering_damped_turn_2644:self.float(),elapsed_2648:self.float(),collision_countdown_2652:self.float(),captured_position_x_2656:self.float(),captured_position_z_2660:self.float(),scalar_2664:self.float(),scalar_2668:self.float(),straighten_scale_2672:self.float(),vector_2688:self.four(),scalar_2704:self.float(),flag_2708:self.word()!=0,flag_2720:self.word()!=0,flag_2721:self.word()!=0,flag_2722:self.word()!=0,anti_flip_nudge_applied_2723:self.word()!=0,human_player_2724:self.word()!=0,controls_latched_2725:self.word()!=0,captured_position_valid_2726:self.word()!=0,pinning_2727:self.word()!=0,was_pinning_2728:self.word()!=0,flag_2729:self.word()!=0,push_suppressed_2730:self.word()!=0,flag_2731:self.word()!=0,manual_correction_2732:self.word()!=0,manual_opposition_2733:self.word()!=0,hang_detection_frames_2740:self.word() as i32,hang_force_frames_2744:self.word() as i32,hung_wipeout_frames_2748:self.word() as i32,anti_flip_nudge_frames_2752:self.word() as i32}}
 fn inertia(&mut self)->RetailInertiaDynamics{RetailInertiaDynamics{inverse_tensor:self.three(),inverse_mass:self.float(),spherical:self.float(),maximum_linear_velocity:self.float(),maximum_angular_velocity:self.float(),linear_drag:self.float(),angular_drag:self.float()}}
}
fn floats(o:&mut Vec<u32>,v:[f32;4]){o.extend(v.map(f32::to_bits));}
fn state(o:&mut Vec<u32>,s:&PhysicsGroundState){floats(o,s.collision_force_2528);
floats(o,s.collision_point_2544);
o.push(s.word_2560 as u32);
o.push(s.word_2564 as u32);
floats(o,s.vector_2592);
floats(o,s.vector_2608);
floats(o,s.anti_flip_torque_2624);
o.push(s.steering_push_scalar_2640.to_bits());
o.push(s.steering_damped_turn_2644.to_bits());
o.push(s.elapsed_2648.to_bits());
o.push(s.collision_countdown_2652.to_bits());
o.push(s.captured_position_x_2656.to_bits());
o.push(s.captured_position_z_2660.to_bits());
o.push(s.scalar_2664.to_bits());
o.push(s.scalar_2668.to_bits());
o.push(s.straighten_scale_2672.to_bits());
floats(o,s.vector_2688);
o.push(s.scalar_2704.to_bits());
o.push(s.flag_2708 as u32);
o.push(s.flag_2720 as u32);
o.push(s.flag_2721 as u32);
o.push(s.flag_2722 as u32);
o.push(s.anti_flip_nudge_applied_2723 as u32);
o.push(s.human_player_2724 as u32);
o.push(s.controls_latched_2725 as u32);
o.push(s.captured_position_valid_2726 as u32);
o.push(s.pinning_2727 as u32);
o.push(s.was_pinning_2728 as u32);
o.push(s.flag_2729 as u32);
o.push(s.push_suppressed_2730 as u32);
o.push(s.flag_2731 as u32);
o.push(s.manual_correction_2732 as u32);
o.push(s.manual_opposition_2733 as u32);
o.push(s.hang_detection_frames_2740 as u32);
o.push(s.hang_force_frames_2744 as u32);
o.push(s.hung_wipeout_frames_2748 as u32);
o.push(s.anti_flip_nudge_frames_2752 as u32);}
struct Services{start:[f32;4],end:[f32;4],deck:[f32;4],y:[f32;4],z:[f32;4],hung:bool,fail:u32,calls:u32,last_error:u32,log:Vec<u32>}
impl Services{
 fn gate(&mut self,id:u32,vectors:&[[f32;4]])->Result<(),u32>{
 self.calls+=1;self.log.extend([id,(vectors.len()*4) as u32]);for v in vectors{self.log.extend(v.map(f32::to_bits));}
 if self.calls==self.fail{self.last_error=id;Err(id)}else{Ok(())}
 }
}
impl AntiFlipNudgeMath for Services{type Error=u32;
 fn dot3(&mut self,a:[f32;4],b:[f32;4])->Result<f32,u32>{self.gate(1,&[a,b])?;Ok(geometry::dot_product(a,b))}
 fn scale_to_magnitude(&mut self,v:[f32;4],square:f32,size:f32)->Result<[f32;4],u32>{self.gate(2,&[v,[square,size,0.,0.]])?;Ok(geometry::scale_to_magnitude(v,square,size))}
}
impl HangUpServices for Services{type Error=u32;
 fn build_hang_force(&mut self)->Result<[f32;4],u32>{self.gate(3,&[])?;Ok(geometry::hang_force(self.start,self.end,self.deck))}
 fn apply_hang_force(&mut self,v:[f32;4])->Result<(),u32>{self.gate(4,&[v])}
 fn detect_hung_up_geometry(&mut self)->Result<bool,u32>{self.gate(5,&[])?;Ok(self.hung)}
 fn request_wipeout(&mut self)->Result<(),u32>{self.gate(6,&[])}
}
impl HalfpipeWheelCatchServices for Services{type Error=u32;
 fn angular_displacement(&mut self)->Result<[f32;4],u32>{self.gate(7,&[])?;Ok(geometry::wheel_catch_displacement(self.y,self.z))}
 fn apply_angular_displacement(&mut self,v:[f32;4])->Result<(),u32>{self.gate(8,&[v])}
}
impl PinningServices for Services{type Error=u32;
 fn pin_to_captured_position(&mut self,x:f32,z:f32)->Result<(),u32>{self.gate(9,&[[x,z,0.,0.]])}
}
fn fill(q:&mut BoardForceQueue,n:u32){q.clear();for j in 0..n{assert!(q.append(QueuedPointForce{tag:100+j,force_world:Vector3::new(j as f32,j as f32+0.25,-(j as f32)),point_body:Vector3::new(0.1,0.2,0.3)}));}}
fn frame(o:&mut Vec<u32>,s:&PhysicsGroundState,q:&BoardForceQueue,indices:&[usize],inertias:&[RetailInertiaDynamics]){
 state(o,s);o.push(q.entries().len() as u32);for f in q.entries(){o.push(f.tag);o.extend([f.force_world.x,f.force_world.y,f.force_world.z,f.point_body.x,f.point_body.y,f.point_body.z].map(f32::to_bits));}
 o.push(indices.len() as u32);o.extend(indices.iter().map(|v|*v as u32));o.push(inertias.len() as u32);for i in inertias{o.extend([i.inverse_tensor.x,i.inverse_tensor.y,i.inverse_tensor.z,i.inverse_mass,i.spherical,i.maximum_linear_velocity,i.maximum_angular_velocity,i.linear_drag,i.angular_drag].map(f32::to_bits));}
}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let cases=i.word();let mut o=Vec::new();
 for c in 0..cases{
  let mut s=i.state();let mut q=BoardForceQueue::default();fill(&mut q,i.word());
  let mut services=Services{start:i.four(),end:i.four(),deck:i.four(),y:i.four(),z:i.four(),hung:false,fail:0,calls:0,last_error:0,log:Vec::new()};
  let mut indices=Vec::new();let mut inertias=Vec::new();let n=i.word();o.extend([c,n,0]);let mark=o.len()-1;frame(&mut o,&s,&q,&indices,&inertias);
  for _ in 0..n{
   let op=i.word();let mut ok=true;let mut a=0;let mut b=0;services.log.clear();services.last_error=0;
   match op{
   0=>s=PhysicsGroundState::before_first_enter(i.word()!=0),1=>s.begin_entry(),2=>s.finish_entry(i.word()),
   3=>{let contacts=i.word() as i32;a=s.begin_update_at(contacts,i.four()).set_skeleton_flag_16505 as u32;},4=>s.finish_update(i.float()),
   5=>{let input=AntiFlipNudgeInput{deck_speed_2652:i.float(),deck_axis_96:i.four()};match update_anti_flip_nudge(&mut s,input,&mut q,&mut services){Ok(r)=>{a=r.attempted as u32;b=r.queued as u32;},Err(_)=>ok=false};},
   6=>{let input=HangUpInput{flags_1516:i.word(),deck_speed_2652:i.float(),scalar_84:i.float(),geometry_axis_dot_positive:i.word()!=0};ok=manage_hang_ups(&mut s,input,&mut services).is_ok();},
   7=>{let input=HalfpipeWheelCatchInput{flags_1516:i.word(),deck_speed_2652:i.float(),deck_x_axis_y:i.float(),deck_y_axis_y:i.float(),signed_deck_distance:i.float()};match manage_halfpipe_wheel_catches(input,&mut services){Ok(r)=>a=r as u32,Err(_)=>ok=false};},
   8=>{let input=PinningInput{flags_2488:i.word(),frames_since_teleport_2584:i.word() as i32,flags_2472:i.word()};ok=consider_pinning(&mut s,input,&mut services).is_ok();},
   9=>s.anti_flip_torque_2624=i.four(),10=>{services.fail=i.word();services.hung=i.word()!=0;services.calls=0;},11=>s=i.state(),12=>fill(&mut q,i.word()),
   13=>{indices.clear();let ni=i.word();for _ in 0..ni{indices.push(i.word() as usize);}inertias.clear();let nb=i.word();for _ in 0..nb{inertias.push(i.inertia());}},
   14=>{let selected=i.word()!=0;let part=i.word() as usize;let drag=i.float();let mut bindings=BodyInertias{part_inertia_indices:&indices,inertias:&mut inertias};match bindings.set_linear_drag(drag,if selected{DragSelection::Part(part)}else{DragSelection::AllParts}){Ok(())=>{},Err(e)=>{ok=false;a=100+match e{DragBindingError::PartOutsideAssembly=>0,DragBindingError::InertiaOutsideStorage=>1};}}},
   15=>{let input=GroundDragInput{flags_2468:i.word(),absolute_body_speed_2616:i.float(),balance_2720:i.float(),scalar_2724:i.float(),ground_normal_y:i.float()};let settings=LinearDragSettings{brake_speed:i.float(),balance_speed:i.float(),comparison_threshold:i.float(),balance_drag:i.float()};a=input.calculate(settings).to_bits();},
   _=>panic!("Ground state operation")}
   o.extend([op,ok as u32,a,b,services.last_error,services.calls,services.log.len() as u32]);o.extend(&services.log);frame(&mut o,&s,&q,&indices,&inertias);
  }o[mark]=(o.len()-mark-1) as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in o{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
