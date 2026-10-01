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
use skate_core::{animation::{output::attributes::{AnimationAttribute,AttributeName},playback::{PlaybackContext,PlaybackRequest,PlaybackService,TransitionSettings},channel_playback::ChannelSettings,playback_parameters::{AttributeSink,SettableAttribute},skeleton_input::name::encode},graph::controller::{Host,Frame}};
use skate_data::{animation_banks::AnimationBanks,animation_metadata::AnimationMetadata,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::MotionHost,motion_gameplay_conditions::GameplayConditions,motion_runout::Observation};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn air(&mut self)->GameplayConditions {
        let remaining=self.float();let duration=self.float();let translation=self.vector();
        // Explicit authored fixture values for fields this operation does not read.
        GameplayConditions{state:0,wants_runout:false,physics_wiping:false,body_flipping:false,wants_wipeout:false,bumped:false,grabbing_object:false,retrieving_board:false,dropping_board:false,in_biped_air:false,hippy_hurdling:false,
            handplant_flags:0,handplant_time:0.,handplant_thresholds:[0.;3],footplant_active:false,footplant_duration:0.,footplant_contact_time:0.,time_to_skitch:0.,skitch_transition_time:0.,time_to_land:0.,time_to_land_valid:false,
            offboard_time_to_land:remaining,offboard_air_scalar_92:duration,offboard_air_translation:translation,offboard_landing_normal:[0.;4],offboard_committed_to_motion:false,offboard_obstacle_distance:0.,offboard_edge_distance:0.,
            offboard_trajectory_time:0.,offboard_trajectory_valid:false,reached_apex:false,can_land_on_board:false,landing_turning:false,grind_contact:false,wheel_contact:false,trucks_or_deck_contact:false,moving_object:false,tricks_blocked_on_stairs:false}
    }
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn name(&mut self,n:AttributeName) {for v in n.0 {self.word(v);}}
    fn attribute(&mut self,a:&AnimationAttribute) {self.name(a.name);self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>{self.word(1);self.string("");},Err(e)=>{self.word(0);self.string(&e);}}}
    fn scalar(&mut self,r:Result<f32,String>) {match r {Ok(v)=>{self.word(1);self.float(v);},Err(e)=>{self.word(0);self.string(&e);}}}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let collections=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};let mut host=MotionHost::from_graph(&graph,&collections,metadata,context)?;host.animation.skater_animation_flags=Some(0x08020000);host.animation.posture_bank_valid=true;
    let settings=ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.,blend_in:0.,hold_during_blend_in:false,blend_out:0.,hold_during_blend_out:false,use_attributes:true};
    for i in 0..7 {if !host.animation.new_channel(&format!("TimingProbe{i}"),&format!("TIMING_OBSERVER_{i}"),settings)? {return Err("Observer alias".into());}}
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());let count=r.word();out.word(count);
    for _ in 0..count {
        let id=r.word() as usize;let phase=r.word();let allocate=r.word()!=0;let play=r.word()!=0;let inject=r.word()!=0;let dt=r.float();host.offboard_cadence_phase=if r.word()!=0 {Some(r.float())} else {None};host.gameplay_conditions=if r.word()!=0 {Some(r.air())} else {None};
        host.runout_physical=if r.word()!=0 {Some(Observation{offboard_flag_331:r.word()!=0,offboard_velocity_128:r.vector(),reckoning_velocity_16:r.vector(),reckoning_up_96:r.vector(),skeleton_vector_0:r.vector(),animation_mirrored:r.word()!=0})} else {None};
        if play {if !host.animation.play(PlaybackRequest{animation:"TIMING_MAIN".into(),speed:1.,start_time:0.,transition:TransitionSettings{kind:1,seconds:0.,under:0,matching:0,use_channels_from_weights:false}})? {return Err("Play refused".into());}}
        host.animation.begin_graph_update();if inject {host.animation.set_attribute(SettableAttribute{name:encode(b"BipedStartAngle"),value:-123.,normalized:false,sequence_id:-1});host.animation.set_attribute(SettableAttribute{name:encode(b"BipedSpeed"),value:-1.,normalized:false,sequence_id:-1});}let frame=Frame{dt,current:None,last:None,state_times:vec![None]};host.errors.clear();if allocate {host.allocate(id,&frame);}match phase {0=>host.begin(id,[0;6],&frame),1=>host.update(id,[0;6],&frame),2=>host.end(id,[0;6],&frame),_=>return Err("Invalid phase".into())};
        out.string(&host.errors.join("|"));out.status(host.animation.apply_parameters());host.animation.advance(dt,host.animation_phase);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());out.float(host.animation_phase);out.scalar(host.animation.current_time());out.scalar(host.animation.current_length());
        out.word(host.animation.tree_attributes().len() as u32);for a in host.animation.tree_attributes() {out.attribute(a);}
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
