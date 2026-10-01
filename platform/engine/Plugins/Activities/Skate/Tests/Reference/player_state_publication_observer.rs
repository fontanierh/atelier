// Append-only source parent adapter; every original method remains unchanged.
mod migration_common_publication {
use super::*;use crate::{Input,Output};
fn block(o:&mut Output,f:impl FnOnce(&mut Output)){let at=o.0.len();o.word(0);f(o);o.0[at]=(o.0.len()-at-1)as u32;}
pub(super)fn snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){
 o.word(5);block(o,|o|player_state::migration_common_observe(o,s));
 block(o,|o|{crate::observe_PhysicsAirState(o,&s.air_state);crate::observe_KnownAirState(o,&s.known_air.state)});
 block(o,|o|grind::migration_owner(o,&s.grind,&s.player_input.grind.jumper));
 block(o,|o|{crate::observe_wipeout_State(o,&s.wipeout_state.state);crate::observe_wipeout_Output(o,&wipeout_states::fill(s))});
 block(o,|o|{o.word(s.slide_state.state.wall_riding as u32);o.word(s.revert_state.active as u32);o.word(s.ground_animation.launched as u32);o.floats(s.ground_animation.launch_velocity);teleport_state::migration_common_observe(o,&s.teleport_state)});
 let _=p;
}
pub(super)fn grind_producer(i:&mut Input,p:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String>{
 let counter=i.word()as i32;let target=i.word()!=0;let x=&s.animation_input.extra;let frame=solve::deck_frame(&p.board);
 let pre=player_input::grind::PreContext{board:frame,air_counter:counter,tip_state:s.player_input.processed.state_2504,air_targeting_grind_9653:target,balance_2720:s.animation_input.fields.balance,translation_2796:x.grind_translation,stability_nudge_2800:x.grind_stability_nudge,up_down_2804:x.grind_up_down,grab_min_height_2808:x.grind_grab_min_height};
 let post=player_input::grind::PostContext{board:frame,balance_2720:s.animation_input.fields.balance,translation_2796:x.grind_translation,stability_nudge_2800:x.grind_stability_nudge,up_down_2804:x.grind_up_down,grab_min_height_2808:x.grind_grab_min_height};
 let mut live=grind_host::LiveHost{board:&mut p.board,settings:&mut p.settings,materials:&p.grind_materials};
 let pending=s.player_input.grind.pre_update(&s.player_input.processed,&p.grind_world,&p.world,pre,&mut live)?;
 let result=s.player_input.grind.post_update(&mut s.player_input.processed,&p.world,pending,post,&mut live)?;
 s.player_input.grind_observation=Some(result.observation);s.grind.observe(result.observation);
 for reason in result.wipeout_reasons{s.wipeout.state.request(reason,0.)}Ok(())
}
}
