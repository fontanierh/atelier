//! Entire frozen host: this executable only transports published actions and
//! reads live owners. Every constructor, control, graph, solve and frame is real.
#![allow(dead_code, unused_imports, non_snake_case)]
mod physics;
mod graph_host;
mod graph_runtime;
mod skater_animation;
mod animation_pose;
mod camera;
mod difficulty;
mod grind_world;
mod input;
mod scoring_runtime;
mod skate_world;
mod animation;
mod crash_context;
mod tuning;
mod session_marker;
pub use physics::bridge;
use std::{io::{Read, Write},sync::{Arc,Mutex}};

struct Input { data:Vec<u8>,at:usize }
impl Input {
 fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn wide(&mut self)->u64 {u64::from(self.word())|(u64::from(self.word())<<32)}
 fn float(&mut self)->f32 {f32::from_bits(self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N] {core::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->[[f32;4];4] {core::array::from_fn(|_|self.floats())}
}
struct Output(Vec<u32>);
impl Output {
 fn word(&mut self,v:u32){self.0.push(v)}
 fn words<const N:usize>(&mut self,v:[u32;N]){self.0.extend(v)}
 fn wide(&mut self,v:u64){self.word(v as u32);self.word((v>>32)as u32)}
 fn float(&mut self,v:f32){self.word(v.to_bits())}
 fn floats<const N:usize>(&mut self,v:[f32;N]){self.0.extend(v.map(f32::to_bits))}
 fn optional(&mut self,v:Option<f32>){self.word(v.is_some()as u32);if let Some(v)=v{self.float(v)}}
 fn matrix(&mut self,v:[[f32;4];4]){for c in v{self.floats(c)}}
 fn string(&mut self,v:&str){self.word(v.len()as u32);self.0.extend(v.bytes().map(u32::from))}
 fn status(&mut self,v:Result<(),String>){match v{Ok(())=>self.word(1),Err(e)=>{self.word(0);self.string(&e)}}}
 fn bytes(&mut self,v:&[u8]){self.word(v.len()as u32);for v in v{self.word(u32::from(*v))}}
 fn carrier(&mut self,c:&skate_core::scoring::carrier::Carrier){self.word(c.scorable.id as u32);self.word(c.scorable.class);self.word(c.scorable.score_type as u32);self.word(c.points as u32);self.float(c.factor);self.float(c.reward);self.float(c.announcement_threshold);self.word(c.start_tick);self.word(c.delay_ticks);self.word(c.announced as u32);self.word(c.completed as u32);self.word(c.unannounced as u32);self.word(c.switch as u32);self.word(c.fakie as u32)}
}
fn gameplay_block(o:&mut Output,f:impl FnOnce(&mut Output)){let at=o.0.len();o.word(0);f(o);o.0[at]=(o.0.len()-at-1)as u32;}
include!("gameplay_player_observers.inc");

#[derive(Clone)]
struct LogSink(Arc<Mutex<Vec<u8>>>);
impl Write for LogSink {
 fn write(&mut self,v:&[u8])->std::io::Result<usize>{self.0.lock().unwrap().extend(v);Ok(v.len())}
 fn flush(&mut self)->std::io::Result<()>{Ok(())}
}
impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for LogSink {
 type Writer=Self;
 fn make_writer(&'a self)->Self::Writer{self.clone()}
}
fn main()->Result<(),String>{
 let log=LogSink(Arc::new(Mutex::new(Vec::new())));
 let subscriber=tracing_subscriber::fmt().with_ansi(false).without_time().with_target(false).with_writer(log.clone()).finish();
 bevy::log::tracing::subscriber::set_global_default(subscriber).map_err(|e|e.to_string())?;
 let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).map_err(|e|e.to_string())?;
 let mut i=Input{data,at:0};let mut o=Output(Vec::new());let args=std::env::args().collect::<Vec<_>>();
 physics::bridge::migration_gameplay_run(std::path::Path::new(&args[1]),&mut i,&mut o,&log)?;
 assert_eq!(i.at,i.data.len());
 let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in o.0{stdout.write_all(&w.to_le_bytes()).map_err(|e|e.to_string())?}Ok(())
}
