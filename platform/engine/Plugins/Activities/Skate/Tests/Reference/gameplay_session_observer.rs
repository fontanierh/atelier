// Appended only after complete byte-identical pinned original modules.
// @SECTION session_marker/state.rs
impl Hold{pub(super)fn migration_session_words(&self)->[u32;3]{[self.elapsed.to_bits(),self.fired as u32,self.tail as u32]}}
// @SECTION session_marker/validation.rs
impl Validation{pub(super)fn migration_session_words(&self)->[u32;4]{[self.slope.to_bits(),self.max_drop.to_bits(),self.clearance_length.to_bits(),self.clearance_radius.to_bits()]}}
// @SECTION session_marker/mod.rs
impl Runtime{pub(crate)fn migration_session_observe(&self,o:&mut crate::Output){
 let s=&self.session;o.word(s.marker.is_some()as u32);if let Some(m)=s.marker{o.matrix(m.transform);o.word(m.on_board as u32);o.word(m.foot_forward as u32);o.wide(m.generation)}
 o.words(s.hold.migration_session_words());o.wide(s.generation);o.wide(s.last_batch);o.words([s.visible as u32,s.can_place as u32,s.can_return as u32,s.blocked_until_release as u32]);o.float(s.progress);o.wide(s.ui_time.to_bits());o.words(self.validation.migration_session_words());
}}
// @SECTION input.rs
pub(crate)fn migration_session_observe(o:&mut crate::Output,c:&ControllerInput){controllers::migration_session_observe(o,c)}
pub(crate)fn migration_session_samples(i:&mut crate::Input)->[Result<platform::DevicePacket,platform::DeviceError>;4]{controllers::migration_session_samples(i)}
// @SECTION input/controllers.rs
pub(super)fn migration_session_observe(o:&mut crate::Output,c:&ControllerInput){migration_gameplay_observe(o,c)}
pub(super)fn migration_session_samples(i:&mut crate::Input)->[Result<DevicePacket,DeviceError>;4]{std::array::from_fn(|_|migration_gameplay_sample(i))}
// @SECTION physics/bridge.rs
fn migration_session_snapshot(o:&mut crate::Output,s:&Session,elapsed:f32,generation:u32,log:&crate::LogSink){
 o.word(6);
 crate::gameplay_block(o,|o|{let p=s.pose();o.matrix(p.root.to_cols_array_2d());o.word(p.bones.len()as u32);for b in p.bones{o.matrix(b.to_cols_array_2d())}o.word(p.names.len()as u32);for n in p.names{o.string(&n)}o.word(p.camera.is_some()as u32);if let Some((position,basis,fov))=p.camera{o.floats(position.to_array());for c in basis.to_cols_array_2d(){o.floats(c)}o.float(fov)}o.floats(p.velocity.to_array());o.wide(p.tick);o.string(&p.state);let(score,reward,trick)=s.score();o.floats([score,reward,s.manual_balance()]);o.string(&trick);o.float(s.period());});
 crate::gameplay_block(o,|o|{match s.reference_pose(){Ok(p)=>{o.status(Ok(()));o.word(p.len()as u32);for m in p{o.matrix(m.to_cols_array_2d())}},Err(e)=>o.status(Err(e))}});
 crate::gameplay_block(o,|o|s.markers.migration_session_observe(o));
 crate::gameplay_block(o,|o|crate::input::migration_session_observe(o,&s.input));
 crate::gameplay_block(o,|o|{o.float(elapsed);o.word(generation)});
 crate::gameplay_block(o,|o|gameplay_snapshot(o,s,log));
}
fn migration_session_check_pose(s:&Session)->Result<(),String>{
 let p=s.pose();
 // @ORIGINAL_PUBLISH_FINITE_GATE
 Ok(())
}
fn migration_session_step(session:&mut Session,retained:&mut f32,dt:f32,raw:Controls)->Result<(),String>{
 let Controls{buttons,left,right,triggers}=raw;let mut elapsed=*retained;
 let result=(||{
 // @ORIGINAL_HOST_STEP
 migration_session_check_pose(session)
 })();*retained=elapsed;result
}
pub(crate)fn migration_session_run(root:&Path,i:&mut crate::Input,o:&mut crate::Output,log:&crate::LogSink)->Result<(),String>{
 let count=i.word();o.word(count);
 for _ in 0..count{
  let(triangles,rails)=i.snapshot();let spawn=i.floats();let heading=i.float();let rows=i.word();o.word(rows);log.0.lock().unwrap().clear();
  let construction=Session::new(root,triangles,rails,spawn,heading);
  let mut s=match construction{Ok(s)=>{o.status(Ok(()));s},Err(e)=>{o.status(Err(e));assert_eq!(rows,0,"Rejected construction must not execute a substitute owner");continue}};
  let mut elapsed=0f32;let mut generation=0u32;migration_session_snapshot(o,&s,elapsed,generation,log);
  for _ in 0..rows{
   let op=i.word();o.word(op);let result=match op{
    0=>{let spawn=i.floats();let heading=i.float();let next=i.word();s.activate(spawn,heading).map(|_|{elapsed=0.;generation=next})},
    1=>{let raw=i.xbox();s.tick(Controls{buttons:raw.buttons,triggers:raw.triggers,left:raw.left,right:raw.right})},
    2=>{let dt=i.float();let samples=crate::input::migration_session_samples(i);s.collect(InputFrame{samples},dt);Ok(())},
    3=>s.advance(),
    4=>{s.suspend_input();elapsed=0.;Ok(())},
    5=>{let dt=i.float();let raw=i.xbox();migration_session_step(&mut s,&mut elapsed,dt,Controls{buttons:raw.buttons,triggers:raw.triggers,left:raw.left,right:raw.right})},
    6=>{let difficulty=i.text();let goofy=i.word()!=0;let trucks=i.float();s.configure(&difficulty,goofy,trucks)},
    7=>{let[pop,spin,speed,power]=i.floats();s.tune(pop,spin,speed,power)},
    8=>{s.launch(i.floats());Ok(())},
    9=>{s.set_aspect_ratio(i.float());Ok(())},
    10=>{let(triangles,rails)=i.snapshot();s.collision_builder().build(triangles,rails).and_then(|w|s.install_collision(w))},
    11=>Ok(()),
    _=>return Err("Invalid whole-session proof operation".into()),
   };o.status(result);migration_session_snapshot(o,&s,elapsed,generation,log);
  }
 }Ok(())
}
