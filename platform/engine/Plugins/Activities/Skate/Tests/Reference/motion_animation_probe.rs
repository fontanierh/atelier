// Shared tree/channel IO and exact frozen owner/factory bodies are prepended.
use skate_core::animation::playback::{PlayAnimation,PlayAnimationInstance,PlaybackContext};
use skate_core::animation::playback_parameters::{PlaybackParameter,ParameterSource};
use skate_core::graph::intents::IntentMap;
use skate_data::state_graph::{GraphAttribute,attributes::Attributes};
const INTENTS:[&str;10]=["A","B","X","Y","TweakX","TweakY","LEFT","left\0tail","ABCDEFGHIJKLMNOPQRSTUVWXYZ012345_A","MISSING"];
impl Input {
 fn graph_attributes(&mut self)->Vec<GraphAttribute> {let n=self.word();(0..n).map(|_|GraphAttribute{name:self.string(),text:self.string(),float_bits:self.word(),boolean_byte:self.word() as u8}).collect()}
 fn context(&mut self)->PlaybackContext {let optional=|v:u32|if v==0 {None}else{Some(v==2)};let is_switch=optional(self.word());let is_mirrored=optional(self.word());let board_available=optional(self.word());let pro_skater=self.name();let transition_override=if self.word()!=0 {Some(self.transition())}else{None};PlaybackContext{is_switch,is_mirrored,board_available,pro_skater,transition_override}}
}
fn full_owner_snapshot(out:&mut Vec<u8>,h:&MotionAnimation) {
 owner_snapshot(out,h);h.channels.probe_snapshot(out);word(out,h.natural_stance);word(out,h.relative_stance);word(out,h.requested_stance);word(out,u32::from(h.reset_action_intents));word(out,u32::from(h.grab_type.is_some()));if let Some(g)=h.grab_type {word(out,g as u32);}
 word(out,h.motion_intents.len() as u32);word(out,h.filtered_intents.len() as u32);for n in INTENTS {for value in [h.motion_intent(n),h.filtered_intent(n)] {word(out,u32::from(value.is_some()));if let Some(v)=value {word(out,v.to_bits());}}}
 word(out,h.motion_attributes.len() as u32);for a in &h.motion_attributes {for w in a.name.0 {word(out,w);}word(out,a.value.to_bits());}
 word(out,h.settable.entries().len() as u32);for a in h.settable.entries() {for w in a.name.0 {word(out,w);}word(out,a.value.to_bits());word(out,u32::from(a.normalized));word(out,a.sequence_id as u32);}
 word(out,h.construction_values.len() as u32);for (a,b) in &h.construction_values {for w in a.0.into_iter().chain(b.0) {word(out,w);}}
}
fn operation_snapshot(out:&mut Vec<u8>,op:&factory_oracle::MotionOperation) {
 use factory_oracle::MotionOperation;
 match op {MotionOperation::Unsupported=>word(out,0),MotionOperation::Play(p)=>{word(out,1);string(out,&p.animation);for n in [&p.switch_animation,&p.mirror_animation,&p.no_board_animation] {word(out,u32::from(n.is_some()));if let Some(n)=n {string(out,n);}}word(out,p.playback_speed.to_bits());word(out,u32::from(p.apply_posture));transition_snapshot(out,p.transition);word(out,p.parameters.len() as u32);for p in &p.parameters {match &p.source {ParameterSource::MotionIntent(s)=>{word(out,0);string(out,s);},ParameterSource::FilteredIntent(s)=>{word(out,1);string(out,s);},ParameterSource::LastAnimation(n)=>{word(out,2);for w in n.0 {word(out,w);}}}word(out,u32::from(p.rename.is_some()));if let Some(n)=p.rename {for w in n.0 {word(out,w);}}word(out,u32::from(p.default_value.is_some()));if let Some(v)=p.default_value {word(out,v.to_bits());}word(out,u32::from(p.normalized));}},MotionOperation::CreateAttribute(factory_oracle::RidingOperation::CreateAttribute{name,values,set})=>{word(out,2);for w in name.0 {word(out,w);}for v in values {word(out,u32::from(v.is_some()));if let Some(v)=v {word(out,v.to_bits());}}word(out,u32::from(*set));}}
}
fn transition_snapshot(out:&mut Vec<u8>,s:TransitionSettings) {for w in [s.kind,s.seconds.to_bits(),s.under,s.matching,u32::from(s.use_channels_from_weights)] {word(out,w);}}
fn context_snapshot(out:&mut Vec<u8>,c:&PlaybackContext) {for v in [c.is_switch,c.is_mirrored,c.board_available] {word(out,match v {None=>0,Some(false)=>1,Some(true)=>2});}for w in c.pro_skater.0 {word(out,w);}word(out,u32::from(c.transition_override.is_some()));if let Some(s)=c.transition_override {transition_snapshot(out,s);}}
fn scalar(out:&mut Vec<u8>,r:Result<f32,String>) {match r {Ok(v)=>{word(out,1);word(out,v.to_bits());},Err(e)=>{word(out,0);string(out,&e);}}}
fn owner_run()->Result<(),String> {
 let args:Vec<_>=std::env::args().collect();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{bytes,at:8};let count=input.word();let mut out=Vec::new();
 for _ in 0..count {
  let mut host=MotionAnimation::from_metadata(load_metadata(&[&args[1]])?);let mut operation=factory_oracle::MotionOperation::Unsupported;let mut instance=PlayAnimationInstance::default();let mut context=PlaybackContext{is_switch:None,is_mirrored:None,board_available:None,pro_skater:encode(b""),transition_override:None};let n=input.word();
  for _ in 0..n {match input.word() {
   0=>{host.skater_animation_flags=if input.word()!=0 {Some(input.word())}else{None};host.natural_stance=input.word();host.relative_stance=input.word();host.requested_stance=input.word();host.posture.set_profile(input.word());host.posture_bank_valid=input.word()!=0;host.posture.set_requested(input.word()!=0);status(&mut out,Ok(()));},
   1=>{let n=input.word();let names:Vec<_>=(0..n).map(|_|input.string()).collect();let n=input.word();let mirror:Vec<_>=(0..n).map(|_|input.word() as i32).collect();status(&mut out,host.set_hierarchy(&names,&mirror));},
   2=>{let animation=input.string();let speed=input.float();let start_time=input.float();let transition=input.transition();boolean(&mut out,host.play(PlaybackRequest{animation,speed,start_time,transition}));},
   3=>{let name=input.string();let animation=input.string();let settings=channel_settings(&mut input);boolean(&mut out,host.new_channel(&name,&animation,settings));},
   4=>{let name=input.string();let animation=input.string();let settings=channel_settings(&mut input);let transition=input.transition();let resurrect=input.word()!=0;let create=input.word()!=0;boolean(&mut out,host.transition_channel(&name,&animation,settings,transition,resurrect,create));},
   5=>status(&mut out,host.apply_parameters()),6=>{let dt=input.float();let phase=input.float();status(&mut out,panic_result(||host.advance(dt,phase)));},7=>status(&mut out,host.refresh_tree_attributes()),
   8=>{let e=Evaluation{cull_threshold:input.float(),update_history:input.word()!=0};match host.evaluate_pose(e) {Ok(c)=>{word(&mut out,1);commands(&mut out,&c);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},
   9=>{for a in input.settable() {host.set_attribute(a);}status(&mut out,Ok(()));},10=>{let a=input.name();let b=input.name();host.set_construction_value(a,b);status(&mut out,Ok(()));},
   11=>{let name=input.string();host.motion_intents.insert(&name,input.float());status(&mut out,Ok(()));},12=>{let name=input.string();host.filtered_intents.insert(&name,input.float());status(&mut out,Ok(()));},
   13=>{let intent=input.string();let attr=input.name();host.attach(&intent,attr,input.word()!=0);status(&mut out,Ok(()));},14=>{let name=input.name();host.emit_packet(name,input.float());status(&mut out,Ok(()));},
   15=>{match input.word() {0=>host.clear_grab_type(),1=>host.set_grab_type(motion_stock_gameplay::GrabType::Fs),2=>host.set_grab_type(motion_stock_gameplay::GrabType::Bs),3=>host.set_grab_type(motion_stock_gameplay::GrabType::Nose),4=>host.set_grab_type(motion_stock_gameplay::GrabType::Tail),_=>unreachable!()};status(&mut out,Ok(()));},
   16=>{host.begin_graph_update();status(&mut out,Ok(()));},17=>{host.reset_from_stock();status(&mut out,Ok(()));},18=>status(&mut out,host.reset_to_given_stance()),19=>{host.synchronize_air_time(input.float());status(&mut out,Ok(()));},20=>status(&mut out,host.jump_into(input.name())),
   21=>{let db=input.string();scalar(&mut out,host.stock_clip_translation_z(&db,&input.string()));},22=>{scalar(&mut out,host.current_time());scalar(&mut out,host.current_length());word(&mut out,u32::from(host.in_transition()));},
   23=>{let name=input.string();if input.word()!=0 {let seconds=input.float();host.channels.end_with(&name,seconds,input.word()!=0);}else {host.channels.end(&name);}status(&mut out,Ok(()));},24=>{let name=input.string();boolean(&mut out,Ok(host.channels.influence(&name,input.float())));},25=>{host.current=Some(input.tree()?);status(&mut out,Ok(()));},
   26=>{let n=input.word();host.tree_attributes=(0..n).map(|_|input.attribute()).collect();status(&mut out,Ok(()));},27=>{match host.last_attribute(input.name()) {Ok(a)=>{word(&mut out,1);word(&mut out,u32::from(a.is_some()));if let Some(a)=a {attribute(&mut out,&a);}},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},
   28=>{let n=input.word();let mut values=IntentMap::new();for _ in 0..n {let name=input.string();values.insert(&name,input.float());}outputs::MotionEffects::from_values(&values).apply_to(&mut host.motion_intents);status(&mut out,Ok(()));},
   29=>{let a=input.graph_attributes();match factory_oracle::parse(&Attributes::new(&a)) {Ok(Some(o))=>{word(&mut out,1);word(&mut out,1);operation=o;instance=PlayAnimationInstance::default();},Ok(None)=>{word(&mut out,1);word(&mut out,0);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}operation_snapshot(&mut out,&operation);},
   30=>{let a=input.graph_attributes();status(&mut out,factory_oracle::add_parameter(&mut operation,&Attributes::new(&a)));operation_snapshot(&mut out,&operation);},
   31=>{let phase=input.word() as u8;status(&mut out,factory_oracle::execute(&operation,&mut instance,phase,&mut context,&mut host));context_snapshot(&mut out,&context);},32=>{context=input.context();status(&mut out,Ok(()));},
   _=>unreachable!(),
  }full_owner_snapshot(&mut out,&host);}
 }assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&out).map_err(|e|e.to_string())?;Ok(())
}
fn main() {std::panic::set_hook(Box::new(|_|{}));if let Err(e)=owner_run() {eprintln!("{e}");std::process::exit(2);}}
