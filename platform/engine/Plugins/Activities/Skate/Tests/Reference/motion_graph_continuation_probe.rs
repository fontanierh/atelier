//! Complete original MotionHost and Controller. Physical publications are explicit caller inputs.
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
use skate_core::{animation::{output::attributes::AnimationAttribute,playback::PlaybackContext,channel_playback::ChannelSettings,playback_tree::{Evaluation,PoseCommand},skeleton_input::name::encode},graph::{controller::{Controller,Host,Frame},activation::ConditionHost,conditions::PhysicalStateInputs,intents::IntentMap}};
use skate_data::{animation_banks::AnimationBanks,animation_metadata::AnimationMetadata,collections::Collections,state_graph::{StateGraph,binding::Binding}};
use graph_host::{motion::MotionHost,motion_gameplay_conditions::GameplayConditions,outputs::{ActionGraphOutput,MotionGraphInput}};
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn boolean(&mut self)->bool {self.word()!=0}
    fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn vector3(&mut self)->[f32;3] {std::array::from_fn(|_|self.float())}
    fn map(&mut self)->IntentMap {let mut m=IntentMap::new();for _ in 0..self.word() {let n=self.string();m.insert(&n,self.float());}m}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn optional(&mut self,v:Option<f32>) {self.word(u32::from(v.is_some()));if let Some(v)=v {self.float(v);}}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>{self.word(1);self.string("");},Err(e)=>{self.word(0);self.string(&e);}}}
    fn scalar(&mut self,r:Result<f32,String>) {match r {Ok(v)=>{self.word(1);self.float(v);},Err(e)=>{self.word(0);self.string(&e);}}}
    fn map(&mut self,m:&IntentMap,names:&[String]) {self.word(m.len() as u32);for n in names {self.optional(m.get(n).copied());}}
    fn attribute(&mut self,a:&AnimationAttribute) {for w in a.name.0 {self.word(w);}self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn name(&mut self,v:Option<skate_core::animation::output::attributes::AttributeName>) {self.word(u32::from(v.is_some()));if let Some(v)=v {for w in v.0 {self.word(w);}}}
    fn named_vector(&mut self,v:Option<(skate_core::animation::output::attributes::AttributeName,[f32;2])>) {self.word(u32::from(v.is_some()));if let Some((n,v))=v {for w in n.0 {self.word(w);}for x in v {self.float(x);}}}
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
fn physical(r:&mut Input,h:&mut MotionHost) {
    let mask=r.word();let flags=r.word();let mirror=r.boolean();let board=r.boolean();let category=r.word();let state=r.word();
    h.animation.skater_animation_flags=(mask&1!=0).then_some(flags);h.playback_context.is_mirrored=(mask&2!=0).then_some(mirror);h.playback_context.board_available=(mask&4!=0).then_some(board);
    h.condition_inputs.physical_state=(mask&16!=0).then_some(PhysicalStateInputs{category,grinding:false,grind_name:String::new()});
    let acceleration=r.vector();h.bump_acceleration=(mask&32!=0).then_some(acceleration);let cadence=r.float();h.offboard_cadence_phase=(mask&64!=0).then_some(cadence);
    let handplant_time=r.float();let handplant_thresholds=std::array::from_fn(|_|r.float());let footplant_duration=r.float();let landing_turning=r.boolean();let offboard_time_to_land=r.float();let offboard_air_scalar_92=r.float();let offboard_air_translation=r.vector();
    // Every unused member is explicit fixture state. Absence belongs to the
    // complete containing publication; these are never fallback producers.
    h.gameplay_conditions=(mask&8!=0).then_some(GameplayConditions{state,wants_runout:false,physics_wiping:false,body_flipping:false,wants_wipeout:false,bumped:false,grabbing_object:false,retrieving_board:false,dropping_board:false,in_biped_air:false,hippy_hurdling:false,handplant_flags:0,handplant_time,handplant_thresholds,footplant_active:false,footplant_duration,footplant_contact_time:0.,time_to_skitch:0.,skitch_transition_time:0.,time_to_land:0.,time_to_land_valid:false,offboard_time_to_land,offboard_air_scalar_92,offboard_air_translation,offboard_landing_normal:[0.;4],offboard_committed_to_motion:false,offboard_obstacle_distance:0.,offboard_edge_distance:0.,offboard_trajectory_time:0.,offboard_trajectory_valid:false,reached_apex:false,can_land_on_board:false,landing_turning,grind_contact:false,wheel_contact:false,trucks_or_deck_contact:false,moving_object:false,tricks_blocked_on_stairs:false});
    let runout=graph_host::motion_runout::Observation{offboard_flag_331:r.boolean(),offboard_velocity_128:r.vector(),reckoning_velocity_16:r.vector(),reckoning_up_96:r.vector(),skeleton_vector_0:r.vector(),animation_mirrored:r.boolean()};h.runout_physical=(mask&128!=0).then_some(runout);
    let air=skate_core::animation::air_leg_extension::Physical{com_velocity:r.vector(),com_position:r.vector(),system_up:r.vector(),right_toe:r.vector(),left_toe:r.vector(),animation_height:r.float(),offboard_316:r.boolean(),remaining_air_time:r.float()};h.air_leg_physical=(mask&256!=0).then_some(air);
    let pre=graph_host::motion_spin::PrelandingPhysical{air_444:r.boolean(),air_normal_144_y:r.float(),animation_16_x:r.float(),com_velocity_y:r.float(),offboard_316:r.boolean(),offboard_319:r.boolean(),offboard_time_32:r.float(),air_437:r.boolean(),air_normal_36:r.float(),air_remaining_184:r.float(),animation_height_72:r.float()};h.prelanding_physical=(mask&512!=0).then_some(pre);
    let centre_of_mass_velocity=r.vector();let system_up=r.vector();h.native_physical=(mask&1024!=0).then_some(graph_host::motion_native::Physical{centre_of_mass_velocity,system_up,board_reckoning_z:[0.,0.,1.,0.],board_reckoning:[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]});
    let landing=graph_host::motion_landing::Physical{height:r.float(),spin:r.float(),kind:r.word(),last_good_landing_velocity:r.float()};h.landing_physical=(mask&2048!=0).then_some(landing);
    let grind=graph_host::motion_grind::Physical{grinding:r.boolean(),grind_name:encode(r.string().as_bytes()),ground_axis:r.vector3(),board_axis:r.vector3(),ground_flag_273:r.boolean(),animation_mirrored:mirror,height:r.float(),crouch:r.float(),twist:r.float()};h.grind_physical=(mask&4096!=0).then_some(grind);
    let toggle=graph_host::motion_toggle_board::Physical{grabbing_object:r.boolean(),holding_board:r.boolean(),free_board:r.boolean(),retrieval_blocked:r.boolean(),retrieval_active:r.boolean(),yaw_radians:r.float(),pitch_radians:r.float()};h.toggle_board_physical=(mask&8192!=0).then_some(toggle);
    let wipe=graph_host::motion_wipeout::Physical{over_599:r.boolean(),collision_time_144:r.float(),no_support_time_548:r.float(),profile_148:r.word(),below_surface_82:r.boolean(),orientation_y:None,hips_right_angle_496:r.float(),hips_up_angle_500:r.float()};h.wipeout_physical=(mask&16384!=0).then_some(wipe);
}
fn snapshot(o:&mut Output,h:&mut MotionHost,c:&Controller,names:&[String],channels:&[String]) {
    o.string(&h.errors.join("|"));let f=&c.frame;o.float(f.dt);o.word(f.current.map_or(0xffffffff,|v|v as u32));o.word(f.last.map_or(0xffffffff,|v|v as u32));o.word(f.state_times.len() as u32);for &v in &f.state_times {o.optional(v);}o.word(c.active.len() as u32);for v in &c.active {o.word(v.behavior as u32);o.word(v.instance);}
    o.map(&h.animation.motion_intents,names);o.map(&h.animation.filtered_intents,names);
    for v in [h.flags.anticipating,h.flags.landing,h.flags.manualing,h.flags.doing_trick,h.flags.tricks_allowed,h.riding.dark,h.is_power_sliding,h.applying_body_tilt,h.hand_services.keep_shove_channels] {o.word(u32::from(v));}
    for v in [h.riding.time_since_teleport,h.riding.time_since_kickturn,h.riding.manual_out_timer,h.riding.last_good_landing_velocity,h.animation_phase] {o.float(v);}for v in h.hand_services.busy_hands {o.word(v);}
    o.word(u32::from(h.animation.skater_animation_flags.is_some()));if let Some(v)=h.animation.skater_animation_flags {o.word(v);}o.word(h.animation.relative_stance);o.word(u32::from(h.animation.reset_action_intents));o.word(u32::from(h.animation.grab_type.is_some()));if let Some(v)=h.animation.grab_type {o.word(v as u32);}
    o.word(u32::from(h.wipeout_controls.seed_from_air_tweak));o.word(u32::from(h.wipeout_controls.gestures_enabled));for v in h.wipeout_controls.gesture {o.float(v);}
    let score=&h.score_packet;o.named_vector(score.handplant);o.named_vector(score.grab);o.name(score.trick_names.first);o.name(score.trick_names.second);o.word(u32::from(score.name.is_some()));if let Some(n)=score.name {o.word(n);}o.word(score.flags);o.word(u32::from(h.allow_pumping));o.word(u32::from(h.moving_objects.active()));
    o.word(h.animation.construction_values.len() as u32);for (n,v) in &h.animation.construction_values {for w in n.0 {o.word(w);}for w in v.0 {o.word(w);}}
    o.word(h.animation.motion_attributes.len() as u32);for v in &h.animation.motion_attributes {for w in v.name.0 {o.word(w);}o.float(v.value);}o.word(h.animation.tree_attributes().len() as u32);for v in h.animation.tree_attributes() {o.attribute(v);}
    let p=h.animation.property();o.word(u32::from(p.crossed_end));o.float(p.overshoot);o.float(p.remaining_before_wrap);o.scalar(h.animation.current_time());o.scalar(h.animation.current_length());o.word(u32::from(h.animation.in_transition()));
    for n in channels {o.word(u32::from(h.animation.channels.has(n)));o.float(h.animation.channels.elapsed(n));o.float(h.animation.channels.remaining(n));o.word(u32::from(h.animation.channels.in_transition(n)));}
    match h.animation.evaluate_pose(Evaluation{cull_threshold:0.,update_history:false}) {Ok(cs)=>{o.status(Ok(()));o.commands(&cs);},Err(e)=>o.status(Err(e))}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let mut o=Output(Vec::new());
    let constructed=(|| {
        let source=StateGraph::load(std::path::Path::new(&args[2])).map_err(|e|e.to_string())?;let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;let graph=graph_runtime::LoadedGraph{source,binding,runtime};
        let data=Collections::load(assets)?;let mut metadata=AnimationBanks::load(assets)?.metadata()?;metadata.merge(AnimationMetadata::load(std::path::Path::new(&args[3]))?)?;
        let context=PlaybackContext{is_switch:Some(false),is_mirrored:Some(false),board_available:Some(true),pro_skater:encode(b"Loose"),transition_override:None};let h=MotionHost::from_graph(&graph,&data,metadata,context)?;Ok::<_,String>((graph,h))
    })();
    let (graph,mut h)=match constructed {Ok(v)=>{o.status(Ok(()));v},Err(e)=>{o.status(Err(e));std::io::stdout().write_all(&o.0).map_err(|e|e.to_string())?;return Ok(())}};
    let (registered,count)=h.migration_continuation_registration();o.word(registered.len() as u32);for v in registered {o.word(u32::from(v));}o.word(count as u32);
    if args[4]=="construct" {std::io::stdout().write_all(&o.0).map_err(|e|e.to_string())?;return Ok(());}
    h.animation.set_hierarchy(&["LeftToeBase".into(),"RightToeBase".into()],&[1,0])?;h.animation.posture_bank_valid=true;h.animation.skater_animation_flags=Some(0x08020000);
    let mut controller=Controller::new(graph.binding.states.len());let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut r=Input{data:bytes,at:0};let names:Vec<_>=(0..r.word()).map(|_|r.string()).collect();let observer=ChannelSettings{priority:0,keep_alive:true,mirrored:false,speed:1.,blend_in:0.,hold_during_blend_in:false,blend_out:0.,hold_during_blend_out:false,use_attributes:true};
    let mut observer_channels=Vec::new();for _ in 0..r.word() {let key=r.string();let tree=r.string();if !h.animation.new_channel(&key,&tree,observer)? {return Err("Observer alias".into());}observer_channels.push((key,tree));}
    let channels:Vec<_>=(0..r.word()).map(|_|r.string()).collect();let steps=r.word();o.word(steps);
    for tick in 0..steps {
        let code=r.word();let id=r.word() as usize;let phase=r.word();let allocate=r.boolean();let dt=r.float();let action=r.map();let motion=r.map();physical(&mut r,&mut h);h.animation.begin_graph_update();h.accept_action_graph(MotionGraphInput{tick:tick as u64,action:ActionGraphOutput::from_host(tick as u64,&action,&motion,&[])});
        let mut handle=0;match code {
            0=>controller.update(&graph.runtime.program,dt,&mut h),1=>controller.end_all_behaviors(&mut h),
            2|4=>{let frame=Frame{dt,current:controller.frame.current,last:controller.frame.last,state_times:controller.frame.state_times.clone()};if allocate {handle=h.allocate(id,&frame);}if code==2 {let context=h.context();match phase {0=>h.begin(id,context,&frame),1=>h.update(id,context,&frame),2=>h.end(id,context,&frame),_=>return Err("Invalid phase".into())}}},
            3=>h.hook(id,&controller.frame),
            // Test fixture creation only: the same actual API/settings as startup.
            5=>{if id!=0||phase!=0||allocate||observer_channels.len()!=30{return Err("Invalid observer restoration".into())}for(key,tree)in &observer_channels{if !h.animation.new_channel(key,tree,observer)?{return Err("Observer alias".into())}}},
            _=>return Err("Invalid opcode".into())
        }
        o.word(handle);o.status(h.animation.apply_parameters());h.animation.advance(dt,h.animation_phase);o.status(Ok(()));o.status(h.animation.refresh_tree_attributes());
        o.word(graph.runtime.operations.conditions.len() as u32);for id in 0..graph.runtime.operations.conditions.len() {o.word(h.condition_activation(id,&controller.frame));}snapshot(&mut o,&mut h,&controller,&names,&channels);
    }
    assert_eq!(r.at,r.data.len());std::io::stdout().write_all(&o.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
