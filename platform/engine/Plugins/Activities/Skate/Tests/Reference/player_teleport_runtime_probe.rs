//! Whole frozen host; the checker appends observation-only privacy helpers.
#![allow(dead_code,unused_imports)]
mod physics;mod graph_host;mod graph_runtime;mod skater_animation;mod animation_pose;mod camera;mod difficulty;mod grind_world;mod input;mod scoring_runtime;mod skate_world;mod animation;mod crash_context;mod tuning;mod session_marker;
pub use physics::bridge;
use std::io::{Read,Write};
use skate_core::{player::input_phase::*,input::animation_packet::AnimationPacketFields,animation::output::{actor_packet::ExternalPhysicsInput,attributes::{AttributeName,AnimationAttribute,AttributePayload}}};
struct Input{data:Vec<u8>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn wide(&mut self)->u64{let lo=self.word();u64::from(lo)|(u64::from(self.word())<<32)}
 fn words<const N:usize>(&mut self)->[u32;N]{core::array::from_fn(|_|self.word())}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{core::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->[[f32;4];4]{core::array::from_fn(|_|self.floats())}
 fn attribute(&mut self)->AnimationAttribute{AnimationAttribute{name:AttributeName(self.words()),kind:self.word()as u8,status:self.word()as u8,sequence_id:self.word()as i32,begin_time:self.float(),end_time:self.float(),payload:AttributePayload(core::array::from_fn(|_|(self.word()!=0).then(||self.word())))}}
}
struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,v:u32){self.0.push(v)}
 fn words<const N:usize>(&mut self,v:[u32;N]){self.0.extend(v)}
 fn optional(&mut self,v:Option<f32>){self.word(v.is_some()as u32);if let Some(v)=v{self.float(v)}}
 fn wide(&mut self,v:u64){self.word(v as u32);self.word((v>>32)as u32)}
 fn float(&mut self,v:f32){self.word(v.to_bits())}
 fn floats<const N:usize>(&mut self,v:[f32;N]){self.0.extend(v.map(f32::to_bits))}
 fn matrix(&mut self,v:[[f32;4];4]){for v in v{self.floats(v)}}
 fn status(&mut self,r:Result<(),String>){self.word(r.is_ok()as u32);if let Err(e)=r{self.word(e.len()as u32);self.0.extend(e.bytes().map(u32::from))}}
}
// GENERATED_CANONICAL_PROTOCOL
fn main(){let args=std::env::args().collect::<Vec<_>>();let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut i=Input{data,at:0};let mut o=Output(Vec::new());physics::migration_player_teleport_run(std::path::Path::new(&args[1]),std::path::Path::new(&args[2]),&mut i,&mut o).unwrap();assert_eq!(i.at,i.data.len());let mut output=std::io::BufWriter::new(std::io::stdout().lock());for w in o.0{output.write_all(&w.to_le_bytes()).unwrap();}}
