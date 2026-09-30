use skate_core::{math::{Basis3,Vector3},physics::{assembly::*,board::BODY_COUNT,drive_frames::*,drive_parameters::*,drive_solver::*,rigid_body::*,hook_drive::HookDriveState,mass::default_skateboard_mass_properties,solver::{self,packed},contact_solver::RetailContactJacobian}};
mod math {pub use skate_core::math::*;}
mod physics {pub use skate_core::physics::*;}
#[path="../../crates/skate-core/src/physics/solver/packing.rs"] mod packing;
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn quat(&mut self)->RetailQuaternion{RetailQuaternion{x:self.float(),y:self.float(),z:self.float(),w:self.float()}}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn body(&mut self)->BodySnapshot{BodySnapshot{state_flags:self.word(),rates:RetailBodyRates{orientation:self.quat(),basis:self.basis(),world_inverse_inertia:self.basis(),position:self.vector(),linear_velocity:self.vector(),angular_velocity:self.vector(),force_acceleration:self.vector(),torque_acceleration:self.vector(),kinetic_energy:self.float(),cool_down:self.word()},inertia:RetailInertiaDynamics{inverse_tensor:self.vector(),inverse_mass:self.float(),spherical:self.float(),maximum_linear_velocity:self.float(),maximum_angular_velocity:self.float(),linear_drag:self.float(),angular_drag:self.float()}}}
}
fn floats(out:&mut Vec<u32>,values:impl IntoIterator<Item=f32>){out.extend(values.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn quat(out:&mut Vec<u32>,q:RetailQuaternion){floats(out,[q.x,q.y,q.z,q.w]);}
fn basis(out:&mut Vec<u32>,b:Basis3){for c in b.columns{floats(out,c);}}
fn rates(out:&mut Vec<u32>,r:RetailBodyRates){quat(out,r.orientation);basis(out,r.basis);basis(out,r.world_inverse_inertia);for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration]{vector(out,v);}out.extend([r.kinetic_energy.to_bits(),r.cool_down]);}
fn frame(out:&mut Vec<u32>,f:RetailDriveFrame){quat(out,f.orientation);vector(out,f.translation);}
fn joint(out:&mut Vec<u32>,j:&solver::JointConstraint){out.extend(j.jacobian.words);out.extend([j.reaction_a as u32,j.reaction_b as u32]);}
fn packed_drive(out:&mut Vec<u32>,d:&RetailDriveRows){let p=packing::drive(d);out.extend(p.words);out.extend([p.reaction_a as u32,p.reaction_b as u32]);}
fn drive_body(out:&mut Vec<u32>,b:RetailDriveBodyState){out.extend([b.reaction_index as u32,b.state]);quat(out,b.orientation);basis(out,b.basis);for v in [b.center_of_mass,b.linear_velocity,b.angular_velocity,b.force_acceleration,b.torque_acceleration]{vector(out,v);}out.push(b.inverse_mass.to_bits());vector(out,b.world_inverse_inertia.full);vector(out,b.world_inverse_inertia.split);}
fn drive(out:&mut Vec<u32>,d:&RetailDriveRows){drive_body(out,d.frame_a_body);drive_body(out,d.frame_b_body);vector(out,d.arm_a);vector(out,d.arm_b);for v in d.linear_axes.into_iter().chain(d.angular_axes){vector(out,v);}floats(out,d.linear_inverse_effective_mass);floats(out,d.angular_inverse_effective_mass);floats(out,[d.linear_softness,d.angular_softness]);for v in [d.linear_target_impulse,d.angular_target_impulse,d.linear_maximum_impulse,d.angular_maximum_impulse,d.accumulated_linear_impulse,d.accumulated_angular_impulse]{floats(out,v);}packed_drive(out,d);}
fn stock_bodies()->[BodySnapshot;BODY_COUNT]{let poses=default_live_body_transforms();let orientations=default_live_body_orientations();let mass=default_skateboard_mass_properties();std::array::from_fn(|n|{let basis=basis_from_quaternion(orientations[n]);BodySnapshot{state_flags:4,inertia:mass[n].dynamics,rates:RetailBodyRates{orientation:orientations[n],basis,world_inverse_inertia:world_inverse_inertia(basis,mass[n].dynamics.inverse_tensor),position:poses[n].translation,linear_velocity:Vector3::ZERO,angular_velocity:Vector3::ZERO,force_acceleration:Vector3::ZERO,torque_acceleration:Vector3::ZERO,kinetic_energy:0.0,cool_down:0}}})}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let cases=i.word();
 for _ in 0..cases{
  let start=out.len();out.push(0);let stock=i.word()!=0;
  let (bodies,hook_body)=if stock{let mut b=stock_bodies();let mut h=b[6];for body in &mut b{body.state_flags=i.word();}h.state_flags=i.word();(b,h)}else{(std::array::from_fn(|_|i.body()),i.body())};
  let mut hook=BoardHook{body:hook_body,drive:HookDriveState{frames:std::array::from_fn(|_|i.word()),dynamics:std::array::from_fn(|_|i.word())}};
  let base=std::array::from_fn(|_|RetailAffineTransform{basis:i.basis(),translation:i.vector()});let targets=[i.float(),i.float()];
  let settings=RetailTruckDriveSettings{use_linear_drives:i.word()!=0,use_hard_linear_drives:i.word()!=0,angular_displacement:i.float(),angular_damping:i.float(),angular_strength:i.float()};let dt=i.float();let calls=i.word();let iterations=i.word();
  let mut frames=None;for _ in 0..calls{let value=prepare_drive_frames(base,targets,&mut hook);for f in value{frame(&mut out,f.body_a);frame(&mut out,f.body_b);}out.extend(hook.drive.frames);out.extend(hook.drive.dynamics);frames=Some(value);}
  let mut constraints=BoardConstraints::build(&bodies,&hook,frames.unwrap(),retail_truck_drive_dynamics(settings),dt);
  out.push(constraints.joints.len() as u32);for j in &constraints.joints{joint(&mut out,j);}out.push(constraints.drives.len() as u32);for d in &constraints.drives{drive(&mut out,d);}
  let mut reactions=[RetailReactionCorrections::default();BODY_COUNT+1];solver::solve_constraints(&mut [],&mut constraints.joints,&mut constraints.drives,&mut reactions,iterations);
  for j in &constraints.joints{joint(&mut out,j);}for d in &constraints.drives{packed_drive(&mut out,d);}for r in reactions{for v in [r.linear_displacement,r.position_displacement,r.angular_displacement,r.orientation_displacement]{vector(&mut out,v);}}
  let simulation=RetailSimulationStep::fixed_60_hz(5,0.0001,Vector3::new(0.0,-9.81,0.0));
  for (n,b) in bodies.into_iter().enumerate(){let step=integrate_body_rates(b.rates,b.inertia,simulation,reactions[n]);rates(&mut out,step.state);vector(&mut out,step.orientation_displacement);floats(&mut out,[step.linear_speed_squared,step.angular_speed_squared]);}
  out[start]=(out.len()-start-1) as u32;
 }
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
