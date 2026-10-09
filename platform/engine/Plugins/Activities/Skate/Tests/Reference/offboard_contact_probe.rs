mod math{pub use skate_core::math::*;}
mod physics{pub use skate_core::physics::*;
#[path="native_arithmetic.rs"]pub(crate)mod native_arithmetic;
#[path="reciprocal_sqrt.rs"]pub(crate)mod reciprocal_sqrt;
}
mod air{pub use skate_core::air::*;}
mod trigonometry{pub use skate_core::trigonometry::*;}
// WORLD_PROTOCOL
use skate_core::air::trajectory::{QueryRequest,QueryResult,Trajectory};
use skate_core::player::offboard::contact_toolkit as external;
#[path="offboard_contact_world.rs"]mod static_world;
mod toolkit{
// ORIGINAL_TOOLKIT
pub use probes::Descriptor;
pub fn migration_observe(o:&mut crate::Writer,s:&Owner){
 crate::layout_out(o,&s.layout);o.word(s.pending.is_some()as u32);if let Some((b,r))=&s.pending{crate::batch_out(o,b);crate::results_out(o,r)}
 o.word(s.readiness);crate::prefix_out(o,s.prefix);let c=s.candidate;crate::v(o,c.position);crate::v(o,c.normal);crate::v(o,c.direction);o.word(c.flags);o.scalar(c.low);o.scalar(c.high);o.scalar(c.order);o.word(c.segment as u32);o.word(c.kind);
 // Derived Debug exposes only the five retained integer fields, in declaration
 // order, without changing the original private History implementation.
 let text=format!("{:?}",s.history);let words:Vec<u32>=text.split(|c:char|!c.is_ascii_digit()).filter(|s|!s.is_empty()).map(|s|s.parse().unwrap()).collect();assert_eq!(words.len(),5);for word in words{o.word(word)}
}
}
fn v(o:&mut Writer,a:[f32;4]){for x in a{o.scalar(x)}}
fn matrix_out(o:&mut Writer,m:[[f32;4];4]){for p in m{v(o,p)}}
fn read_v(r:&mut Reader)->[f32;4]{std::array::from_fn(|_|r.scalar())}
fn read_input(r:&mut Reader)->toolkit::Input{toolkit::Input::from_vectors(std::array::from_fn(|_|read_v(r)))}
fn read_line(r:&mut Reader)->toolkit::LineProbe{toolkit::LineProbe{start:read_v(r),end:read_v(r),radius:r.scalar()}}
fn read_request(r:&mut Reader)->QueryRequest{QueryRequest{trajectory:Trajectory{position:read_v(r),velocity:read_v(r),acceleration:read_v(r),duration:r.scalar()},radius:r.scalar(),start_error:r.scalar(),end_error:r.scalar()}}
fn line_out(o:&mut Writer,p:toolkit::LineProbe){v(o,p.start);v(o,p.end);o.scalar(p.radius)}
fn descriptors_out(o:&mut Writer,d:&[toolkit::Descriptor]){o.word(d.len()as u32);for p in d{line_out(o,p.line);o.word(p.forward_index as u32);o.word(p.reverse_index.is_some()as u32);o.word(p.reverse_index.unwrap_or(0)as u32)}}
fn layout_out(o:&mut Writer,l:&toolkit::ProbeLayout){for p in l.trajectories{line_out(o,p)}descriptors_out(o,&l.secondary);descriptors_out(o,&l.primary)}
fn request_out(o:&mut Writer,q:QueryRequest){v(o,q.trajectory.position);v(o,q.trajectory.velocity);v(o,q.trajectory.acceleration);o.scalar(q.trajectory.duration);o.scalar(q.radius);o.scalar(q.start_error);o.scalar(q.end_error)}
fn batch_out(o:&mut Writer,b:&toolkit::Batch){let p=b.input;for a in [p.position,p.forward,p.up,p.right,p.velocity,p.animation_up,p.animation_right]{v(o,a)}o.word(b.matching_group as u32);o.word(b.mesh_reject_mask);for q in b.trajectories{request_out(o,q)}o.word(b.lines.len()as u32);for &p in &b.lines{line_out(o,p)}descriptors_out(o,&b.secondary);descriptors_out(o,&b.primary)}
fn query_out(o:&mut Writer,q:QueryResult){v(o,q.contact_position);v(o,q.contact_normal);v(o,q.landing_normal);o.scalar(q.contact_time);matrix_out(o,q.contact_transform);o.word(q.contact_frame as u32);o.word(q.surface);o.word(q.geometry)}
fn hit_out(o:&mut Writer,h:Option<toolkit::LineHit>){o.word(h.is_some()as u32);if let Some(h)=h{v(o,h.position);v(o,h.normal);o.scalar(h.fraction);o.word(h.surface as u32);matrix_out(o,h.mesh_frame);o.word(h.geometry)}}
fn results_out(o:&mut Writer,r:&toolkit::QueryResults){for q in r.trajectories{query_out(o,q)}o.word(r.lines.len()as u32);for &h in &r.lines{hit_out(o,h)}o.word(r.edges.len()as u32);for e in &r.edges{v(o,e[0]);v(o,e[1])}}
fn prefix_out(o:&mut Writer,p:toolkit::ContactPrefix){v(o,p.position);v(o,p.normal);matrix_out(o,p.support_frame);v(o,p.target_position);v(o,p.target_normal);v(o,p.edge_position);v(o,p.edge_normal);o.scalar(p.scalar_160);o.word(p.kind_164);o.scalar(p.distance_168);o.scalar(p.distance_172);o.word(p.flags_176);o.word(p.support_180)}
fn samples_out(o:&mut Writer,s:&toolkit::Samples){for points in [&s.ground,&s.other]{o.word(points.len()as u32);for p in points{v(o,p.position);v(o,p.normal);o.scalar(p.forward_distance);o.scalar(p.height);o.word(p.flags);o.scalar(p.sort_distance)}}o.word(s.original_ground_count as u32)}
fn collected_out(o:&mut Writer,c:Option<toolkit::Collected>){o.word(c.is_some()as u32);if let Some(c)=c{batch_out(o,&c.batch);results_out(o,&c.results);prefix_out(o,c.prefix);samples_out(o,&c.samples)}}
fn read_world(r:&mut Reader)->Result<BoardWorld,&'static str>{let count=r.word();let triangles=(0..count).map(|_|cached(triangle(r))).collect();let enabled=r.word()!=0;let data=metadata(r);if enabled{BoardWorld::with_query_metadata(triangles,data)}else{Ok(BoardWorld::new(triangles))}}
fn status(o:&mut Writer,result:Result<(),&str>){o.word(result.is_ok()as u32);o.error(result.err())}
fn scene(world:&Result<BoardWorld,&'static str>)->Result<static_world::StaticScene<'_>,&'static str>{match world{Ok(w)=>static_world::StaticScene::new(w),Err(e)=>Err(*e)}}
fn external_input(p:toolkit::Input)->external::Input{external::Input::from_vectors([p.position,p.forward,p.up,p.right,p.velocity,p.animation_up,p.animation_right])}
struct Bridge<'a>(static_world::StaticScene<'a>);
impl toolkit::Scene for Bridge<'_>{
 type Error=&'static str;
 fn execute(&self,b:&toolkit::Batch)->Result<toolkit::QueryResults,Self::Error>{
  // The duplicate module supplies private-state observation only. The actual
  // unchanged host scene consumes the identical input, requests and line wire.
  let mut batch=external::ProbeLayout::stock().prepare(external_input(b.input),b.matching_group);batch.mesh_reject_mask=b.mesh_reject_mask;batch.trajectories=b.trajectories;batch.lines=b.lines.iter().map(|p|external::LineProbe{start:p.start,end:p.end,radius:p.radius}).collect();
  let r=external::Scene::execute(&self.0,&batch)?;
  Ok(toolkit::QueryResults{trajectories:r.trajectories,lines:r.lines.into_iter().map(|h|h.map(|h|toolkit::LineHit{position:h.position,normal:h.normal,fraction:h.fraction,surface:h.surface,mesh_frame:h.mesh_frame,geometry:h.geometry})).collect(),edges:r.edges})
 }
}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Reader{bytes,at:0};let count=input.word();let mut all=vec![];
 for index in 0..count{
  let mut world=read_world(&mut input);let commands=input.word();let mut owner=toolkit::Owner::default();let mut out=Writer{words:vec![]};status(&mut out,world.as_ref().map(|_|()).map_err(|e|*e));toolkit::migration_observe(&mut out,&owner);out.word(commands);
  for _ in 0..commands{
   let op=input.word();out.word(op);
   match op{
    0=>owner.begin_input(),1=>owner.reset_history(),3=>collected_out(&mut out,owner.refresh()),
    2|4=>{let packet=read_input(&mut input);let group=input.word()as i32;let active=scene(&world).map(Bridge);if op==2{status(&mut out,active.and_then(|s|owner.submit(packet,group,&s)))}else{match active.and_then(|s|toolkit::Scene::execute(&s,&toolkit::ProbeLayout::stock().prepare(packet,group))){Ok(r)=>{status(&mut out,Ok(()));results_out(&mut out,&r)},Err(e)=>status(&mut out,Err(e))}}},
    5=>{let num=input.word();let requests:Vec<_>=(0..num).map(|_|{let p=read_line(&mut input);skate_core::player::offboard::ground_query::Line{start:Vector3::new(p.start[0],p.start[1],p.start[2]),end:Vector3::new(p.end[0],p.end[1],p.end[2]),radius:p.radius}}).collect();let group=input.word()as i32;match scene(&world).and_then(|s|s.lines(&requests,group)){Ok(lines)=>{status(&mut out,Ok(()));out.word(lines.len()as u32);for hit in lines{out.word(hit.is_some()as u32);if let Some(h)=hit{out.vector(h.position);out.vector(h.face_normal);out.scalar(h.fraction);out.word(h.packed_surface as u32)}}},Err(e)=>status(&mut out,Err(e))}},
    6=>{let request=read_request(&mut input);let group=input.word()as i32;let reject=input.word();match scene(&world).and_then(|s|s.trajectory(request,group,reject)){Ok(r)=>{status(&mut out,Ok(()));query_out(&mut out,r)},Err(e)=>status(&mut out,Err(e))}},
    7=>{world=read_world(&mut input);status(&mut out,world.as_ref().map(|_|()).map_err(|e|*e))},
    _=>panic!("Unknown offboard contact operation"),
   }
   toolkit::migration_observe(&mut out,&owner);
  }
  all.extend([index,out.words.len()as u32]);all.extend(out.words);
 }
 assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&all.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
