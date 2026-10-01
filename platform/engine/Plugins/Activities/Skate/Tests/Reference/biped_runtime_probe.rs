//! Whole source owners; only wire transport and privacy observers are appended.
#![allow(dead_code,unused_imports,non_snake_case)]
mod physics;mod graph_host;mod graph_runtime;mod skater_animation;mod animation_pose;mod camera;mod difficulty;mod grind_world;mod input;mod scoring_runtime;mod skate_world;mod animation;mod crash_context;mod tuning;mod session_marker;
pub use physics::bridge;
use std::io::{Read,Write};
use skate_core::{player::{input_phase::*,offboard::*},animation::output::{attributes::AttributeName,actor_packet::ExternalPhysicsInput},air::state::{PhysicsAirState,PhysicsAirSettings},air::known::*,point_graph::PointGraph};
use skate_core::{math::Vector3,physics::{board_world::{BoardWorld,WorldTriangle,query_metadata::{QueryMetadata,QueryMesh,QueryPool,Bounds}},world_contact::triangle_from_volume,drive_frames::RetailAffineTransform,contact::RetailContactMaterial}};
type WipeoutFrame=skate_core::player::wipeout::Frame;
use skate_core::physics::skeleton_body::{SkeletonCollisionFeedback,SkeletonContactFlags};
struct Input{data:Vec<u8>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn wide(&mut self)->u64{u64::from(self.word())|(u64::from(self.word())<<32)}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->[[f32;4];4]{std::array::from_fn(|_|self.floats())}
 fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}
 fn text(&mut self)->String{let n=self.word();String::from_utf8((0..n).map(|_|self.word()as u8).collect()).unwrap()}
 fn curve<const N:usize>(&mut self)->PointGraph<N>{PointGraph{x:self.floats(),y:self.floats()}}
}
struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,v:u32){self.0.push(v)}fn words<const N:usize>(&mut self,v:[u32;N]){self.0.extend(v)}
 fn wide(&mut self,v:u64){self.word(v as u32);self.word((v>>32)as u32)}
 fn float(&mut self,v:f32){self.word(v.to_bits())}fn floats<const N:usize>(&mut self,v:[f32;N]){self.0.extend(v.map(f32::to_bits))}
 fn matrix(&mut self,v:[[f32;4];4]){for row in v{self.floats(row)}}
 fn vector(&mut self,v:Vector3){self.floats([v.x,v.y,v.z])}
 fn optional(&mut self,v:Option<f32>){self.word(v.is_some()as u32);if let Some(v)=v{self.float(v)}}
 fn status(&mut self,r:Result<(),String>){match r{Ok(())=>self.word(1),Err(e)=>{self.word(0);self.word(e.len()as u32);self.0.extend(e.bytes().map(u32::from))}}}
}
// GENERATED_PROTOCOL
// GENERATED_WORLD
// GENERATED_PROVIDER
fn main(){let a=std::env::args().collect::<Vec<_>>();let mut o=Output(vec![]);if a.len()==4{physics::migration_biped_load(std::path::Path::new(&a[1]),std::path::Path::new(&a[3]),&mut o).unwrap()}else{let mut data=vec![];std::io::stdin().read_to_end(&mut data).unwrap();let mut i=Input{data,at:0};physics::migration_biped_run(std::path::Path::new(&a[1]),std::path::Path::new(&a[2]),&mut i,&mut o).unwrap();assert_eq!(i.at,i.data.len())}for w in o.0{std::io::stdout().write_all(&w.to_le_bytes()).unwrap()}}
