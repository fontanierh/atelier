//! Actual newest pinned bridge Session and marker runtime; no completed producers.
// @GAMEPLAY_PROBE_PREFIX
impl Input{
 fn text(&mut self)->String{let n=self.word();String::from_utf8((0..n).map(|_|self.word()as u8).collect()).unwrap()}
 fn xbox(&mut self)->skate_core::input::xbox::XboxState{skate_core::input::xbox::XboxState{buttons:self.word()as u16,triggers:std::array::from_fn(|_|self.word()as u8),left:std::array::from_fn(|_|self.word()as i16),right:std::array::from_fn(|_|self.word()as i16)}}
 fn snapshot(&mut self)->(Vec<[[f32;3];3]>,Vec<Vec<[f32;3]>>){let n=self.word();let triangles=(0..n).map(|_|std::array::from_fn(|_|self.floats())).collect();let n=self.word();let rails=(0..n).map(|_|{let n=self.word();(0..n).map(|_|self.floats()).collect()}).collect();(triangles,rails)}
}
fn main()->Result<(),String>{
 let log=LogSink(Arc::new(Mutex::new(Vec::new())));
 let subscriber=tracing_subscriber::fmt().with_ansi(false).without_time().with_target(false).with_writer(log.clone()).finish();
 bevy::log::tracing::subscriber::set_global_default(subscriber).map_err(|e|e.to_string())?;
 let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).map_err(|e|e.to_string())?;
 let mut i=Input{data,at:0};let mut o=Output(Vec::new());let args=std::env::args().collect::<Vec<_>>();
 physics::bridge::migration_session_run(std::path::Path::new(&args[1]),&mut i,&mut o,&log)?;
 physics::migration_latest_vert_leaf_run(&mut i,&mut o);
 assert_eq!(i.at,i.data.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in o.0{stdout.write_all(&w.to_le_bytes()).map_err(|e|e.to_string())?}Ok(())
}
