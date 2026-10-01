//! Complete unchanged original host/core; appended private-field observers only.
#![allow(dead_code, unused_imports)]
mod physics;mod graph_host;mod graph_runtime;mod skater_animation;mod animation_pose;mod camera;mod difficulty;mod grind_world;mod input;mod scoring_runtime;mod skate_world;mod animation;mod crash_context;mod tuning;mod session_marker;
pub use physics::bridge;
use std::io::{Read,Write};
struct Input{data:Vec<u8>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn words<const N:usize>(&mut self)->[u32;N]{core::array::from_fn(|_|self.word())}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{core::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->[[f32;4];4]{core::array::from_fn(|_|self.floats())}
}
struct Output(Vec<u32>);
impl Output{
 fn word(&mut self,v:u32){self.0.push(v)}
 fn words<const N:usize>(&mut self,v:[u32;N]){self.0.extend(v)}
 fn float(&mut self,v:f32){self.word(v.to_bits())}
 fn floats<const N:usize>(&mut self,v:[f32;N]){self.0.extend(v.map(f32::to_bits))}
 fn matrix(&mut self,v:[[f32;4];4]){for row in v{self.floats(row)}}
 fn optional(&mut self,v:Option<f32>){self.word(v.is_some()as u32);if let Some(v)=v{self.float(v)}}
 fn status(&mut self,v:Result<(),String>){match v{Ok(())=>self.word(1),Err(e)=>{self.word(0);self.word(e.len()as u32);self.0.extend(e.bytes().map(u32::from));}}}
}
fn main(){let args=std::env::args().collect::<Vec<_>>();let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut i=Input{data,at:0};let mut o=Output(Vec::new());physics::migration_air_reckoning_run(std::path::Path::new(&args[1]),std::path::Path::new(&args[2]),&mut i,&mut o).unwrap();assert_eq!(i.at,i.data.len());for word in o.0{std::io::stdout().write_all(&word.to_le_bytes()).unwrap();}}
