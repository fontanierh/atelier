// Appended after the whole original physics.rs. Wire and read-only observations
// live in the original parent privacy scope; every invoked body stays unchanged.
mod migration_air {
use super::*;use crate::{Input,Output};use skate_core::{player::input_phase::*,physics::board_toolkit::BoardToolkit};
fn block(o:&mut Output,f:impl FnOnce(&mut Output)){let at=o.0.len();o.word(0);f(o);o.0[at]=(o.0.len()-at-1)as u32;}
fn settings(o:&mut Output,s:&air_phase::AirSettings){crate::observe_PhysicsAirSettings(o,&s.state);o.float(s.steering_blend);o.floats(s.grind_lock_distance);}
macro_rules! observation { ($p:ident,$s:ident) => { wipeout::Observations {
 processed:&$s.player_input.processed,board:&$p.riding.ground,collision:&$s.collision_feedback,
 deck:solve::deck_frame(&$p.board),input_board:$s.animated_skeleton.board_frames.animation_target,
 world_to_animation:$s.animated_skeleton.roots.world_to_animation,pose_error:$s.collision_pose_error,
 maximum_pose_error:$s.collision_maximum_error,jump_fix_frames:$s.player_state.post.jump_fix_frames,
 air:&$s.air_reckoning.state,system_up_y:$p.riding.reckoning_frames.system[1][1],
 grind_locked_to_middle:$s.trajectory.selector.grind_locked_to_middle(),grind_normal:$s.trajectory.selector.grind_normal()
 } }; }

fn snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,last:&skate_core::air::known::KnownAirOutput){
 o.word(10);block(o,|o|crate::observe_PhysicsAirState(o,&s.air_state));block(o,|o|settings(o,&s.air_settings));block(o,|o|s.known_air.migration_air_observe(o));block(o,|o|crate::observe_AirOutputFields(o,&s.player_input.physical.air));block(o,|o|{crate::observe_ProcessedPhysicsInput(o,&s.player_input.processed);o.words(s.player_state.post.jump_reference);o.word(s.player_state.post.jump_fix_frames)});
 block(o,|o|{let l=&s.ground_lifecycle;let c=&l.skeleton_controller;o.words([c.effective,c.requested,c.has_request as u32,c.override_enabled as u32,c.flag_18 as u32,l.skeleton_elapsed_16505 as u32,l.board_animated_290 as u32]);o.float(l.manual_drag_2724);o.word(l.edge.is_some()as u32);o.word(l.pending_wall_jump.is_some()as u32)});
 block(o,|o|{o.0.extend(p.board.forces().migration_air_words());o.word(p.contact_count as u32);o.word(p.network_contacts as u32);o.wide(p.ticks);o.word(p.failed as u32)});
 block(o,|o|crate::observe_SkeletonCollisionFeedback(o,&s.collision_feedback));
 block(o,|o|{match observation!(p,s).frame(){Ok(f)=>{o.status(Ok(()));crate::observe_WipeoutFrame(o,&f)},Err(e)=>o.status(Err(e))}o.word(s.wipeout.requests_runout(&s.player_input.processed)as u32);o.word(s.wipeout.requests_wipeout(&s.player_input.processed)as u32)});
 block(o,|o|crate::observe_KnownAirOutput(o,last));footplant::migration_air_snapshot(o,p,s);
}
fn actual_packet(p:&GamePhysics,s:&mut SkaterRuntime){let x=&mut s.player_input.processed;let v=p.board.bodies()[6].rates.linear_velocity;x.vectors_400_416[0]=[v.x,v.y,v.z,0.].map(f32::to_bits);x.vectors_400_416[1]=x.vectors_400_416[0];x.vectors_544_560_592_608[2]=s.skeleton.record.centre_of_mass.map(f32::to_bits);x.vectors_544_560_592_608[3]=s.skeleton.record.centre_of_mass_velocity.map(f32::to_bits);x.collision_pose_error_736=s.collision_pose_error.map(f32::to_bits);x.effective_anim_transform_192=s.animated_skeleton.roots.animation_to_world.map(|v|v.map(f32::to_bits));}
fn solve_feedback(p:&mut GamePhysics,s:&mut SkaterRuntime)->Result<(),String>{solve::advance(p,s,[0.;2])?;let x=&s.player_input.processed;let t=s.player_input.toolkit.as_ref().ok_or("Postphysics wall probe requires the current board toolkit")?;p.processed_flags_2468=x.flags_2468;p.riding.probes.prepare_wall(x,t);p.riding.finish_post_physics(&mut p.board,p.board_wiping_out,p.processed_flags_2468,p.settings.step.simulation.time_step)?;let partial=skateboard_controller::partial_request(&s.skateboard_controller,&p.riding.ground);skeleton_feedback::publish(p,s,partial);p.ticks+=1;Ok(())}
pub(super)fn load(stock:&std::path::Path,invalid:&std::path::Path,o:&mut Output)->Result<(),String>{let data=skate_data::collections::Collections::load(stock).map_err(|e|e.to_string())?;let mut settings=air_phase::AirSettings::load(&data)?;let invalid=skate_data::collections::Collections::load(invalid).map_err(|e|e.to_string())?;match air_phase::AirSettings::load(&invalid){Ok(next)=>{settings=next;o.status(Ok(()))},Err(e)=>o.status(Err(e))}self::settings(o,&settings);Ok(())}
pub(super)fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:footplant::migration_air_loaded(&fixtures.join("actor.action.reference"))?,motion:footplant::migration_air_loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{let mut p=GamePhysics::load_with_terrain(assets,ground::Terrain::Flat)?;p.world=crate::fixture_world(i.word());let provider=std::sync::Arc::new(crate::read_provider(i));p.grind_world=provider.clone();let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;s.trajectory.bind_grind_world(provider);let mut last=known_air::migration_air_empty_output();let n=i.word();o.word(n);snapshot(o,&p,&s,&last);
 for _ in 0..n{let op=i.word();o.word(op);let r=match op{
 0=>{s.player_input.processed=crate::read_ProcessedPhysicsInput(i);s.player_state.post.jump_reference=i.words();s.player_state.post.jump_fix_frames=i.word();s.animation_input.fields.body_spin=i.float();s.animation_input.extra.physical_body_spin=i.float();let adjust=i.float();s.animation_input.extra.body_adjust=[adjust,-adjust];actual_packet(&p,&mut s);Ok(())},
 1=>{let kind=i.word();let globals=if kind==4{vec![]}else{const POSES:[&str;4]=["RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"];let e=&s.animation.evaluator;e.hierarchy(&e.evaluate(&[skate_core::animation::playback_tree::PoseCommand::Pose{name:POSES[kind as usize].into()}])?)?};s.animation.packet.hierarchy=globals.clone();let x=&mut s.player_input.processed;let deck=solve::deck_frame(&p.board);let landing=skate_core::physics::skeleton_landing::LandingInput{filtered_state:0,flags_2468:x.flags_2468,flags_2472:x.flags_2472,flags_2476:x.flags_2476,balance:0.,physical_com_velocity_along_up:s.skeleton.record.centre_of_mass_velocity[1],physical_com_height:s.skeleton.record.centre_of_mass[1]-deck[3][1],animation_com_height:0.};s.animated_skeleton.process_pose(&globals,landing,x.timestep_2604,&mut x.flags_2468,&mut x.flags_2472,None)},
 2=>{s.player_input.toolkit=if i.word()!=0{let x=&s.player_input.processed;Some(BoardToolkit::from_board(&p.board,x.flags_2468,x.scalar_2612,x.vectors_464_480_496_512_528[0].map(f32::from_bits),[0.,1.,0.,0.]))}else{None};Ok(())},
 3=>air_phase::enter(&mut p,&mut s),4=>air_phase::advance(&mut p,&mut s),5=>{air_phase::exit(&mut s);Ok(())},6=>{air_phase::update_apex(&p,&mut s.air_state);let obs=observation!(p,s);s.wipeout.check_air(&obs,false)},
 7=>{let out=skate_core::air::state::fill_physics_output(&s.air_state);let a=&mut s.player_input.physical.air;a.landing_normal_144=out.landing_normal.map(f32::to_bits);a.jump_height_200=out.jump_height;a.reached_apex_436=out.is_at_apex as u8;if let Some(v)=out.scalar_184_write{a.scalar_184=v}Ok(())},
 8=>known_air::enter(&mut p,&mut s),9=>known_air::update(&mut p,&mut s),10=>{let next=i.word();known_air::exit(&mut p,&mut s,next)},11=>known_air::post_physics(&mut p,&mut s),12=>known_air::fill(&mut p,&mut s).map(|v|last=v),
 13=>{p.board.clear_forces();p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.finish_wheel_queries())},14=>solve_feedback(&mut p,&mut s),15=>{p.world=crate::fixture_world(i.word());Ok(())},16=>{s.trajectory.selector.reset();Ok(())},17=>{s.ground_lifecycle.skeleton_controller.override_enabled=i.word()!=0;Ok(())},18=>{s.animation.packet.flags=i.word();s.animation.packet.air_dismount_revert_frames=i.word()as i32;Ok(())},19=>{s.skeleton_air.capture_physics_error(&p.board,&s.animated_skeleton.board_frames.animation_target);Ok(())},20=>{s.trajectory.bind_grind_world(std::sync::Arc::new(crate::read_provider(i)));Ok(())},
 21=>{let kind=i.word();let obs=observation!(p,s);match kind{0=>s.wipeout.check_ground(&obs),1=>s.wipeout.check_air(&obs,false),2=>s.wipeout.check_air(&obs,true),3=>s.wipeout.check_ground_animation(&obs,0.731),_=>s.wipeout.migration_air_check_plant(&obs)}},22=>{s.wipeout.state.clear_after_selection();Ok(())},_=>panic!("Air phase operation")};o.status(r);snapshot(o,&p,&s,&last);
 }
 }Ok(())
}
}
pub(crate)fn migration_air_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_air::run(a,f,i,o)}
pub(crate)fn migration_air_load(a:&std::path::Path,f:&std::path::Path,o:&mut crate::Output)->Result<(),String>{migration_air::load(a,f,o)}
