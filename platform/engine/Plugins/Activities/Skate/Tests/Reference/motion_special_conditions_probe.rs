//! Original full MotionHost evaluates registered grind/landing/wipeout predicates.
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
use skate_core::{animation::{playback::PlaybackContext,skeleton_input::name::encode},graph::{activation::ConditionHost,controller::Frame}};
use skate_data::{animation_banks::AnimationBanks,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::MotionHost,motion_grind,motion_landing,motion_wipeout,motion_spin};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn boolean(&mut self)->bool {self.word()!=0}
}
struct Output(Vec<u8>);
impl Output {fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;
    let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
    let collections=Collections::load(assets)?;let metadata=AnimationBanks::load(assets)?.metadata()?;
    let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};
    let mut host=MotionHost::from_graph(&graph,&collections,metadata,context)?;
    let mut data=Vec::new();std::io::stdin().read_to_end(&mut data).unwrap();let mut r=Input{data,at:0};let mut out=Output(Vec::new());let frames=r.word();out.word(frames);out.word(graph.runtime.operations.conditions.len() as u32);
    let frame=Frame{dt:0.,current:None,last:None,state_times:vec![None]};
    for _ in 0..frames {
        let mask=r.word();
        let g=motion_grind::conditions::Physical{filtered_grinding_80:r.boolean(),blunting_136:r.word(),approach_268:r.word(),trick_out_240:r.word(),air_grind_443:r.boolean(),air_time_184:r.float(),dropping_in_324:r.boolean()};
        let l=motion_landing::Physical{height:r.float(),spin:r.float(),kind:r.word(),last_good_landing_velocity:r.float()};
        let over_599=r.boolean();let collision_time_144=r.float();let no_support_time_548=r.float();let profile_148=r.word();let below_surface_82=r.boolean();let orientation=r.boolean();let y=r.float();let hips_right_angle_496=r.float();let hips_up_angle_500=r.float();
        let w=motion_wipeout::Physical{over_599,collision_time_144,no_support_time_548,profile_148,below_surface_82,orientation_y:orientation.then_some(y),hips_right_angle_496,hips_up_angle_500};
        let p=motion_spin::PrelandingPhysical{air_444:r.boolean(),air_normal_144_y:r.float(),animation_16_x:r.float(),com_velocity_y:r.float(),offboard_316:r.boolean(),offboard_319:r.boolean(),offboard_time_32:r.float(),air_437:r.boolean(),air_normal_36:r.float(),air_remaining_184:r.float(),animation_height_72:r.float()};
        host.grind_conditions=(mask&1!=0).then_some(g);host.landing_physical=(mask&2!=0).then_some(l);host.wipeout_physical=(mask&4!=0).then_some(w);host.prelanding_physical=(mask&8!=0).then_some(p);
        for id in 0..graph.runtime.operations.conditions.len() {host.errors.clear();out.word(host.condition_activation(id,&frame));out.string(&host.errors.join("|"));}
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
