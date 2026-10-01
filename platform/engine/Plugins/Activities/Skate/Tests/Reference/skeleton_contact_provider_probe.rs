// The checker prepends tested skeleton body/collision record adapters and
// compiles complete unchanged original host providers. Transport facades below
// supply record ownership to the private original collector; publish is not run.
extern crate self as skate_core;
use crate::physics::{board_step::{CollisionBody,BoardCollision},board_world::BoardWorldVolume,contact::RetailContactInput,contact_solver::RetailContactJacobian,drive_frames::RetailAffineTransform};
use crate::physics::world_contact::{ContactPrimitive,transform_triangle_volume};
mod provider_oracle {
 use super::*;
 pub struct ProbeBoard {pub bodies:[BodySnapshot;7],pub rows:Vec<RetailContactJacobian>,pub poses:[RetailAffineTransform;7],pub group:u32}
 impl ProbeBoard {pub fn bodies(&self)->&[BodySnapshot;7]{&self.bodies}pub fn solved_contacts(&self)->&[RetailContactJacobian]{&self.rows}pub fn part_transforms(&self)->[RetailAffineTransform;7]{self.poses}pub fn collision_group(&self)->u32{self.group}}
 pub struct ProbeMasses {pub part_weights:[f32;24]}
 pub struct ProbeDefinition {pub animation_masses:ProbeMasses}
 pub struct ProbeSkeleton {pub states:Vec<BodySnapshot>,pub record:SkeletonPhysicalRecord,pub frames:[AnimationPartTransform;26],pub definition:ProbeDefinition}
 impl ProbeSkeleton {pub fn bodies(&self)->&[BodySnapshot]{&self.states}pub fn part_transforms(&self)->[AnimationPartTransform;26]{self.frames}}
 pub struct Targets {pub bodies:Vec<BodySnapshot>}pub struct Drives {pub targets:Targets}
 pub struct Simulation {pub time_step:f32,pub frequency:f32}pub struct Step {pub simulation:Simulation}pub struct Settings {pub step:Step}
 pub struct Proxies {pub bodies:Vec<BodySnapshot>}pub struct Reckoning {pub ground_normal:Vector3}pub struct Riding {pub reckoning:Reckoning}
 pub struct GamePhysics {pub board:ProbeBoard,pub settings:Settings,pub network_proxies:Proxies,pub riding:Riding}
 pub struct Processed {pub state_2508:u32,pub category_2512:u32,pub vectors_464_480_496_512_528:[[u32;4];5],pub flags_2480:u32,pub vectors_880_896_912_928_944:[[u32;4];5],pub flags_2472:u32}
 pub struct PlayerInput {pub processed:Processed}pub struct Output {pub correction:crate::physics::skeleton_output::correction::CorrectionState}
 pub struct Animated {pub roots:crate::physics::skeleton_root::SkeletonRootFrames,pub board_frames:crate::physics::skeleton_board_frames::SkeletonBoardFrames}
 pub struct SkeletonInput {pub deck_velocity:[f32;4],pub extra_target_positions:[[f32;4];3],pub drive_frames:[AnimationPartTransform;24]}
 pub struct SkaterRuntime {pub skeleton:ProbeSkeleton,pub skeleton_drives:Drives,pub skeleton_collision:SkeletonCollisionMode,pub player_input:PlayerInput,pub skeleton_output:Output,pub animated_skeleton:Animated,pub collision_feedback:SkeletonCollisionFeedback,pub skeleton_input:SkeletonInput,pub pose_errors:SkeletonPoseErrors,pub collision_pose_error:[f32;4],pub collision_extra_errors:[[f32;4];2],pub collision_maximum_error:Option<f32>}
 pub mod solve {use super::*;pub fn deck_frame(board:&ProbeBoard)->AnimationPartTransform {let deck=board.part_transforms()[4];let mut frame=crate::physics::skeleton_animation_record::IDENTITY;for(axis,column)in deck.basis.columns.iter().enumerate(){frame[axis][..3].copy_from_slice(column);}frame[3]=[deck.translation.x,deck.translation.y,deck.translation.z,0.];frame}}
 #[path="../host-source/skeleton_colliders.rs"]pub mod colliders;
 #[path="../host-source/assembly_contacts.rs"]pub mod assembly;
 #[path="../host-source/skeleton_feedback_forward.rs"]pub mod feedback;
 pub fn enabled(body:&SkeletonBody,mode:&SkeletonCollisionMode)->Result<Vec<BoardWorldVolume>,String>{colliders::enabled_volumes(body,mode)}
 pub fn world(body:&SkeletonBody,mode:&SkeletonCollisionMode)->Result<Vec<BoardWorldVolume>,String>{colliders::world_volumes(body,mode)}
 pub fn append(contacts:&mut Vec<BoardCollision>,board:&[BoardWorldVolume],rider:&[BoardWorldVolume],group:u32,mode:&SkeletonCollisionMode)->Result<(),String>{assembly::append(contacts,board,rider,group,mode)}
 pub fn collect(board:[BodySnapshot;7],attached:Vec<BodySnapshot>,local:usize,board_group:u32,rider_group:u32,frequency:f32,rows:Vec<RetailContactJacobian>)->Vec<SkeletonContactReport>{
  assert!(local>=26 && attached.len()>=local);let identity=crate::physics::skeleton_animation_record::IDENTITY;
  let parts=attached[..26].to_vec();let targets=attached[26..local].to_vec();let external=attached[local..].to_vec();
  let settings=SkeletonCollisionSettings{enabled:false,normal_material:RetailContactMaterial{static_friction:0.,dynamic_friction:0.,restitution:0.},compliant:[false;24],priority:[0.;24],effect_time:0.};
  let mut collision=SkeletonCollisionMode::new_normal(settings,true);collision.assembly_group=rider_group;
  let feedback_settings=SkeletonFeedbackSettings{body:settings,small_object_mass:0.,ground_plane_max_distance:0.,ground_plane_max_angle:0.,skater_scalar:0.,ai_scalar:0.,groin_offset:[0.;4],face_offset:[0.;4],groin_radius:0.,face_radius:0.};
  let poses=[RetailAffineTransform{basis:Basis3{columns:[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]},translation:Vector3::ZERO};7];
  let physics=GamePhysics{board:ProbeBoard{bodies:board,rows,poses,group:board_group},settings:Settings{step:Step{simulation:Simulation{time_step:1./60.,frequency}}},network_proxies:Proxies{bodies:external},riding:Riding{reckoning:Reckoning{ground_normal:Vector3::ZERO}}};
  let skater=SkaterRuntime{skeleton:ProbeSkeleton{states:parts,record:SkeletonPhysicalRecord::default(),frames:[identity;26],definition:ProbeDefinition{animation_masses:ProbeMasses{part_weights:[0.;24]}}},skeleton_drives:Drives{targets:Targets{bodies:targets}},skeleton_collision:collision,
   player_input:PlayerInput{processed:Processed{state_2508:0,category_2512:0,vectors_464_480_496_512_528:[[0;4];5],flags_2480:0,vectors_880_896_912_928_944:[[0;4];5],flags_2472:0}},skeleton_output:Output{correction:Default::default()},animated_skeleton:Animated{roots:Default::default(),board_frames:Default::default()},collision_feedback:SkeletonCollisionFeedback::new(feedback_settings),skeleton_input:SkeletonInput{deck_velocity:[0.;4],extra_target_positions:[[0.;4];3],drive_frames:[identity;24]},pose_errors:SkeletonPoseErrors::default(),collision_pose_error:[0.;4],collision_extra_errors:[[0.;4];2],collision_maximum_error:None};
  feedback::migration_collect(&physics,&skater)
 }
}
impl ProbeInput {
 fn body(&mut self)->BodySnapshot{
  let state_flags=self.word();let q=self.floats::<4>();let orientation=RetailQuaternion{x:q[0],y:q[1],z:q[2],w:q[3]};let basis=Basis3{columns:std::array::from_fn(|_|self.floats())};let world_inverse_inertia=Basis3{columns:std::array::from_fn(|_|self.floats())};let position=self.vector();let linear_velocity=self.vector();let angular_velocity=self.vector();let force_acceleration=self.vector();let torque_acceleration=self.vector();let kinetic_energy=self.float();let cool_down=self.word();let rates=RetailBodyRates{orientation,basis,world_inverse_inertia,position,linear_velocity,angular_velocity,force_acceleration,torque_acceleration,kinetic_energy,cool_down};let inverse_tensor=self.vector();let inertia=RetailInertiaDynamics{inverse_tensor,inverse_mass:self.float(),spherical:self.float(),maximum_linear_velocity:self.float(),maximum_angular_velocity:self.float(),linear_drag:self.float(),angular_drag:self.float()};BodySnapshot{state_flags,rates,inertia}
 }
 fn affine(&mut self)->RetailAffineTransform{RetailAffineTransform{basis:Basis3{columns:std::array::from_fn(|_|self.floats())},translation:self.vector()}}
 fn primitive(&mut self)->ContactPrimitive{match self.word(){
  0=>ContactPrimitive::Sphere(crate::physics::collision::Sphere{center:self.vector(),radius:self.float()}),
  1=>ContactPrimitive::Capsule{center:self.vector(),axis:self.vector(),half_length:self.float(),radius:self.float()},
  2=>{let vertices=std::array::from_fn(|_|self.vector());let fat=self.float();let cosines=self.floats();let flags=self.word();let frame=self.affine();ContactPrimitive::Triangle(transform_triangle_volume(vertices,fat,cosines,flags,frame.basis,frame.translation))},
  3=>ContactPrimitive::RoundedBox{center:self.vector(),basis:Basis3{columns:std::array::from_fn(|_|self.floats())},half_extents:self.vector(),radius:self.float()},_=>panic!("Provider primitive kind")}}
 fn volume(&mut self)->BoardWorldVolume{let body=CollisionBody::from_contact_id(self.word());let primitive=self.primitive();let linear_velocity=self.vector();let material=self.material();BoardWorldVolume{body,primitive,linear_velocity,material}}
 fn volumes(&mut self)->Vec<BoardWorldVolume>{let n=self.word();(0..n).map(|_|self.volume()).collect()}
 fn collision(&mut self)->BoardCollision{let body_a=CollisionBody::from_contact_id(self.word());let body_b=CollisionBody::from_contact_id(self.word());let contact=RetailContactInput{position_on_a:self.vector(),position_on_b:self.vector(),normal:self.vector(),restitution:self.float(),static_friction:self.float(),dynamic_friction:self.float(),tag:self.word()};BoardCollision{body_a,body_b,contact}}
 fn skeleton(&mut self)->SkeletonBody{let definition=self.definition().unwrap();let authored=self.matrices();let spawn=self.matrix();let sim=self.simulation();SkeletonBody::new(definition,&authored,spawn,sim)}
}
fn provider_primitive(out:&mut Vec<u32>,p:ContactPrimitive){match p{
 ContactPrimitive::Sphere(s)=>{out.push(0);probe_vector(out,s.center);out.push(s.radius.to_bits());},
 ContactPrimitive::Capsule{center,axis,half_length,radius}=>{out.push(1);probe_vector(out,center);probe_vector(out,axis);probe_floats(out,[half_length,radius]);},
 ContactPrimitive::Triangle(t)=>{out.push(2);for v in t.vertices{probe_vector(out,v);}probe_vector(out,t.feature.normal);for v in t.feature.edges{probe_vector(out,v);}out.push(t.feature.flags);probe_floats(out,t.feature.edge_cosines);probe_floats(out,t.edge_lengths);out.push(t.fatness.to_bits());},
 ContactPrimitive::RoundedBox{center,basis,half_extents,radius}=>{out.push(3);probe_vector(out,center);probe_basis(out,basis);probe_vector(out,half_extents);out.push(radius.to_bits());}
}}
fn provider_volumes(out:&mut Vec<u32>,v:&[BoardWorldVolume]){out.push(v.len() as u32);for v in v{out.push(v.body.contact_id());provider_primitive(out,v.primitive);probe_vector(out,v.linear_velocity);probe_floats(out,[v.material.static_friction,v.material.dynamic_friction,v.material.restitution]);}}
fn provider_collisions(out:&mut Vec<u32>,v:&[BoardCollision]){out.push(v.len() as u32);for c in v{out.extend([c.body_a.contact_id(),c.body_b.contact_id()]);let q=c.contact;for v in [q.position_on_a,q.position_on_b,q.normal]{probe_vector(out,v);}probe_floats(out,[q.restitution,q.static_friction,q.dynamic_friction]);out.push(q.tag);}}
fn provider_reports(out:&mut Vec<u32>,v:&[SkeletonContactReport]){out.push(v.len() as u32);for r in v{out.push(r.part as u32);probe_floats(out,r.normal);probe_floats(out,r.point);out.extend([r.tag,r.other_group,r.other_entity.is_some() as u32,r.other_entity.unwrap_or(0) as u32]);for b in [r.body_a,r.body_b]{out.extend([b.state_flags,b.inverse_mass.to_bits()]);probe_floats(out,b.linear_velocity);}out.push(r.side_a as u32);probe_floats(out,r.solved_vector);}}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=ProbeInput{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for index in 0..count{let op=i.word();out.extend([index,op,0]);let mark=out.len()-1;let start=out.len();match op{
  0=>{let mut body=i.skeleton();let settings=i.collision_settings();let mut mode=SkeletonCollisionMode::new_normal(settings,i.word()!=0);let n=i.word();out.push(n);for _ in 0..n{let cmd=i.word();out.push(cmd);match cmd{
   0=>{let p=&mut mode.parts[i.word() as usize];p.enabled=i.word()!=0;p.volume_group=i.word();p.part_group=i.word();p.material=i.material();},
   1=>{let p=&mut body.definition.parts[i.word() as usize];let kind=i.word();let radius=i.float();let half_length=i.float();let padding=i.float();let half_extents=i.vector();p.shape=match kind{0=>MassShape::Sphere{radius},1=>MassShape::Capsule{radius,half_length},2=>MassShape::RoundedBox{half_extents,radius},3=>MassShape::Cylinder{radius,half_length,padding},_=>MassShape::Unsupported};},
   2=>{let p=&mut body.definition.parts[i.word() as usize];p.hat=if i.word()!=0{Some(i.hat())}else{None};},3=>{let part=i.word() as usize;let frame=i.matrix();body.set_part_transform(part,frame);},4=>{let part=i.word() as usize;body.bodies_mut()[part]=i.body();},_=>panic!("Collider command")}
   for world in [false,true]{let result=if world{provider_oracle::world(&body,&mode)}else{provider_oracle::enabled(&body,&mode)};match result{Ok(v)=>{out.push(1);provider_volumes(&mut out,&v);},Err(e)=>{out.push(0);probe_error(&mut out,&e);}}}probe_snapshot(&mut out,&body);collision_mode(&mut out,&mode);
  }},
  1=>{let settings=i.collision_settings();let mut mode=SkeletonCollisionMode::new_normal(settings,i.word()!=0);mode.assembly_group=i.word();for p in &mut mode.parts{p.part_group=i.word();}for row in &mut mode.self_culling{for b in row{*b=i.word()!=0;}}let group=i.word();let board=i.volumes();let rider=i.volumes();let initial=i.word();let mut contacts=(0..initial).map(|_|i.collision()).collect::<Vec<_>>();match provider_oracle::append(&mut contacts,&board,&rider,group,&mode){Ok(())=>out.push(1),Err(e)=>{out.push(0);probe_error(&mut out,&e);}}provider_collisions(&mut out,&contacts);},
  2=>{let board=std::array::from_fn(|_|i.body());let n=i.word();let attached=(0..n).map(|_|i.body()).collect();let local=i.word() as usize;let bg=i.word();let sg=i.word();let frequency=i.float();let n=i.word();let rows=(0..n).map(|_|RetailContactJacobian{words:std::array::from_fn(|_|i.word()),reaction_index_a:0,reaction_index_b:0}).collect();provider_reports(&mut out,&provider_oracle::collect(board,attached,local,bg,sg,frequency,rows));},_=>panic!("Provider op")}
  out[mark]=(out.len()-start) as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
