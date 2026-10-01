// GENERATED_COMPLETE_OWNER_OBSERVATIONS
fn climb_snapshot(o:&mut Output,p:&GamePhysics,s:&SkaterRuntime,last:&skate_core::air::known::KnownAirOutput,camera:&crate::camera::CameraRuntime){
 block(o,|o|climbing::migration_climber_observe(o,&s.climbing));
 block(o,|o|{crate::observe_PlayerInputState(o,&s.player_input.player);crate::observe_PhysicalPlayerInput(o,&s.player_input.physical);o.word(s.player_input.pending_teleport().is_some()as u32);if let Some(target)=s.player_input.pending_teleport(){o.matrix(target)}});
 block(o,|o|{o.word(s.render_pose.len()as u32);for m in &s.render_pose{o.matrix(*m)}o.wide(s.pose_generation);o.word(s.player_state.current()as u32);o.word(s.skateboard_controller.fields.state_448);o.words(s.centre_of_mass_filter.migration_climber_words());for v in[s.centre_of_mass_output.velocity,s.centre_of_mass_output.acceleration,s.centre_of_mass_output.position]{o.floats(v)}o.float(s.animation_input.extra.look_x);o.float(s.animation_input.extra.look_y);o.word(p.clock.migration_climber_ticks());o.wide(p.clock.period().as_nanos()as u64);o.word(camera.frame.is_some()as u32);o.word(camera.latest_subject.is_some()as u32);o.word(camera.simulation_rate_requests.len()as u32);});
 block(o,|o|crate::observe_BoardPossessionManager(o,&s.offboard_feet));
 block(o,|o|selector_obs::owner_out(o,&s.offboard_air_selector));
 block(o,|o|{riding_outputs::migration_climber_observe(o,&p.riding);o.word(p.board.solved_contacts().len()as u32);for c in p.board.solved_contacts(){o.words(c.words());o.word(c.reaction_index_a as u32);o.word(c.reaction_index_b as u32)}});
 snapshot(o,p,s,last);
}
pub(super)fn run(assets:&std::path::Path,fixtures:&std::path::Path,i:&mut Input,o:&mut Output)->Result<(),String>{
// GENERATED_COMPLETE_OWNER_CONSTRUCTION
 s.climbing=climbing::Runtime::load(fixtures,&s.animation.evaluator.frames.bone_names)?;
 let mut camera=crate::camera::CameraRuntime::load(&fixtures.join("camera-0"))?;
 let mut controls=PlayerControls::default();controls.controller=skate_core::input::controller::DerivedControllerInput::from_words([0;26]);
 climb_snapshot(o,&p,&s,&last,&camera);
 for _ in 0..n{let op=i.word();o.word(op);let mut handled=None;let r=match op{
 0=>{s.player_input.processed=crate::read_ProcessedPhysicsInput(i);s.player_state.post.jump_reference=i.words();s.player_state.post.jump_fix_frames=i.word();s.animation_input.fields.body_spin=i.float();s.animation_input.extra.physical_body_spin=i.float();let adjust=i.float();s.animation_input.extra.body_adjust=[adjust,-adjust];actual_packet(&p,&mut s);Ok(())},
 30=>{s.player_state.lifecycle=skate_core::player::lifecycle::PhysicalPlayerStateLifecycle::new(skate_core::player::state::PhysicalStateId::try_from(i.word()).unwrap());s.player_input.physical.reckoning.vector_16=i.floats::<4>().map(f32::to_bits);s.player_input.processed.flags_2476=i.word();let present=i.word()!=0;let vector=i.floats();controls.offboard_direction=if present{Some(vector)}else{None};Ok(())},
 31=>climbing::migration_climber_seed(&p,&mut s,i),
 32=>{controls.controller=skate_core::input::controller::DerivedControllerInput::from_words(i.words());Ok(())},
 33=>climbing::advance(&mut p,&mut s,&controls,&mut camera).map(|value|handled=Some(value)),
 34=>{climbing::approach::advance(&p,&mut s,&controls);Ok(())},
 35=>climbing::migration_climber_publish(&p,&mut s,i),
 36=>{let root=i.matrix();p.board.set_transform(skate_core::physics::drive_frames::RetailAffineTransform{basis:skate_core::math::Basis3{columns:core::array::from_fn(|j|[root[j][0],root[j][1],root[j][2]])},translation:skate_core::math::Vector3::new(root[3][0],root[3][1],root[3][2])});Ok(())},
 37=>{climbing::migration_climber_clear(&mut s.climbing,i.float());Ok(())},
 38=>s.player_input.request_teleport(i.matrix()),
 39=>{climbing::migration_climber_empty_ground(&mut s.climbing);Ok(())},
 40=>{let which=i.word();let count=i.word();let names=if count==0{s.animation.evaluator.frames.bone_names.clone()}else{(0..count).map(|_|i.text()).collect()};match climbing::Runtime::load(&fixtures.join("climbing-loaders").join(which.to_string()),&names){Ok(next)=>{s.climbing=next;Ok(())},Err(e)=>Err(e)}},
 41=>climbing::migration_climber_hang_pose(&p,&mut s,i),
 42=>{s.skateboard_controller.fields.state_448=i.word();Ok(())},
 43=>{let marker=i.word();let feet=&mut s.offboard_feet;feet.word_300=marker;feet.words_308_to_316=[marker,marker.wrapping_add(1),marker.wrapping_add(2)];feet.flags_304_to_307=[true;4];for hand in &mut feet.hands{hand.word_80=marker;hand.flag_84=true;hand.flags_104_to_107=[true;4]}Ok(())},
 44=>{s.pose_generation=i.wide();s.player_input.player.update_count_1316=i.word();Ok(())},
 _=>panic!("Climbing wire operation")};o.status(r);o.word(handled.is_some()as u32);if let Some(v)=handled{o.word(v as u32)}climb_snapshot(o,&p,&s,&last,&camera);
 }
 assert!(camera.frame.is_none()&&camera.latest_subject.is_none()&&camera.simulation_rate_requests.is_empty());
 }Ok(())
}
}
pub(crate)fn migration_climbing_run(a:&std::path::Path,f:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output)->Result<(),String>{migration_climbing::run(a,f,i,o)}
