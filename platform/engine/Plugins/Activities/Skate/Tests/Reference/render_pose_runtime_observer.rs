// Appended transport inside the original Handplant module, after immutable
// live-owner observation helpers. All numerical calls are production source.
fn render_text(i:&mut Input)->String{let n=i.word();String::from_utf8((0..n).map(|_|i.word()as u8).collect()).unwrap()}
fn render_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime){
 let at=o.0.len();snapshot(o,p,s);o.0[at]=13;
 block(o,|o|s.skeleton_output.migration_render_observe(o));
 block(o,|o|s.foot_physical.migration_render_observe(o));
 block(o,|o|{o.wide(s.pose_generation);o.word(s.render_pose.len()as u32);for m in &s.render_pose{o.matrix(*m)}o.word(s.animation.pose.len()as u32);for q in &s.animation.pose{o.floats(q.scale);o.floats(q.rotation);o.floats(q.translation)}let f=&s.player_input.physical;o.word(f.skeleton.flag_597 as u32);o.word(f.skeleton.flag_600 as u32);o.word(f.skeleton.flag_601 as u32);for v in f.skeleton.anim_to_world_11920{o.words(v)}for v in [f.reckoning.vector_16,f.reckoning.vector_64,f.reckoning.vector_96]{o.words(v)}o.word(s.wipeout.requests_wipeout(&s.player_input.processed)as u32);});
}
pub(super)fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 for _ in 0..i.word(){let _=render_text(i);}let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{
  let mut physics=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;physics.world=authored_query_world(i);let edges=(0..i.word()).map(|_|Primitive{start:i.floats(),end:i.floats(),owner:i.wide()}).collect();physics.grind_world=std::sync::Arc::new(crate::grind_world::migration_handplant_primitives(edges));
  let mut s=SkaterRuntime::load(assets,&graphs,&physics,"normal")?;let rows=i.word();o.word(rows);render_snapshot(o,&physics,&s);
  for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Output(Vec::new());let result=match op{
   0=>{publish(i,&mut s,&mut physics);Ok(())},
   1=>{use skate_core::animation::playback_tree::PoseCommand;let kind=i.word();let command=if kind==4{PoseCommand::Clip{name:render_text(i),previous_time:0.,time:i.float(),loops:0}}else{const NAMES:[&str;4]=["RIG_TPOSE","POSTURE_STIFF_POSE","POSTURE_SLOUCH_POSE","POSTURE_BUFF_POSE"];PoseCommand::Pose{name:NAMES[(kind%4)as usize].into()}};s.animation.evaluator.evaluate(&[command]).map(|v|s.animation.pose=v)},
   2=>{let compression=s.skeleton_output.average_compressions(&physics.board);extra.floats(compression);super::super::render_pose::publish(&physics,&mut s,compression)},
   3=>{let part=i.word()as usize;s.skeleton.set_part_transform(part,i.matrix());Ok(())},
   4=>{s.ground.steering.targets=i.floats();Ok(())},
   5=>{let landing=i.word()!=0;let reverse=i.word()!=0;s.skeleton_output.trigger_wobble(landing,reverse);Ok(())},
   6=>{let deck=crate::physics::solve::deck_frame(&physics.board);let matrix=s.skeleton_output.advance_wobble(&mut s.skeleton,&deck);extra.matrix(matrix);Ok(())},
   7=>{let actual=i.floats();let predicted=i.floats();s.skeleton_output.correction.observe_board(actual,predicted);s.skeleton_output.correction.pending=i.word()!=0;Ok(())},
   8=>{let dt=i.float();s.foot_physical.publish(&s.skeleton.record,dt);Ok(())},
   9=>{s.foot_physical.migration_render_reset();Ok(())},
   10=>{let part=i.word()as usize;s.skeleton.record.velocities[part]=i.floats();Ok(())},
   11=>{let mut globals=Vec::new();let mut locals=s.animation.pose.iter().copied().map(skate_core::animation::output::sqt_to_matrix).collect::<Vec<_>>();let r=s.animation.evaluator.hierarchy(&s.animation.pose).and_then(|v|{globals=v;extra.word(globals.len()as u32);for m in &globals{extra.matrix(*m)}extra.word(locals.len()as u32);for m in &locals{extra.matrix(*m)}let compression=s.skeleton_output.average_compressions(&physics.board);s.skeleton_output.publish(&s.animated_skeleton,&s.skeleton,&physics.board,physics.settings.step.base_truck_transforms,s.ground.steering.targets,compression,&mut globals,&mut locals)});extra.word(globals.len()as u32);for m in globals{extra.matrix(m)}extra.word(locals.len()as u32);for m in locals{extra.matrix(m)}r},
   12=>{let count=i.word()as i32;let detach=i.word()as i32;let parents=(0..i.word()).map(|_|i.word()as i32).collect::<Vec<_>>();let mut matrices=(0..i.word()).map(|_|i.matrix()).collect::<Vec<_>>();let r=skate_core::animation::output::compose_hierarchy_in_place(count,&parents,detach,&mut matrices).map_err(|e|format!("{e:?}"));extra.word(matrices.len()as u32);for m in matrices{extra.matrix(m)}r},
   13=>{let index=i.word();let kind=i.word();let data=skate_data::collections::Collections::load(&fixtures.join(format!("case-{index}"))).map_err(|e|e.to_string())?;if kind==0{super::super::foot_physical_output::FootPhysicalOutputs::load(&data).map(|v|s.foot_physical=v)}else{super::super::skeleton_output::SkeletonOutput::load(&data,&s.animation.evaluator.frames,&s.animated_skeleton).map(|v|s.skeleton_output=v)}},
   14=>{s.animation.pose.truncate(i.word()as usize);Ok(())},
   15=>{let part=i.word()as usize;s.skeleton_output.pose.bone_indices[part]=i.word()as usize;Ok(())},
   16=>{let part=i.word()as usize;s.skeleton_output.pose.geometry.parents[part]=if i.word()!=0{Some(i.word()as usize)}else{None};Ok(())},
   17=>{let body=i.word()as usize;let v:[f32;3]=i.floats();physics.board.bodies_mut()[body].rates.position=Vector3::new(v[0],v[1],v[2]);Ok(())},
   18=>{s.pose_generation=i.wide();Ok(())},
   19=>{let anchor=i.floats();let bone=i.word();s.animation.evaluator.hierarchy(&s.animation.pose).and_then(|v|{s.animation.packet.hierarchy=v;plant_skeleton::advance(&mut physics,&mut s,anchor,(bone!=u32::MAX).then_some(bone as usize))})},
   20=>{let p=&mut s.player_input.processed;p.flags_2468=i.word();p.flags_2472=i.word();p.flags_2476=i.word();p.flags_2480=i.word();p.flags_2484=i.word();p.state_2508=i.word();p.category_2512=i.word();p.state_timer_2664=i.float();p.player_state_value_2520=i.word();p.vectors_544_560_592_608[0]=i.floats::<4>().map(f32::to_bits);physics.riding.ground.part_contact_count=i.word()as u8;Ok(())},
   _=>panic!("render owner opcode")};o.status(result);o.word(extra.0.len()as u32);o.0.append(&mut extra.0);render_snapshot(o,&physics,&s);
  }
 }Ok(())
}
}
pub(crate)fn migration_render_pose_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration::run(a,f,i,o)}
