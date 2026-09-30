//! Full pinned MotionHost factories and phase dispatch; no surrogate outputs.
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
use skate_core::{animation::{output::attributes::{AnimationAttribute,AttributeName},playback::{PlaybackContext,PlaybackRequest,PlaybackService,TransitionSettings},channel_playback::ChannelSettings,skeleton_input::name::encode},graph::{controller::{Host,Frame},intents::IntentMap}};
use skate_data::{animation_banks::AnimationBanks,animation_metadata::AnimationMetadata,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::MotionHost,motion_native::ScorePacket};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn map(&mut self)->IntentMap {let mut m=IntentMap::new();for _ in 0..self.word() {let name=self.string();m.insert(&name,self.float());}m}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn name(&mut self,n:AttributeName) {for w in n.0 {self.word(w);}}
    fn optional_name(&mut self,n:Option<AttributeName>) {self.word(u32::from(n.is_some()));if let Some(n)=n {self.name(n);}}
    fn vector(&mut self,v:Option<(AttributeName,[f32;2])>) {self.word(u32::from(v.is_some()));if let Some((n,v))=v {self.name(n);for f in v {self.float(f);}}}
    fn attribute(&mut self,a:&AnimationAttribute) {self.name(a.name);self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>{self.word(1);self.string("");},Err(e)=>{self.word(0);self.string(&e);}}}
    fn scalar(&mut self,r:Result<f32,String>) {match r {Ok(v)=>{self.word(1);self.float(v);},Err(e)=>{self.word(0);self.string(&e);}}}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let collections=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};let mut host=MotionHost::from_graph(&graph,&collections,metadata,context)?;
    host.animation.posture_bank_valid=true;host.animation.skater_animation_flags=Some(0x08020000);
    let channel_settings=ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.,blend_in:0.,hold_during_blend_in:false,blend_out:0.,hold_during_blend_out:false,use_attributes:true};
    host.animation.new_channel("ProbeX","PROBE_TWEAK_X",channel_settings)?;host.animation.new_channel("ProbeY","PROBE_TWEAK_Y",channel_settings)?;
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());let commands=r.word();out.word(commands);
    for _ in 0..commands {
        let id=r.word() as usize;let phase=r.word();let clip=r.word();let mirror=r.word();let reset_score=r.word()!=0;let channel_mask=r.word();let dt=r.float();
        host.animation.motion_intents=r.map();host.animation.filtered_intents=r.map();host.playback_context.is_mirrored=(mirror!=0).then_some(mirror==2);if reset_score {host.score_packet=ScorePacket::default();}
        host.animation.begin_graph_update();
        if clip!=0 {
            let played=host.animation.play(PlaybackRequest{animation:if clip==1 {"PROBE_EMPTY"} else {"PROBE_HEIGHT"}.into(),speed:1.,start_time:0.,transition:TransitionSettings{kind:1,seconds:0.,under:0,matching:0,use_channels_from_weights:false}})?;
            if !played {return Err("Fixture play refused".into());}host.animation.refresh_tree_attributes()?;
        }
        for (i,n) in ["SKCH_2H_SHIMMY_LEFT_CHANNEL","SKCH_2H_SHIMMY_RIGHT_CHANNEL"].into_iter().enumerate() {if channel_mask&(1<<i)!=0 {host.animation.new_channel(n,"PROBE_EMPTY",channel_settings)?;}}
        let frame=Frame{dt,current:None,last:None,state_times:vec![None]};host.errors.clear();
        match phase {0=>{host.allocate(id,&frame);host.begin(id,[0;6],&frame);},1=>host.update(id,[0;6],&frame),2=>host.end(id,[0;6],&frame),_=>return Err("Invalid phase".into())};
        out.string(&host.errors.join("|"));out.status(host.animation.apply_parameters());host.animation.advance(dt,0.);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());
        out.vector(host.score_packet.handplant);out.vector(host.score_packet.grab);out.optional_name(host.score_packet.trick_names.first);out.optional_name(host.score_packet.trick_names.second);
        out.word(u32::from(host.score_packet.name.is_some()));if let Some(n)=host.score_packet.name {out.word(n);}out.word(host.score_packet.flags);out.word(u32::from(host.moving_objects.active()));
        out.word(host.animation.construction_values.len() as u32);for &(n,v) in &host.animation.construction_values {out.name(n);out.name(v);}
        out.word(host.animation.motion_attributes.len() as u32);for a in &host.animation.motion_attributes {out.name(a.name);out.float(a.value);}
        out.word(host.animation.tree_attributes().len() as u32);for a in host.animation.tree_attributes() {out.attribute(a);}
        for channel in ["ProbeX","ProbeY","SKCH_2H_SHIMMY_LEFT_CHANNEL","SKCH_2H_SHIMMY_RIGHT_CHANNEL"] {out.word(u32::from(host.animation.channels.has(channel)));out.float(host.animation.channels.remaining(channel));out.float(host.animation.channels.elapsed(channel));out.word(u32::from(host.animation.channels.in_transition(channel)));}
        out.scalar(host.animation.current_time());out.scalar(host.animation.current_length());
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
