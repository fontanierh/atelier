// Complete original core query plus byte-identical host world leaves.
extern crate self as skate_core;
#[path="air-host-world.rs"]mod air_host_world;
use std::io::{Read,Write};
use std::cell::RefCell;
use air::trajectory::{Trajectory,QueryRequest,QueryResult,SurfaceHit,query_trajectory};
use physics::{board_world::{BoardWorld,WorldTriangle},world_contact::triangle_from_volume,contact::RetailContactMaterial};
struct Reader{words:Vec<u32>,at:usize}
impl Reader{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->[f32;4]{std::array::from_fn(|_|self.float())}
 fn trajectory(&mut self)->Trajectory{Trajectory{position:self.vector(),velocity:self.vector(),acceleration:self.vector(),duration:self.float()}}
 fn request(&mut self)->QueryRequest{QueryRequest{trajectory:self.trajectory(),radius:self.float(),start_error:self.float(),end_error:self.float()}}
 fn world(&mut self)->BoardWorld{
  let n=self.word();let triangles=(0..n).map(|_|{
   let vertices=std::array::from_fn(|_|math::Vector3::new(self.float(),self.float(),self.float()));let fatness=self.float();let flags=self.word();let tag=self.word();
   WorldTriangle{triangle:triangle_from_volume(vertices,fatness,[1.;3],flags),material:RetailContactMaterial{static_friction:0.,dynamic_friction:0.,restitution:0.},tag}
  }).collect();BoardWorld::new(triangles)
 }
}
fn floats<const N:usize>(out:&mut Vec<u32>,v:[f32;N]){out.extend(v.map(f32::to_bits));}
fn matrix(out:&mut Vec<u32>,v:[[f32;4];4]){for p in v{floats(out,p);}}
fn result(out:&mut Vec<u32>,v:QueryResult){floats(out,v.contact_position);floats(out,v.contact_normal);floats(out,v.landing_normal);out.push(v.contact_time.to_bits());matrix(out,v.contact_transform);out.extend([v.contact_frame as u32,v.surface,v.geometry]);}
fn status(out:&mut Vec<u32>,e:Option<&str>){let bytes=e.unwrap_or("").as_bytes();out.extend([e.is_none()as u32,bytes.len()as u32]);out.extend(bytes.iter().map(|&c|u32::from(c)));}
fn hit(out:&mut Vec<u32>,v:Option<SurfaceHit>){out.push(v.is_some()as u32);if let Some(v)=v{floats(out,v.position);floats(out,v.normal);matrix(out,v.transform);out.extend([v.surface,v.geometry]);}}
fn triangles(out:&mut Vec<u32>,v:Vec<[[f32;4];3]>){out.push(v.len()as u32);for t in v{for p in t{floats(out,p);}}}
fn completed(out:&mut Vec<u32>,r:Result<QueryResult,String>){match r{Ok(v)=>{status(out,None);result(out,v)},Err(e)=>{status(out,Some(&e));let mut v=QueryResult::miss();v.contact_time=17.;result(out,v)}}}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Reader{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for index in 0..count{
  let world=i.world();let op=i.word();out.extend([index,op,0]);let mark=out.len()-1;
  match op{
   0|4=>{
    let request=i.request();let failure=i.word();let trace=RefCell::new(Vec::new());
    let r=query_trajectory(request,|start,end,radius|{
     {let mut t=trace.borrow_mut();t.push(1);floats(&mut t,start);floats(&mut t,end);t.push(radius.to_bits());}
     if failure==1{return Err("Explicit line producer failure".into())}air_host_world::line(&world,start,end,radius)
    },|center,radius|{
     {let mut t=trace.borrow_mut();t.push(2);floats(&mut t,center);t.push(radius.to_bits());}
     if failure==2{return Err("Explicit nearby producer failure".into())}air_host_world::nearby(&world,center,radius)
    });completed(&mut out,r);let t=trace.into_inner();out.push(t.len()as u32);out.extend(t);
   },
   1=>{let start=i.vector();let end=i.vector();let radius=i.float();match air_host_world::line(&world,start,end,radius){Ok(v)=>{status(&mut out,None);hit(&mut out,v)},Err(e)=>{status(&mut out,Some(&e));hit(&mut out,None)}}},
   2=>{let center=i.vector();let radius=i.float();match air_host_world::nearby(&world,center,radius){Ok(v)=>{status(&mut out,None);triangles(&mut out,v)},Err(e)=>{status(&mut out,Some(&e));triangles(&mut out,Vec::new())}}},
   3=>{let trajectory=i.trajectory();let time=i.float();floats(&mut out,trajectory.position_at(time));floats(&mut out,trajectory.velocity_at(time));let(p,t)=trajectory.highest_position();floats(&mut out,p);out.push(t.to_bits());},
   5=>{let request=i.request();for _ in 0..2{completed(&mut out,query_trajectory(request,|s,e,r|air_host_world::line(&world,s,e,r),|p,r|air_host_world::nearby(&world,p,r)));}},
   _=>panic!("operation")
  };out[mark]=(out.len()-mark-1)as u32;
 }
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}
}
