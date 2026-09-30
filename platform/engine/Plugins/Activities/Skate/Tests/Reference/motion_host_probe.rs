//! Original MotionHost/controller oracle. All production modules are staged verbatim.
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
use skate_core::{animation::{output::attributes::AnimationAttribute,playback::PlaybackContext,skeleton_input::name::encode},
    graph::{activation::ConditionHost,controller::Controller,intents::IntentMap,conditions::PhysicalStateInputs},
    input::set_turning::{Physical,SlideLatch},riding::push_behaviors::PushFootFrame};
use skate_data::{animation_banks::AnimationBanks,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::{MotionHost,MotionPhysical},motion_gameplay_conditions::GameplayConditions,
    outputs::{ActionGraphOutput,MotionGraphInput}};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn map(&mut self)->IntentMap {let mut m=IntentMap::new();for _ in 0..self.word() {let name=self.string();m.insert(&name,self.float());}m}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn optional(&mut self,v:Option<f32>) {self.word(u32::from(v.is_some()));if let Some(v)=v {self.float(v);}}
    fn map(&mut self,m:&IntentMap,names:&[String]) {self.word(m.len() as u32);for n in names {self.optional(m.get(n).copied());}}
    fn attribute(&mut self,a:&AnimationAttribute) {for w in a.name.0 {self.word(w);}self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>{self.word(1);self.string("");},Err(e)=>{self.word(0);self.string(&e);}}}
    fn scalar(&mut self,r:Result<f32,String>) {match r {Ok(v)=>{self.word(1);self.float(v);},Err(e)=>{self.word(0);self.string(&e);}}}
}
// This is an explicit fixture publication. The production containing Option
// stays None when no completed physics record was supplied on the wire.
fn gameplay(state:u32,dropping_board:bool)->GameplayConditions {
    GameplayConditions {state,wants_runout:false,physics_wiping:false,body_flipping:false,wants_wipeout:false,bumped:false,
        grabbing_object:false,retrieving_board:false,dropping_board,in_biped_air:false,hippy_hurdling:false,
        handplant_flags:0,handplant_time:0.,handplant_thresholds:[0.;3],footplant_active:false,footplant_duration:0.,
        footplant_contact_time:0.,time_to_skitch:0.,skitch_transition_time:0.,time_to_land:0.,time_to_land_valid:false,
        offboard_time_to_land:0.,offboard_air_scalar_92:0.,offboard_air_translation:[0.;4],offboard_landing_normal:[0.;4],
        offboard_committed_to_motion:false,offboard_obstacle_distance:0.,offboard_edge_distance:0.,offboard_trajectory_time:0.,
        offboard_trajectory_valid:false,reached_apex:false,can_land_on_board:false,landing_turning:false,grind_contact:false,
        wheel_contact:false,trucks_or_deck_contact:false,moving_object:false,tricks_blocked_on_stairs:false}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);
    let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;
    let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let collections=Collections::load(assets)?;let metadata=AnimationBanks::load(assets)?.metadata()?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};
    let mut host=MotionHost::from_graph(&graph,&collections,metadata,context)?;
    host.animation.set_hierarchy(&["LeftToeBase".into(),"RightToeBase".into()],&[1,0])?;
    host.animation.posture_bank_valid=true;host.animation.skater_animation_flags=Some(0x08020000);
    let mut controller=Controller::new(graph.binding.states.len());let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();
    let mut input=Input{data,at:0};let names:Vec<_>=(0..input.word()).map(|_|input.string()).collect();let steps=input.word();let mut out=Output(Vec::new());out.word(steps);
    for tick in 0..steps {
        let ending=input.word()!=0;let dt=input.float();let action=input.map();let motion=input.map();
        host.animation.skater_animation_flags=Some(input.word());host.playback_context.is_mirrored=Some(input.word()!=0);host.playback_context.is_switch=Some(input.word()!=0);
        host.condition_inputs.physical_state=Some(PhysicalStateInputs{category:input.word(),grinding:false,grind_name:String::new()});
        let present=input.word()!=0;let state=input.word();let dropping=input.word()!=0;host.gameplay_conditions=present.then(||gameplay(state,dropping));
        let feet=PushFootFrame{left_foot:input.vector(),right_foot:input.vector(),deck_position:input.vector(),deck_y:input.vector(),deck_z:input.vector(),skateboard_flipped:input.word()!=0};
        host.physical=Some(MotionPhysical{turning:Physical{field_32:0.,field_36:0.,field_52:0.,field_56:0.,field_60:0.,body_168:0.},stance:(false,false),forward_speed:0.,time_since_teleport:0.,is_switch:false,foot_frame:Some(feet)});
        host.slide_latch=unsafe{std::mem::transmute::<[u32;5],SlideLatch>(std::array::from_fn(|_|input.word()))};host.hold_fakie=input.word()!=0;
        let push=host.push_state.as_mut().unwrap();push.out_factor=input.float();push.continue_push=input.word()!=0;
        host.time_tags=Some(std::collections::BTreeMap::from([("probe".into(),input.float())]));
        host.animation.begin_graph_update();host.accept_action_graph(MotionGraphInput{tick:tick as u64,action:ActionGraphOutput::from_host(tick as u64,&action,&motion,&[])});
        if ending {controller.end_all_behaviors(&mut host);} else {controller.update(&graph.runtime.program,dt,&mut host);}
        out.word(graph.runtime.operations.conditions.len() as u32);for id in 0..graph.runtime.operations.conditions.len() {out.word(host.condition_activation(id,&controller.frame));}
        out.string(&host.errors.join("|"));out.status(host.animation.apply_parameters());host.animation.advance(dt,host.animation_phase);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());
        let frame=&controller.frame;out.float(frame.dt);out.word(frame.current.map_or(0xffffffff,|v|v as u32));out.word(frame.last.map_or(0xffffffff,|v|v as u32));
        out.word(frame.state_times.len() as u32);for &time in &frame.state_times {out.optional(time);}
        out.word(controller.active.len() as u32);for a in &controller.active {out.word(a.behavior as u32);out.word(a.instance);}
        out.map(&host.animation.motion_intents,&names);out.map(&host.animation.filtered_intents,&names);
        for value in [host.flags.anticipating,host.flags.landing,host.flags.manualing,host.flags.doing_trick,host.flags.tricks_allowed,host.riding.dark,host.is_power_sliding,host.applying_body_tilt,host.hand_services.keep_shove_channels] {out.word(u32::from(value));}
        for value in [host.riding.time_since_teleport,host.riding.time_since_kickturn,host.riding.manual_out_timer,host.riding.last_good_landing_velocity] {out.float(value);}
        for v in host.hand_services.busy_hands {out.word(v);}for v in unsafe{std::mem::transmute::<SlideLatch,[u32;5]>(host.slide_latch)} {out.word(v);}
        out.word(u32::from(host.animation.grab_type.is_some()));if let Some(v)=host.animation.grab_type {out.word(v as u32);}
        out.word(host.animation.skater_animation_flags.unwrap());out.word(host.animation.relative_stance);out.word(u32::from(host.animation.reset_action_intents));
        out.word(host.animation.motion_attributes.len() as u32);for a in &host.animation.motion_attributes {for w in a.name.0 {out.word(w);}out.float(a.value);}
        out.word(host.animation.tree_attributes().len() as u32);for a in host.animation.tree_attributes() {out.attribute(a);}
        let p=host.animation.property();out.word(u32::from(p.crossed_end));out.float(p.overshoot);out.float(p.remaining_before_wrap);
        out.scalar(host.animation.current_time());out.scalar(host.animation.current_length());out.word(u32::from(host.animation.in_transition()));
    }
    assert_eq!(input.at,input.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
