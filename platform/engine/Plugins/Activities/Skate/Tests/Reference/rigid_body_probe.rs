// Temporary independent migration oracle; original implementations are unmodified.
use skate_core::{math::{Basis3,Vector3},physics::rigid_body::*};
use std::io::{Read,Write};
struct Input { words:Vec<u32>, at:usize }
impl Input {
 fn word(&mut self)->u32 {let value=self.words[self.at];self.at+=1;value}
 fn float(&mut self)->f32 {f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3 {Vector3::new(self.float(),self.float(),self.float())}
 fn quat(&mut self)->RetailQuaternion {RetailQuaternion{x:self.float(),y:self.float(),z:self.float(),w:self.float()}}
 fn basis(&mut self)->Basis3 {Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}
}
fn vector(out:&mut Vec<u32>,v:Vector3){out.extend([v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}
fn basis(out:&mut Vec<u32>,b:Basis3){for c in b.columns{out.extend(c.map(f32::to_bits));}}
fn quat(out:&mut Vec<u32>,q:RetailQuaternion){out.extend([q.x,q.y,q.z,q.w].map(f32::to_bits));}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);
 let mut input=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();
 let count=input.word();for _ in 0..count{let op=input.word();match op{
  0|5=>{let mut body=input.words::<44>();let inertia=input.words::<10>();let sim=RetailSimulationStep{time_step:input.float(),frequency:input.float(),cool_down:input.word(),minimum_energy:input.float(),gravity_acceleration:input.vector()};let mut corrections=input.words::<16>();let steps=input.word();
    if op==0 {for _ in 0..steps{let result=dynamic_update_packed(&mut body,&inertia,sim,&mut corrections);out.extend(body);out.extend(corrections);out.extend(result.orientation_displacement.map(f32::to_bits));out.extend([result.linear_speed_squared.to_bits(),result.angular_speed_squared.to_bits()]);}}
    else {let v=|offset|Vector3::new(f32::from_bits(body[offset]),f32::from_bits(body[offset+1]),f32::from_bits(body[offset+2]));let mut b=RetailBodyRates{orientation:RetailQuaternion{x:f32::from_bits(body[0]),y:f32::from_bits(body[1]),z:f32::from_bits(body[2]),w:f32::from_bits(body[3])},basis:Basis3{columns:[[0.;3];3]},world_inverse_inertia:Basis3{columns:[[0.;3];3]},position:v(4),linear_velocity:v(8),angular_velocity:v(12),force_acceleration:v(36),torque_acceleration:v(40),kinetic_energy:f32::from_bits(body[39]),cool_down:body[43]};
      let data=RetailInertiaDynamics{inverse_tensor:Vector3::new(f32::from_bits(inertia[0]),f32::from_bits(inertia[1]),f32::from_bits(inertia[2])),inverse_mass:f32::from_bits(inertia[4]),spherical:f32::from_bits(inertia[5]),maximum_linear_velocity:f32::from_bits(inertia[6]),maximum_angular_velocity:f32::from_bits(inertia[7]),linear_drag:f32::from_bits(inertia[8]),angular_drag:f32::from_bits(inertia[9])};
      let rv=|o|Vector3::new(f32::from_bits(corrections[o]),f32::from_bits(corrections[o+1]),f32::from_bits(corrections[o+2]));let mut r=RetailReactionCorrections{linear_displacement:rv(0),position_displacement:rv(4),angular_displacement:rv(8),orientation_displacement:rv(12)};
      for _ in 0..steps{let result=integrate_body_rates(b,data,sim,r);b=result.state;r=RetailReactionCorrections::default();quat(&mut out,b.orientation);basis(&mut out,b.basis);basis(&mut out,b.world_inverse_inertia);for v in [b.position,b.linear_velocity,b.angular_velocity,b.force_acceleration,b.torque_acceleration]{vector(&mut out,v);}out.extend([b.kinetic_energy.to_bits(),b.cool_down]);vector(&mut out,result.orientation_displacement);out.extend([result.linear_speed_squared.to_bits(),result.angular_speed_squared.to_bits()]);}
    }
  },
  1=>{let q=input.quat();let v=input.vector();quat(&mut out,integrate_orientation(q,v));basis(&mut out,basis_from_quaternion(q));},
  2=>{let b=input.basis();let v=input.vector();basis(&mut out,world_inverse_inertia(b,v));},
  3=>{let b=input.basis();let v=input.vector();let p=pack_world_inverse_inertia(b);vector(&mut out,p.full);vector(&mut out,p.split);vector(&mut out,multiply_packed_world_inverse_inertia(p,v));},
  4=>{let a=RetailForceAccumulator{force_acceleration:input.vector(),torque_acceleration:input.vector(),cool_down:input.word()};let force=input.vector();let point=input.vector();let deck=input.basis();let mass=input.float();let inertia=input.basis();let result=accumulate_point_force(a,force,point,deck,mass,inertia);vector(&mut out,result.force_acceleration);vector(&mut out,result.torque_acceleration);out.push(result.cool_down);},
  6=>{let s=RetailSimulationStep::fixed_60_hz(input.word(),input.float(),input.vector());out.extend([s.time_step.to_bits(),s.frequency.to_bits(),s.cool_down,s.minimum_energy.to_bits()]);vector(&mut out,s.gravity_acceleration);},
  7=>{use skate_core::physics::mass::{MassShape,primitive_mass};let kind=input.word();let radius=input.float();let half_length=input.float();let padding=input.float();let half_extents=input.vector();let shape=match kind{0=>MassShape::Sphere{radius},1=>MassShape::Capsule{radius,half_length},2=>MassShape::RoundedBox{radius,half_extents},3=>MassShape::Cylinder{radius,half_length,padding},4=>MassShape::Unsupported,_=>panic!("shape")};match primitive_mass(shape){Some(v)=>{out.push(1);vector(&mut out,v.moments_per_unit_mass);out.push(v.volume.to_bits());},None=>out.push(0)}},
  _=>panic!("unknown operation")
 }}assert_eq!(input.at,input.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
