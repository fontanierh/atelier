// Appended after complete byte-identical original modules. These sections only
// construct real owners, transport caller packets and read retained fields.
// @SECTION physics/bridge.rs
fn gameplay_snapshot(o:&mut crate::Output,session:&Session,log:&crate::LogSink){
 let p=&session.physics;let s=&session.skater;o.word(9);
 crate::gameplay_block(o,|o|super::handplant::migration_gameplay_physical(o,p,s));
 crate::gameplay_block(o,|o|crate::observe_PlayerInputState(o,&s.player_input.player));
 crate::gameplay_block(o,|o|crate::observe_PhysicalPlayerInput(o,&s.player_input.physical));
 crate::gameplay_block(o,|o|crate::observe_ProcessedPhysicsInput(o,&s.player_input.processed));
 crate::gameplay_block(o,|o|s.player_state.migration_gameplay_observe(o));
 crate::gameplay_block(o,|o|session.controls.migration_gameplay_observe(o));
 crate::gameplay_block(o,|o|{
  o.wide(p.ticks);o.word(p.contact_count as u32);o.word(p.failed as u32);o.word(p.processed_flags_2468);o.word(p.board_wiping_out as u32);o.word(p.network_active as u32);
  let t=p.trainer;o.floats([t.pop,t.grind_pop,t.push_speed,t.push_power,t.braking,t.steering,t.wobble,t.offboard_jump,t.grip,t.turn_power,t.manual_drag]);o.word(t.hold_fakie as u32);
  let f=s.centre_of_mass_filter.migration_gameplay_words();o.words(f);let c=s.centre_of_mass_output;o.floats(c.velocity);o.floats(c.acceleration);o.floats(c.position);p.clock.migration_gameplay_observe(o);
  o.word(s.player_input.pending_teleport().is_some()as u32);if let Some(v)=s.player_input.pending_teleport(){o.matrix(v)}
  super::migration_gameplay_exchange(o,&p.exchange);s.animation.migration_gameplay_observe(o);
 });
 crate::gameplay_block(o,|o|{let mut bytes=Vec::new();session.camera.migration_gameplay_observe(&mut bytes,log);o.bytes(&bytes)});
 crate::gameplay_block(o,|o|crate::scoring_runtime::observe(&s.scoring,o));
}
pub(crate)fn migration_gameplay_run(root:&std::path::Path,i:&mut crate::Input,o:&mut crate::Output,log:&crate::LogSink)->Result<(),String>{
 let count=i.word();o.word(count);
 for _ in 0..count{
  let natural=i.word();let rows=i.word();o.word(rows);
  log.0.lock().unwrap().clear();
  let assets=skate_data::GameAssets::load(root).map_err(|e|e.to_string())?;
  let graphs=StockGraphs::load(root,&assets)?;
  let physics=GamePhysics::load_with_terrain(root,super::ground::Terrain::Flat)?;
  let skater=SkaterRuntime::load(root,&graphs,&physics,"easy")?;
  let stock_spin_speed=skater.air_settings.state.body_spin_scale_428;
  let mut session=Session{physics,skater,controls:PlayerControls::load(root)?,graphs,input:ControllerInput::default(),camera:CameraRuntime::load(root)?,markers:crate::session_marker::Runtime::load(root)?,stock_spin_speed};
  // The profile edit is an actual source method on the constructed live actor.
  session.skater.animation.set_customisation(natural,0);
  o.status(Ok(()));gameplay_snapshot(o,&session,log);
  for _ in 0..rows{
   let op=i.word();o.word(op);let result=match op{
    0=>{
     let tick=i.wide();let available=i.word()!=0;let packet=skate_core::input::tick::TickInput::new(tick,skate_core::input::gameplay_map::GameplayActions::from_values(i.floats()),available);
     let mut actions=packet.actions();
     match session.controls.update_for_physics(&mut actions,&session.physics,&session.skater,&session.camera){
      Err(e)=>Err(format!("Offboard controller publication: {e}")),
      Ok(())=>{
       session.controls.publish_gestures(session.physics.animation_profile.physics_mode,session.skater.player_input.physical.state.state_16);
       super::frame::advance(&mut session.physics,&mut session.skater,&mut session.controls,&session.graphs,&mut actions,packet.controller_available(),&mut session.camera)
      }
     }
    },
    1=>session.skater.travel_to(i.matrix()),
    2=>{session.launch(i.floats());Ok(())},
    3=>{let [pop,spin,speed,power]=i.floats();session.tune(pop,spin,speed,power)},
    4=>{session.skater.animation.set_customisation(i.word(),i.word());Ok(())},
    5=>{session.set_aspect_ratio(i.float());Ok(())},
    _=>return Err("Invalid complete gameplay opcode".into()),
   };
   o.status(result);gameplay_snapshot(o,&session,log);
  }
 }Ok(())
}
// @SECTION physics/controls.rs
impl PlayerControls {
 pub(crate)fn migration_gameplay_observe(&self,o:&mut crate::Output){
  o.words(*self.controller.words());o.word(self.offboard_direction.is_some()as u32);if let Some(v)=self.offboard_direction{o.floats(v)}
  o.word(self.intents.len()as u32);for v in &self.intents{o.string(v.name);o.float(v.value)}self.action_intents.migration_gameplay_observe(&mut o.0);
  o.wide(self.ticks);o.word(self.actor_flags);o.word(self.bumper_state_502 as u32);o.word(self.bumper_state_104 as u32);o.word(self.preferences.automatic_push_enabled as u32);o.word(self.preferences.automatic_push_right as u32);
  o.word(self.offboard_axes.is_some()as u32);if let Some(v)=self.offboard_axes{o.floats(v)}o.word(self.gestures.is_some()as u32);if let Some(v)=&self.gestures{v.migration_gameplay_observe(o)}
 }
}
// @SECTION input/gesture_input.rs
impl GestureInput{pub(crate)fn migration_gameplay_observe(&self,o:&mut crate::Output){o.word(self.held_pattern.is_some()as u32);if let Some(v)=&self.held_pattern{o.string(v)}}}
// @SECTION physics/player_state.rs
impl PlayerState{pub(crate)fn migration_gameplay_observe(&self,o:&mut crate::Output){
 o.word(self.current()as u32);o.word(self.requested_state as u32);o.word(self.state_count);o.word(self.update_count);o.word(self.initialized as u32);for v in self.state_flags{o.word(v as u32)}
 let s=self.selector;o.word(s.current_state.is_some()as u32);if let Some(v)=s.current_state{o.word(v as u32)}for v in [s.nonspecific_collision_free_frames,s.nonspecific_collision_frames,s.something_colliding_frames,s.two_wheel_counter,s.three_wheel_counter,s.post_grind_jump_counter,s.air_frames,s.teleport_countdown,s.skitch_exit_countdown]{o.word(v as u32)}o.word(s.revert_exited_normally as u32);o.word(s.request_teleport as u32);
 let s=&self.post;o.words(s.jump_reference);for v in [s.jump_fix_frames,s.latch_frames,s.state_frames]{o.word(v)}o.float(s.heading_adjust);for v in [s.complete,s.trajectory_pending,s.trajectory_valid,s.trajectory_available,s.trajectory_new_candidate]{o.word(v as u32)}
 self.filtered.migration_gameplay_observe(&mut o.0);o.word(self.filtered_output.is_some()as u32);if let Some(v)=self.filtered_output{v.migration_gameplay_observe(&mut o.0)}
}}
// @SECTION physics/clock.rs
impl SimulationClock{pub(crate)fn migration_gameplay_observe(&self,o:&mut crate::Output){o.word(self.ticks_until_reset);o.wide(self.timer_period.as_nanos()as u64)}}
// @SECTION skater_animation.rs
impl SkaterAnimation{pub(crate)fn migration_gameplay_observe(&self,o:&mut crate::Output){
 use skate_core::migration_camera_observer::Observe;
 o.wide(self.ticks);o.word(self.state.flags);o.float(self.state.phase);o.word(self.checkpoint_stance());
 let p=&self.state.publication;o.word(p.natural_stance as u32);o.word(p.relative_stance as u32);o.word(self.motion.animation.requested_stance);o.word(self.motion.animation.reset_action_intents as u32);
 self.motion.animation.motion_intents.migration_gameplay_observe(&mut o.0);self.motion.animation.filtered_intents.migration_gameplay_observe(&mut o.0);
 let mut bytes=Vec::new();self.action_controller.observe(&mut bytes);self.motion_controller.observe(&mut bytes);o.bytes(&bytes);
}}
// @SECTION physics.rs
fn migration_gameplay_event(o:&mut crate::Output,e:&skate_core::physics::phase::PhysicsEvent){use skate_core::physics::phase::{PhysicsEvent as E,PhysicsBody as B};match e{
 E::StateChanged{from,to}=>{o.word(0);o.word(*from as u32);o.word(*to as u32)},E::Landing=>o.word(1),E::Wipeout=>o.word(2),E::Contact{body}=>{o.word(3);o.word(match body{B::Board=>0,B::Rider=>1})}}}
fn migration_gameplay_exchange(o:&mut crate::Output,e:&SimulationExchange){
 o.wide(e.commands.tick());o.word(e.commands.commands().len()as u32);
 for c in e.commands.commands(){use skate_core::physics::phase::{PhysicsCommand as C,PhysicsBody as B};let body=|b:&B|match b{B::Board=>0,B::Rider=>1};let vec=|o:&mut crate::Output,v:&skate_core::math::Vector3|o.floats([v.x,v.y,v.z]);match c{
 C::SetVelocity{body:b,linear,angular}=>{o.word(0);o.word(body(b));vec(o,linear);vec(o,angular)},C::ApplyImpulse{body:b,impulse,point}=>{o.word(1);o.word(body(b));vec(o,impulse);vec(o,point)},C::RequestState(v)=>{o.word(2);o.word(*v as u32)},C::SetContactMode{body:b,enabled}=>{o.word(3);o.word(body(b));o.word(*enabled as u32)}}}
 o.word(e.events().len()as u32);for v in e.events(){migration_gameplay_event(o,v)}o.word(e.output().is_some()as u32);if let Some(v)=e.output(){o.wide(v.tick);o.word(v.state as u32);for p in [v.board_position,v.board_linear_velocity,v.rider_root_position,v.rider_linear_velocity,v.ground_normal]{o.floats([p.x,p.y,p.z])}o.word(v.contact_count);o.floats([v.predicted_position.x,v.predicted_position.y,v.predicted_position.z]);for p in [v.grounded,v.wiping_out,v.landed]{o.word(p as u32)}o.word(v.events.len()as u32);for p in &v.events{migration_gameplay_event(o,p)}}
}
