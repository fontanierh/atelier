//! Full pinned MotionHost push factories, per-activation lifecycle and publication.
#![allow(dead_code,unused_imports)]
mod physics;
mod graph_host;
mod graph_runtime;
mod skater_animation;
mod animation_pose;
mod camera;
mod difficulty;
mod grind_world;
mod input;
mod scoring_runtime;
mod skate_world;
mod animation;
mod crash_context;
mod tuning;
mod session_marker;
pub use physics::bridge;
use std::io::{Read,Write};
use skate_core::{animation::{output::attributes::{AnimationAttribute,AttributeName},playback::PlaybackContext,channel_playback::ChannelSettings,skeleton_input::name::encode},graph::{controller::{Host,Frame},intents::IntentMap},input::set_turning::Physical,riding::{push_behaviors::{PushState,PushFootFrame},push_animation::PushBlendParameters}};
use skate_data::{animation_banks::AnimationBanks,animation_metadata::AnimationMetadata,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::motion::{MotionHost,MotionPhysical};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn map(&mut self)->IntentMap {let mut m=IntentMap::new();for _ in 0..self.word() {let n=self.string();m.insert(&n,self.float());}m}
    fn state(&mut self)->PushState {PushState{out_factor:self.float(),current_push_dv:self.float(),current:PushBlendParameters{hstr_vel_b:self.float(),lstr_vel_b:self.float(),vel_e:self.float()},target:PushBlendParameters{hstr_vel_b:self.float(),lstr_vel_b:self.float(),vel_e:self.float()},continue_push:self.word()!=0}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn name(&mut self,n:AttributeName) {for v in n.0 {self.word(v);}}
    fn state(&mut self,s:Option<PushState>) {self.word(u32::from(s.is_some()));if let Some(s)=s {self.float(s.out_factor);self.float(s.current_push_dv);for v in [s.current.hstr_vel_b,s.current.lstr_vel_b,s.current.vel_e,s.target.hstr_vel_b,s.target.lstr_vel_b,s.target.vel_e] {self.float(v);}self.word(u32::from(s.continue_push));}}
    fn attribute(&mut self,a:&AnimationAttribute) {self.name(a.name);self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>{self.word(1);self.string("");},Err(e)=>{self.word(0);self.string(&e);}}}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let collections=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};let mut host=MotionHost::from_graph(&graph,&collections,metadata,context)?;
    host.animation.posture_bank_valid=true;host.animation.skater_animation_flags=Some(0x08020000);
    let channel_settings=ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.,blend_in:0.,hold_during_blend_in:false,blend_out:0.,hold_during_blend_out:false,use_attributes:true};
    for i in 0..5 {if !host.animation.new_channel(&format!("PushProbe{i}"),&format!("PUSH_OBSERVER_{i}"),channel_settings)? {return Err("Observer channel alias".into());}}
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());let count=r.word();out.word(count);
    for _ in 0..count {
        let id=r.word() as usize;let phase=r.word();let allocate=r.word()!=0;let mode=r.word();let physical_kind=r.word();let is_switch=r.word()!=0;let speed=r.float();let teleport=r.float();let dt=r.float();
        match mode {1=>{let z=PushBlendParameters{hstr_vel_b:0.,lstr_vel_b:0.,vel_e:0.};host.push_state=Some(PushState{out_factor:0.,current_push_dv:0.,current:z,target:z,continue_push:false});},2=>host.push_state=None,3=>host.push_state=Some(r.state()),_=>()};
        host.physical=if physical_kind==0 {None} else {let feet=if physical_kind==2 {Some(PushFootFrame{left_foot:r.vector(),right_foot:r.vector(),deck_position:r.vector(),deck_y:r.vector(),deck_z:r.vector(),skateboard_flipped:r.word()!=0})} else {None};Some(MotionPhysical{turning:Physical{field_32:0.,field_36:0.,field_52:0.,field_56:0.,field_60:0.,body_168:0.},stance:(false,false),forward_speed:speed,time_since_teleport:teleport,is_switch,foot_frame:feet})};
        host.riding.time_since_teleport=teleport;host.animation.motion_intents=r.map();host.animation.begin_graph_update();let frame=Frame{dt,current:None,last:None,state_times:vec![None]};host.errors.clear();
        if allocate {host.allocate(id,&frame);}match phase {0=>host.begin(id,[0;6],&frame),1=>host.update(id,[0;6],&frame),2=>host.end(id,[0;6],&frame),_=>return Err("Invalid phase".into())};
        out.string(&host.errors.join("|"));out.status(host.animation.apply_parameters());host.animation.advance(dt,0.);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());out.state(host.push_state);
        out.word(host.animation.tree_attributes().len() as u32);for a in host.animation.tree_attributes() {out.attribute(a);}
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
