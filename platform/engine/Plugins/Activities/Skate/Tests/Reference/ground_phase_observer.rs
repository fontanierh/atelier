// Appended after the COMPLETE unchanged GroundPhase module. Inputs/observers
// only: all entry/update/reset, plant, selector and skeleton calls are original.
mod migration {
use super::*;
use crate::{Input,Output,grind_world};
use skate_core::physics::{board_toolkit::BoardToolkit,force_queue::QueuedPointForce,board_world::{BoardWorld,WorldTriangle},world_contact::triangle_from_volume,contact::RetailContactMaterial};
fn block(o:&mut Output,f:impl FnOnce(&mut Output)){let at=o.0.len();o.word(0);f(o);o.0[at]=(o.0.len()-at-1)as u32;}
// GENERATED_TRANSPORT_HELPERS
fn outcome(o:&mut Output,s:GroundBoardOutcome){match s{GroundBoardOutcome::Animated=>o.words([0,0,0,0,0,0]),GroundBoardOutcome::Collision{tag_15_queued}=>o.words([1,tag_15_queued as u32,0,0,0,0]),GroundBoardOutcome::Ordinary(v)=>o.words([2,0,v.manual_correction as u32,v.terminal_force_tag,v.terminal_force_queued as u32,v.speed_model_reset as u32])}}
fn snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){
 o.word(8);
 block(o,|o|super::super::ground_runtime::migration_observe_state(o,&s.ground));
 block(o,|o|super::super::ground_runtime::migration_observe_runtime(o,&s.ground_runtime));
 block(o,|o|{let l=&s.ground_lifecycle;let c=&l.skeleton_controller;o.words([c.effective,c.requested,c.has_request as u32,c.override_enabled as u32,c.flag_18 as u32,l.skeleton_elapsed_16505 as u32,l.board_animated_290 as u32]);o.float(l.manual_drag_2724);o.word(l.edge.is_some()as u32);if let Some(e)=l.edge{o.word(e.flags);o.floats(e.point);o.vector(e.start);o.vector(e.end)}o.word(l.pending_wall_jump.is_some()as u32);if let Some(v)=&l.pending_wall_jump{crate::observe_GroundLaunchInfo(o,v)}let w=&s.skeleton_output.wobble;o.words([w.active as u32,w.landing as u32]);o.floats([w.time,w.amplitude,w.direction]);});
 block(o,|o|{let g=&s.board_possession_live;o.word(p.board_wiping_out as u32);o.word(p.board.collision_group());o.words([g.volumes.deck as u32,g.volumes.trucks as u32,g.volumes.wheels as u32]);o.word(g.volumes.deck_children.len()as u32);for v in &g.volumes.deck_children{o.word(*v as u32)}for m in [p.settings.wheel_material,p.settings.standard_wheel_material,p.settings.truck_material,p.settings.deck_material]{o.floats([m.static_friction,m.dynamic_friction,m.restitution]);}for b in p.board.bodies(){o.floats([b.inertia.linear_drag,b.inertia.angular_drag]);}let q=p.board.forces().entries();o.word(q.len()as u32);for v in q{o.word(v.tag);o.vector(v.force_world);o.vector(v.point_body)}});
 block(o,|o|super::super::biped_ground::grab_runtime::migration_observe(&mut o.0,&s.offboard_grab));
 block(o,|o|{let x=&s.player_input.processed;for w in x.vectors_400_416{for v in w{o.word(v)}}o.word(x.flags_2468);o.word(x.flags_2472);o.word(x.flags_2476);o.word(x.state_variant_index_2528);o.word(x.actor_query_2948);o.word(x.actor_query_2952);});
 block(o,|o|super::super::ground_runtime::migration_observe_settings(o,&s.ground_settings));
 block(o,|o|p.riding.probes.migration_observe(o));
 super::super::footplant::migration_ground_snapshot(o,p,s,&skate_core::player::input_phase::AirOutputFields::default());
}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{
  let mut p=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;p.world=authored_query_world(i);p.grind_world=std::sync::Arc::new(read_provider(i));
  let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;s.ground_settings=std::sync::Arc::new(s.ground_profiles.select(1,1)?.tuned(p.trainer));let rows=i.word();o.word(rows);snapshot(o,&p,&s);
  for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Output(Vec::new());let result=match op{
   0=>{publish(i,&mut s,&mut p);let x=&mut s.player_input.processed;x.category_2516=i.word();x.frames_since_teleport_2584=i.word();x.time_since_last_input_2748=i.float();x.time_on_ground_2752=i.float();x.signed_ground_time_2756=i.float();x.truck_tightness_2760=i.float();x.crouch_2776=i.float();x.crouch_delta_2780=i.float();x.spin_input_2672=i.float();x.actor_query_2948=i.word();x.actor_query_2952=i.word();x.vectors_720_784_800_816_832_864[0]=i.floats::<4>().map(f32::to_bits);s.animation_input.fields.turn=i.float();s.animation_input.fields.hard_turn=i.float();Ok(())},
   1=>{let kind=i.word();let mut globals=if kind==4{Vec::new()}else{const POSES:[&str;4]=["RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"];let e=&s.animation.evaluator;e.hierarchy(&e.evaluate(&[skate_core::animation::playback_tree::PoseCommand::Pose{name:POSES[if kind==5{0}else{kind as usize}].into()}])?)?};if kind==5{globals.truncate(1)}s.animation.packet.hierarchy=globals.clone();let x=&mut s.player_input.processed;let deck=crate::physics::solve::deck_frame(&p.board);let landing=skate_core::physics::skeleton_landing::LandingInput{filtered_state:0,flags_2468:x.flags_2468,flags_2472:x.flags_2472,flags_2476:x.flags_2476,balance:0.,physical_com_velocity_along_up:s.skeleton.record.centre_of_mass_velocity[1],physical_com_height:s.skeleton.record.centre_of_mass[1]-deck[3][1],animation_com_height:0.};s.animated_skeleton.process_pose(&globals,landing,x.timestep_2604,&mut x.flags_2468,&mut x.flags_2472,None)},
   2=>{s.player_input.toolkit=if i.word()!=0{let x=&s.player_input.processed;Some(BoardToolkit::from_board(&p.board,x.flags_2468,x.scalar_2612,x.vectors_464_480_496_512_528[0].map(f32::from_bits),x.vectors_544_560_592_608[0].map(f32::from_bits)))}else{None};Ok(())},
   3=>enter(&mut p,&mut s),4=>advance(&mut p,&mut s).map(|v|outcome(&mut extra,v)),
   5=>{reset_board_state(&mut s.ground,&mut s.ground_runtime,&mut s.ground_lifecycle,&mut p.board_wiping_out);Ok(())},
   6=>super::super::handplant::ground_update(&mut p,&mut s),7=>super::super::input_phase::update_ground(&p,&mut s),
   8=>{p.board.forces_mut().clear();Ok(())},9=>{let tag=i.word();p.board.forces_mut().append(QueuedPointForce{tag,force_world:i.three(),point_body:i.three()});Ok(())},
   10=>{s.ground.state=crate::read_PhysicsGroundState(i);s.ground.pumping=crate::read_PumpingState(i);s.ground.entered=i.word()!=0;Ok(())},
   11=>{let l=&mut s.ground_lifecycle;let c=&mut l.skeleton_controller;c.effective=i.word();c.requested=i.word();c.has_request=i.word()!=0;c.override_enabled=i.word()!=0;c.flag_18=i.word()!=0;l.skeleton_elapsed_16505=i.word()!=0;l.board_animated_290=i.word()as u8;s.air_reckoning.state.spin_angle=i.float();s.air_reckoning.state.spin_speed=i.float();s.wipeout.state.mode=i.word();s.wipeout.state.balance=i.float();p.board_wiping_out=i.word()!=0;Ok(())},
   12=>{let seed=i.word();let flags=i.word()as u8;super::super::biped_ground::grab_runtime::migration_seed(&mut s.offboard_grab,seed,flags);Ok(())},
   13=>{s.ground_lifecycle.edge=if i.word()!=0{Some(GroundEdge{flags:i.word(),point:i.floats(),start:i.three(),end:i.three()})}else{None};Ok(())},
   14=>{s.ground_lifecycle.pending_wall_jump=if i.word()!=0{Some(crate::read_GroundLaunchInfo(i))}else{None};Ok(())},
   15=>{let mode=i.word();let surface=i.word();s.ground_profiles.select(mode,surface).map(|selected|s.ground_settings=std::sync::Arc::new(selected.tuned(p.trainer)))},
   16=>{let data=skate_data::collections::Collections::load(assets)?;super::super::air_trajectory::AirTrajectoryRuntime::load(&data).map(|v|s.trajectory=v)},17=>{s.trajectory.bind_grind_world(std::sync::Arc::clone(&p.grind_world));Ok(())},
   18=>{let x=&s.player_input.processed;p.riding.update_ground_reckoning(&p.board,super::super::riding_outputs::RidingPoseInputs{com_to_deck:s.animated_skeleton.record.com_to_deck(),body_spin:s.animation_input.extra.physical_body_spin},x.flags_2468,s.animation_input.fields.balance,false,x);Ok(())},
   19=>{let v=super::super::input_phase::collision(&s);extra.words([v.contact_4070 as u32,v.has_pose_error_4077 as u32,v.partial_ragdoll as u32]);extra.floats(v.pose_error_16272);extra.float(v.drive_weight_4028);Ok(())},
   20=>{p.riding.probes.prepare_wall(&s.player_input.processed,s.player_input.toolkit.as_ref().unwrap());p.riding.probes.start(&p.board,&p.world).and_then(|()|p.riding.probes.publish())},
   21=>p.riding.probes.start(&p.board,&p.world),22=>p.riding.probes.publish(),23=>{p.riding.probes.reset_results();Ok(())},
   _=>panic!("GroundPhase wire operation")};o.status(result);o.word(extra.0.len()as u32);o.0.extend(extra.0);snapshot(o,&p,&s);
  }
 }Ok(())
}
}
pub(crate) fn migration_ground_phase_run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration::run(assets,fixtures,i,o)}
