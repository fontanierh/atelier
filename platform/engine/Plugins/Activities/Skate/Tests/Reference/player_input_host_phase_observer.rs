// Append-only source adapter: the complete input_phase and reset methods execute.
mod migration_input_host {
use super::*;use crate::{Input,Output};
// GENERATED_TRAJECTORY_READERS
#[derive(Default)]struct Actions{values:[f32;18],calls:Vec<u32>}
impl skate_core::input::controller::ActionMap for Actions {
 fn value(&mut self,a:u32)->f32{self.calls.push(a);self.values[(a-64)as usize]}
 fn state(&mut self,a:u32)->u8{(self.value(a)!=0.)as u8}
}
fn attribute(i:&mut Input)->skate_core::animation::output::attributes::AnimationAttribute{
 use skate_core::animation::output::attributes::{AnimationAttribute,AttributeName,AttributePayload};
 AnimationAttribute{name:AttributeName(i.words()),kind:i.word()as u8,status:i.word()as u8,sequence_id:i.word()as i32,
 begin_time:i.float(),end_time:i.float(),payload:AttributePayload(std::array::from_fn(|_|(i.word()!=0).then(||i.word())))}
}
pub(super)fn snapshot(o:&mut Output,s:&SkaterRuntime){o.word(1);let at=o.0.len();o.word(0);player_input::migration_input_host_observe(o,&s.player_input,&s.ground_runtime,s);o.0[at]=(o.0.len()-at-1)as u32;}
pub(super)fn launch(i:&mut Input,p:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String>{let info=read_launch(i);let input=read_selector_input(i);s.trajectory.launch(info,input,&p.world).map(|_|())}
pub(super)fn update(i:&mut Input,p:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String>{let input=read_selector_input(i);let board=i.floats();let body=i.floats::<4>();let actor=i.word();let matching=i.word();let mut context=ProcessedPhysicsInput::default();context.vectors_544_560_592_608[2]=body.map(f32::to_bits);context.actor_query_2948=actor;context.actor_query_2952=matching;s.trajectory.update(input,&p.world,air_trajectory::GrindContext::from_processed(&context,board)).map(|_|())}
pub(super)fn advance(i:&mut Input,o:&mut Output,p:&mut GamePhysics,s:&mut SkaterRuntime,teleported:&mut bool)->Result<(),String>{
 let publication=crate::read_AnimationPacketFields(i);let external=crate::read_ExternalPhysicsInput(i);let packet=crate::read_packet(i,&publication,&external);
 s.animation.attributes=Default::default();let n=i.word();for _ in 0..n{s.animation.attributes.append(&attribute(i));}
 let mut actions=Actions{values:i.floats(),calls:Vec::new()};let available=i.word()!=0;
 let result=input_phase::advance(p,s,&packet,&mut actions,available);let result=match result{Ok(value)=>{*teleported=value;Ok(())},Err(error)=>Err(error)};
 o.word(*teleported as u32);o.word(actions.calls.len()as u32);o.0.extend(actions.calls);result
}
pub(super)fn consume_pending(p:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String>{
 let pending=s.player_input.pending_grind.take().ok_or("Proof caller has no actual pending grind work")?;
 let e=&s.animation_input.extra;let context=player_input::grind::PostContext{board:solve::deck_frame(&p.board),balance_2720:s.animation_input.fields.balance,
 translation_2796:e.grind_translation,stability_nudge_2800:e.grind_stability_nudge,up_down_2804:e.grind_up_down,grab_min_height_2808:e.grind_grab_min_height};
 let mut live=grind_host::LiveHost{board:&mut p.board,settings:&mut p.settings,materials:&p.grind_materials};
 let result=s.player_input.grind.post_update(&mut s.player_input.processed,&p.world,pending,context,&mut live)?;
 s.player_input.grind_observation=Some(result.observation);s.grind.observe(result.observation);
 for reason in result.wipeout_reasons{s.wipeout.state.request(reason,0.)}Ok(())
}
}
