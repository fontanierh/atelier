mod math{pub use skate_core::math::*;}
mod physics{pub use skate_core::physics::*;}
// WORLD_PROTOCOL
use skate_core::player::offboard::ground_query as q;
use q::GroundQueryScene;
mod offboard{
 pub(crate)mod ground_query;
 pub(crate)mod ground_sync;
 pub(crate)mod ground_geometry{
// ORIGINAL_STATE
pub fn migration_offset(s:&State)->f32{s.collision_offset}
pub fn migration_observe(o:&mut crate::Writer,s:&State){o.scalar(s.collision_offset);o.word(s.pending.is_some()as u32);if let Some((packet,hits))=&s.pending{crate::packet_out(o,packet);crate::hits_out(o,hits)}}
 }
}
fn read_frame(r:&mut Reader)->q::Frame{q::Frame{right:r.vector(),up:r.vector(),forward:r.vector(),position:r.vector()}}
fn read_matrix(r:&mut Reader)->[[f32;4];4]{std::array::from_fn(|_|std::array::from_fn(|_|r.scalar()))}
fn read_v(r:&mut Reader)->[f32;4]{std::array::from_fn(|_|r.scalar())}
fn read_context(r:&mut Reader)->q::QueryContext{q::QueryContext{selection_flags_2948:r.word(),matching_id_2952:r.word()as i32}}
fn read_consume(r:&mut Reader)->q::ConsumeInput{q::ConsumeInput{frame_80:read_frame(r),contact_position_192:r.vector(),contact_flags_368:r.word(),reach_364:r.scalar(),previous_input_up_416:r.vector()}}
fn frame_out(o:&mut Writer,f:q::Frame){o.vector(f.right);o.vector(f.up);o.vector(f.forward);o.vector(f.position)}
fn context_out(o:&mut Writer,c:q::QueryContext){o.word(c.selection_flags_2948);o.word(c.matching_id_2952 as u32)}
fn packet_out(o:&mut Writer,p:&q::GroundQueryPacket){context_out(o,p.context);o.vector(p.center);o.vector(p.up);o.vector(p.tangent);for line in p.lines{o.vector(line.start);o.vector(line.end);o.scalar(line.radius)}}
fn hits_out(o:&mut Writer,h:&[Option<q::LineHit>;7]){for hit in h{o.word(hit.is_some()as u32);if let Some(h)=hit{o.vector(h.position);o.vector(h.face_normal);o.scalar(h.fraction);o.word(h.packed_surface as u32)}}}
fn adjustment_out(o:&mut Writer,a:q::GroundAdjustment){o.word(a.state_752 as u32);o.word(a.state_753 as u32);o.word(a.state_754 as u32);frame_out(o,a.frame_768);o.vector(a.input_up_416)}
fn search_out(o:&mut Writer,s:q::EdgeSearch){o.vector(s.min);o.vector(s.max);frame_out(o,s.frame);context_out(o,s.context);o.word(s.narrow_forward as u32)}
fn edges_out(o:&mut Writer,e:&[q::Edge]){o.word(e.len()as u32);for e in e{o.vector(e.start);o.vector(e.end)}}
fn selection_out(o:&mut Writer,s:Option<q::EdgeSelection>){o.word(s.is_some()as u32);if let Some(s)=s{o.vector(s.edge.start);o.vector(s.edge.end);o.vector(s.closest)}}
fn status(o:&mut Writer,result:Result<(),&str>){o.word(result.is_ok()as u32);o.error(result.err())}
fn read_world(r:&mut Reader)->Result<BoardWorld,&'static str>{let count=r.word();let triangles=(0..count).map(|_|cached(triangle(r))).collect();let enabled=r.word()!=0;let data=metadata(r);if enabled{BoardWorld::with_query_metadata(triangles,data)}else{Ok(BoardWorld::new(triangles))}}
struct BodyData{frame:q::Frame,bounds:offboard::ground_query::Bounds,segments:Vec<offboard::ground_query::Segment>}
struct Registry{bodies:Vec<BodyData>,dynamic:Vec<usize>,vehicles:Vec<usize>,alternate:Vec<(bool,[(bool,usize,i32);2])>,indexed:Vec<(u32,bool,usize)>,use_alternate:bool}
fn scene_bounds(r:&mut Reader)->offboard::ground_query::Bounds{offboard::ground_query::Bounds{min:r.vector(),max:r.vector()}}
fn read_registry(r:&mut Reader)->Registry{
 let count=r.word();let bodies=(0..count).map(|_|{let frame=read_frame(r);let bounds=scene_bounds(r);let count=r.word();let segments=(0..count).map(|_|offboard::ground_query::Segment{edge:q::Edge{start:r.vector(),end:r.vector()},local_bounds:scene_bounds(r)}).collect();BodyData{frame,bounds,segments}}).collect();
 let count=r.word();let dynamic=(0..count).map(|_|r.word()as usize).collect();let count=r.word();let vehicles=(0..count).map(|_|r.word()as usize).collect();
 let count=r.word();let alternate=(0..count).map(|_|(r.word()!=0,std::array::from_fn(|_|(r.word()!=0,r.word()as usize,r.word()as i32)))).collect();
 let count=r.word();let indexed=(0..count).map(|_|(r.word(),r.word()!=0,r.word()as usize)).collect();Registry{bodies,dynamic,vehicles,alternate,indexed,use_alternate:r.word()!=0}
}
fn main(){
 let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1])).unwrap();let mut all=Writer{words:vec![]};
 let initial=match offboard::ground_geometry::State::load(&data){Ok(s)=>{status(&mut all,Ok(()));offboard::ground_geometry::migration_observe(&mut all,&s);Some(s)},Err(e)=>{status(&mut all,Err(&e));None}};
 if initial.is_some()&&args.len()==2{
  let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Reader{bytes,at:0};let count=input.word();all.word(count);
  for index in 0..count{
   let mut world=read_world(&mut input);let commands=input.word();let mut state=offboard::ground_geometry::State::load(&data).unwrap();let mut out=Writer{words:vec![]};status(&mut out,world.as_ref().map(|_|()).map_err(|e|*e));offboard::ground_geometry::migration_observe(&mut out,&state);out.word(commands);
   for _ in 0..commands{
    let op=input.word();out.word(op);
    match op{
     0=>{let frame=read_matrix(&mut input);let velocity=read_v(&mut input);let context=read_context(&mut input);let flags=input.word();let result=match &world{Ok(w)=>state.submit(w,frame,velocity,context,flags),Err(e)=>Err(e.to_string())};status(&mut out,result.as_ref().map(|_|()).map_err(|e|e.as_str()))},
     1=>adjustment_out(&mut out,state.consume(read_consume(&mut input))),2=>state.reset(),3=>{world=read_world(&mut input);status(&mut out,world.as_ref().map(|_|()).map_err(|e|*e))},
     4=>{
      let frame=read_frame(&mut input);let context=read_context(&mut input);let velocity=input.vector();let flags=input.word();let registry=read_registry(&mut input);let search=q::edge_search(frame,context,velocity,flags);search_out(&mut out,search);
      let result=match &world{Err(e)=>Err(*e),Ok(world)=>{
       let bodies:Vec<_>=registry.bodies.iter().map(|b|offboard::ground_query::EdgeBody{local_to_world:b.frame,local_bounds:b.bounds,segments:&b.segments}).collect();
       let dynamic:Vec<_>=registry.dynamic.iter().map(|&i|offboard::ground_query::EdgeBody{local_to_world:bodies[i].local_to_world,local_bounds:bodies[i].local_bounds,segments:bodies[i].segments}).collect();let vehicles:Vec<_>=registry.vehicles.iter().map(|&i|offboard::ground_query::EdgeBody{local_to_world:bodies[i].local_to_world,local_bounds:bodies[i].local_bounds,segments:bodies[i].segments}).collect();
       let alternate:Vec<_>=registry.alternate.iter().map(|(enabled,choices)|offboard::ground_query::AlternateRecord{enabled:*enabled,choices:choices.map(|(some,i,g)|some.then(||(&bodies[i],g)))}).collect();let indexed:Vec<_>=registry.indexed.iter().map(|&(id,disabled,i)|offboard::ground_query::IndexedEdgeBody{id,disabled,body:&bodies[i]}).collect();
       let primary=if registry.use_alternate{offboard::ground_query::PrimaryEdges::Alternate(&alternate)}else{offboard::ground_query::PrimaryEdges::Normal{dynamic:&dynamic,vehicles:&vehicles}};
       offboard::ground_query::with_world_scene(world,primary,&indexed,|scene|{status(&mut out,Ok(()));let candidates=scene.edge_candidates(&search)?;edges_out(&mut out,&candidates);let selected=q::select_edge(search,&candidates);selection_out(&mut out,selected);let packet=selected.and_then(|edge|q::prepare_packet(frame,context,edge,offboard::ground_geometry::migration_offset(&state)));out.word(packet.is_some()as u32);if let Some(packet)=packet{packet_out(&mut out,&packet);match scene.query_lines(&packet){Ok(hits)=>{status(&mut out,Ok(()));hits_out(&mut out,&hits)},Err(e)=>status(&mut out,Err(e))}}Ok(())})
      }};
      if let Err(e)=result{status(&mut out,Err(e))}
     },
     5=>{let point=input.vector();let edge=q::Edge{start:input.vector(),end:input.vector()};out.vector(q::closest_point(point,edge))},
     _=>panic!("Unknown offboard ground geometry operation"),
    }
    offboard::ground_geometry::migration_observe(&mut out,&state);
   }
   all.word(index);all.word(out.words.len()as u32);all.words.extend(out.words);
  }
  assert_eq!(input.at,input.bytes.len());
 }
 std::io::stdout().write_all(&all.words.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
