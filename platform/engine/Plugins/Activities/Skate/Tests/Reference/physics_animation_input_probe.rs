//! Entire actual host AnimationInput plus unchanged Skeleton attribute modules.
use std::io::{Read,Write};
use skate_core::{animation::{output::attributes::{AnimationAttribute,AttributeName,AttributePayload},skeleton_input::{scalar_attributes::{ScalarAttributeInputs,AnimationControlOutput},extended_attributes::ExtendedAttributes,attribute_finalization::{FinalizationInput,JumpAttributeState},contact_events::ContactEventState}},input::controller::ActionMap};
mod difficulty {pub const NATIVE_MODES:[&str;5]=["easy","normal","hardcore","motorized","test"];}
mod original_host {
// ORIGINAL_HOST
pub(super) fn snapshot(out:&mut crate::Output,s:&AnimationInput,actions:&crate::Actions) {
    let mut row=crate::Output(Vec::new());crate::observe_ScalarAttributeInputs(&mut row,&s.fields);crate::observe_ExtendedAttributes(&mut row,&s.extra);crate::observe_ContactEventState(&mut row,&s.contacts);crate::observe_AnimationControlOutput(&mut row,&s.output);crate::observe_JumpAttributeState(&mut row,&s.cached_jump);crate::observe_FinalizationInput(&mut row,&s.settings);
    for value in s.height_overrides {row.word(value as u32);}row.word(s.right_toe as u32);row.word(s.bone_names.len() as u32);for name in &s.bone_names {row.words(name.0);}row.word(actions.calls.len() as u32);for action in &actions.calls {row.word(*action);}out.block(row);
}
}
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let b=&self.bytes[self.at..self.at+4];self.at+=4;u32::from_le_bytes(b.try_into().unwrap())}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn floats<const N:usize>(&mut self)->[f32;N] {std::array::from_fn(|_|self.float())}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let s=std::str::from_utf8(&self.bytes[self.at..self.at+n]).unwrap().into();self.at+=n;s}
    fn attribute(&mut self)->AnimationAttribute {AnimationAttribute{name:AttributeName(self.words()),kind:self.word() as u8,status:self.word() as u8,sequence_id:self.word() as i32,begin_time:self.float(),end_time:self.float(),payload:AttributePayload(std::array::from_fn(|_|if self.word()!=0 {Some(self.word())} else {None}))}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,w:u32) {self.0.extend(w.to_le_bytes());}
    fn float(&mut self,f:f32) {self.word(f.to_bits());}
    fn words<const N:usize>(&mut self,w:[u32;N]) {for v in w {self.word(v);}}
    fn floats<const N:usize>(&mut self,w:[f32;N]) {for v in w {self.float(v);}}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn block(&mut self,s:Self) {self.word((s.0.len()/4) as u32);self.0.extend(s.0);}
}
// GENERATED_PROTOCOL
#[derive(Default)]
struct Actions {values:[f32;18],calls:Vec<u32>}
impl ActionMap for Actions {fn value(&mut self,a:u32)->f32 {self.calls.push(a);self.values[(a-64) as usize]}fn state(&mut self,a:u32)->u8 {(self.value(a)!=0.0) as u8}}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[2]))?;let banks=skate_data::animation_banks::AnimationBanks::load(std::path::Path::new(&args[1]))?;let mut frames=skate_data::animation_frames::AnimationFrames::from_banks(&banks)?;let names=frames.bone_names.clone();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{bytes,at:0};let programs=i.word();let mut out=Output(Vec::new());
    for p in 0..programs {
        frames.bone_names=names.clone();match i.word() {1=>for name in &mut frames.bone_names {name.make_ascii_uppercase();},2=>for name in &mut frames.bone_names {if name.eq_ignore_ascii_case("RightToeBase") {*name="MissingRightToe".into();}},3=>frames.bone_names[0]="RightToeBase".into(),_=>{}}
        let mode=i.string();let load=original_host::AnimationInput::load(&data,&frames,&mode);out.word(p);out.word(load.is_ok() as u32);out.string(load.as_ref().err().map_or("",String::as_str));let commands=i.word();let mut s=match load {Ok(s)=>s,Err(_)=>{assert_eq!(commands,0);continue}};let mut actions=Actions::default();original_host::snapshot(&mut out,&s,&actions);
        for c in 0..commands {
            actions.calls.clear();let opcode=i.word();let result=match opcode {
                0=>{s.fields=read_ScalarAttributeInputs(&mut i);s.extra=read_ExtendedAttributes(&mut i);s.contacts=read_ContactEventState(&mut i);s.output=read_AnimationControlOutput(&mut i);Ok(())},
                1=>{s.reset_processed();Ok(())},2=>{s.finish_output_publication();Ok(())},3=>s.select_physics_mode(i.word()),
                4=>{let n=i.word();let attrs:Vec<_>=(0..n).map(|_|i.attribute()).collect();let n=i.word();let hierarchy:Vec<_>=(0..n).map(|_|std::array::from_fn(|_|i.floats::<4>())).collect();let dt=i.float();let flags=i.word();let impulse=i.word()!=0;actions.values=i.floats();s.process(&attrs,&hierarchy,dt,flags,impulse,&mut actions)},
                _=>return Err("Invalid animation input operation".into())
            };out.word(p);out.word(c);out.word(opcode);out.word(result.is_ok() as u32);out.string(result.as_ref().err().map_or("",String::as_str));original_host::snapshot(&mut out,&s,&actions);
        }
    }
    assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
