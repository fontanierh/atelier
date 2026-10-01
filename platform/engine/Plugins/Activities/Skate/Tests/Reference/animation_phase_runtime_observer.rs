// Appended after the entire original physics/input_phase.rs prefix. The
// production animation_phase calls and every physical owner remain unchanged.
mod migration_animation_phase {
// GENERATED_ORIGINAL_OWNER_PREFIX
// GENERATED_PROVIDER_READER
// GENERATED_GRIND_WORLD
fn phase_text(i:&mut Input)->String{let n=i.word();String::from_utf8((0..n).map(|_|i.word()as u8).collect()).unwrap()}
fn live_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,c:&CollisionInput,teleported:bool,actions:&Actions,phase:&super::super::animation_phase::AnimationPhaseOutput){
 o.word(4);block(o,|o|snapshot(o,p,s,c,teleported,actions));
 block(o,|o|super::super::player_state::migration_conditioning_observe(o,s));
 block(o,|o|{let raw=crate::phase_actor_wire::observe(&s.animation,phase.migration_phase_reset());o.word(raw.len()as u32);for chunk in raw.chunks(4){let mut lane=[0u8;4];lane[..chunk.len()].copy_from_slice(chunk);o.word(u32::from_le_bytes(lane));}});
 block(o,|o|super::super::animation_phase::migration_phase_observe(o,s,phase));
}
pub(super)fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 for _ in 0..i.word(){let _=phase_text(i);}let count=i.word();o.word(count);
 for _ in 0..count{
  let graph_id=i.word();let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join(format!("actor-{graph_id}.action.reference")))?,motion:loaded(&fixtures.join(format!("actor-{graph_id}.motion.reference")))?};
  let mut p=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;p.world=fixture_world(i.word());let _provider=read_provider(i);
  let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;
  let mut controls=super::super::PlayerControls::default();let mut phase=super::super::animation_phase::migration_phase_new();let rows=i.word();o.word(rows);
  let mut c=collision(&s);let mut teleported=false;let mut actions=Actions::default();live_snapshot(o,&p,&s,&c,teleported,&actions,&phase);
  for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Vec::new();let result=match op{
// GENERATED_ORIGINAL_PACKET_CASE
   6=>super::super::solve::advance(&mut p,&mut s,[0.;2]).map(|_|super::super::skeleton_feedback::publish(&p,&mut s,false)),
   12=>{s.player_input.toolkit=Some(s.ground_runtime.prepare_toolkit(&p.board,&s.player_input.processed));Ok(())},
   28=>{s.air_reckoning.state.spin_angle=i.float();s.air_reckoning.state.spin_speed=i.float();s.air_reckoning.state.secondary_lean_angle=i.float();Ok(())},
   34=>p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.finish_wheel_queries()).and_then(|_|p.riding.finish_post_physics(&mut p.board,p.board_wiping_out,s.player_input.processed.flags_2468,s.player_input.processed.timestep_2604)),
   40=>{s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(skate_core::player::state::PhysicalStateId::try_from(i.word()).unwrap());Ok(())},
   41=>{let output=if s.player_state.current()==skate_core::player::state::PhysicalStateId::PhysicsGround{let toolkit=s.player_input.toolkit.as_ref().ok_or("State output requires actual board toolkit")?;Some(s.ground.output(&s.player_input.processed,&s.animation_input,toolkit))}else{None};super::super::player_state::migration_conditioning(&p,&mut s,output)},
   45=>{let lane=i.word();let value=i.word();let g=&mut s.player_input.physical.grinds;match lane{0=>g.animation_name_156=None,1=>g.scoring_name_176=None,2=>g.words_136_140[0]=value,3=>g.words_136_140[1]=value,4=>s.player_input.physical.filtered_state_0=value,5..=9=>{if g.animation_name_156.is_none(){g.animation_name_156=Some(skate_core::animation::output::attributes::AttributeName([0;5]));}g.animation_name_156.as_mut().unwrap().0[(lane-5)as usize]=value},_=>panic!("field transport")}Ok(())},
   47=>{s.player_input.update_dynamic_normal(&p.riding,p.settings.step.simulation.gravity_acceleration);s.player_input.publish_board(&p.riding)},
   48=>{let v:[f32;3]=i.floats();for b in p.board.bodies_mut(){b.rates.linear_velocity=Vector3::new(v[0],v[1],v[2]);}Ok(())},
   50=>{controls.controller=skate_core::input::controller::DerivedControllerInput::from_words(i.words());controls.actor_flags=i.word();controls.action_intents=skate_core::graph::intents::IntentMap::new();for _ in 0..i.word(){let name=phase_text(i);controls.action_intents.insert(&name,i.float());}Ok(())},
   51=>{s.player_state.state_flags=std::array::from_fn(|_|i.word()!=0);Ok(())},
   52=>{match super::super::animation_phase::advance(&p,&mut s,&controls,&graphs,&p.animation_profile){Ok(next)=>{phase=next;Ok(())},Err(e)=>Err(e)}},
   53=>{super::super::animation_phase::publish_feedback(&p,&mut s);Ok(())},
   54=>{s.teleport_state.reply(super::super::teleport_state::Checkpoint{transform:i.matrix(),on_board:i.word()!=0});Ok(())},
   55=>{s.player_state.filtered.reset();s.player_state.filtered_output=None;Ok(())},
   56=>{s.player_input.physical.filtered_state_0=i.word();Ok(())},
   58=>{use skate_core::graph::controller::ConditionHost;let mut record=Output(Vec::new());record.word(graphs.action.runtime.operations.conditions.len()as u32);for id in 0..graphs.action.runtime.operations.conditions.len(){let opid=graphs.action.runtime.operations.conditions[id];record.word(s.animation.action.instances.operations[opid].unsupported().is_none()as u32);s.animation.action.errors.clear();record.word(s.animation.action.condition_activation(id,&s.animation.action_controller.frame));let message=s.animation.action.errors.join("|");record.word(message.len()as u32);record.0.extend(message.bytes().map(u32::from));}extra=record.0;Ok(())},
   _=>panic!("animation phase opcode")};
   c=collision(&s);o.status(result);o.word(extra.len()as u32);o.0.append(&mut extra);live_snapshot(o,&p,&s,&c,teleported,&actions,&phase);
  }
 }Ok(())
}
}
pub(crate)fn migration_animation_phase_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_animation_phase::run(a,f,i,o)}
