//! Unchanged full original host evaluates actual physical condition factories.
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
use skate_core::{animation::{playback::PlaybackContext,skeleton_input::name::encode,crouching},
    graph::{activation::ConditionHost,controller::Frame,conditions::PushBrakeInputs}};
use skate_data::{animation_banks::AnimationBanks,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::MotionHost,motion_gameplay_conditions::GameplayConditions,motion_riding_conditions::RidingConditionInputs,motion_toggle_board};
struct Input{data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn boolean(&mut self)->bool {self.word()!=0}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn gameplay(&mut self)->GameplayConditions {
        GameplayConditions {state:self.word(),wants_runout:self.boolean(),physics_wiping:self.boolean(),body_flipping:self.boolean(),wants_wipeout:self.boolean(),bumped:self.boolean(),
            grabbing_object:self.boolean(),retrieving_board:self.boolean(),dropping_board:self.boolean(),in_biped_air:self.boolean(),hippy_hurdling:self.boolean(),
            handplant_flags:self.word(),handplant_time:self.float(),handplant_thresholds:std::array::from_fn(|_|self.float()),footplant_active:self.boolean(),footplant_duration:self.float(),
            footplant_contact_time:self.float(),time_to_skitch:self.float(),skitch_transition_time:self.float(),time_to_land:self.float(),time_to_land_valid:self.boolean(),
            offboard_time_to_land:self.float(),offboard_air_scalar_92:self.float(),offboard_air_translation:self.vector(),offboard_landing_normal:self.vector(),
            offboard_committed_to_motion:self.boolean(),offboard_obstacle_distance:self.float(),offboard_edge_distance:self.float(),offboard_trajectory_time:self.float(),
            offboard_trajectory_valid:self.boolean(),reached_apex:self.boolean(),can_land_on_board:self.boolean(),landing_turning:self.boolean(),grind_contact:self.boolean(),
            wheel_contact:self.boolean(),trucks_or_deck_contact:self.boolean(),moving_object:self.boolean(),tricks_blocked_on_stairs:self.boolean()}
    }
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
        let mask=r.word();let game=r.gameplay();host.gameplay_conditions=(mask&1!=0).then_some(game);
        let stance=(r.boolean(),r.boolean());let loco=r.word();let slope=r.word();let thin=r.boolean();let held=r.boolean();let free=r.boolean();let manual=r.boolean();let height=r.float();
        let riding=RidingConditionInputs{com_velocity:r.vector(),skeleton_x:r.vector(),skeleton_z:r.vector(),skate_up_y:r.float(),surface_up_y:r.float()};
        let push=PushBrakeInputs{ground_axis_y:r.float(),skeleton_disables_push_brake:r.boolean(),maximum_ground_angle_degrees:r.float()};
        host.physical_stance=(mask&2!=0).then_some(stance);host.offboard_locomotion_state=(mask&4!=0).then_some(loco);host.ground_slope_type=(mask&8!=0).then_some(slope);
        host.biped_ground_thin=(mask&16!=0).then_some(thin);host.toggle_board_physical=(mask&32!=0).then_some(motion_toggle_board::Physical{grabbing_object:false,holding_board:held,free_board:free,retrieval_blocked:false,retrieval_active:false,yaw_radians:0.,pitch_radians:0.});
        host.manual_exit=(mask&64!=0).then_some(manual);host.crouching_physical=(mask&128!=0).then_some(crouching::Physical{body_84:0.,body_164:0.,body_188:0.,force_516:0.,ground_force_520:0.,minimum_crouch_528:0.,deck_angle_532:0.,animation_height_72:height});
        host.riding_conditions=(mask&256!=0).then_some(riding);host.condition_inputs.push_brake=(mask&512!=0).then_some(push);
        for id in 0..graph.runtime.operations.conditions.len() {host.errors.clear();out.word(host.condition_activation(id,&frame));out.string(&host.errors.join("|"));}
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
