//! Full untouched MotionHost ControlAirLegExtension/BodySpin lifecycle and consumed outputs.
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
use skate_core::{animation::{output::attributes::{AnimationAttribute,MotionGraphAttribute},
    playback::{PlaybackContext,PlaybackRequest,PlaybackService},channel_playback::ChannelSettings,
    playback_tree::{Evaluation,PoseCommand},skeleton_input::name::encode,crouching,body_tilt,riding_fakie},
    graph::{controller::{Frame,Host},intents::IntentMap},input::set_turning};
use skate_data::{animation_banks::AnimationBanks,animation_metadata::AnimationMetadata,collections::Collections,
    state_graph::{StateGraph,binding::Binding}};
use graph_host::motion::{MotionHost,MotionPhysical};
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let w=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;w}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn boolean(&mut self)->bool {self.word()!=0}
    fn string(&mut self)->String {let n=self.word() as usize;let s=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;s}
    fn vector(&mut self)->[f32;4] {core::array::from_fn(|_|self.float())}
    fn map(&mut self)->IntentMap {let mut out=IntentMap::new();for _ in 0..self.word() {let name=self.string();out.insert(&name,self.float());}out}
    fn crouch(&mut self)->crouching::Physical {crouching::Physical{body_84:self.float(),body_164:self.float(),body_188:self.float(),force_516:self.float(),ground_force_520:self.float(),minimum_crouch_528:self.float(),deck_angle_532:self.float(),animation_height_72:self.float()}}
    fn tilt(&mut self)->body_tilt::Physical {body_tilt::Physical{lateral_tilt:self.float(),body_spin_speed:self.float(),filtered_category:self.word()}}
    fn fakie(&mut self)->riding_fakie::Physical {riding_fakie::Physical{category:self.word(),grind_state:self.word(),doing_trick:self.boolean(),board_axis:self.vector(),deck_velocity:self.vector(),external_velocity:self.vector(),ground_projected_speed:self.float()}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,w:u32) {self.0.extend(w.to_le_bytes());}
    fn float(&mut self,f:f32) {self.word(f.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>self.word(1),Err(e)=>{self.word(0);self.string(&e);}}}
    fn attribute(&mut self,a:&AnimationAttribute) {for w in a.name.0 {self.word(w);}self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for w in a.payload.0 {self.word(u32::from(w.is_some()));if let Some(w)=w {self.word(w);}}}
    fn commands(&mut self,cs:&[PoseCommand]) {
        self.word(cs.len() as u32);for c in cs {match c {
            PoseCommand::Clip{name,previous_time,time,loops}=>{self.word(0);self.string(name);self.float(*previous_time);self.float(*time);self.word(*loops);},
            PoseCommand::Blend{weight}=>{self.word(1);self.float(*weight);},
            PoseCommand::WeightedBlend{weights}=>{self.word(2);self.word(weights.len() as u32);for w in weights {self.float(*w);}},
            PoseCommand::ChannelBlend{weight,use_channels_from_weights}=>{self.word(3);self.float(*weight);self.word(u32::from(*use_channels_from_weights));},
            PoseCommand::Pose{name}=>{self.word(4);self.string(name);},PoseCommand::Add{motion_is_a}=>{self.word(5);self.word(u32::from(*motion_is_a));},PoseCommand::Mirror{trajectory_mode}=>{self.word(6);self.word(*trajectory_mode);},
        }}
    }
}
fn gameplay(state:u32)->graph_host::motion_gameplay_conditions::GameplayConditions {
    // Only state is consumed by BodySpin. All other complete-record fields are
    // explicit unused fixture sentinels, never substitute callbacks/producers.
    graph_host::motion_gameplay_conditions::GameplayConditions{state,wants_runout:false,physics_wiping:false,body_flipping:false,wants_wipeout:false,bumped:false,grabbing_object:false,retrieving_board:false,dropping_board:false,in_biped_air:false,hippy_hurdling:false,handplant_flags:0,handplant_time:0.,handplant_thresholds:[0.;3],footplant_active:false,footplant_duration:0.,footplant_contact_time:0.,time_to_skitch:0.,skitch_transition_time:0.,time_to_land:0.,time_to_land_valid:false,offboard_time_to_land:0.,offboard_air_scalar_92:0.,offboard_air_translation:[0.;4],offboard_landing_normal:[0.;4],offboard_committed_to_motion:false,offboard_obstacle_distance:0.,offboard_edge_distance:0.,offboard_trajectory_time:0.,offboard_trajectory_valid:false,reached_apex:false,can_land_on_board:false,landing_turning:false,grind_contact:false,wheel_contact:false,trucks_or_deck_contact:false,moving_object:false,tricks_blocked_on_stairs:false}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let data=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};
    let mut host=MotionHost::from_graph(&graph,&data,metadata,context)?;host.animation.posture_bank_valid=true;host.animation.skater_animation_flags=Some(0x08020000);
    host.animation.play(PlaybackRequest{animation:"AIR_INITIAL_NONE".into(),speed:1.,start_time:0.,transition:skate_core::animation::playback::TransitionSettings{kind:1,seconds:0.,under:0,matching:0,use_channels_from_weights:false}})?;host.animation.refresh_tree_attributes()?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut r=Input{data:bytes,at:0};let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();
    for i in 0..names.len() {host.animation.new_channel(&format!("OBS{i}"),&format!("OBS_TREE{i}"),ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.,blend_in:0.,hold_during_blend_in:false,blend_out:0.,hold_during_blend_out:false,use_attributes:false})?;}
    let rows=r.word();let mut out=Output(Vec::new());out.word(rows);
    for _ in 0..rows {
        let id=r.word() as usize;let phase=r.word();let allocate=r.boolean();let cache=r.word();let dt=r.float();let mask=r.word();let category=r.word();let state=r.word();host.flags.doing_trick=r.boolean();host.hand_services.busy_hands=[r.word(),r.word()];let mirrored=r.boolean();
        let air=skate_core::animation::air_leg_extension::Physical{com_velocity:r.vector(),com_position:r.vector(),system_up:r.vector(),right_toe:r.vector(),left_toe:r.vector(),animation_height:r.float(),offboard_316:r.boolean(),remaining_air_time:r.float()};
        let preland=graph_host::motion_spin::PrelandingPhysical{air_444:r.boolean(),air_normal_144_y:r.float(),animation_16_x:r.float(),com_velocity_y:r.float(),offboard_316:r.boolean(),offboard_319:r.boolean(),offboard_time_32:r.float(),air_437:r.boolean(),air_normal_36:r.float(),air_remaining_184:r.float(),animation_height_72:r.float()};
        let map=r.map();
        if cache!=0 {let clips=["AIR_INITIAL_NONE","AIR_INITIAL_FLOAT","AIR_INITIAL_VECTOR","AIR_INITIAL_FULL_VECTOR"];host.animation.play(PlaybackRequest{animation:clips[((cache-1) as usize)%clips.len()].into(),speed:1.,start_time:0.,transition:skate_core::animation::playback::TransitionSettings{kind:1,seconds:0.,under:0,matching:0,use_channels_from_weights:false}})?;host.animation.refresh_tree_attributes()?;}
        host.animation.begin_graph_update();host.animation.motion_intents=map;host.air_leg_physical=(mask&1!=0).then_some(air);host.prelanding_physical=(mask&2!=0).then_some(preland);
        host.condition_inputs.physical_state=(mask&4!=0).then_some(skate_core::graph::conditions::PhysicalStateInputs{category,grinding:false,grind_name:String::new()});host.gameplay_conditions=(mask&8!=0).then_some(gameplay(state));host.playback_context.is_mirrored=(mask&16!=0).then_some(mirrored);
        let frame=Frame{dt,current:Some(0),last:None,state_times:vec![Some(0.)]};host.errors.clear();if allocate {host.allocate(id,&frame);}let context=host.context();
        match phase {0=>host.begin(id,context,&frame),1=>host.update(id,context,&frame),2=>host.end(id,context,&frame),_=>unreachable!()};out.status(if host.errors.is_empty() {Ok(())}else{Err(host.errors.join("|"))});
        out.status(host.animation.apply_parameters());host.animation.advance(dt,0.);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());
        for name in &names {let mut a=MotionGraphAttribute{name:encode(name.as_bytes()),value:0.}.to_animation();let result=host.animation.channels.query_attribute(a.name,15,&mut a);let found=result.as_ref().copied().unwrap_or(false);out.status(result.map(|_|()));out.word(u32::from(found));out.attribute(&a);}
        for name in ["IA_BODYSPIN_OLLIE_FS_0_N","IA_BODYSPIN_OLLIE_BS_0_N"] {out.word(u32::from(host.animation.channels.has(name)));out.float(host.animation.channels.elapsed(name));out.float(host.animation.channels.remaining(name));out.word(u32::from(host.animation.channels.in_transition(name)));}
        match host.animation.evaluate_pose(Evaluation{cull_threshold:0.01,update_history:true}) {Ok(cs)=>{out.word(1);out.commands(&cs);},Err(e)=>out.status(Err(e))};
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
