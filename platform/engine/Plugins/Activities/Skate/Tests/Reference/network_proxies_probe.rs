// Complete original network producer runs against explicit physical owners.
// Wire types and fingerprint are transport; encoding/capture identity is separate.
extern crate self as skate_net;
#[derive(Clone,Copy)]pub struct Pose{pub p:[f32;3],pub q:[f32;4]}
pub struct Body{pub pose:Pose,pub velocity:[f32;3],pub angular:[f32;3]}
pub struct Bone{pub index:u16,pub pose:Pose}
pub mod packed{use super::*;pub struct BodyState{pub root:Pose,pub enabled:u64,pub bodies:Vec<Body>}pub struct PoseState{pub root:Pose,pub bones:Vec<Bone>}}
// Schema's format/hash result is overwritten with the supplied wire identity.
pub fn hash(_: &[u8])->u64{0}
pub mod animation{pub fn native_matrix(m:skate_core::physics::skeleton_animation_record::AnimationPartTransform)->bevy::prelude::Mat4{use bevy::prelude::*;Mat4::from_cols(Vec3::new(m[0][0],m[0][1],m[0][2]).extend(0.),Vec3::new(m[1][0],m[1][1],m[1][2]).extend(0.),Vec3::new(m[2][0],m[2][1],m[2][2]).extend(0.),Vec3::new(m[3][0],m[3][1],m[3][2]).extend(1.))}}
mod proxy_oracle{
 use super::*;
 use bevy::prelude::{Mat4,Mat3,Quat,Vec3,Transform};
 pub struct ProbeBoard{pub bodies:[BodySnapshot;7]}
 impl ProbeBoard{pub fn bodies(&self)->&[BodySnapshot;7]{&self.bodies}}
 pub struct ProbeSkeleton{pub bodies:[BodySnapshot;26],pub definition:SkeletonBodyDefinition,pub volumes:Vec<BoardWorldVolume>}
 impl ProbeSkeleton{pub fn bodies(&self)->&[BodySnapshot;26]{&self.bodies}}
 pub struct PhysicsSettings{pub masses:[RetailBodyMassProperties;7],pub authored:u32,pub deck_geometry:u32,pub truck_shape:skate_core::physics::mass::MassShape,pub wheel_radius:f32,pub truck_collisions:bool,pub volumes:Vec<BoardWorldVolume>}
 pub struct GamePhysics{pub board:ProbeBoard,pub settings:PhysicsSettings,pub network_proxies:network::Proxies,pub network_contacts:usize,pub contact_count:usize}
 pub struct Animated{pub bone_indices:[usize;24],pub roots:skate_core::physics::skeleton_root::SkeletonRootFrames}
 #[derive(Clone,Copy)]pub struct BoardBones{pub front_truck:usize,pub back_truck:usize,pub front_left_wheel:usize,pub front_right_wheel:usize,pub back_left_wheel:usize,pub back_right_wheel:usize}
 pub struct OutputPose{pub board_bones:BoardBones}pub struct Output{pub pose:OutputPose}
 pub struct FrameNames{pub bone_names:Vec<String>}pub struct Evaluator{pub frames:FrameNames}pub struct Animation{pub evaluator:Evaluator}
 pub struct Possession;impl Possession{pub fn volume_enabled(&self,_:CollisionBody)->bool{true}}
 pub struct Targets{pub bodies:Vec<BodySnapshot>}pub struct Drives{pub targets:Targets}
 pub struct SkaterRuntime{pub skeleton:ProbeSkeleton,pub animated_skeleton:Animated,pub skeleton_output:Output,pub animation:Animation,pub board_possession_live:Possession,pub skeleton_collision:SkeletonCollisionMode,pub skeleton_drives:Drives,pub render_pose:Vec<AnimationPartTransform>}
 pub mod colliders{use super::*;pub fn world_volumes(_: &ProbeBoard,s:&PhysicsSettings)->Vec<BoardWorldVolume>{s.volumes.clone()}}
 pub mod skeleton_colliders{use super::*;pub fn world_volumes(s:&ProbeSkeleton,_:&SkeletonCollisionMode)->Result<Vec<BoardWorldVolume>,String>{Ok(s.volumes.clone())}}
 #[path="../network-source/network_forward.rs"]pub mod network;
 #[path="../network-source/assembly_contacts.rs"]pub mod assembly_contacts;
 // Checker inserts the exact original solve.rs remote loop here.
 include!("../network-source/remote_loop.rs");
 pub fn make(i:&mut ProbeInput)->(GamePhysics,SkaterRuntime,u64){
  let definition=i.definition().unwrap();let board=std::array::from_fn(|_|i.body());let skeleton=std::array::from_fn(|_|i.body());let masses=std::array::from_fn(|_|RetailBodyMassProperties{local_mass_frame:skate_core::physics::rigid_body::RetailLocalMassFrame{basis:Basis3{columns:[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]},translation:Vector3::ZERO},dynamics:i.inertia()});let target_count=i.word();let board_volumes=i.volumes();let rider_volumes=i.volumes();let fingerprint=i.wide();
  let settings=SkeletonCollisionSettings{enabled:false,normal_material:RetailContactMaterial{static_friction:0.,dynamic_friction:0.,restitution:0.},compliant:[false;24],priority:[0.;24],effect_time:0.};
  let target_seed=board[0];let physics=GamePhysics{board:ProbeBoard{bodies:board},settings:PhysicsSettings{masses,authored:0,deck_geometry:0,truck_shape:skate_core::physics::mass::MassShape::Sphere{radius:0.1},wheel_radius:0.1,truck_collisions:true,volumes:board_volumes},network_proxies:Default::default(),network_contacts:0,contact_count:0};
  let skater=SkaterRuntime{skeleton:ProbeSkeleton{bodies:skeleton,definition,volumes:rider_volumes},animated_skeleton:Animated{bone_indices:[0;24],roots:Default::default()},skeleton_output:Output{pose:OutputPose{board_bones:BoardBones{front_truck:0,back_truck:0,front_left_wheel:0,front_right_wheel:0,back_left_wheel:0,back_right_wheel:0}}},animation:Animation{evaluator:Evaluator{frames:FrameNames{bone_names:Vec::new()}}},board_possession_live:Possession,skeleton_collision:SkeletonCollisionMode::new_normal(settings,false),skeleton_drives:Drives{targets:Targets{bodies:vec![target_seed;target_count as usize]}},render_pose:Vec::new()};(physics,skater,fingerprint)
 }
}
impl ProbeInput{
 fn wide(&mut self)->u64{let lo=self.word();let hi=self.word();u64::from(lo)|(u64::from(hi)<<32)}
 fn inertia(&mut self)->RetailInertiaDynamics{RetailInertiaDynamics{inverse_tensor:self.vector(),inverse_mass:self.float(),spherical:self.float(),maximum_linear_velocity:self.float(),maximum_angular_velocity:self.float(),linear_drag:self.float(),angular_drag:self.float()}}
 fn network_pose(&mut self)->Pose{Pose{p:self.floats(),q:self.floats()}}
 fn network_state(&mut self)->packed::BodyState{let root=self.network_pose();let enabled=self.wide();let n=self.word();let bodies=(0..n).map(|_|Body{pose:self.network_pose(),velocity:self.floats(),angular:self.floats()}).collect();packed::BodyState{root,enabled,bodies}}
 fn proxies(&mut self)->proxy_oracle::network::Proxies{let n=self.word();let bodies=(0..n).map(|_|self.body()).collect();proxy_oracle::network::Proxies{bodies,volumes:self.volumes()}}
}
fn wide(out:&mut Vec<u32>,w:u64){out.extend([w as u32,(w>>32) as u32]);}
fn proxies(out:&mut Vec<u32>,p:&proxy_oracle::network::Proxies){out.push(p.bodies.len() as u32);for b in &p.bodies{probe_body(out,*b);}provider_volumes(out,&p.volumes);}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=ProbeInput{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for index in 0..count{let op=i.word();out.extend([index,op,0]);let mark=out.len()-1;let start=out.len();match op{
  0=>{let(c,r)=proxy_oracle::network::bounds(i.primitive());probe_floats(&mut out,c.to_array());out.push(r.to_bits());},
  1|2=>{let(mut physics,skater,fingerprint)=proxy_oracle::make(&mut i);let schema=proxy_oracle::network::migration_schema(&physics,&skater,fingerprint).unwrap();wide(&mut out,schema.fingerprint);let entries=proxy_oracle::network::migration_entries(&schema);out.push(entries.len() as u32);for(index,v)in entries{out.push(index as u32);provider_volumes(&mut out,&[v]);}
   if op==2{physics.network_proxies=i.proxies();proxies(&mut out,&physics.network_proxies);let n=i.word();out.push(n);for _ in 0..n{let cmd=i.word();out.push(cmd);match cmd{
    0=>{let frame=i.network_state();let age=i.float();let mut p=std::mem::take(&mut physics.network_proxies);p.append(&frame,&schema,&physics,&skater,age);physics.network_proxies=p;},
    1=>physics.network_proxies=Default::default(),
    2=>{let n=i.word();let mut contacts=(0..n).map(|_|i.collision()).collect();proxy_oracle::remote(&mut physics,&skater,&mut contacts);out.push(physics.network_contacts as u32);provider_collisions(&mut out,&contacts);},_=>panic!("Proxy command")}
    proxies(&mut out,&physics.network_proxies);
   }}for b in physics.board.bodies{probe_body(&mut out,b);}for b in skater.skeleton.bodies{probe_body(&mut out,b);}probe_definition(&mut out,&skater.skeleton.definition);
  },
  3=>{let board=i.volumes();let rider=i.volumes();let remote=i.volumes();let n=i.word();let mut contacts=(0..n).map(|_|i.collision()).collect::<Vec<_>>();out.push(proxy_oracle::remote_explicit(&board,&rider,&remote,&mut contacts) as u32);provider_collisions(&mut out,&contacts);},_=>panic!("Proxy operation")}
  out[mark]=(out.len()-start) as u32;
 }assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
