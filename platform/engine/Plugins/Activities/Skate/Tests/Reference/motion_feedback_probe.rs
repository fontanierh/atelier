//! Unchanged original MotionHost factories and ordered behavior lifecycle.
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
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let data=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};
    let mut host=MotionHost::from_graph(&graph,&data,metadata,context)?;host.animation.set_hierarchy(&["LeftToeBase".into(),"RightToeBase".into()],&[1,0])?;host.animation.posture_bank_valid=true;host.animation.skater_animation_flags=Some(0x08020000);
    host.animation.play(PlaybackRequest{animation:"R_STAND_IDLE2_N_0_CYC".into(),speed:1.0,start_time:0.0,transition:skate_core::animation::playback::TransitionSettings{kind:1,seconds:0.0,under:0,matching:0,use_channels_from_weights:false}})?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut r=Input{data:bytes,at:0};let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();
    for i in 0..names.len() {host.animation.new_channel(&format!("OBS{i}"),&format!("OBS_TREE{i}"),ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.0,blend_in:0.0,hold_during_blend_in:false,blend_out:0.0,hold_during_blend_out:false,use_attributes:false})?;}
    let steps=r.word();let mut out=Output(Vec::new());out.word(steps);let mut frame=Frame{dt:0.0,current:Some(0),last:None,state_times:vec![Some(0.0)]};
    for _ in 0..steps {
        frame.dt=r.float();let intents=r.map();let mask=r.word();let flags=r.word();let mirrored=r.boolean();host.flags.doing_trick=r.boolean();host.is_power_sliding=r.boolean();host.applying_body_tilt=r.boolean();host.slide_latch=unsafe{core::mem::transmute::<[u32;5],set_turning::SlideLatch>(core::array::from_fn(|_|r.word()))};
        let turning=set_turning::Physical{field_32:r.float(),field_36:r.float(),field_52:r.float(),field_56:r.float(),field_60:r.float(),body_168:r.float()};let crouch=r.crouch();let tilt=r.tilt();let fakie=r.fakie();let pump=r.float();let deck=[r.float(),r.float()];
        // Only turning is consumed from this completed record in the tested
        // leaves. Other source fields are explicit unused fixture sentinels.
        host.physical=(mask&1!=0).then_some(MotionPhysical{turning,stance:(true,false),forward_speed:0.731,time_since_teleport:0.317,is_switch:true,foot_frame:None});
        host.crouching_physical=(mask&2!=0).then_some(crouch);host.body_tilt_physical=(mask&4!=0).then_some(tilt);host.fakie_physical=(mask&8!=0).then_some(fakie);host.pumping_acceleration=(mask&16!=0).then_some(pump);host.deck_yaw_pitch=(mask&32!=0).then_some(deck);host.playback_context.is_mirrored=(mask&64!=0).then_some(mirrored);host.animation.skater_animation_flags=(mask&128!=0).then_some(flags);
        host.animation.begin_graph_update();host.animation.motion_intents=intents;let calls=r.word();out.word(calls);
        for _ in 0..calls {
            let id=r.word() as usize;let phase=r.word();host.errors.clear();let context=host.context();
            match phase {0=>{host.allocate(id,&frame);host.begin(id,context,&frame);},1=>host.update(id,context,&frame),2=>host.end(id,context,&frame),_=>unreachable!()};
            out.status(if host.errors.is_empty() {Ok(())}else{Err(host.errors.join("|"))});
        }
        out.word(u32::from(host.allow_pumping));out.word(u32::from(host.animation.skater_animation_flags.is_some()));if let Some(w)=host.animation.skater_animation_flags {out.word(w);}for w in unsafe{core::mem::transmute::<set_turning::SlideLatch,[u32;5]>(host.slide_latch)} {out.word(w);}
        out.word(host.animation.motion_attributes.len() as u32);for a in &host.animation.motion_attributes {for w in a.name.0 {out.word(w);}out.float(a.value);}
        out.status(host.animation.apply_parameters());host.animation.advance(frame.dt,0.137);out.status(Ok(()));out.status(host.animation.refresh_tree_attributes());
        for name in &names {let mut a=MotionGraphAttribute{name:encode(name.as_bytes()),value:0.0}.to_animation();let result=host.animation.channels.query_attribute(a.name,15,&mut a);let found=result.as_ref().copied().unwrap_or(false);out.status(result.map(|_|()));out.word(u32::from(found));out.attribute(&a);}
        for name in ["PUMP0","PUMP1","PUMP2","PUMP3","PUMP4"] {out.word(u32::from(host.animation.channels.has(name)));out.float(host.animation.channels.elapsed(name));out.float(host.animation.channels.remaining(name));out.word(u32::from(host.animation.channels.in_transition(name)));}
        out.word(host.animation.tree_attributes().len() as u32);for a in host.animation.tree_attributes() {out.attribute(a);}let p=host.animation.property();out.word(u32::from(p.crossed_end));out.float(p.overshoot);out.float(p.remaining_before_wrap);
        match host.animation.evaluate_pose(Evaluation{cull_threshold:0.01,update_history:true}) {Ok(cs)=>{out.word(1);out.commands(&cs);},Err(e)=>out.status(Err(e))};
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
