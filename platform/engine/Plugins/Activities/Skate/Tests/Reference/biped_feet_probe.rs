#![allow(dead_code,unused_imports,non_snake_case)]
use std::io::{Read,Write};
use skate_core::player::offboard::{biped_air::recovered::feet,board_possession::manager};
use skate_core::animation::foot_ik::{state::FootIkState,external::ExternalTarget,status::Mode};
use skate_core::player::input_phase::{ProcessedPhysicsInput,OffBoardOutputFields};
use skate_core::physics::{skeleton_animation_record::SkeletonAnimationRecord,skeleton_root::SkeletonRootFrames};
mod physics {
 pub struct PlayerInput {pub processed:skate_core::player::input_phase::ProcessedPhysicsInput}
 pub struct Animation {pub roots:skate_core::physics::skeleton_root::SkeletonRootFrames,pub record:skate_core::physics::skeleton_animation_record::SkeletonAnimationRecord}
 pub struct Ik {pub state:skate_core::animation::foot_ik::state::FootIkState}
 pub struct SkaterRuntime {pub player_input:PlayerInput,pub animated_skeleton:Animation,pub foot_ik:Ik}
}
mod ground_feet;
mod air_feet;
struct Input{bytes:Vec<u8>,at:usize}
impl Input{fn word(&mut self)->u32{let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}fn float(&mut self)->f32{f32::from_bits(self.word())}}
struct Output{words:Vec<u32>}
impl Output{fn word(&mut self,v:u32){self.words.push(v)}fn float(&mut self,v:f32){self.word(v.to_bits())}}
// GENERATED_PROTOCOL
fn ik_out(o:&mut Output,s:&FootIkState){
 o.word(s.feet_enabled()as u32);
 for l in &s.limbs{o.word(l.mode as u32);o.float(l.board_blend);o.float(l.external_blend);o.float(l.target_blend);o.word(l.external_target_set as u32);o.word(l.local_target_set as u32);for v in[l.external_target_local_delta,l.part_position]{for x in v{o.float(x)}}}
 for f in &s.frames{for m in[f.target,f.world,f.external_world,f.board,f.parent_world,f.external_parent_world,f.parent_board]{for v in m{for x in v{o.float(x)}}}o.word(f.within_contact_bounds as u32);}
 for t in &s.external_targets{observe_BipedExternalTarget(o,t)}
 for c in &s.contacts.feet{o.word(c.query_state);for x in c.position{o.float(x)}o.float(c.desired_offset);o.float(c.offset)}o.word(s.contacts.support_failed as u32);o.word(s.contacts.support_failed_this_update as u32);
}
fn seed_ik(i:&mut Input,s:&mut FootIkState){
 s.enable_feet(i.word()!=0);
 for l in &mut s.limbs{l.mode=match i.word(){0=>Mode::Disabled,1=>Mode::OnDeck,2=>Mode::External,3=>Mode::Local,_=>panic!("mode")};l.board_blend=i.float();l.external_blend=i.float();l.target_blend=i.float();l.external_target_set=i.word()!=0;l.local_target_set=i.word()!=0;l.external_target_local_delta=std::array::from_fn(|_|i.float());l.part_position=std::array::from_fn(|_|i.float());}
 for t in &mut s.external_targets{*t=read_BipedExternalTarget(i);}
}
fn snapshot(o:&mut Output,manager:&manager::State,skater:&physics::SkaterRuntime,fields:&mut OffBoardOutputFields){let at=o.words.len();o.word(0);observe_BoardPossessionManager(o,manager);ik_out(o,&skater.foot_ik.state);air_feet::publish(manager,fields);observe_OffBoardOutputFields(o,fields);o.words[at]=(o.words.len()-at-1)as u32;}
fn air_input(i:&mut Input,s:&mut physics::SkaterRuntime){
 for f in &mut s.animated_skeleton.record.pose{*f=std::array::from_fn(|_|std::array::from_fn(|_|i.float()));}
 s.animated_skeleton.roots.animation_to_world=std::array::from_fn(|_|std::array::from_fn(|_|i.float()));s.animated_skeleton.roots.world_to_animation=std::array::from_fn(|_|std::array::from_fn(|_|i.float()));
 let p=&mut s.player_input.processed;
 for n in 0..2{let l=read_BipedFootLine(i);p.line_tests_960_1008_1056[n].position=l.position.map(f32::to_bits);p.line_tests_960_1008_1056[n].normal=l.normal.map(f32::to_bits);p.line_tests_960_1008_1056[n].surface=l.surface;p.line_tests_960_1008_1056[n].valid=l.valid as u8;}
 p.vectors_544_560_592_608[2]=std::array::from_fn(|_|i.word());p.vectors_544_560_592_608[3]=std::array::from_fn(|_|i.word());p.flags_2476=i.word();p.flags_2480=i.word();p.flags_2484=i.word();p.state_2508=i.word();
}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{bytes,at:0};let mut o=Output{words:vec![]};let count=i.word();o.word(count);
 for c in 0..count{
  let mut manager=manager::State::default();let mut skater=physics::SkaterRuntime{player_input:physics::PlayerInput{processed:ProcessedPhysicsInput::default()},animated_skeleton:physics::Animation{roots:SkeletonRootFrames::default(),record:SkeletonAnimationRecord::default()},foot_ik:physics::Ik{state:FootIkState::default()}};let mut fields=OffBoardOutputFields::default();fields.flag_329=171;fields.scalar_112=0.137;fields.vector_160=[1,2,3,4];let n=i.word();o.word(c);o.word(n);snapshot(&mut o,&manager,&skater,&mut fields);
  for _ in 0..n{
   let op=i.word();o.word(op);
   match op{
    0=>{let t=feet::update(&mut manager,&read_BipedFeetInput(&mut i));for t in &t{observe_BipedFootTarget(&mut o,t)}},
    1=>ground_feet::update(&mut manager,read_BipedFeetInput(&mut i),&mut skater.foot_ik.state),
    2=>{air_input(&mut i,&mut skater);air_feet::update_air(&mut skater,&mut manager);},
    3=>{skater.player_input.processed.state_2504=i.word();skater.player_input.processed.state_2508=i.word();air_feet::enter(&mut skater,&mut manager);},
    4=>{let n=i.word()as usize;feet::set_normal(&mut skater.foot_ik.state.external_targets[n],std::array::from_fn(|_|i.float()));},
    5=>{manager=read_BoardPossessionManager(&mut i);seed_ik(&mut i,&mut skater.foot_ik.state);},6=>manager.reset(),7=>skater.foot_ik.state.reset(),_=>panic!("command")
   }snapshot(&mut o,&manager,&skater,&mut fields);
  }
 }
 assert_eq!(i.at,i.bytes.len());let mut out=std::io::stdout().lock();for w in o.words{out.write_all(&w.to_le_bytes()).unwrap();}
}
