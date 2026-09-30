use skate_core::{math::{Basis3,Vector3},physics::{drive_frames::*,drive_parameters::*,drive_solver::*,joint_builder::*,joint_records::*,rigid_body::*}};
use skate_core::physics::{solver::packed,contact_solver::RetailContactJacobian};
// The production packer is private; include its untouched file as a module.
mod math {pub use skate_core::math::*;}
mod physics {pub use skate_core::physics::*;}
#[path="../../crates/skate-core/src/physics/solver/packing.rs"] mod packing;
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=self.words[self.at];self.at+=1;v}fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn quaternion(&mut self)->RetailQuaternion{RetailQuaternion{x:self.float(),y:self.float(),z:self.float(),w:self.float()}}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn body(&mut self)->RetailDriveBodyState{RetailDriveBodyState{reaction_index:self.word() as usize,state:self.word(),orientation:self.quaternion(),basis:self.basis(),center_of_mass:self.vector(),linear_velocity:self.vector(),angular_velocity:self.vector(),force_acceleration:self.vector(),torque_acceleration:self.vector(),inverse_mass:self.float(),world_inverse_inertia:RetailPackedWorldInverseInertia{full:self.vector(),split:self.vector()}}}
 fn joint_body(&mut self)->RetailJointBodyInput{let b=self.body();RetailJointBodyInput{reaction_guest_address:b.reaction_index as u32,state:b.state,orientation:b.orientation,center_of_mass:b.center_of_mass,basis:b.basis,linear_velocity:b.linear_velocity,angular_velocity:b.angular_velocity,force_acceleration:b.force_acceleration,torque_acceleration:b.torque_acceleration,inverse_mass:b.inverse_mass,world_inverse_inertia:b.world_inverse_inertia}}
 fn frame(&mut self)->RetailDriveFrame{RetailDriveFrame{orientation:self.quaternion(),translation:self.vector()}}
 fn params(&mut self)->RetailDriveParams{let spring_or_max_velocity=self.float();let damping=self.float();let max_strength=self.float();let drive_type=match self.word(){0=>RetailDriveType::NoDrive,1=>RetailDriveType::SoftDrive,2=>RetailDriveType::HardDrive,_=>panic!("type")};RetailDriveParams{spring_or_max_velocity,damping,max_strength,drive_type}}
}
fn floats(out:&mut Vec<u32>,v:impl IntoIterator<Item=f32>){out.extend(v.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn params(out:&mut Vec<u32>,p:RetailDriveParams){floats(out,[p.spring_or_max_velocity,p.damping,p.max_strength]);out.push(p.drive_type as u32);}
fn dynamics(out:&mut Vec<u32>,d:RetailDriveDynamics){params(out,d.linear);params(out,d.angular);}
fn rows(out:&mut Vec<u32>,d:RetailDriveRows){
 vector(out,d.arm_a);vector(out,d.arm_b);for v in d.linear_axes{vector(out,v);}for v in d.angular_axes{vector(out,v);}
 floats(out,d.linear_inverse_effective_mass);floats(out,d.angular_inverse_effective_mass);floats(out,[d.linear_softness,d.angular_softness]);
 for v in [d.linear_target_impulse,d.angular_target_impulse,d.linear_maximum_impulse,d.angular_maximum_impulse,d.accumulated_linear_impulse,d.accumulated_angular_impulse]{floats(out,v);}
 let p=packing::drive(&d);out.extend(p.words);out.push(p.reaction_a as u32);out.push(p.reaction_b as u32);
}
fn main(){let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for _ in 0..count{match i.word(){
  0=>{let parameters=RetailJointParametersRaw{words:std::array::from_fn(|_|i.word())};let frames=RetailJointFramesRaw{words:std::array::from_fn(|_|i.word())};let body_a=i.joint_body();let body_b=i.joint_body();let time_step=i.float();let joint_guest_address=i.word();out.extend(build_retail_joint_jacobian(RetailJointBuildInput{parameters,frames,body_a,body_b,time_step,joint_guest_address}).words);},
  1=>{let a=i.body();let b=i.body();let frames=RetailDriveFrames{body_a:i.frame(),body_b:i.frame()};let d=RetailDriveDynamics{linear:i.params(),angular:i.params()};let dt=i.float();rows(&mut out,build_drive_rows(a,b,frames,d,dt));},
  2=>{let s=RetailTruckDriveSettings{use_linear_drives:i.word()!=0,use_hard_linear_drives:i.word()!=0,angular_displacement:i.float(),angular_damping:i.float(),angular_strength:i.float()};dynamics(&mut out,retail_truck_drive_dynamics(s));dynamics(&mut out,retail_wheel_drive_dynamics(false));dynamics(&mut out,retail_wheel_drive_dynamics(true));},
  _=>panic!("operation")}}
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
