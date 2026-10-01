use riding::ground_correction_math as correction;
use riding::ground_contact_response::{WallRideSettings,WallRidePhysical,wall_ride_response};
use riding::grounded::state::board_types::GroundContactFrame;
use physics::assembly::BodySnapshot;
use physics::rigid_body::{RetailBodyRates as BodyRates,RetailInertiaDynamics as InertiaDynamics,RetailQuaternion};
use math::{Basis3,Vector3};
use point_graph::PointGraph;
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input {
 fn word(&mut self)->u32{let v=self.words[self.at];self.at+=1;v}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn three(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn four(&mut self)->[f32;4]{std::array::from_fn(|_|self.float())}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn curve(&mut self)->PointGraph<8>{PointGraph{x:std::array::from_fn(|_|self.float()),y:std::array::from_fn(|_|self.float())}}
 fn body(&mut self)->BodySnapshot{
  let state_flags=self.word();let q=self.four();
  let rates=BodyRates{orientation:RetailQuaternion{x:q[0],y:q[1],z:q[2],w:q[3]},basis:self.basis(),world_inverse_inertia:self.basis(),position:self.three(),linear_velocity:self.three(),angular_velocity:self.three(),force_acceleration:self.three(),torque_acceleration:self.three(),kinetic_energy:self.float(),cool_down:self.word()};
  let inertia=InertiaDynamics{inverse_tensor:self.three(),inverse_mass:self.float(),spherical:self.float(),maximum_linear_velocity:self.float(),maximum_angular_velocity:self.float(),linear_drag:self.float(),angular_drag:self.float()};BodySnapshot{state_flags,rates,inertia}
 }
}
fn floats(o:&mut Vec<u32>,v:impl IntoIterator<Item=f32>){o.extend(v.into_iter().map(f32::to_bits));}
fn vector(o:&mut Vec<u32>,v:Vector3){floats(o,[v.x,v.y,v.z]);}
fn body(o:&mut Vec<u32>,b:BodySnapshot){
 o.push(b.state_flags);let r=b.rates;floats(o,[r.orientation.x,r.orientation.y,r.orientation.z,r.orientation.w]);
 for c in r.basis.columns{floats(o,c);}for c in r.world_inverse_inertia.columns{floats(o,c);}
 for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration]{vector(o,v);}
 o.extend([r.kinetic_energy.to_bits(),r.cool_down]);let d=b.inertia;vector(o,d.inverse_tensor);floats(o,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);
}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut o=Vec::new();let cases=i.word();
 for c in 0..cases{let op=i.word();o.extend([c,op,0]);let mark=o.len()-1;match op{
  0=>o.push(correction::center_of_mass_height(i.four()).to_bits()),
  1=>{let a=i.four();let b=i.four();o.push(correction::collision_force_projection(a,b).to_bits());},
  2=>{let a=i.four();let b=i.four();floats(&mut o,correction::edge_direction(a,b));},
  3=>floats(&mut o,correction::edge_up(i.four())),
  4=>{let a=i.four();let b=i.four();let d=i.four();floats(&mut o,correction::hang_force(a,b,d));},
  5=>{let y=i.four();let z=i.four();floats(&mut o,correction::wheel_catch_displacement(y,z));},
  6=>{let p=i.four();let x=i.float();let z=i.float();let dt=i.float();floats(&mut o,correction::pinning_velocity(p,x,z,dt));},
  7=>{let v=i.four();let squared=i.float();let magnitude=i.float();floats(&mut o,correction::scale_to_magnitude(v,squared,magnitude));},
  8=>{let mut b=i.body();let deck=i.three();body(&mut o,b);let count=i.word();o.push(count);for _ in 0..count{let force=i.three();let point=i.three();correction::apply_world_force(&mut b,deck,force,point);body(&mut o,b);}},
  9=>{
   let settings=WallRideSettings{anti_gravity_vs_time:i.curve(),max_dot_floor_wall:i.float(),foot_force_time:i.float(),auto_jump_height:i.float(),max_time:i.float(),velocity_time_to_consider:i.float(),auto_jump_y_down_scalar:i.float(),auto_jump_force:i.float()};
   let physical=WallRidePhysical{board_normal:i.four(),up:i.four(),velocity:i.four(),board_mass:i.float(),gravity:i.float(),speed:i.float(),contact_count:i.word() as i32};
   let frame=GroundContactFrame{vector_8032:i.four(),vector_8048:i.four(),vector_8064:i.four(),word_8080:i.word(),flag_8084:i.word()!=0,scalar_2752:i.float(),scalar_2756:i.float()};
   let r=wall_ride_response(&settings,physical,frame,i.four());o.extend([r.active_2731 as u32,r.tag_16_force.tag]);vector(&mut o,r.tag_16_force.force_world);vector(&mut o,r.tag_16_force.point_body);floats(&mut o,r.vector_2688);o.extend([r.scalar_2704.to_bits(),r.animated_board_2708 as u32]);
  },_=>panic!("Unknown ground correction operation")};o[mark]=(o.len()-mark-1) as u32;
 }
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in o{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
