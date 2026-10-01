// SPDX-License-Identifier: Apache-2.0
mod math{pub use skate_core::math::*;}
mod physics{
 pub use skate_core::physics::*;
 pub mod player_input{
  pub struct BoardToolkit{pub deck:[[f32;4];4]}
  pub struct PlayerInputRuntime{pub processed:skate_core::player::input_phase::ProcessedPhysicsInput,pub toolkit:Option<BoardToolkit>}
 }
 pub mod animated_skeleton{
  pub struct AnimationRecord{pub centre_of_mass:[f32;4]}
  pub struct AnimatedSkeleton{pub roots:skate_core::physics::skeleton_root::SkeletonRootFrames,pub record:AnimationRecord}
 }
 pub mod offboard{
  pub mod contact_toolkit;
  pub mod landing_deck{
// ORIGINAL_MANAGER_HOST
   pub fn migration_completion(owner:&Owner)->Option<QueryResult>{owner.completion}
  }
 }
}
// WORLD_PROTOCOL
use skate_core::{air::trajectory::{Trajectory,QueryRequest,QueryResult},player::{input_phase::OffBoardOutputFields,offboard::{landing_deck as native,landing_state}},physics::{skeleton_root::SkeletonRootFrames,skeleton_landing_on_board as skeleton},point_graph::PointGraph};
mod configuration{
 use skate_core::{player::offboard::landing_state::{Settings,State},physics::skeleton_landing_on_board::Settings as RootSettings};
 use skate_data::collections::Collections;
// ORIGINAL_MOUNTING_CONFIGURATION
 pub fn values(s:&Runtime)->[f32;9]{[s.settings.minimum_auto_angle,s.settings.automatic_speed,s.settings.input_speed,s.settings.input_delta,s.settings.automatic_delta,s.settings.maximum_landing_speed,s.root_settings.root_y_offset,s.root_settings.capsule_radius,s.root_settings.capsule_length]}
 pub fn state_settings(s:&Runtime)->Settings{s.settings}
 pub fn root_settings(s:&Runtime)->RootSettings{s.root_settings}
}
fn v(r:&mut Reader)->[f32;4]{std::array::from_fn(|_|r.scalar())}
fn m(r:&mut Reader)->[[f32;4];4]{std::array::from_fn(|_|v(r))}
fn t(r:&mut Reader)->Trajectory{Trajectory{position:v(r),velocity:v(r),acceleration:v(r),duration:r.scalar()}}
fn request(r:&mut Reader)->QueryRequest{QueryRequest{trajectory:t(r),radius:r.scalar(),start_error:r.scalar(),end_error:r.scalar()}}
fn vo(o:&mut Writer,v:[f32;4]){for x in v{o.scalar(x)}}fn mo(o:&mut Writer,m:[[f32;4];4]){for v in m{vo(o,v)}}
fn to(o:&mut Writer,t:Trajectory){vo(o,t.position);vo(o,t.velocity);vo(o,t.acceleration);o.scalar(t.duration)}
fn request_out(o:&mut Writer,q:QueryRequest){to(o,q.trajectory);o.scalar(q.radius);o.scalar(q.start_error);o.scalar(q.end_error)}
fn qo(o:&mut Writer,q:QueryResult){vo(o,q.contact_position);vo(o,q.contact_normal);vo(o,q.landing_normal);o.scalar(q.contact_time);mo(o,q.contact_transform);o.word(q.contact_frame as u32);o.word(q.surface);o.word(q.geometry)}
fn status(o:&mut Writer,r:Result<(),&str>){o.word(r.is_ok()as u32);o.error(r.err())}
fn read_world(r:&mut Reader)->Result<BoardWorld,&'static str>{let count=r.word();let triangles=(0..count).map(|_|cached(triangle(r))).collect();let enabled=r.word()!=0;let data=metadata(r);if enabled{BoardWorld::with_query_metadata(triangles,data)}else{Ok(BoardWorld::new(triangles))}}
fn player_read(r:&mut Reader,p:&mut physics::player_input::PlayerInputRuntime){
 let present=r.word()!=0;let deck=m(r);p.toolkit=present.then_some(physics::player_input::BoardToolkit{deck});
 p.processed.vectors_400_416[0]=v(r).map(f32::to_bits);p.processed.vectors_544_560_592_608[0]=v(r).map(f32::to_bits);p.processed.vectors_544_560_592_608[2]=v(r).map(f32::to_bits);p.processed.vectors_544_560_592_608[3]=v(r).map(f32::to_bits);
 p.processed.vectors_880_896_912_928_944[3][1]=r.word();p.processed.external_physics_1616.flags=r.word();p.processed.flags_2480=r.word();p.processed.surface_mode_2540=r.word();p.processed.wheel_count_2556=r.word();p.processed.actor_query_2952=r.word();p.processed.flags_2488=r.word();
}
fn position(p:&physics::player_input::PlayerInputRuntime)->[f32;4]{p.processed.vectors_544_560_592_608[2].map(f32::from_bits)}
fn velocity(p:&physics::player_input::PlayerInputRuntime)->[f32;4]{p.processed.vectors_544_560_592_608[3].map(f32::from_bits)}
fn output(o:&mut Writer,p:native::UpdateOutput){
 o.word(p.can_land as u32);o.word(p.trajectory_valid as u32);o.scalar(p.time_to_land);o.scalar(p.elapsed);o.scalar(p.landing_time);o.scalar(p.apex_time);
 for v in [p.position,p.landing_velocity,p.launch_position,p.landing_position,p.normal,p.apex_position,p.direction,p.up]{vo(o,v)}o.word(p.query.is_some()as u32);if let Some(q)=p.query{request_out(o,q)}
}
fn root_out(o:&mut Writer,r:&SkeletonRootFrames){mo(o,r.board);mo(o,r.inverse_board);vo(o,r.previous_board_position);vo(o,r.predicted_board_position);o.word(r.supplied_prediction.is_some()as u32);if let Some(v)=r.supplied_prediction{vo(o,v)}mo(o,r.animation_to_board);mo(o,r.animation_to_world);mo(o,r.world_to_animation);mo(o,r.heading_alignment);o.word(r.initialize_heading as u32)}
fn settings_out(o:&mut Writer,s:&physics::offboard::landing_deck::Owner,c:&configuration::Runtime){o.scalar(s.settings.deck_min_uprightness);o.scalar(s.settings.approximate_com_height);for v in configuration::values(c){o.scalar(v)}}
fn owner_out(o:&mut Writer,s:&physics::offboard::landing_deck::Owner,state:&landing_state::State,roots:&SkeletonRootFrames,p:&OffBoardOutputFields,skeleton:[u32;4],flag:u8){
 let start=o.words.len();o.word(0);let m=s.manager;to(o,m.trajectory_32);to(o,m.proposed_96);o.scalar(m.elapsed_160);o.word(m.trajectory_valid_164 as u32);for v in [m.ik_offset_176,m.vector_192,m.moving_contact_208,m.vector_224]{vo(o,v)}o.scalar(m.obstruction_height_240);o.scalar(m.time_to_land_244);o.scalar(m.proposed_time_248);o.word(m.completed_queries_252);for b in [m.can_land_256,m.force_257,m.blocked_258,m.tested_259,m.hippy_hurdling_260,m.publish_moving_contact_261,m.pending_262]{o.word(b as u32)}
 let q=physics::offboard::landing_deck::migration_completion(s);o.word(q.is_some()as u32);if let Some(q)=q{qo(o,q)}let f=s.fill();o.word(f.can_land_316 as u32);o.word(f.hippy_hurdling_317 as u32);o.word(f.moving_contact.is_some()as u32);if let Some(v)=f.moving_contact{vo(o,v)}
 o.word(state.output.is_some()as u32);if let Some(value)=state.output{output(o,value)}o.scalar(state.time_to_land);for b in [state.dangerous,state.near_deck,state.turning,state.hippy]{o.word(b as u32)}o.word(state.takeoff_frames as u32);for v in [state.spin_rate,state.applied_spin,state.transition_angle,state.accumulated_spin]{o.scalar(v)}o.word(state.half_turns as u32);o.word(state.next_half_turns as u32);o.word(state.landing_half_turns()as u32);o.word(state.requests_board_flip()as u32);
 root_out(o,roots);o.word(p.flag_316 as u32);o.word(p.hippy_hurdling_317 as u32);for v in skeleton{o.word(v)}o.word(flag as u32);o.words[start]=(o.words.len()-start-1)as u32;
}
fn main(){
 let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1])).unwrap();let mut all=Writer{words:vec![]};
 let loaded=physics::offboard::landing_deck::Owner::load(&data).and_then(|o|configuration::Runtime::load(&data).map(|c|(o,c)));status(&mut all,loaded.as_ref().map(|_|()).map_err(|s|s.as_str()));
 if let Ok((mut initial,mut config))=loaded{
  settings_out(&mut all,&initial,&config);
  if args.len()>2{let d=skate_data::collections::Collections::load(std::path::Path::new(&args[2])).unwrap();let result=physics::offboard::landing_deck::Owner::load(&d).and_then(|o|configuration::Runtime::load(&d).map(|c|(o,c)));status(&mut all,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if let Ok((o,c))=result{initial=o;config=c;}settings_out(&mut all,&initial,&config);}
  else{
   let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Reader{bytes,at:0};let count=input.word();all.word(count);
   for index in 0..count{
    let mut world=read_world(&mut input);let commands=input.word();let mut owner=physics::offboard::landing_deck::Owner::load(&data).unwrap();let mut state=landing_state::State::default();let mut roots=SkeletonRootFrames::default();let mut player=physics::player_input::PlayerInputRuntime{processed:Default::default(),toolkit:None};let mut last=None;let mut publication=OffBoardOutputFields::default();let mut skeleton=[0x11112222,0x33334444,0x55556666,0x77778888];let mut flag=7u8;let mut o=Writer{words:vec![]};
    status(&mut o,world.as_ref().map(|_|()).map_err(|s|*s));owner_out(&mut o,&owner,&state,&roots,&publication,skeleton,flag);o.word(commands);
    for _ in 0..commands{
     let op=input.word();o.word(op);match op{
      0=>player_read(&mut input,&mut player),
      1=>{let previous_category=input.word();let hippy=input.word()!=0;let strength=input.scalar();let board_position=player.toolkit.as_ref().map_or([0.;4],|b|b.deck[3]);let com_position=position(&player);let com_velocity=velocity(&player);let board_velocity=player.processed.vectors_400_416[0].map(f32::from_bits);let up=player.processed.vectors_544_560_592_608[0].map(f32::from_bits);let hips_up=v(&mut input);let animation_right=v(&mut input);let reversed=input.word()!=0;state.enter(&mut owner.manager,landing_state::Entry{previous_category,hippy,strength,board_position,com_position,com_velocity,board_velocity,up,hips_up,animation_right,reversed});}
      2|3|13=>{let maximum=if op==2{input.scalar()}else{0.};let request=if op==13{Some(request(&mut input))}else{None};let result=match &world{Err(e)=>Err(e.to_string()),Ok(w)=>physics::offboard::contact_toolkit::StaticScene::new(w).map_err(str::to_owned).and_then(|scene|if op==2{owner.assist(&scene,&player,maximum)}else if let Some(q)=request{owner.submit(&scene,q,&player.processed)}else{owner.update(&scene,&player).map(|out|last=Some(out))})};status(&mut o,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if op==3&&result.is_ok(){output(&mut o,last.unwrap())}}
      4=>{let a=v(&mut input);let b=v(&mut input);let time=input.scalar();let velocity=input.scalar();let spin=input.scalar();state.align(&configuration::state_settings(&config),a,b,time,velocity,spin);}
      5=>{if let Some(out)=last{state.advance_spin(out);status(&mut o,Ok(()))}else{status(&mut o,Err("No completed Landing Update"))}}
      6=>{let y=input.scalar();let bv=input.scalar();let cv=input.scalar();let toes=[input.scalar(),input.scalar()];let wheels=input.word();o.scalar(landing_state::State::accurate_time(y,bv,cv,toes,wheels));}
      7=>state.finish(&configuration::state_settings(&config),input.scalar()),
      8=>owner.manager.correct_trajectory(v(&mut input)),
      9=>{let root=m(&mut input);let com=v(&mut input);let mapped=v(&mut input);let time=input.scalar();let mut animation_roots=SkeletonRootFrames::default();animation_roots.animation_to_world=root;let animation=physics::animated_skeleton::AnimatedSkeleton{roots:animation_roots,record:physics::animated_skeleton::AnimationRecord{centre_of_mass:com}};let result=owner.calculate_accurate_ik_offset(&player,&animation,mapped,time);status(&mut o,result.as_ref().map(|_|()).map_err(|s|s.as_str()));if let Ok(v)=result{vo(&mut o,v)}}
      10=>{let result=owner.post_physics(&player);status(&mut o,result.as_ref().map(|_|()).map_err(|s|s.as_str()));}
      11=>owner.reset(),12=>{world=read_world(&mut input);status(&mut o,world.as_ref().map(|_|()).map_err(|s|*s));}
      14=>{let old=m(&mut input);let com=v(&mut input);let f=input.word();let y=input.scalar();mo(&mut o,skeleton::skate_root(old,com,f,y,configuration::root_settings(&config)));}
      15=>{let com=v(&mut input);let local=v(&mut input);let spin=input.scalar();let revert=if input.word()!=0{Some(input.word())}else{None};let reverse=input.word()!=0;skeleton::update_root(&mut roots,com,local,spin,revert,reverse);}
      16=>{let inverse=m(&mut input);let actual=m(&mut input);let mapped=m(&mut input);let ik=v(&mut input);let velocity=input.scalar();let f=input.word();let time=input.scalar();let blend=PointGraph{x:std::array::from_fn(|_|input.scalar()),y:std::array::from_fn(|_|input.scalar())};let result=skeleton::pose_adjustment(&inverse,&actual,&mapped,ik,velocity,f,time,&blend);o.word(result.is_some()as u32);if let Some(m)=result{mo(&mut o,m)}}
      17=>owner.publish(physics::offboard::landing_deck::PublishTargets{off_board:&mut publication,skeleton_position_48:&mut skeleton,skeleton_flag_3482:&mut flag}),
      _=>panic!("Unknown LandingDeck operation"),
     }owner_out(&mut o,&owner,&state,&roots,&publication,skeleton,flag);
    }all.word(index);all.word(o.words.len()as u32);all.words.extend(o.words);
   }assert_eq!(input.at,input.bytes.len());
  }
 }std::io::stdout().write_all(&all.words.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
