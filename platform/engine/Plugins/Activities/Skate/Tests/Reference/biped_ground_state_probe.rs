#![allow(dead_code,unused_imports,non_snake_case)]
mod math{pub use skate_core::math::*;}
mod physics{pub use skate_core::physics::*;}
// WORLD_PROTOCOL
// GEOMETRY_PROTOCOL
use skate_core::player::offboard::{ground_entry,ground_input,ground_job,controller,contact_toolkit};
mod ground_entry_bridge;
struct Input<'a>{r:&'a mut Reader}
impl Input<'_>{fn word(&mut self)->u32{self.r.word()}fn float(&mut self)->f32{self.r.scalar()}}
struct Output<'a>{r:&'a mut Writer}
impl Output<'_>{fn word(&mut self,v:u32){self.r.word(v)}fn float(&mut self,v:f32){self.r.scalar(v)}}
// GENERATED_PROTOCOL
fn snapshot(out:&mut Writer,state:&ground_entry::State,contact:&contact_toolkit::ContactPrefix,geometry:&offboard::ground_geometry::State){let at=out.words.len();out.word(0);let mut o=Output{r:out};observe_BipedGroundState(&mut o,state);observe_BipedContactPrefix(&mut o,contact);offboard::ground_geometry::migration_observe(o.r,geometry);o.r.words[at]=(o.r.words.len()-at-1)as u32;}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let mut out=Writer{words:vec![]};let count=reader.word();out.word(count);
 for c in 0..count{
  let mut world=read_world(&mut reader).unwrap();let mut state=ground_entry::State::default();let mut contact=contact_toolkit::ContactPrefix::reset();let mut geometry=offboard::ground_geometry::migration_new(reader.scalar());let n=reader.word();out.word(c);out.word(n);snapshot(&mut out,&state,&contact,&geometry);
  for _ in 0..n{
   let op=reader.word();out.word(op);let mut i=Input{r:&mut reader};let mut o=Output{r:&mut out};match op{
    0=>{let p=state.enter(&read_BipedGroundEntryInput(&mut i));observe_BipedGroundPlacement(&mut o,&p);},
    1=>{let input=read_BipedGroundControlInput(&mut i);let a=skate_core::point_graph::PointGraph{x:std::array::from_fn(|_|i.float()),y:std::array::from_fn(|_|i.float())};let b=skate_core::point_graph::PointGraph{x:std::array::from_fn(|_|i.float()),y:std::array::from_fn(|_|i.float())};observe_BipedGroundControlOutput(&mut o,&ground_input::calculate(&input,&a,&b));},
    2=>{let p=ground_job::prepare(&mut contact,&mut state.distance_164,read_BipedGroundPrepareInput(&mut i),|v|Ok::<_,String>(geometry.consume(v))).unwrap();observe_BipedGroundJob(&mut o,&p.job);adjustment_out(o.r,p.geometry);},
    3=>{let animation=ground_job::sync_frames(&mut state,contact,read_BipedGroundResult(&mut i));for v in animation{for x in v{o.float(x)}}},
    4=>{let frame=read_matrix(i.r);let v=read_v(i.r);let context=read_context(i.r);let flags=i.word();let result=geometry.submit(&world,frame,v,context,flags);status(o.r,result.as_ref().map(|_|()).map_err(|e|e.as_str()));},
    5=>{state=read_BipedGroundState(&mut i);contact=read_BipedContactPrefix(&mut i);},6=>geometry.reset(),
    7=>{let result=read_world(i.r);status(o.r,result.as_ref().map(|_|()).map_err(|e|*e));world=result.unwrap();},
    8=>{let frame=read_matrix(i.r);let flags=i.word();let f=ground_entry_bridge::migration_effective(frame,flags);for v in f{for x in v{o.float(x)}}},_=>panic!("command")
   }snapshot(&mut out,&state,&contact,&geometry);
  }
 }
 assert_eq!(reader.at,reader.bytes.len());let mut w=std::io::stdout().lock();for v in out.words{w.write_all(&v.to_le_bytes()).unwrap();}
}
