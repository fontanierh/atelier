// Appended to the frozen crate root; every original numerical module remains unchanged.
use std::io::{Read,Write};
use crate::{math::{Basis3,Vector3},physics::{skeleton_body::*,skeleton_animation_record::*,skeleton_root::inverse_rigid,rigid_body::*,assembly::BodySnapshot,mass::MassShape}};
struct ProbeInput{words:Vec<u32>,at:usize}
impl ProbeInput{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}
 fn vector(&mut self)->Vector3{let v=self.floats::<3>();Vector3::new(v[0],v[1],v[2])}
 fn matrix(&mut self)->AnimationPartTransform{std::array::from_fn(|_|self.floats())}
 fn matrices<const N:usize>(&mut self)->[AnimationPartTransform;N]{std::array::from_fn(|_|self.matrix())}
 fn sizes(&mut self)->[Vector3;24]{std::array::from_fn(|_|self.vector())}
 fn hat(&mut self)->HatGeometry{HatGeometry{radius:self.float(),half_length:self.float(),basis:Basis3{columns:std::array::from_fn(|_|self.floats())},translation:self.vector()}}
 fn simulation(&mut self)->RetailSimulationStep{RetailSimulationStep{time_step:self.float(),frequency:self.float(),cool_down:self.word(),minimum_energy:self.float(),gravity_acceleration:self.vector()}}
 fn definition(&mut self)->Result<SkeletonBodyDefinition,&'static str>{let sizes=self.sizes();let bones=std::array::from_fn(|_|BoneSettings{mass_factor:self.float(),ragdoll_mass_factor:self.float(),has_collision:self.word()!=0,use_root_drive:self.word()!=0,volume_type:self.word(),volume_scalar:self.float(),num_parents:self.word()});let settings=SkeletonBodySettings{density:self.float(),root_radius:self.float(),root_half_length:self.float(),capsule_radius_scalar:self.float(),capsule_length_scalar:self.float(),ragdoll_inverse_mass_factor:self.float(),inertia_multiply_type:self.word(),inertia_factor:self.float()};let hat=if self.word()!=0{Some(self.hat())}else{None};SkeletonBodyDefinition::new(sizes,bones,settings,hat)}
 fn animation_record(&mut self)->SkeletonAnimationRecord{if self.word()==0{SkeletonAnimationRecord::default()}else{SkeletonAnimationRecord{pose:self.matrices(),centre_of_mass:self.floats(),centre_of_mass_delta:self.floats(),com_to_deck_world:self.floats(),com_to_deck_world_delta:self.floats(),reset_scalar:self.float()}}}
 fn physical_record(&mut self)->SkeletonPhysicalRecord{if self.word()==0{SkeletonPhysicalRecord::default()}else{SkeletonPhysicalRecord{pose:self.matrices(),positions:std::array::from_fn(|_|self.floats()),velocities:std::array::from_fn(|_|self.floats()),velocity_changes:std::array::from_fn(|_|self.floats()),centre_of_mass:self.floats(),centre_of_mass_velocity:self.floats(),timestep:self.float()}}}
}
fn probe_floats(out:&mut Vec<u32>,f:impl IntoIterator<Item=f32>){out.extend(f.into_iter().map(f32::to_bits));}
fn probe_vector(out:&mut Vec<u32>,v:Vector3){probe_floats(out,[v.x,v.y,v.z]);}
fn probe_matrix(out:&mut Vec<u32>,m:AnimationPartTransform){for c in m{probe_floats(out,c);}}
fn probe_basis(out:&mut Vec<u32>,b:Basis3){for c in b.columns{probe_floats(out,c);}}
fn probe_error(out:&mut Vec<u32>,e:&str){out.push(e.len() as u32);out.extend(e.bytes().map(u32::from));}
fn probe_hat(out:&mut Vec<u32>,h:HatGeometry){probe_floats(out,[h.radius,h.half_length]);probe_basis(out,h.basis);probe_vector(out,h.translation);}
fn probe_masses(out:&mut Vec<u32>,m:&SkeletonAnimationMasses){probe_floats(out,m.part_weights);out.push(m.total.to_bits());probe_floats(out,m.fractional);}
fn probe_animation_record(out:&mut Vec<u32>,r:&SkeletonAnimationRecord){for m in r.pose{probe_matrix(out,m);}for v in [r.centre_of_mass,r.centre_of_mass_delta,r.com_to_deck_world,r.com_to_deck_world_delta]{probe_floats(out,v);}out.push(r.reset_scalar.to_bits());probe_vector(out,r.com_to_deck());}
fn probe_physical_record(out:&mut Vec<u32>,r:&SkeletonPhysicalRecord){for m in r.pose{probe_matrix(out,m);}for set in [r.positions,r.velocities,r.velocity_changes]{for v in set{probe_floats(out,v);}}probe_floats(out,r.centre_of_mass);probe_floats(out,r.centre_of_mass_velocity);out.push(r.timestep.to_bits());}
fn probe_bone(out:&mut Vec<u32>,b:BoneSettings){probe_floats(out,[b.mass_factor,b.ragdoll_mass_factor]);out.extend([b.has_collision as u32,b.use_root_drive as u32,b.volume_type,b.volume_scalar.to_bits(),b.num_parents]);}
fn probe_properties(out:&mut Vec<u32>,m:RetailBodyMassProperties){probe_basis(out,m.local_mass_frame.basis);probe_vector(out,m.local_mass_frame.translation);probe_vector(out,m.dynamics.inverse_tensor);let d=m.dynamics;probe_floats(out,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
fn probe_definition(out:&mut Vec<u32>,d:&SkeletonBodyDefinition){for p in d.parts{match p.shape{
 MassShape::Sphere{radius}=>{out.push(0);probe_floats(out,[radius,0.,0.,0.,0.,0.]);},
 MassShape::Capsule{radius,half_length}=>{out.push(1);probe_floats(out,[radius,half_length,0.,0.,0.,0.]);},
 MassShape::RoundedBox{half_extents,radius}=>{out.push(2);probe_floats(out,[radius,0.,0.]);probe_vector(out,half_extents);},
 MassShape::Cylinder{radius,half_length,padding}=>{out.push(3);probe_floats(out,[radius,half_length,padding,0.,0.,0.]);},MassShape::Unsupported=>{out.push(4);probe_floats(out,[0.;6]);}
 }out.push(p.hat.is_some() as u32);if let Some(h)=p.hat{probe_hat(out,h);}else{probe_floats(out,[0.;14]);}probe_properties(out,p.animated);probe_properties(out,p.ragdoll);probe_floats(out,[p.inverse_mass_animated,p.inverse_mass_ragdoll]);}for b in d.bones{probe_bone(out,b);}probe_masses(out,&d.animation_masses);}
fn probe_body(out:&mut Vec<u32>,b:BodySnapshot){out.push(b.state_flags);let r=b.rates;probe_floats(out,[r.orientation.x,r.orientation.y,r.orientation.z,r.orientation.w]);probe_basis(out,r.basis);probe_basis(out,r.world_inverse_inertia);for v in [r.position,r.linear_velocity,r.angular_velocity,r.force_acceleration,r.torque_acceleration]{probe_vector(out,v);}out.extend([r.kinetic_energy.to_bits(),r.cool_down]);let d=b.inertia;probe_vector(out,d.inverse_tensor);probe_floats(out,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
fn probe_snapshot(out:&mut Vec<u32>,body:&SkeletonBody){probe_matrix(out,body.animation_to_world);for b in body.bodies(){probe_body(out,*b);}for m in body.part_transforms(){probe_matrix(out,m);}probe_physical_record(out,&body.record);}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);let mut i=ProbeInput{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let cases=i.word();
 for index in 0..cases{let op=i.word();out.extend([index,op,0]);let size_at=out.len()-1;let start=out.len();match op{
  0=>{let radius=i.float();let thickness=i.float();let angles=i.vector();let translation=i.vector();probe_hat(&mut out,HatGeometry::from_offsets(radius,thickness,angles,translation));},
  1=>probe_masses(&mut out,&SkeletonAnimationMasses::normalize(i.floats())),
  2=>{let sizes=i.sizes();let shapes=std::array::from_fn(|_|i.word());let hat=i.word()!=0;probe_masses(&mut out,&SkeletonAnimationMasses::from_bone_data(sizes,shapes,hat));},
  3=>{let q=i.floats();let translation=i.floats();let a=i.matrix();let b=i.matrix();let point=i.floats();probe_matrix(&mut out,physics_bone_frame(q,translation));probe_matrix(&mut out,compose_affine(&a,&b));probe_matrix(&mut out,inverse_rigid(&a));probe_floats(&mut out,transform_point(&a,point));},
  4=>{let count=i.word();let bones=(0..count).map(|_|i.matrix()).collect::<Vec<_>>();let indices=std::array::from_fn(|_|i.word() as usize);let frames=i.matrices();let _initial=i.matrices::<24>();match map_animation_parts(&bones,&indices,&frames){Ok(mapped)=>{out.push(1);for m in mapped{probe_matrix(&mut out,m);}},Err(e)=>{out.push(0);probe_error(&mut out,e);}}},
  5=>{let mut r=i.animation_record();let masses=SkeletonAnimationMasses::normalize(i.floats());probe_masses(&mut out,&masses);probe_animation_record(&mut out,&r);let count=i.word();out.push(count);for _ in 0..count{if i.word()==0{r.reset_history();}else{let pose=i.matrices();let board=i.matrix();r.update(&pose,&board,&masses);}probe_animation_record(&mut out,&r);}},
  6=>{let mut r=i.physical_record();let fractional=i.floats();probe_physical_record(&mut out,&r);let count=i.word();out.push(count);for _ in 0..count{let cmd=i.word();let parts=i.matrices();if cmd==0{r.reset(&parts);}else{let board=i.matrix();r.update(&parts,board,&fractional);}probe_physical_record(&mut out,&r);}},
  7=>match i.definition(){Ok(d)=>{out.push(1);probe_definition(&mut out,&d);},Err(e)=>{out.push(0);probe_error(&mut out,e);}},
  8=>{let d=i.definition().unwrap();let authored=i.matrices();let spawn=i.matrix();let simulation=i.simulation();let mut body=SkeletonBody::new(d,&authored,spawn,simulation);probe_snapshot(&mut out,&body);let count=i.word();out.push(count);for _ in 0..count{match i.word(){
   0=>{let part=i.word() as usize;body.set_part_transform(part,i.matrix());},
   1=>{let part=i.word() as usize;body.apply_part_displacement(part,i.floats());},
   2=>body.publish_physical_record(i.matrix()),
   3=>{let part=i.word() as usize;let b=&mut body.bodies_mut()[part];b.state_flags=i.word();b.rates.linear_velocity=i.vector();b.rates.angular_velocity=i.vector();b.rates.force_acceleration=i.vector();b.rates.torque_acceleration=i.vector();b.rates.kinetic_energy=i.float();b.rates.cool_down=i.word();},
   4=>{let step=i.simulation();for b in body.bodies_mut(){let reaction=RetailReactionCorrections{linear_displacement:i.vector(),position_displacement:i.vector(),angular_displacement:i.vector(),orientation_displacement:i.vector()};if b.state_flags&4!=0{b.rates=integrate_body_rates(b.rates,b.inertia,step,reaction).state;}}},
   5=>{let pose=body.part_transforms();body.record.reset(&pose);},_=>panic!("skeleton command")
  }probe_snapshot(&mut out,&body);}},_=>panic!("skeleton operation")
 }out[size_at]=(out.len()-start) as u32;}
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
