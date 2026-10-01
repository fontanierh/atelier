// Append-only sections. The checker retains the complete original source prefix
// for every containing host/core module, including bridge and platform bodies.
// BEGIN BRIDGE
pub(crate) fn migration_gameplay_world_run(i:&mut crate::Input,o:&mut crate::Output,commands:u32){
 let mut prepared:Option<PreparedCollision>=None;
 for n in 0..commands{let op=i.word();let mut result=crate::Output(Vec::new());match op{
  0=>{let material=i.material();let count=i.word();let triangles=(0..count).map(|_|std::array::from_fn(|_|i.floats::<3>())).collect();let count=i.word();let rails=(0..count).map(|_|{let n=i.word();(0..n).map(|_|i.floats::<3>()).collect()}).collect();let builder=CollisionBuilder{material};match builder.build(triangles,rails){Ok(value)=>{prepared=Some(value);result.status(true,"")},Err(error)=>result.status(false,&error)}},
  1=>crate::query(i,&mut result,prepared.as_ref().map(|p|(&p.world,p.grind.as_ref()))),
  2=>crate::contacts(i,&mut result,prepared.as_mut().map(|p|&mut p.world)),
  3=>{prepared=None;result.status(true,"")},4=>result.status(true,""),_=>panic!("Gameplay world operation")}
 let mut snapshot=crate::Output(Vec::new());snapshot.word(prepared.is_some()as u32);if let Some(p)=&prepared{crate::observe_world(&mut snapshot,&p.world,p.grind.as_ref())}let mut row=crate::Output(Vec::new());row.block(0,&result);row.block(1,&snapshot);o.word(n);o.word(op);o.word(row.0.len()as u32);o.0.extend(row.0);
 }
}
// END BRIDGE
// BEGIN INPUT
pub(crate) fn migration_gameplay_input_run(i:&mut crate::Input,o:&mut crate::Output,commands:u32){controllers::migration_gameplay_input_run(i,o,commands)}
// END INPUT
// BEGIN CONTROLLERS
fn migration_gameplay_raw(o:&mut crate::Output,r:RawInput){o.word(u32::from(r.buttons));o.floats(r.triggers);o.floats(r.left);o.floats(r.right)}
fn migration_gameplay_actions(o:&mut crate::Output,mut a:GameplayActions){for n in 64..82{o.float(a.value(n));o.word(u32::from(a.state(n)))}}
pub(super) fn migration_gameplay_observe(o:&mut crate::Output,c:&ControllerInput){
 o.wide(c.tick);o.wide(c.publications);o.wide(c.consumed_batches);o.word(c.active as u32);
 for r in c.raw{migration_gameplay_raw(o,r)}for b in &c.cache{for r in b{o.0.extend(skate_core::input::history::migration_gameplay_record(r))}}
 o.0.extend(c.history.migration_gameplay_ring());
 for n in 0..DEVICE_SLOTS{match c.status[n]{ControllerStatus::Unpolled=>o.word(0),ControllerStatus::Ready=>o.word(1),ControllerStatus::Unavailable(error)=>{o.word(2);match error{DeviceError::Disconnected=>{o.word(0);o.word(0)},DeviceError::State(code)=>{o.word(1);o.word(code)},DeviceError::Capabilities(code)=>{o.word(2);o.word(code)},#[cfg(not(windows))]DeviceError::UnsupportedPlatform=>{o.word(3);o.word(0)}}}}o.word(c.packet_numbers[n].is_some()as u32);if let Some(v)=c.packet_numbers[n]{o.word(v)}let p=&c.pads[n];o.word(p.count()as u32);o.word(p.records().len()as u32);for r in p.records(){o.0.extend(r)}o.floats(c.mapped_actions[n]);migration_gameplay_actions(o,GameplayActions::from_pad(p))}
 let t=c.tick_input();o.wide(t.tick());o.word(t.controller_available()as u32);migration_gameplay_actions(o,t.actions());migration_gameplay_actions(o,c.player_actions());migration_gameplay_raw(o,c.raw_input());let(a,b,d)=c.session_marker_actions();o.0.extend([a as u32,b as u32,d as u32]);
}
fn migration_gameplay_sample(i:&mut crate::Input)->Result<DevicePacket,DeviceError>{match i.word(){0=>{let number=i.word();let state=i.xbox();let subtype=i.word()as u8;Ok(DevicePacket{number,state,subtype})},kind=>{let code=i.word();Err(match kind{1=>DeviceError::Disconnected,2=>DeviceError::State(code),3=>DeviceError::Capabilities(code),#[cfg(not(windows))]4=>DeviceError::UnsupportedPlatform,_=>panic!("Gameplay input error kind")})}}}
pub(super) fn migration_gameplay_input_run(i:&mut crate::Input,o:&mut crate::Output,commands:u32){
 let mut c=ControllerInput::default();for n in 0..commands{let op=i.word();let mut result=crate::Output(Vec::new());match op{
 0=>{c.collect(std::array::from_fn(|_|migration_gameplay_sample(i)));result.word(1)},1=>result.word(c.publish_actions()as u32),2=>{c.discard_gameplay();result.word(1)},3=>{super::sample(&mut c,i.xbox());result.word(1)},4=>{c.tick=i.wide();c.publications=i.wide();c.consumed_batches=i.wide();result.word(1)},5=>result.word(1),_=>panic!("Gameplay input operation")}
 let mut snapshot=crate::Output(Vec::new());migration_gameplay_observe(&mut snapshot,&c);let mut row=crate::Output(Vec::new());row.block(0,&result);row.block(1,&snapshot);o.word(n);o.word(op);o.word(row.0.len()as u32);o.0.extend(row.0);
 }
}
// END CONTROLLERS
// BEGIN CORE_HISTORY
pub fn migration_gameplay_record(r:&HistoryRecord)->Vec<u32>{let mut o=vec![r.count as u32];o.extend(r.values.map(f32::to_bits));o}
impl PadHistory{pub fn migration_gameplay_ring(&self)->Vec<u32>{let mut o=vec![self.read as u32,self.write as u32];for b in &self.batches{for r in b{o.extend(migration_gameplay_record(r))}}o}}
// END CORE_HISTORY
// BEGIN CORE_WORLD
impl BoardWorld{pub fn migration_gameplay_world_storage(&self)->(&[Bounds],f32,bool){(&self.triangle_bounds,self.maximum_fatness,self.imported_floor_seams)}}
// END CORE_WORLD
