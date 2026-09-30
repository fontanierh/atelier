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
use skate_core::{animation::{output::attributes::{AnimationAttribute,AttributeName},playback::{PlaybackContext,PlaybackRequest,PlaybackService,TransitionSettings},channel_playback::ChannelSettings,skeleton_input::name::encode,playback_tree::{Evaluation,PoseCommand}},graph::{controller::{Host,Frame},intents::IntentMap,conditions::PhysicalStateInputs},animation::crouching::Physical};
use skate_data::{animation_banks::AnimationBanks,animation_metadata::AnimationMetadata,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::MotionHost,motion_native::GesturePhysical,motion_shove::ShovePhysical};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn map(&mut self)->IntentMap {let mut m=IntentMap::new();for _ in 0..self.word() {let n=self.string();m.insert(&n,self.float());}m}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn name(&mut self,n:AttributeName) {for v in n.0 {self.word(v);}}
    fn attribute(&mut self,a:&AnimationAttribute) {self.name(a.name);self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>{self.word(1);self.string("");},Err(e)=>{self.word(0);self.string(&e);}}}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let collections=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};let mut host=MotionHost::from_graph(&graph,&collections,metadata,context)?;
    host.animation.posture_bank_valid=true;host.animation.skater_animation_flags=Some(0x08020000);
    let settings=ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.,blend_in:0.,hold_during_blend_in:false,blend_out:0.,hold_during_blend_out:false,use_attributes:false};let observer=ChannelSettings{use_attributes:true,..settings};
    if !host.animation.play(PlaybackRequest{animation:"GESTURE_HEIGHT_OBSERVER".into(),speed:1.,start_time:0.,transition:TransitionSettings{kind:1,seconds:0.,under:0,matching:0,use_channels_from_weights:false}})? || !host.animation.new_channel("GestureAngleProbe","GESTURE_ANGLE_OBSERVER",observer)? {return Err("Fixture refused".into());}
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());let count=r.word();out.word(count);
    for _ in 0..count {
        let id=r.word() as usize;let phase=r.word();let allocate=r.word()!=0;let clear=r.word()!=0;let seed=r.word();let available=r.word();let hands=[r.word(),r.word()];let keep=r.word()!=0;let category=r.word();let board=r.word()!=0;let ground=r.word()!=0;let offboard=r.word()!=0;let suppress=r.word()!=0;let bypass=r.word()!=0;
        let selections=std::array::from_fn(|_|r.word());let interaction=r.word()!=0;let biped=r.word()!=0;let board_ground=r.word()!=0;let mirror=r.word()!=0;let height=r.float();let dt=r.float();let direction=r.vector();host.animation.motion_intents=r.map();host.animation.begin_graph_update();
        host.playback_context.board_available=(available&4!=0).then_some(board);host.playback_context.is_mirrored=(available&32!=0).then_some(mirror);
        host.gesture_physical=(available&1!=0).then_some(GesturePhysical{ground321:ground,state_offboard75:offboard,selections:(available&64!=0).then_some(selections),suppress_up:suppress,force_brake_bypass:bypass});
        host.condition_inputs.physical_state=(available&2!=0).then_some(PhysicalStateInputs{category,grinding:false,grind_name:String::new()});
        host.crouching_physical=(available&8!=0).then_some(Physical{body_84:0.,body_164:0.,body_188:0.,force_516:0.,ground_force_520:0.,minimum_crouch_528:0.,deck_angle_532:0.,animation_height_72:height});
        host.shove_physical=(available&16!=0).then_some(ShovePhysical{interaction_trigger:interaction,direction,in_biped_category:biped,board_on_ground:board_ground,animation_height:height});host.hand_services.busy_hands=hands;host.hand_services.keep_shove_channels=keep;
        if clear {host.animation.channels.reset_from_stock();if !host.animation.new_channel("GestureAngleProbe","GESTURE_ANGLE_OBSERVER",observer)? {return Err("Observer refused".into());}}
        if seed!=0 {host.animation.new_channel(["RetrieveBoard","WipeoutPushOff","Shove"][(seed-1) as usize],"GESTURE_EMPTY",settings)?;}
        let frame=Frame{dt,current:None,last:None,state_times:vec![None]};host.errors.clear();if allocate {host.allocate(id,&frame);}match phase {0=>host.begin(id,[0;6],&frame),1=>host.update(id,[0;6],&frame),2=>host.end(id,[0;6],&frame),_=>return Err("Invalid phase".into())};
        out.string(&host.errors.join("|"));out.status(host.animation.apply_parameters());host.animation.advance(dt,0.);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());let pose=host.animation.evaluate_pose(Evaluation{cull_threshold:0.,update_history:false});let clips=pose.as_ref().ok().map_or(Vec::new(),|commands|commands.iter().filter_map(|c|if let PoseCommand::Clip{name,..}=c {Some(name.clone())} else {None}).collect::<Vec<_>>());out.status(pose.map(|_|()));
        out.word(u32::from(host.gesture_publication.is_some()));if let Some(p)=host.gesture_publication {out.word(p.gesture);out.word(u32::from(p.down));}
        for c in ["GestureBoth","GestureRight","GestureLeft","SkitchAntic","Shove","RetrieveBoard","WipeoutPushOff"] {out.word(u32::from(host.animation.channels.has(c)));out.float(host.animation.channels.remaining(c));out.float(host.animation.channels.elapsed(c));out.word(u32::from(host.animation.channels.in_transition(c)));}
        out.word(host.animation.tree_attributes().len() as u32);for a in host.animation.tree_attributes() {out.attribute(a);}out.word(clips.len() as u32);for c in clips {out.string(&c);}
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
