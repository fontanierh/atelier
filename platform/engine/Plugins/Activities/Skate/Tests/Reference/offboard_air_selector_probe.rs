mod math{pub use skate_core::math::*;}
mod physics{pub use skate_core::physics::*;}
// WORLD_PROTOCOL
use skate_core::{air::trajectory::{Trajectory,QueryResult,QueryRequest,Prediction},player::offboard::{air_launch,air_selector as core,biped_air::recovered::{TrajectoryResult,sampling::SelectorState,selection::Candidate},controller},point_graph::PointGraph};
use skate_core::player::offboard::ground_query::{self as ground,GroundQueryScene};
mod offboard{
 pub(crate)mod contact_toolkit;
 pub(crate)mod ground_query;
 pub(crate)mod air_selector{
// ORIGINAL_HOST
pub fn migration_completions<'a>(s:&'a AirSelector)->(&'a Option<Vec<QueryResult>>,&'a Option<Prediction>){(&s.completed_launch,&s.completed_requery)}
 }
}
fn v(r:&mut Reader)->[f32;4]{std::array::from_fn(|_|r.scalar())}
fn m(r:&mut Reader)->[[f32;4];4]{std::array::from_fn(|_|v(r))}
fn t(r:&mut Reader)->Trajectory{Trajectory{position:v(r),velocity:v(r),acceleration:v(r),duration:r.scalar()}}
fn context(r:&mut Reader)->core::Context{core::Context{selection_flags_2948:r.word(),matching_group_2952:r.word()as i32,up_544:v(r),forward_224:v(r)}}
fn packet(r:&mut Reader)->air_launch::Packet{air_launch::Packet{velocity_0:v(r),secondary_velocity_16:v(r),position_32:v(r),up_48:v(r),forward_64:v(r),board_position_80:v(r),scalar_96:r.scalar(),scalar_100:r.scalar(),scalar_104:r.scalar(),kind_108:r.word(),kind_112:r.word(),has_board_position_116:r.word()!=0,flag_117:r.word()!=0}}
fn launch_input(r:&mut Reader)->air_launch::Processed{
 let board_position_112=v(r);let forward_224=v(r);let up_544=v(r);let position_592=v(r);let velocity_608=v(r);let velocity_912=v(r);let departure_geometry=if r.word()!=0{Some(air_launch::DepartureGeometry{point_1120:v(r),axis_1136:v(r)})}else{None};
 air_launch::Processed{board_position_112,forward_224,up_544,position_592,velocity_608,velocity_912,departure_geometry,flags_2472:r.word(),flags_2476:r.word(),flags_2480:r.word(),previous_state_2504:r.word(),current_state_2508:r.word(),current_category_2512:r.word(),previous_category_2516:r.word(),raw_x_2692:r.scalar(),raw_z_2688:r.scalar()}
}
fn vo(o:&mut Writer,v:[f32;4]){for x in v{o.scalar(x)}}fn mo(o:&mut Writer,m:[[f32;4];4]){for v in m{vo(o,v)}}
fn to(o:&mut Writer,t:Trajectory){vo(o,t.position);vo(o,t.velocity);vo(o,t.acceleration);o.scalar(t.duration)}
fn qo(o:&mut Writer,q:QueryResult){vo(o,q.contact_position);vo(o,q.contact_normal);vo(o,q.landing_normal);o.scalar(q.contact_time);mo(o,q.contact_transform);o.word(q.contact_frame as u32);o.word(q.surface);o.word(q.geometry)}
fn request_out(o:&mut Writer,q:QueryRequest){to(o,q.trajectory);o.scalar(q.radius);o.scalar(q.start_error);o.scalar(q.end_error)}
fn prediction_out(o:&mut Writer,p:Prediction){qo(o,p.result);request_out(o,p.request)}
fn packet_out(o:&mut Writer,p:air_launch::Packet){for v in [p.velocity_0,p.secondary_velocity_16,p.position_32,p.up_48,p.forward_64,p.board_position_80]{vo(o,v)}o.scalar(p.scalar_96);o.scalar(p.scalar_100);o.scalar(p.scalar_104);o.word(p.kind_108);o.word(p.kind_112);o.word(p.has_board_position_116 as u32);o.word(p.flag_117 as u32)}
fn candidate_out(o:&mut Writer,c:Candidate){to(o,c.trajectory);vo(o,c.normal_64);vo(o,c.contact_velocity_80);vo(o,c.contact_position_96);o.word(c.start_frame_112 as u32);o.word(c.landing_frame_116 as u32);o.word(c.valid_120 as u32);o.word(c.special_121 as u32)}
fn sampling_out(o:&mut Writer,p:&SelectorState){o.word(p.pending_8492 as u32);o.word(p.restart_allowed_8493 as u32);o.word(p.preinitialized_8494 as u32);to(o,p.fallback_8208);let s=p.selection;to(o,s.trajectory_8144);vo(o,s.normal_6144);vo(o,s.velocity_6160);vo(o,s.position_6176);o.word(s.valid_6200 as u32);o.word(s.result_present_3888 as u32);o.word(s.landing_frame_8480 as u32);o.scalar(s.scalar_8392);o.word(s.word_8396);o.scalar(s.candidate_scalar_100);vo(o,p.adjustment_8336);o.scalar(p.blend_8384);o.scalar(p.elapsed_8388);o.word(p.frame_8484 as u32)}
fn result_out(o:&mut Writer,r:TrajectoryResult){for v in [r.position_272,r.velocity_288,r.normal_304,r.contact_velocity_320,r.contact_position_336,r.adjustment_352,r.apex_368]{vo(o,v)}o.scalar(r.time_remaining_384);o.scalar(r.duration_388);o.scalar(r.scalar_392);o.scalar(r.apex_time_396);o.word(r.frame_400 as u32);o.word(r.valid_404 as u32);o.word(r.word_408)}
fn owner_out(o:&mut Writer,owner:&offboard::air_selector::AirSelector,p:air_launch::Packet,r:TrajectoryResult){
 let prefix=o.words.len();o.word(0);let c=&owner.core;sampling_out(o,&c.sampling);packet_out(o,c.launch);o.word(c.candidates.len()as u32);for &v in &c.candidates{candidate_out(o,v)}o.word(c.predictions.len()as u32);for &v in &c.predictions{prediction_out(o,v)}o.word(c.scores.len()as u32);for &v in &c.scores{o.scalar(v)}o.word(c.selected_index.is_some()as u32);if let Some(n)=c.selected_index{o.word(n as u32)}candidate_out(o,c.selected_candidate);
 vo(o,c.offset_8272);vo(o,c.correction_8304);vo(o,c.ledge_normal_8320);o.word(c.ledge_selected_8496 as u32);o.word(c.just_changed_8497 as u32);o.word(c.requery_pending_8499 as u32);o.word(c.requery_count_8488 as u32);vo(o,c.requery_position_8352);vo(o,c.requery_normal_8368);
 let (launch,requery)=offboard::air_selector::migration_completions(owner);o.word(launch.is_some()as u32);if let Some(values)=launch{o.word(values.len()as u32);for &q in values{qo(o,q)}}o.word(requery.is_some()as u32);if let Some(q)=requery{prediction_out(o,*q)}packet_out(o,p);result_out(o,r);o.words[prefix]=(o.words.len()-prefix-1)as u32;
}
fn settings_out(o:&mut Writer,s:&offboard::air_selector::Settings){o.scalar(s.query.height);o.scalar(s.query.sphere_radius);o.word(s.query.start_index as u32);for v in s.blend.x{o.scalar(v)}for v in s.blend.y{o.scalar(v)}o.scalar(s.deck_center_to_truck)}
fn status(o:&mut Writer,result:Result<(),&str>){o.word(result.is_ok()as u32);o.error(result.err())}
fn selected(o:&mut Writer,index:Option<usize>){o.word(index.is_some()as u32);if let Some(index)=index{o.word(index as u32)}}
fn read_world(r:&mut Reader)->Result<BoardWorld,&'static str>{let count=r.word();let triangles=(0..count).map(|_|cached(triangle(r))).collect();let enabled=r.word()!=0;let data=metadata(r);if enabled{BoardWorld::with_query_metadata(triangles,data)}else{Ok(BoardWorld::new(triangles))}}
fn search_out(o:&mut Writer,s:ground::EdgeSearch){o.vector(s.min);o.vector(s.max);o.vector(s.frame.right);o.vector(s.frame.up);o.vector(s.frame.forward);o.vector(s.frame.position);o.word(s.context.selection_flags_2948);o.word(s.context.matching_id_2952 as u32);o.word(s.narrow_forward as u32)}
fn edges_out(o:&mut Writer,edges:&[ground::Edge]){o.word(edges.len()as u32);for e in edges{o.vector(e.start);o.vector(e.end)}}
fn ledge_out(o:&mut Writer,a:core::ledge::Adjustment){o.vector(a.edge.start);o.vector(a.edge.end);vo(o,a.point);to(o,a.lowered_trajectory);o.word(a.landing_frame as u32);o.scalar(a.radius)}
fn inspect_ledge(o:&mut Writer,owner:&offboard::air_selector::AirSelector,world:&Result<BoardWorld,&'static str>,context:core::Context,half:f32,hit_count:u32){
 let mut next=owner.core.clone();let results=offboard::air_selector::migration_completions(owner).0;let okay=match results{Some(r)=>next.observe_launch(r),None=>Err("No completed launch observation")};status(o,okay);if okay.is_err(){return}
 let first=next.candidates[0];let prediction=next.predictions[0];let search=core::ledge::search(first,prediction,context);o.word(search.is_some()as u32);let Some(search)=search else{return};search_out(o,search);
 let result=match world{Err(e)=>Err(*e),Ok(w)=>offboard::ground_query::with_world_scene(w,offboard::ground_query::PrimaryEdges::Normal{dynamic:&[],vehicles:&[]},&[],|scene|scene.edge_candidates(&search))};
 status(o,result.as_ref().map(|_|()).map_err(|e|*e));let Ok(edges)=result else{return};edges_out(o,&edges);let filtered=core::ledge::filter_edges(&edges,first.trajectory.position);edges_out(o,&filtered);
 let a=core::ledge::choose(first,prediction,context,owner.settings.query.sphere_radius,&filtered);o.word(a.is_some()as u32);let Some(a)=a else{return};ledge_out(o,a);let mut c=first;a.apply(&mut c);candidate_out(o,c);
 let lines=core::ledge::lines(a,half);o.word(lines.is_some()as u32);if let Some(lines)=lines{for l in lines{o.vector(l.start);o.vector(l.end);o.scalar(l.radius)}}status(o,core::ledge::consume_lines(&vec![None;hit_count as usize]));
}
fn main(){
 let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1])).unwrap();let mut all=Writer{words:vec![]};
 let settings=match offboard::air_selector::Settings::load(&data){Ok(s)=>{status(&mut all,Ok(()));settings_out(&mut all,&s);Some(s)},Err(e)=>{status(&mut all,Err(&e));None}};
 if let Some(mut settings)=settings{
  if args.len()>2{let d=skate_data::collections::Collections::load(std::path::Path::new(&args[2])).unwrap();match offboard::air_selector::Settings::load(&d){Ok(next)=>{status(&mut all,Ok(()));settings=next},Err(e)=>status(&mut all,Err(&e))}settings_out(&mut all,&settings)}
  else{
   let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Reader{bytes,at:0};let count=input.word();all.word(count);
   for index in 0..count{
    let mut world=read_world(&mut input);let commands=input.word();let mut owner=offboard::air_selector::AirSelector::new(offboard::air_selector::Settings::load(&data).unwrap());let mut packet_state=air_launch::Packet::initialized(0.);let mut sample=TrajectoryResult::default();let mut out=Writer{words:vec![]};status(&mut out,world.as_ref().map(|_|()).map_err(|e|*e));owner_out(&mut out,&owner,packet_state,sample);out.word(commands);
    for _ in 0..commands{
     let op=input.word();out.word(op);match op{
      0|13=>{if op==0{packet_state=packet(&mut input)}let gravity=v(&mut input);let context=context(&mut input);let result=match &world{Ok(w)=>owner.launch(w,packet_state,gravity,context),Err(e)=>Err(*e)};status(&mut out,result)},
      1|9=>{let context=context(&mut input);let half=input.scalar();let result=match &world{Ok(w)=>if op==1{owner.consume(w,context,half)}else{owner.consume_launch(w,context,half)},Err(e)=>Err(*e)};status(&mut out,result.as_ref().map(|_|()).map_err(|e|*e));if let Ok(index)=result{selected(&mut out,index)}},
      2=>{let frame=input.word()as i32;let animation=v(&mut input);let axes=m(&mut input);owner.adjust_animation(frame,animation,axes)},
      3=>{let frame=input.word()as i32;let dt=input.scalar();owner.sample(frame,dt,&mut sample);result_out(&mut out,sample)},
      4=>{let context=context(&mut input);let f=input.word();let g=input.word();let result=match &world{Ok(w)=>owner.requery(w,context,f,g),Err(e)=>Err(*e)};status(&mut out,result.as_ref().map(|_|()).map_err(|e|*e));if let Ok(done)=result{out.word(done as u32)}},
      5=>{let result=owner.consume_requery();status(&mut out,result.as_ref().map(|_|()).map_err(|e|*e));if let Ok(done)=result{out.word(done as u32)}},6=>owner.reset(),7=>owner.exit(),
      8=>{world=read_world(&mut input);status(&mut out,world.as_ref().map(|_|()).map_err(|e|*e))},
      10=>{let trajectory=t(&mut input);let point=v(&mut input);let normal=v(&mut input);let time=core::ledge::plane_time(trajectory,point,normal);out.word(time.is_some()as u32);if let Some(time)=time{out.scalar(time)}},
      11=>{let context=context(&mut input);let half=input.scalar();let count=input.word();inspect_ledge(&mut out,&owner,&world,context,half,count)},
      12=>{
       packet_state=packet(&mut input);let p=launch_input(&mut input);let mut s=controller::State::new([None;3]);s.frame_output.frame[1]=v(&mut input);s.motion.frame_0[1]=v(&mut input);s.motion.speed_704=input.scalar();s.intent.steering=input.scalar();s.motion.angular_velocity_688=input.scalar();s.contact.active=input.word()!=0;
       let turn=PointGraph{x:std::array::from_fn(|_|input.scalar()),y:std::array::from_fn(|_|input.scalar())};let settings=air_launch::Settings{jump_speed_scalar:input.scalar(),jump_height:input.scalar()};let current=input.word()!=0;
       out.word(air_launch::mode(&p,current)as u32);status(&mut out,air_launch::produce(&mut packet_state,&s,&turn,settings,&p,current));packet_out(&mut out,packet_state);
      },14=>owner.core.reset(),15=>sample.reset(),16=>{let length=input.word()as usize;let mut results=offboard::air_selector::migration_completions(&owner).0.clone().unwrap_or_default();results.truncate(length);status(&mut out,owner.core.observe_launch(&results))},
      18=>{let s=core::Settings{height:input.scalar(),sphere_radius:input.scalar(),start_index:input.word()as i32};let p=packet(&mut input);let gravity=v(&mut input);let result=owner.core.begin_launch(p,gravity,s);status(&mut out,result.as_ref().map(|_|()).map_err(|e|*e));if let Ok(requests)=result{out.word(requests.len()as u32);for q in requests{request_out(&mut out,q)}}},
      _=>panic!("Unknown offboard air selector operation"),
     }owner_out(&mut out,&owner,packet_state,sample);
    }all.word(index);all.word(out.words.len()as u32);all.words.extend(out.words);
   }assert_eq!(input.at,input.bytes.len());
  }
 }std::io::stdout().write_all(&all.words.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
