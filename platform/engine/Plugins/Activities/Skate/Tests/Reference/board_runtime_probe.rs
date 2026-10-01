use skate_core::{math::{Basis3,Vector3},physics::{assembly::*,board::{BODY_COUNT,BodyId},board_runtime::*,board_step::*,drive_frames::*,drive_parameters::*,drive_solver::*,rigid_body::*,joint_builder::*,joint_records::*,force_queue::*,mass::default_skateboard_mass_properties,contact::*,contact_solver::*,contact_feedback::BoardContactReport,solver::{self,packed}}};
mod math {pub use skate_core::math::*;}
mod physics {pub use skate_core::physics::*;}
#[path="../../crates/skate-core/src/physics/solver/packing.rs"] mod packing;
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn transform(&mut self)->RetailAffineTransform{RetailAffineTransform{basis:self.basis(),translation:self.vector()}}
 fn simulation(&mut self)->RetailSimulationStep{RetailSimulationStep{time_step:self.float(),frequency:self.float(),cool_down:self.word(),minimum_energy:self.float(),gravity_acceleration:self.vector()}}
}
fn floats(out:&mut Vec<u32>,v:impl IntoIterator<Item=f32>){out.extend(v.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn basis(out:&mut Vec<u32>,b:Basis3){for c in b.columns{floats(out,c);}}
fn transform(out:&mut Vec<u32>,t:RetailAffineTransform){basis(out,t.basis);vector(out,t.translation);}
fn body(out:&mut Vec<u32>,b:BodySnapshot){let r=b.rates;let d=b.inertia;out.push(b.state_flags);floats(out,[r.orientation.x,r.orientation.y,r.orientation.z,r.orientation.w]);basis(out,r.basis);basis(out,r.world_inverse_inertia);for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration]{vector(out,v);}out.extend([r.kinetic_energy.to_bits(),r.cool_down]);vector(out,d.inverse_tensor);floats(out,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
fn contact(out:&mut Vec<u32>,c:&RetailContactJacobian){out.extend(c.words());out.extend([c.reaction_index_a as u32,c.reaction_index_b as u32]);}
fn joint(out:&mut Vec<u32>,j:&solver::JointConstraint){out.extend(j.jacobian.words);out.extend([j.reaction_a as u32,j.reaction_b as u32]);}
fn drive(out:&mut Vec<u32>,d:&RetailDriveRows){let p=packing::drive(d);out.extend(p.words);out.extend([p.reaction_a as u32,p.reaction_b as u32]);}
fn report(out:&mut Vec<u32>,r:BoardContactReport){out.extend([r.part.index() as u32,r.other.contact_id(),r.is_body_a as u32]);vector(out,r.normal);vector(out,r.position);vector(out,r.relative_linear_velocity);out.push(r.other_surface as u32);vector(out,r.normal_force_on_a);vector(out,r.friction_force_on_a);for t in r.tangents{vector(out,t);}}
fn drive_body(b:BodySnapshot,id:usize)->RetailDriveBodyState{let r=b.rates;RetailDriveBodyState{reaction_index:id,state:b.state_flags,orientation:r.orientation,basis:r.basis,center_of_mass:r.position,linear_velocity:r.linear_velocity,angular_velocity:r.angular_velocity,force_acceleration:r.force_acceleration,torque_acceleration:r.torque_acceleration,inverse_mass:b.inertia.inverse_mass,world_inverse_inertia:pack_world_inverse_inertia(r.world_inverse_inertia)}}
fn joint_body(b:BodySnapshot)->RetailJointBodyInput{let r=b.rates;RetailJointBodyInput{reaction_guest_address:0,state:b.state_flags,orientation:r.orientation,basis:r.basis,center_of_mass:r.position,linear_velocity:r.linear_velocity,angular_velocity:r.angular_velocity,force_acceleration:r.force_acceleration,torque_acceleration:r.torque_acceleration,inverse_mass:b.inertia.inverse_mass,world_inverse_inertia:pack_world_inverse_inertia(r.world_inverse_inertia)}}
fn contact_body(b:BodySnapshot,id:u32)->RetailContactBodyState{let r=b.rates;let inertia=pack_world_inverse_inertia(r.world_inverse_inertia);RetailContactBodyState{contact_body_id:id,center_of_mass:r.position,reaction_id:id,inverse_inertia_full:inertia.full,inverse_mass:b.inertia.inverse_mass,inverse_inertia_split:inertia.split,state:b.state_flags|8,force_acceleration:r.force_acceleration,kinetic_energy:r.kinetic_energy,torque_acceleration:r.torque_acceleration,cool_down:r.cool_down,linear_velocity:r.linear_velocity,angular_velocity:r.angular_velocity}}
fn snapshot(out:&mut Vec<u32>,board:&BoardRuntime,attached:&[BodySnapshot],contacts:&[RetailContactJacobian],joints:&[solver::JointConstraint],drives:&[RetailDriveRows]){
 for b in board.bodies(){body(out,*b);}body(out,board.hook().body);out.extend(board.hook().drive.frames);out.extend(board.hook().drive.dynamics);
 for t in board.part_transforms(){transform(out,t);}for id in BodyId::ORDER{transform(out,board.body_transform(id));}transform(out,board.hook_transform());
 out.push(board.forces().entries().len() as u32);for f in board.forces().entries(){out.push(f.tag);vector(out,f.force_world);vector(out,f.point_body);}out.push(total_body_mass(&board.bodies().map(|b|b.inertia.inverse_mass)).to_bits());out.push(board.collision_group());
 out.push(board.solved_contacts().len() as u32);for c in board.solved_contacts(){contact(out,c);}out.push(board.contact_reports().len() as u32);for r in board.contact_reports(){report(out,*r);}
 out.push(attached.len() as u32);for b in attached{body(out,*b);}out.push(contacts.len() as u32);for c in contacts{contact(out,c);}out.push(joints.len() as u32);for j in joints{joint(out,j);}out.push(drives.len() as u32);for d in drives{drive(out,d);}
}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let cases=i.word();
 for _ in 0..cases{
  let mode=match i.word(){0=>BoardMotion::Active,1=>BoardMotion::Frozen,2=>BoardMotion::Static,_=>panic!("mode")};let spawn=i.transform();let simulation=i.simulation();let mut masses=default_skateboard_mass_properties();
  if i.word()!=0{for mass in &mut masses{let t=i.transform();mass.local_mass_frame=RetailLocalMassFrame{basis:t.basis,translation:t.translation};}}
  let authored=authored_body_transforms(AuthoredTransformInputs::STOCK);let mut board=BoardRuntime::new(masses,authored,spawn,simulation,mode);let mut attached=Vec::new();let count=i.word();
  for _ in 0..count{let mut b=board.bodies()[6];b.state_flags=i.word();b.rates.position=i.vector();attached.push(b);}
  let mut contacts=Vec::new();let mut joints=Vec::new();let mut drives=Vec::new();let initial=out.len();out.extend([0,0]);snapshot(&mut out,&board,&attached,&contacts,&joints,&drives);out[initial]=(out.len()-initial-1) as u32;
  let commands=i.word();for _ in 0..commands{
   let start=out.len();out.push(0);let op=i.word();let mut result=0;
   match op{
    0=>{let f=QueuedPointForce{tag:i.word(),force_world:i.vector(),point_body:i.vector()};result=board.forces_mut().append(f) as u32;},
    1=>board.clear_forces(),2=>board.set_transform(i.transform()),3=>board.set_hook_transform(i.transform()),
    4=>{let flags=i.word();let gravity=i.vector();let target=i.transform();board.reset_physical(authored,target,flags,gravity);},
    5=>{let id=i.word() as usize;let b=if id<7{&mut board.bodies_mut()[id]}else if id==7{&mut board.hook_mut().body}else{&mut attached[id-8]};b.state_flags=i.word();b.rates.linear_velocity=i.vector();b.rates.angular_velocity=i.vector();b.rates.force_acceleration=i.vector();b.rates.torque_acceleration=i.vector();b.rates.kinetic_energy=i.float();b.rates.cool_down=i.word();},
    6=>{let mut animated=i.word() as u8;match i.word(){0=>board.hook_mut().drive.enable_animation_soft(&mut animated),1=>board.hook_mut().drive.enable_angular_soft(),2=>board.hook_mut().drive.enable_angular_only(&mut animated),3=>board.hook_mut().drive.disable_animation(&mut animated),4=>board.hook_mut().drive.disable_linear(),5=>board.hook_mut().drive.disable_angular(),_=>panic!("hook op")};result=animated as u32;},
    7=>{
     let simulation=i.simulation();let iterations=i.word();let targets=[i.float(),i.float()];let settings=BoardStepSettings{simulation,iterations,base_truck_transforms:default_truck_transforms(),truck_dynamics:retail_truck_drive_dynamics(RetailTruckDriveSettings::STOCK),force_point_y_offset:i.float()};let count=i.word();let mut collisions=Vec::new();
     for _ in 0..count{let id=i.word();let reverse=i.word()!=0;let gap=i.float();let mut input=RetailContactInput{position_on_a:Vector3::ZERO,position_on_b:Vector3::ZERO,normal:i.vector(),restitution:i.float(),static_friction:i.float(),dynamic_friction:i.float(),tag:i.word()};let b=if id<7{board.bodies()[id as usize]}else{attached[id as usize-8]};input.position_on_a=b.rates.position;input.position_on_a.y-=0.05;input.position_on_b=input.position_on_a;input.position_on_b.y-=gap;let mut a=CollisionBody::from_contact_id(id);let mut world=CollisionBody::StaticWorld;if reverse{std::mem::swap(&mut a,&mut world);std::mem::swap(&mut input.position_on_a,&mut input.position_on_b);input.normal=Vector3::new(-input.normal.x,-input.normal.y,-input.normal.z);}collisions.push(BoardCollision{body_a:a,body_b:world,contact:input});}
     let supplement=i.word()!=0;contacts.clear();joints.clear();drives.clear();
     if supplement && !attached.is_empty(){let a=attached[0];let b=board.bodies()[6];let input=RetailContactInput{position_on_a:a.rates.position,position_on_b:b.rates.position,normal:Vector3::new(0.,1.,0.),restitution:0.05,static_friction:0.4,dynamic_friction:0.3,tag:0x12345678};contacts.push(build_contact_jacobian(generate_contact(input,contact_body(a,8),contact_body(b,6)),simulation.time_step));let record=default_joint_records()[0];joints.push(solver::JointConstraint{jacobian:build_retail_joint_jacobian(RetailJointBuildInput{parameters:record.parameters,frames:record.frames,body_a:joint_body(a),body_b:joint_body(b),time_step:simulation.time_step,joint_guest_address:0}),reaction_a:8,reaction_b:6});let frame=RetailDriveFrame{orientation:RetailQuaternion::IDENTITY,translation:Vector3::ZERO};drives.push(build_drive_rows(drive_body(a,8),drive_body(b,6),RetailDriveFrames{body_a:frame,body_b:frame},retail_truck_drive_dynamics(RetailTruckDriveSettings::STOCK),simulation.time_step));}
     if attached.is_empty(){board.advance(&collisions,targets,settings);}else{board.advance_attached(&collisions,targets,settings,AttachedStep{bodies:attached.iter_mut().collect(),contacts:&mut contacts,joints:&mut joints,drives:&mut drives});}
    },
    8=>board.set_collision_group(i.word()),9=>{result=board.take_solver_diagnostics(i.word()!=0).is_some() as u32;},_=>panic!("op")
   }
   out.push(result);snapshot(&mut out,&board,&attached,&contacts,&joints,&drives);out[start]=(out.len()-start-1) as u32;
  }
 }
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
