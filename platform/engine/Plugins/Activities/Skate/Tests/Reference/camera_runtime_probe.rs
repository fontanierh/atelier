//! Full original active camera owner with observation-only module extensions.
#![allow(dead_code,unused_imports)]
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
pub use skate_core::migration_camera_observer::{Input,ReadValue,Observe};
use std::{io::{Read,Write},sync::{Arc,Mutex}};

#[derive(Clone)]
struct LogSink(Arc<Mutex<Vec<u8>>>);
impl Write for LogSink {
    fn write(&mut self,data:&[u8])->std::io::Result<usize> {self.0.lock().unwrap().extend(data);Ok(data.len())}
    fn flush(&mut self)->std::io::Result<()> {Ok(())}
}
impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for LogSink {
    type Writer=Self;
    fn make_writer(&'a self)->Self::Writer {self.clone()}
}
fn main() {
    let log=LogSink(Arc::new(Mutex::new(Vec::new())));
    let subscriber=tracing_subscriber::fmt().with_ansi(false).without_time().with_target(false)
        .with_writer(log.clone()).finish();
    bevy::log::tracing::subscriber::set_global_default(subscriber).unwrap();
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();
    let mut input=Input{data:bytes,at:0};let args:Vec<_>=std::env::args().collect();
    let mut output=Vec::new();
    if let Err(error)=camera::migration_camera_run(std::path::Path::new(&args[1]),&mut input,&mut output,&log) {
        eprintln!("{error}");std::process::exit(2);
    }
    assert_eq!(input.at,input.data.len());std::io::stdout().write_all(&output).unwrap();
}
