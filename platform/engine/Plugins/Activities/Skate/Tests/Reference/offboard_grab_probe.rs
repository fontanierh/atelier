mod math{pub use skate_core::math::*;}
mod physics{
 pub use skate_core::physics::*;
 pub mod offboard{pub mod grab_scene{
// ORIGINAL_SCENE
 }}
 pub mod biped_ground{pub mod grab_runtime{
// ORIGINAL_OWNER
 pub fn migration_observe(o:&mut crate::Writer,c:&Owner){
  use crate::{query_out,records_out,record_option,line_out,hit_out,object_option,vo};let start=o.words.len();o.word(0);o.word(c.queries.len()as u32);for q in &c.queries{query_out(o,*q)}o.word(c.query_result.is_some()as u32);if let Some(records)=&c.query_result{records_out(o,records)}records_out(o,&c.pending);records_out(o,&c.validated);
  o.word(c.validation.is_some()as u32);if let Some(hits)=&c.validation{o.word(hits.len()as u32);for &h in hits{hit_out(o,h)}}for d in c.requests{o.word(d.is_some()as u32);if let Some(d)=d{o.word(d.kind);o.word(d.id)}}for d in &c.data{record_option(o,d.as_ref())}for d in c.data_ready{o.word(d as u32)}o.word(c.interactable_request.is_some()as u32);if let Some(lines)=c.interactable_request{for l in lines{line_out(o,l)}}object_option(o,c.interactable_result);o.word(c.interactable_latched as u32);o.word(c.flags_12836 as u32);vo(o,c.query_position);vo(o,c.validation_position);o.words[start]=(o.words.len()-start-1)as u32;
 }
 }}
}
// WORLD_PROTOCOL
use skate_core::player::offboard::{grab_scene as native,ground_query::QueryContext,ground_sync::{Bounds,BoardLimits}};
use physics::{offboard::grab_scene as host,biped_ground::grab_runtime::Owner};
fn v(r:&mut Reader)->[f32;4]{std::array::from_fn(|_|r.scalar())}fn m(r:&mut Reader)->[[f32;4];4]{std::array::from_fn(|_|v(r))}
fn vo(o:&mut Writer,v:[f32;4]){for x in v{o.scalar(x)}}fn mo(o:&mut Writer,m:[[f32;4];4]){for v in m{vo(o,v)}}
fn status(o:&mut Writer,result:Result<(),&str>){o.word(result.is_ok()as u32);o.error(result.err())}
fn descriptor(r:&mut Reader)->native::Descriptor{native::Descriptor{kind:r.word(),id:r.word()}}
fn context(r:&mut Reader)->QueryContext{QueryContext{selection_flags_2948:r.word(),matching_id_2952:r.word()as i32}}
fn query(r:&mut Reader)->native::Query{native::Query{position:v(r),sort_position:v(r),bounds:Bounds{frame:m(r),extents:v(r)},limits:BoardLimits{margin:r.scalar(),angle_a:r.scalar(),angle_b:r.scalar()},mode:r.word(),capacity:r.word()as usize,context:context(r)}}
fn line(r:&mut Reader)->native::Line{native::Line{start:v(r),end:v(r),radius:r.scalar(),group:r.word()as i32,reject_flags:r.word(),source_pool_mask:r.word()as u8,selection_flags:r.word()}}
fn geometry(r:&mut Reader)->std::sync::Arc<native::Geometry>{let id=r.word();let count=r.word();let points=(0..count).map(|_|v(r)).collect();let count=r.word();let approach_vectors=(0..count).map(|_|v(r)).collect();std::sync::Arc::new(native::Geometry{id,points,approach_vectors,word_60:r.word()})}
fn object(r:&mut Reader)->native::Object{
 let id=r.word();let provider_kind=r.word();let selection_variant=r.word()as u8;let matching_group=r.word()as i32;let record_enabled=r.word()!=0;let provider=if provider_kind==0{native::Provider::Dmo{selection_variant,matching_group,record_enabled}}else{native::Provider::LivingWorld};let disabled=r.word()!=0;let assembly_ready=r.word()!=0;
 let assembly=if r.word()!=0{let identity=r.word();let first_part=if r.word()!=0{let identity=r.word();let rates=if r.word()!=0{Some(native::record::RatesData{identity:r.word(),vector_48:v(r),transform_position_48:v(r)})}else{None};Some(native::record::PartData{identity,rates,coefficients_0_to_36:std::array::from_fn(|_|r.scalar())})}else{None};Some(native::AssemblyData{identity,first_part})}else{None};
 let frame=m(r);let object_vector_128=v(r);let count=r.word();let splines=(0..count).map(|_|native::Spline{descriptor:descriptor(r),geometry:geometry(r),word_272:r.word()}).collect();native::Object{id,provider,disabled,assembly_ready,assembly,frame,object_vector_128,splines}
}
fn read_world(r:&mut Reader)->Result<BoardWorld,&'static str>{let count=r.word();let triangles=(0..count).map(|_|cached(triangle(r))).collect();let enabled=r.word()!=0;let data=metadata(r);if enabled{BoardWorld::with_query_metadata(triangles,data)}else{Ok(BoardWorld::new(triangles))}}
fn registry(r:&mut Reader,world:&Result<BoardWorld,&'static str>)->Result<host::Registry,String>{let count=r.word();let objects=(0..count).map(|_|object(r)).collect();let count=r.word();let bindings=(0..count).map(|_|host::MeshAssembly{mesh:r.word(),assembly:r.word()}).collect();match world{Ok(w)=>host::Registry::new(w,objects,bindings),Err(e)=>Err(e.to_string())}}
fn record_out(o:&mut Writer,r:&native::Record){for w in r.0{o.word(w)}o.word(r.1.id);o.word(r.1.word_60);o.word(r.1.points.len()as u32);for &v in &r.1.points{vo(o,v)}o.word(r.1.approach_vectors.len()as u32);for &v in &r.1.approach_vectors{vo(o,v)}}
fn records_out(o:&mut Writer,records:&[native::Record]){o.word(records.len()as u32);for r in records{record_out(o,r)}}
fn record_option(o:&mut Writer,r:Option<&native::Record>){o.word(r.is_some()as u32);if let Some(r)=r{record_out(o,r)}}
fn query_out(o:&mut Writer,q:native::Query){vo(o,q.position);vo(o,q.sort_position);mo(o,q.bounds.frame);vo(o,q.bounds.extents);o.scalar(q.limits.margin);o.scalar(q.limits.angle_a);o.scalar(q.limits.angle_b);o.word(q.mode);o.word(q.capacity as u32);o.word(q.context.selection_flags_2948);o.word(q.context.matching_id_2952 as u32)}
fn line_out(o:&mut Writer,l:native::Line){vo(o,l.start);vo(o,l.end);o.scalar(l.radius);o.word(l.group as u32);o.word(l.reject_flags);o.word(l.source_pool_mask as u32);o.word(l.selection_flags)}
fn hit_out(o:&mut Writer,h:Option<native::Hit>){o.word(h.is_some()as u32);if let Some(h)=h{o.scalar(h.fraction);o.word(h.assembly.is_some()as u32);if let Some(a)=h.assembly{o.word(a)}}}
fn object_option(o:&mut Writer,value:Option<Option<u32>>){o.word(value.is_some()as u32);if let Some(v)=value{o.word(v.is_some()as u32);if let Some(v)=v{o.word(v)}}}
fn scene<'a>(w:&'a Result<BoardWorld,&'static str>,r:&'a Result<host::Registry,String>)->Result<host::Scene<'a>,String>{match(w,r){(Err(e),_)=>Err(e.to_string()),(_,Err(e))=>Err(e.clone()),(Ok(w),Ok(r))=>Ok(host::Scene::new(w,r))}}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Reader{bytes,at:0};let count=input.word();let mut all=Writer{words:vec![]};all.word(count);
 for index in 0..count{
  let mut world=read_world(&mut input);let mut registry=registry(&mut input,&world);let commands=input.word();let mut owner=Owner::default();let mut out=Writer{words:vec![]};status(&mut out,world.as_ref().map(|_|()).map_err(|s|*s));status(&mut out,registry.as_ref().map(|_|()).map_err(|s|s.as_str()));physics::biped_ground::grab_runtime::migration_observe(&mut out,&owner);out.word(commands);
  for _ in 0..commands{
   let op=input.word();out.word(op);match op{
    0=>owner.query(query(&mut input)),1=>owner.request_primary(descriptor(&mut input)),2=>{let frame=m(&mut input);let ctx=context(&mut input);owner.request_interactable(frame,ctx)}
    3|4=>{let ctx=if op==4{Some(context(&mut input))}else{None};let result=scene(&world,&registry).and_then(|s|if op==3{owner.execute_queries(&s)}else{owner.sync(&s,ctx.unwrap())});status(&mut out,result.as_ref().map(|_|()).map_err(|s|s.as_str()));}
    5=>{let p=owner.publish();for r in &p.records{record_option(&mut out,r.as_ref())}object_option(&mut out,p.object);}
    6=>owner.invalidate(),7=>owner.enter_reset(),8=>{let position=v(&mut input);let r=owner.best(position);record_option(&mut out,r.as_ref())}
    9=>{let q=query(&mut input);let result=scene(&world,&registry).and_then(|s|s.query(&q));status(&mut out,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if let Ok(r)=result{records_out(&mut out,&r)}}
    10=>{let d=descriptor(&mut input);let result=scene(&world,&registry).and_then(|s|s.resolve(d));status(&mut out,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if let Ok(r)=result{record_option(&mut out,r.as_ref())}}
    11=>{let l=line(&mut input);let result=scene(&world,&registry).and_then(|s|s.line(l).map(|h|(h,h.and_then(|h|s.eligible_object(h)))));status(&mut out,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if let Ok((h,id))=result{hit_out(&mut out,h);out.word(id.is_some()as u32);if let Some(id)=id{out.word(id)}}}
    12=>{world=read_world(&mut input);status(&mut out,world.as_ref().map(|_|()).map_err(|s|*s));}
    13=>{registry=crate::registry(&mut input,&world);status(&mut out,registry.as_ref().map(|_|()).map_err(|s|s.as_str()));}
    14=>{let index=input.word()as usize;let frame=m(&mut input);let result=registry.as_mut().ok().and_then(|r|r.objects.objects.get_mut(index));if let Some(o)=result{o.frame=frame;status(&mut out,Ok(()))}else{status(&mut out,Err("Fixture object index is unavailable"))}}
    15=>{let d=descriptor(&mut input);let position=v(&mut input);let bounds=Bounds{frame:m(&mut input),extents:v(&mut input)};let limits=BoardLimits{margin:input.scalar(),angle_a:input.scalar(),angle_b:input.scalar()};let result=scene(&world,&registry).and_then(|s|s.resolve(d));status(&mut out,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if let Ok(r)=result{out.word(r.is_some()as u32);if let Some(r)=r{out.word(native::qualify(&r,position,bounds,limits)as u32)}}}
    16=>{let p=v(&mut input);let a=v(&mut input);let b=v(&mut input);vo(&mut out,native::closest_point(p,[a,b]));}
    _=>panic!("Unknown Grab owner operation"),
   }physics::biped_ground::grab_runtime::migration_observe(&mut out,&owner);
  }all.word(index);all.word(out.words.len()as u32);all.words.extend(out.words);
 }assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&all.words.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
