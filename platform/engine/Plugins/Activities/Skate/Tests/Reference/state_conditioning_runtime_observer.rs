// Actual original host constructors and source publication fragments. No
// completed collision/query/toolkit/grind producer is replaced by an observer.
mod migration_state_conditioning {
// GENERATED_ORIGINAL_OWNER_PREFIX
// GENERATED_PROVIDER_READER
// GENERATED_GRIND_WORLD
fn live_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,c:&CollisionInput,teleported:bool,actions:&Actions){o.word(3);block(o,|o|snapshot(o,p,s,c,teleported,actions));block(o,|o|super::super::grind::migration_owner(o,&s.grind,&s.player_input.grind.jumper));block(o,|o|super::super::player_state::migration_conditioning_observe(o,s));}
pub(super) fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
 let graphs=crate::graph_runtime::StockGraphs{action:loaded(&fixtures.join("actor.action.reference"))?,motion:loaded(&fixtures.join("actor.motion.reference"))?};let count=i.word();o.word(count);
 for _ in 0..count{let mut p=GamePhysics::load_with_terrain(assets,super::super::ground::Terrain::Flat)?;p.world=fixture_world(i.word());let provider=read_provider(i);let _=provider;let mut s=SkaterRuntime::load(assets,&graphs,&p,"normal")?;let rows=i.word();o.word(rows);let mut c=collision(&s);let mut teleported=false;let mut actions=Actions::default();live_snapshot(o,&p,&s,&c,teleported,&actions);
 for _ in 0..rows{let op=i.word();o.word(op);let mut extra=Vec::new();let result=match op{
// GENERATED_ORIGINAL_PACKET_RESET_CASES
 6=>super::super::solve::advance(&mut p,&mut s,[0.;2]).map(|_|super::super::skeleton_feedback::publish(&p,&mut s,false)),
 10=>{let state=skate_core::player::state::PhysicalStateId::try_from(i.word()).unwrap();s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(state);super::super::grind::enter(&mut p,&mut s)},
 12=>{s.player_input.toolkit=Some(s.ground_runtime.prepare_toolkit(&p.board,&s.player_input.processed));Ok(())},
 13=>super::super::grind::advance(&mut p,&mut s),14=>super::super::grind::fill(&p,&mut s),
 20=>{s.grind.observe(read_manager(i));Ok(())},
 22=>{let pose=i.word();s.animation.packet.riding_fakie=i.word()!=0;s.player_state.post.jump_fix_frames=i.word();p.trainer.grind_pop=i.float();s.animation.packet.hierarchy=globals(&s,pose)?;Ok(())},
 28=>{s.air_reckoning.state.spin_angle=i.float();s.air_reckoning.state.spin_speed=i.float();s.air_reckoning.state.secondary_lean_angle=i.float();Ok(())},
 34=>p.riding.start_wheel_queries(&p.board,&p.world).and_then(|_|p.riding.finish_wheel_queries()).and_then(|_|p.riding.finish_post_physics(&mut p.board,p.board_wiping_out,s.player_input.processed.flags_2468,s.player_input.processed.timestep_2604)),
 40=>{let state=skate_core::player::state::PhysicalStateId::try_from(i.word()).unwrap();s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(state);s.known_air.state.targeting_grind_213=i.word()!=0;Ok(())},
 41=>{let output=if s.player_state.current()==skate_core::player::state::PhysicalStateId::PhysicsGround{let toolkit=s.player_input.toolkit.as_ref().ok_or("State output requires actual board toolkit")?;Some(s.ground.output(&s.player_input.processed,&s.animation_input,toolkit))}else{None};super::super::player_state::migration_conditioning(&p,&mut s,output)},
 42=>{super::super::animation_phase::migration_conditioning_landing(&p,&mut s);Ok(())},
 43=>{let height=i.float();let mirrored=i.word()!=0;let mut record=Output(Vec::new());let r=super::super::animation_phase::migration_conditioning_graph(&mut record,&s.player_input.physical,s.player_state.filtered_output.as_ref(),height,mirrored,p.riding.motion.effective_basis.columns[2]);if r.is_ok(){extra=record.0}r},
 44=>{s.player_state.filtered.reset();s.player_state.filtered_output=None;Ok(())},
 45=>{let lane=i.word();let word=i.word();let g=&mut s.player_input.physical.grinds;match lane{0=>g.animation_name_156=None,1=>g.scoring_name_176=None,2=>g.words_136_140[0]=word,3=>g.words_136_140[1]=word,4=>s.player_input.physical.filtered_state_0=word,5..=9=>{if g.animation_name_156.is_none(){g.animation_name_156=Some(skate_core::animation::output::attributes::AttributeName([0;5]))}g.animation_name_156.as_mut().unwrap().0[(lane-5)as usize]=word},_=>panic!("field transport")}Ok(())},
 46=>{let flags=i.word();extra.push(skate_core::player::conditioner_capabilities::ConditionerCapabilityContext{in_front_end:flags&1!=0,hall_of_meat_enabled:flags&2!=0,challenge_query_active:flags&4!=0,challenge_configuration_enabled:flags&8!=0}.capabilities());Ok(())},
 47=>{s.player_input.update_dynamic_normal(&p.riding,p.settings.step.simulation.gravity_acceleration);s.player_input.publish_board(&p.riding)},
 48=>{let v:[f32;3]=i.floats();for b in p.board.bodies_mut(){b.rates.linear_velocity=Vector3::new(v[0],v[1],v[2])}Ok(())},
 _=>panic!("conditioning opcode")};c=collision(&s);o.status(result);o.word(extra.len()as u32);o.0.extend(extra);live_snapshot(o,&p,&s,&c,teleported,&actions);
 }
 }Ok(())
}
}
pub(crate) fn migration_state_conditioning_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_state_conditioning::run(a,f,i,o)}
