// Appends only explicit transport and read-only observation after complete
// byte-preserved original Handplant and Plant/SkeletonAir source prefixes.
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{
  let mut physics=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;physics.world=authored_query_world(i);let edges=(0..i.word()).map(|_|Primitive{start:i.floats(),end:i.floats(),owner:i.wide()}).collect();physics.grind_world=std::sync::Arc::new(crate::grind_world::migration_handplant_primitives(edges));
  let mut skater=SkaterRuntime::load(assets,&graphs,&physics,"normal")?;let rows=i.word();o.word(rows);skater.skeleton_air.migration_plant_air_settings(o);snapshot(o,&physics,&skater);
  for _ in 0..rows{let op=i.word();o.word(op);let mut target=None;let result=match op{
   0=>{publish(i,&mut skater,&mut physics);Ok(())},
   1=>{let kind=i.word();let mut globals=if kind==4{Vec::new()}else{const POSES:[&str;4]=["RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"];let e=&skater.animation.evaluator;e.hierarchy(&e.evaluate(&[skate_core::animation::playback_tree::PoseCommand::Pose{name:POSES[if kind==5{0}else{kind as usize}].into()}])?)?};if kind==5{globals.truncate(1)}skater.animation.packet.hierarchy=globals.clone();let p=&mut skater.player_input.processed;let deck=crate::physics::solve::deck_frame(&physics.board);let landing=skate_core::physics::skeleton_landing::LandingInput{filtered_state:0,flags_2468:p.flags_2468,flags_2472:p.flags_2472,flags_2476:p.flags_2476,balance:0.,physical_com_velocity_along_up:skater.skeleton.record.centre_of_mass_velocity[1],physical_com_height:skater.skeleton.record.centre_of_mass[1]-deck[3][1],animation_com_height:0.};skater.animated_skeleton.process_pose(&globals,landing,p.timestep_2604,&mut p.flags_2468,&mut p.flags_2472,None)},
   2=>{ground_query(&physics,&mut skater);Ok(())},3=>ground_update(&mut physics,&mut skater),4=>enter(&mut physics,&mut skater),5=>update(&mut physics,&mut skater),
   6=>{let anchor=i.floats();let bone=i.word();plant_skeleton::advance(&mut physics,&mut skater,anchor,(bone!=u32::MAX).then_some(bone as usize))},
   7=>{let right=i.word()!=0;let point=i.floats();let delay=i.word();plant_skeleton::hold_foot(&mut skater,right,point,delay);Ok(())},
   8=>{skater.skeleton_air.capture_physics_error(&physics.board,&skater.animated_skeleton.board_frames.animation_target);Ok(())},9=>{skater.skeleton_air.reset_board();Ok(())},
   10|11=>{let fast=if op==10{i.word()!=0}else{true};let com=if op==11{i.floats()}else{[0.;4]};if op==11{skater.animation.packet.flags=i.word();skater.animation.packet.air_dismount_revert_frames=i.word()as i32;}let collision=super::super::input_phase::collision(&skater);let mut owners=super::super::skeleton_input_runtime::SkeletonOwners{animated:&mut skater.animated_skeleton,body:&mut skater.skeleton,drives:&mut skater.skeleton_drives,ik:&mut skater.foot_ik,animation_input:&mut skater.animation_input,correction:&mut skater.skeleton_output.correction,pose_errors:&mut skater.pose_errors};let r=if op==10{skater.skeleton_input.update_animated(&mut skater.skeleton_air,&mut physics.board,&physics.riding.reckoning_frames.system,&mut skater.player_input.processed,&mut owners,&skater.animation.packet.hierarchy,&collision,physics.settings.step.simulation,fast)}else{skater.skeleton_input.update_known_air(&mut skater.skeleton_air,&mut physics.board,&physics.riding.reckoning_frames.system,com,&skater.animation.packet,&mut skater.player_input.processed,&mut owners,&skater.animation.packet.hierarchy,&collision,physics.settings.step.simulation)};r.map(|m|target=Some(m))},
   12=>{skater.handplant.continuation=i.word()!=0;Ok(())},13=>{if i.word()!=0{skater.handplant.full_reset()}else{skater.handplant.reset()}Ok(())},
   14=>{let c=candidate(i);let com=i.floats();let velocity=i.floats();let normal=i.floats();let body=i.floats();let heading=i.floats();skater.handplant.launch(c,com,velocity,normal,body,heading);Ok(())},15=>{skater.animated_skeleton.motion.next_trajectory=i.matrix();Ok(())},
   16=>{let index=i.word();let data=skate_data::collections::Collections::load(&fixtures.join(format!("case-{index}"))).map_err(|e|e.to_string())?;super::super::skeleton_air::SkeletonAir::load(&data).map(|air|skater.skeleton_air=air)},
   17=>{let matrix=i.matrix();let fast=i.word()!=0;target=Some(skater.skeleton_air.apply_board(&mut physics.board,&matrix,fast));Ok(())},
   18=>{let matrix=i.matrix();skater.skeleton_air.capture_physics_error(&physics.board,&matrix);Ok(())},
   19=>{physics.riding.reckoning_frames.system=i.matrix();Ok(())},
   _=>panic!("plant air owner operation")};o.status(result);o.word(target.is_some()as u32);if let Some(m)=target{o.matrix(m)}skater.skeleton_air.migration_plant_air_settings(o);snapshot(o,&physics,&skater);
  }
 }Ok(())
}
}
pub(crate) fn migration_plant_air_owner_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration::run(a,f,i,o)}
