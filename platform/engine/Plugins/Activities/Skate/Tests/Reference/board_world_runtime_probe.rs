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

#[path="../../crates/skate-host/src/physics/settings.rs"] mod settings;
#[path="../../crates/skate-host/src/physics/colliders.rs"] mod colliders;
use skate_core::physics::{board_world::*,world_contact::*,mass::{DeckChild,DeckShape},collision::WorldContactSettings};

fn primitive(out:&mut Vec<u32>,p:ContactPrimitive){match p{
 ContactPrimitive::Sphere(s)=>{out.push(0);vector(out,s.center);out.push(s.radius.to_bits());},
 ContactPrimitive::Capsule{center,axis,half_length,radius}=>{out.push(1);vector(out,center);vector(out,axis);floats(out,[half_length,radius]);},
 ContactPrimitive::Triangle(t)=>{out.push(2);for v in t.vertices{vector(out,v);}vector(out,t.feature.normal);for v in t.feature.edges{vector(out,v);}out.push(t.feature.flags);floats(out,t.feature.edge_cosines);floats(out,t.edge_lengths);out.push(t.fatness.to_bits());},
 ContactPrimitive::RoundedBox{center,basis:b,half_extents,radius}=>{out.push(3);vector(out,center);basis(out,b);vector(out,half_extents);out.push(radius.to_bits());}
}}
fn material(out:&mut Vec<u32>,m:RetailContactMaterial){floats(out,[m.static_friction,m.dynamic_friction,m.restitution]);}
fn parameters(out:&mut Vec<u32>,d:RetailDriveParams){floats(out,[d.spring_or_max_velocity,d.damping,d.max_strength]);out.push(d.drive_type as u32);}
fn settings(out:&mut Vec<u32>,s:&settings::PhysicsSettings){let v=s.step.simulation;floats(out,[v.time_step,v.frequency]);out.push(v.cool_down);out.push(v.minimum_energy.to_bits());vector(out,v.gravity_acceleration);
 out.push(s.step.iterations);for t in s.step.base_truck_transforms{transform(out,t);}parameters(out,s.step.truck_dynamics.linear);parameters(out,s.step.truck_dynamics.angular);out.push(s.step.force_point_y_offset.to_bits());
 for t in s.authored{transform(out,t);}for m in [s.truck_material,s.deck_material,s.wheel_material,s.standard_wheel_material,s.floor_material]{material(out,m);}out.push(s.wheel_radius.to_bits());out.push(s.truck_collisions as u32);out.push(s.input_magnitude_threshold.to_bits());}
fn main(){
 let assets=std::env::args().nth(1).unwrap();let data=skate_data::collections::Collections::load(std::path::Path::new(&assets)).unwrap();
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();out.push(count);
 for _ in 0..count{
  let begin=out.len();out.push(0);let mut s=settings::PhysicsSettings::load(&data).unwrap();let mode=match i.word(){0=>BoardMotion::Active,1=>BoardMotion::Frozen,2=>BoardMotion::Static,_=>panic!()};let spawn=i.transform();
  if i.word()!=0{s.truck_collisions=i.word()!=0;s.deck_geometry.children.clear();let n=i.word();for _ in 0..n{
   let shape=match i.word(){0=>DeckShape::Sphere{radius:i.float()},1=>DeckShape::Capsule{radius:i.float(),half_length:i.float()},2=>DeckShape::RoundedBox{half_extents:i.vector(),radius:i.float()},_=>DeckShape::Triangle{vertices:[i.vector(),i.vector(),i.vector()],fatness:i.float(),edge_cosines:[i.float(),i.float(),i.float()],volume_flags:i.word()}};
   let transform=i.transform();let collision_enabled=i.word()!=0;s.deck_geometry.children.push(DeckChild{shape,transform,collision_enabled});
  }}
  let mut board=BoardRuntime::new(s.masses,s.authored,spawn,s.step.simulation,mode);settings(&mut out,&s);
  for b in board.bodies_mut(){b.state_flags=i.word();b.rates.linear_velocity=i.vector();}
  let n=i.word();let mut triangles=Vec::new();for _ in 0..n{let vertices=[i.vector(),i.vector(),i.vector()];let fatness=i.float();let flags=i.word();let tag=i.word();triangles.push(WorldTriangle{triangle:triangle_from_volume(vertices,fatness,[1.;3],flags),material:s.floor_material,tag});}
  let mut world=BoardWorld::new(triangles);if i.word()!=0{world.enable_imported_floor_seams();}let frames=i.word();out.push(frames);
  for t in 0..frames{
   let start=out.len();out.push(0);s.step.simulation=i.simulation();s.step.iterations=i.word();let targets=[i.float(),i.float()];board.clear_forces();let force_world=i.vector();let point_body=i.vector();board.forces_mut().append(QueuedPointForce{tag:t,force_world,point_body});
   let query=WorldContactSettings{volume_padding:i.float(),maximum_separating_distance:i.float(),edge_cos_bend_normal_threshold:i.float(),convexity_epsilon:i.float(),is_object:i.word()!=0};let retention=ContactRetentionSettings{capacity:i.word(),duplicate_distance_squared:i.float(),deferred_reduction:i.word()!=0};
   let volumes=colliders::world_volumes(&board,&s);out.push(volumes.len() as u32);for v in &volumes{out.push(v.body.contact_id());primitive(&mut out,v.primitive);vector(&mut out,v.linear_velocity);material(&mut out,v.material);}
   let collisions=world.query_primitives(&volumes,query,retention).to_vec();out.push(world.dropped_contacts());out.push(collisions.len() as u32);for c in &collisions{out.extend([c.body_a.contact_id(),c.body_b.contact_id()]);let q=c.contact;vector(&mut out,q.position_on_a);vector(&mut out,q.position_on_b);vector(&mut out,q.normal);floats(&mut out,[q.restitution,q.static_friction,q.dynamic_friction]);out.push(q.tag);}
   board.advance(&collisions,targets,s.step);for b in board.bodies(){body(&mut out,*b);}body(&mut out,board.hook().body);out.extend(board.hook().drive.frames);for t in board.part_transforms(){transform(&mut out,t);}
   out.push(board.solved_contacts().len() as u32);for c in board.solved_contacts(){contact(&mut out,c);}out.push(board.contact_reports().len() as u32);for r in board.contact_reports(){report(&mut out,*r);}out[start]=(out.len()-start-1) as u32;
  }out[begin]=(out.len()-begin-1) as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
