//! All operation code is from the unmodified frozen reference. This host logs
//! read/write effects and returns explicit native play refusal/error fixtures.
use skate_core::animation::{playback::{PlayAnimation,PlayAnimationInstance,PlaybackContext,PlaybackRequest,PlaybackService,TransitionSettings},playback_parameters::{PlaybackParameter,ParameterSource,ParameterInputs,AttributeSink,SettableAttribute},output::attributes::{AttributeName,AttributePayload,AnimationAttribute},skeleton_input::name::encode};
use std::{collections::BTreeMap,cell::RefCell,io::{Read,Write}};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let s=String::from_utf8(self.bytes[self.at..self.at+n].to_vec()).unwrap();self.at+=n;s}
    fn name(&mut self)->AttributeName {AttributeName(core::array::from_fn(|_|self.word()))}
    fn attribute(&mut self)->AnimationAttribute {let name=self.name();let kind=self.word() as u8;let status=self.word() as u8;let sequence_id=self.word() as i32;let begin_time=self.float();let end_time=self.float();let payload=AttributePayload(core::array::from_fn(|_|if self.word()!=0 {Some(self.word())} else {None}));AnimationAttribute{name,kind,status,sequence_id,begin_time,end_time,payload}}
    fn optional_string(&mut self)->Option<String> {if self.word()!=0 {Some(self.string())} else {None}}
    fn transition(&mut self)->TransitionSettings {TransitionSettings{kind:self.word(),seconds:self.float(),under:self.word(),matching:self.word(),use_channels_from_weights:self.word()!=0}}
    fn parameter(&mut self)->PlaybackParameter {let source=match self.word() {0=>ParameterSource::MotionIntent(self.string()),1=>ParameterSource::FilteredIntent(self.string()),2=>ParameterSource::LastAnimation(self.name()),_=>unreachable!()};let rename=if self.word()!=0 {Some(self.name())} else {None};let default_value=if self.word()!=0 {Some(self.float())} else {None};let normalized=self.word()!=0;PlaybackParameter{source,rename,default_value,normalized}}
    fn parameters(&mut self)->Vec<PlaybackParameter> {let n=self.word();(0..n).map(|_|self.parameter()).collect()}
    fn operation(&mut self)->PlayAnimation {PlayAnimation{animation:self.string(),switch_animation:self.optional_string(),mirror_animation:self.optional_string(),no_board_animation:self.optional_string(),playback_speed:self.float(),apply_posture:self.word()!=0,transition:self.transition(),parameters:self.parameters()}}
    fn optional_bool(&mut self)->Option<bool> {match self.word() {0=>None,1=>Some(false),2=>Some(true),_=>unreachable!()}}
    fn context(&mut self)->PlaybackContext {PlaybackContext{is_switch:self.optional_bool(),is_mirrored:self.optional_bool(),board_available:self.optional_bool(),pro_skater:self.name(),transition_override:if self.word()!=0 {Some(self.transition())} else {None}}}
    fn values(&mut self)->BTreeMap<String,f32> {let n=self.word();(0..n).map(|_|(self.string(),self.float())).collect()}
    fn service(&mut self)->Service {let motion=self.values();let filtered=self.values();let last_error=self.optional_string();let n=self.word();let last=(0..n).map(|_|{let a=self.attribute();(a.name.0,a)}).collect();let n=self.word();let responses=(0..n).map(|_|{let kind=self.word();(kind,if kind==2 {self.string()} else {String::new()})}).collect();Service{motion,filtered,last,last_error,responses,played:0,events:RefCell::new(Vec::new())}}
}
fn word(out:&mut Vec<u8>,v:u32) {out.extend(v.to_le_bytes());}
fn string(out:&mut Vec<u8>,v:&str) {word(out,v.len() as u32);out.extend(v.as_bytes());}
fn name(out:&mut Vec<u8>,v:AttributeName) {for w in v.0 {word(out,w);}}
fn attribute(out:&mut Vec<u8>,a:AnimationAttribute) {name(out,a.name);word(out,u32::from(a.kind));word(out,u32::from(a.status));word(out,a.sequence_id as u32);word(out,a.begin_time.to_bits());word(out,a.end_time.to_bits());for p in a.payload.0 {word(out,u32::from(p.is_some()));if let Some(v)=p {word(out,v);}}}
fn transition(out:&mut Vec<u8>,s:TransitionSettings) {word(out,s.kind);word(out,s.seconds.to_bits());word(out,s.under);word(out,s.matching);word(out,u32::from(s.use_channels_from_weights));}
fn status(out:&mut Vec<u8>,r:Result<(),String>) {match r {Ok(())=>word(out,1),Err(e)=>{word(out,0);string(out,&e);}}}
struct Service {motion:BTreeMap<String,f32>,filtered:BTreeMap<String,f32>,last:BTreeMap<[u32;5],AnimationAttribute>,last_error:Option<String>,responses:Vec<(u32,String)>,played:usize,events:RefCell<Vec<u8>>}
impl ParameterInputs for Service {
    fn motion_intent(&self,n:&str)->Option<f32> {let value=self.motion.get(n).copied();let mut out=self.events.borrow_mut();word(&mut out,1);string(&mut out,n);word(&mut out,u32::from(value.is_some()));if let Some(v)=value {word(&mut out,v.to_bits());}value}
    fn filtered_intent(&self,n:&str)->Option<f32> {let value=self.filtered.get(n).copied();let mut out=self.events.borrow_mut();word(&mut out,2);string(&mut out,n);word(&mut out,u32::from(value.is_some()));if let Some(v)=value {word(&mut out,v.to_bits());}value}
    fn last_attribute(&mut self,n:AttributeName)->Result<Option<AnimationAttribute>,String> {let mut out=self.events.borrow_mut();word(&mut out,3);name(&mut out,n);if let Some(e)=&self.last_error {word(&mut out,2);string(&mut out,e);return Err(e.clone());}let a=self.last.get(&n.0).copied();word(&mut out,u32::from(a.is_some()));if let Some(v)=a {attribute(&mut out,v);}Ok(a)}
}
impl AttributeSink for Service {
    fn set_attribute(&mut self,a:SettableAttribute) {let mut out=self.events.borrow_mut();word(&mut out,4);name(&mut out,a.name);word(&mut out,a.value.to_bits());word(&mut out,u32::from(a.normalized));word(&mut out,a.sequence_id as u32);for (n,v) in &mut self.motion {if encode(n.as_bytes())==a.name {*v=a.value;}}}
}
impl PlaybackService for Service {
    fn set_construction_value(&mut self,n:AttributeName,v:AttributeName) {let mut out=self.events.borrow_mut();word(&mut out,5);name(&mut out,n);name(&mut out,v);}
    fn set_posture_enabled(&mut self,v:bool) {let mut out=self.events.borrow_mut();word(&mut out,6);word(&mut out,u32::from(v));}
    fn play(&mut self,r:PlaybackRequest)->Result<bool,String> {let mut out=self.events.borrow_mut();word(&mut out,7);string(&mut out,&r.animation);word(&mut out,r.speed.to_bits());word(&mut out,r.start_time.to_bits());transition(&mut out,r.transition);let response=self.responses.get(self.played).cloned().unwrap_or((1,String::new()));self.played+=1;word(&mut out,response.0);if response.0==2 {string(&mut out,&response.1);Err(response.1)} else {Ok(response.0!=0)}}
}
fn run() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{bytes,at:8};let n=input.word();let mut out=Vec::new();
    for _ in 0..n {let kind=input.word();let mut service=input.service();if kind==1 {let beginning=input.word()!=0;let parameters=input.parameters();for p in parameters {struct One(Option<SettableAttribute>);impl AttributeSink for One {fn set_attribute(&mut self,a:SettableAttribute) {self.0=Some(a);}}
            let mut one=One(None);let result=p.update(beginning,&mut service,&mut one);if let Some(a)=one.0 {service.set_attribute(a);}status(&mut out,result);}}
        else {let operation=input.operation();let mut context=input.context();let mut instance=PlayAnimationInstance::default();let steps=input.word();for _ in 0..steps {let result=match input.word() {0=>instance.begin(&operation,&mut context,&mut service),1=>instance.update(&operation,&mut service),2=>{instance.end();Ok(())},3=>{let motion=input.values();service.motion=motion;Ok(())},_=>unreachable!()};status(&mut out,result);word(&mut out,u32::from(context.transition_override.is_some()));if let Some(s)=context.transition_override {transition(&mut out,s);}}}
        let events=service.events.into_inner();word(&mut out,events.len() as u32);out.extend(events);
    }assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&out).unwrap();
}
fn main() {run();}
