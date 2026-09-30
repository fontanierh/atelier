//! Direct frozen SkaterAnimation::from_source/advance oracle. Every host module
//! and production actor method is staged unchanged; the probe supplies inputs.
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
use std::{io::{Read,Write},path::Path};
use skate_core::{animation::{output::{NativeMatrix,attributes::AnimationAttribute,packet_reset::AdditionalResetFields},physical_feedback::PhysicalFeedback,body_tilt,riding_fakie,crouching,channel_playback::ChannelSettings},
    graph::{controller::Controller,intents::IntentMap,conditions::{ConditionInputs,SpeedInputs,PhysicalStateInputs,PushBrakeInputs}},
    input::set_turning,riding::push_behaviors::PushFootFrame};
use skate_data::{collections::Collections,state_graph::{StateGraph,binding::Binding}};
use skater_animation::{SkaterAnimation,AnimationSource,AnimationPhysical};
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn boolean(&mut self)->bool {self.word()!=0}
    fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
    fn vector(&mut self)->[f32;4] {core::array::from_fn(|_|self.float())}
    fn map(&mut self)->IntentMap {let mut map=IntentMap::new();for _ in 0..self.word() {let name=self.string();map.insert(&name,self.float());}map}
    fn physical(&mut self)->AnimationPhysical {
        let speeds=self.boolean().then(||SpeedInputs{speed:self.float(),forward_speed:self.float(),speed_and_slope:self.float()});
        let physical_state=self.boolean().then(||PhysicalStateInputs{category:self.word(),grinding:self.boolean(),grind_name:self.string()});
        let time_since_last_input=self.boolean().then(||self.float());let mirrored=self.boolean().then(||self.boolean());let riding_fakie=self.boolean().then(||self.boolean());
        let push_brake=self.boolean().then(||PushBrakeInputs{ground_axis_y:self.float(),skeleton_disables_push_brake:self.boolean(),maximum_ground_angle_degrees:self.float()});
        let physical_conditions=self.boolean().then(||self.boolean());let state=self.boolean().then(||self.word());
        // Only the original actor-owned ConditionInputs cross this boundary;
        // action physical_conditions remain separately published by physics.
        assert!(physical_conditions.is_none()&&state.is_none());
        let conditions=ConditionInputs{speeds,physical_state,time_since_last_input,mirrored,riding_fakie,push_brake};
        let turning=set_turning::Physical{field_32:self.float(),field_36:self.float(),field_52:self.float(),field_56:self.float(),field_60:self.float(),body_168:self.float()};
        let crouching=crouching::Physical{body_84:self.float(),body_164:self.float(),body_188:self.float(),force_516:self.float(),ground_force_520:self.float(),minimum_crouch_528:self.float(),deck_angle_532:self.float(),animation_height_72:self.float()};
        let feedback=PhysicalFeedback{turning,crouching,pumping_acceleration:self.float(),ground_acceleration:self.vector(),bumped:self.boolean(),conditioned_turn:core::array::from_fn(|_|self.float())};
        let body_tilt=body_tilt::Physical{lateral_tilt:self.float(),body_spin_speed:self.float(),filtered_category:self.word()};
        let fakie=riding_fakie::Physical{category:self.word(),grind_state:self.word(),doing_trick:self.boolean(),board_axis:self.vector(),deck_velocity:self.vector(),external_velocity:self.vector(),ground_projected_speed:self.float()};
        let physical_stance=(self.boolean(),self.boolean());let foot_frame=PushFootFrame{left_foot:self.vector(),right_foot:self.vector(),deck_position:self.vector(),deck_y:self.vector(),deck_z:self.vector(),skateboard_flipped:self.boolean()};
        AnimationPhysical{conditions,feedback,body_tilt,fakie,physical_stance,foot_frame,board_present:self.boolean(),physical_28_byte75:self.boolean(),time_since_teleport:self.float()}
    }
    fn channel(&mut self)->ChannelSettings {ChannelSettings{priority:self.word() as i32,keep_alive:self.boolean(),mirrored:self.boolean(),speed:self.float(),blend_in:self.float(),hold_during_blend_in:self.boolean(),blend_out:self.float(),hold_during_blend_out:self.boolean(),use_attributes:self.boolean()}}
    fn extra_physical(&mut self,host:&mut graph_host::motion::MotionHost) {
        let mask=self.word();
        let riding=graph_host::motion_riding_conditions::RidingConditionInputs{com_velocity:self.vector(),skeleton_x:self.vector(),skeleton_z:self.vector(),skate_up_y:self.float(),surface_up_y:self.float()};
        let grind=graph_host::motion_grind::conditions::Physical{filtered_grinding_80:self.boolean(),blunting_136:self.word(),approach_268:self.word(),trick_out_240:self.word(),air_grind_443:self.boolean(),air_time_184:self.float(),dropping_in_324:self.boolean()};
        let landing=graph_host::motion_landing::Physical{height:self.float(),spin:self.float(),kind:self.word(),last_good_landing_velocity:self.float()};
        let over_599=self.boolean();let collision_time_144=self.float();let no_support_time_548=self.float();let profile_148=self.word();let below_surface_82=self.boolean();let orientation=self.boolean();let y=self.float();let hips_right_angle_496=self.float();let hips_up_angle_500=self.float();
        let wipeout=graph_host::motion_wipeout::Physical{over_599,collision_time_144,no_support_time_548,profile_148,below_surface_82,orientation_y:orientation.then_some(y),hips_right_angle_496,hips_up_angle_500};
        let prelanding=graph_host::motion_spin::PrelandingPhysical{air_444:self.boolean(),air_normal_144_y:self.float(),animation_16_x:self.float(),com_velocity_y:self.float(),offboard_316:self.boolean(),offboard_319:self.boolean(),offboard_time_32:self.float(),air_437:self.boolean(),air_normal_36:self.float(),air_remaining_184:self.float(),animation_height_72:self.float()};
        host.riding_conditions=(mask&1!=0).then_some(riding);host.grind_conditions=(mask&2!=0).then_some(grind);host.landing_physical=(mask&4!=0).then_some(landing);host.wipeout_physical=(mask&8!=0).then_some(wipeout);host.prelanding_physical=(mask&16!=0).then_some(prelanding);
    }
}
struct Output(Vec<u8>,bool);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn string(&mut self,v:&str) {self.word(v.len() as u32);self.0.extend(v.as_bytes());}
    fn status(&mut self,r:Result<(),String>) {match r {Ok(())=>self.word(1),Err(e)=>{self.word(0);self.string(&e);}}}
    fn optional(&mut self,v:Option<f32>) {self.word(u32::from(v.is_some()));if let Some(v)=v {self.float(v);}}
    fn optional_name(&mut self,v:Option<skate_core::animation::output::attributes::AttributeName>) {self.word(u32::from(v.is_some()));if let Some(v)=v {for w in v.0 {self.word(w);}}}
    fn named_vector(&mut self,v:Option<(skate_core::animation::output::attributes::AttributeName,[f32;2])>) {self.word(u32::from(v.is_some()));if let Some((n,v))=v {for w in n.0 {self.word(w);}for f in v {self.float(f);}}}
    fn map(&mut self,m:&IntentMap,names:&[String]) {self.word(m.len() as u32);for n in names {self.optional(m.get(n).copied());}}
    fn attribute(&mut self,a:&AnimationAttribute) {for w in a.name.0 {self.word(w);}self.word(a.kind as u32);self.word(a.status as u32);self.word(a.sequence_id as u32);self.float(a.begin_time);self.float(a.end_time);for v in a.payload.0 {self.word(u32::from(v.is_some()));if let Some(v)=v {self.word(v);}}}
    fn matrices(&mut self,ms:&[NativeMatrix]) {self.word(ms.len() as u32);for m in ms {for c in m {for f in c {self.float(*f);}}}}
    fn frame(&mut self,c:&Controller) {self.float(c.frame.dt);self.word(c.frame.current.map_or(0xffffffff,|n|n as u32));self.word(c.frame.last.map_or(0xffffffff,|n|n as u32));self.word(c.frame.state_times.len() as u32);for t in &c.frame.state_times {self.optional(*t);}self.word(c.active.len() as u32);for a in &c.active {self.word(a.behavior as u32);self.word(a.instance);}}
    fn reset(&mut self,r:&AdditionalResetFields) {self.float(r.compression);for f in r.foot_ik_influence {self.float(f);}for b in [r.next_step_position_valid,r.actor_flag_1904_bit23,r.actor_flag_1908_bit2,r.external_impulse_active,r.external_physics_input_active,r.externally_controlled,r.prevent_manual_respawn] {self.word(u32::from(b));}self.word(r.ignore_respawn_reset_button as u32);self.word(u32::from(r.force_braking));self.float(r.truck_tightness);self.float(r.wheel_hardness);for v in r.auxiliary_vectors {for f in v {self.float(f);}}self.word(r.requested_physics_mode);}
    fn scalar(&mut self,r:Result<f32,String>) {match r {Ok(v)=>{self.word(1);self.float(v);},Err(e)=>{self.word(0);self.string(&e);}}}
    fn snapshot(&mut self,a:&SkaterAnimation,reset:&AdditionalResetFields,names:&[String]) {
        self.word(a.ticks as u32);self.word((a.ticks>>32) as u32);let stance=a.stance();self.word(u32::from(stance.0));self.word(u32::from(stance.1));self.word(a.checkpoint_stance());self.word(u32::from(a.foot_forward()));
        self.frame(&a.action_controller);self.frame(&a.motion_controller);let output=a.action.output();self.word(output.tick as u32);self.word((output.tick>>32) as u32);self.word(u32::from(a.action.is_tricking.is_some()));if let Some(v)=a.action.is_tricking {self.word(u32::from(v));}
        self.map(&a.action.action_intents,names);self.map(&a.action.motion_intents,names);self.map(&a.motion.animation.motion_intents,names);self.map(&a.motion.animation.filtered_intents,names);
        self.string(&a.action.errors.join("\n"));self.string(&a.motion.errors.join("\n"));
        for b in [a.motion.flags.anticipating,a.motion.flags.landing,a.motion.flags.manualing,a.motion.flags.doing_trick,a.motion.flags.tricks_allowed,a.motion.riding.dark,a.motion.is_power_sliding,a.motion.applying_body_tilt,a.motion.hand_services.keep_shove_channels] {self.word(u32::from(b));}
        for f in [a.motion.riding.time_since_teleport,a.motion.riding.time_since_kickturn,a.motion.riding.manual_out_timer,a.motion.riding.last_good_landing_velocity,a.motion.animation_phase] {self.float(f);}
        for h in a.motion.hand_services.busy_hands {self.word(h);}for w in unsafe{core::mem::transmute::<skate_core::input::set_turning::SlideLatch,[u32;5]>(a.motion.slide_latch)} {self.word(w);}
        let anim=&a.motion.animation;self.word(u32::from(anim.skater_animation_flags.is_some()));if let Some(w)=anim.skater_animation_flags {self.word(w);}
        self.word(anim.natural_stance);self.word(anim.relative_stance);self.word(anim.requested_stance);self.word(u32::from(anim.reset_action_intents));self.word(u32::from(anim.grab_type.is_some()));if let Some(v)=anim.grab_type {self.word(v as u32);}
        self.word(anim.posture.profile());self.word(u32::from(anim.posture.is_pending()));self.word(u32::from(anim.current_name.is_some()));if let Some(v)=&anim.current_name {self.string(v);}
        self.scalar(anim.current_time());self.scalar(anim.current_length());self.word(u32::from(anim.in_transition()));let p=anim.property();self.word(u32::from(p.crossed_end));self.float(p.overshoot);self.float(p.remaining_before_wrap);
        for n in ["Overlay","overlay","SkitchAntic","Missing"] {self.word(u32::from(anim.channels.has(n)));self.float(anim.channels.elapsed(n));self.float(anim.channels.remaining(n));self.word(u32::from(anim.channels.in_transition(n)));}
        self.word(anim.tree_attributes().len() as u32);for v in anim.tree_attributes() {self.attribute(v);}self.word(a.action.animation_attributes.len() as u32);for v in &a.action.animation_attributes {self.attribute(v);}
        self.word(anim.motion_attributes.len() as u32);for v in &anim.motion_attributes {for w in v.name.0 {self.word(w);}self.float(v.value);}
        self.word(a.attributes.entries().len() as u32);for v in a.attributes.entries() {self.attribute(v);}
        self.word(a.pose.len() as u32);for p in &a.pose {for v in [p.scale,p.rotation,p.translation] {for f in v {self.float(f);}}}
        let p=&a.packet;self.word(p.bone_count);self.matrices(&p.hierarchy);self.matrices(&p.local);self.float(p.timestep);for f in p.foot_surface_ids {self.word(f);}self.word(p.flags);
        for b in [p.board_flipped,p.mirrored,p.riding_switch,p.riding_fakie,p.weight_forwards,p.regular_stance] {self.word(u32::from(b));}self.word(p.air_dismount_revert_frames as u32);self.reset(reset);
        if self.1 {
            let score=&a.motion.score_packet;self.named_vector(score.handplant);self.named_vector(score.grab);self.optional_name(score.trick_names.first);self.optional_name(score.trick_names.second);
            self.word(u32::from(score.name.is_some()));if let Some(name)=score.name {self.word(name);}self.word(score.flags);self.word(u32::from(a.motion.allow_pumping));self.word(u32::from(a.motion.moving_objects.active()));
            self.word(anim.construction_values.len() as u32);for (n,v) in &anim.construction_values {for w in n.0 {self.word(w);}for w in v.0 {self.word(w);}}
            for n in ["PUMP0","PUMP1","PUMP2","PUMP3","PUMP4"] {self.word(u32::from(anim.channels.has(n)));self.float(anim.channels.elapsed(n));self.float(anim.channels.remaining(n));self.word(u32::from(anim.channels.in_transition(n)));}
        }
    }
}
fn load_graph(path:&Path)->Result<graph_runtime::LoadedGraph,String> {let source=StateGraph::load(path).map_err(|e|e.to_string())?;let binding=Binding::from_graph(&source).map_err(|e|e.to_string())?;let runtime=graph_runtime::CompiledGraph::from_binding(&binding).map_err(|e|e.to_string())?;Ok(graph_runtime::LoadedGraph{source,binding,runtime})}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let assets=Path::new(&args[1]);let fixtures=Path::new(&args[2]);let data=Collections::load(assets)?;let source=AnimationSource::load(assets)?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let extended=bytes.get(7)==Some(&b'2');let mut input=Input{data:bytes,at:8};let mut out=Output(Vec::new(),extended);
    for _ in 0..input.word() {let _=input.string();}let names:Vec<_>=(0..input.word()).map(|_|input.string()).collect();let count=input.word();out.word(count);
    for _ in 0..count {
        let id=input.word();let pro=input.string();let graphs=graph_runtime::StockGraphs{action:load_graph(&fixtures.join(format!("actor-{id}.action.reference")))?,motion:load_graph(&fixtures.join(format!("actor-{id}.motion.reference")))?};
        let mut actor=SkaterAnimation::from_source(&data,&graphs,pro.as_bytes(),source.clone())?;
        let mut reset=AdditionalResetFields{compression:0.137,foot_ik_influence:[0.317,0.731],next_step_position_valid:true,actor_flag_1904_bit23:true,actor_flag_1908_bit2:true,external_impulse_active:true,external_physics_input_active:true,externally_controlled:true,prevent_manual_respawn:true,ignore_respawn_reset_button:255,force_braking:true,truck_tightness:0.113,wheel_hardness:0.719,auxiliary_vectors:[[0.137,0.317,0.731,0.113];6],requested_physics_mode:0xdeadbeef};
        let steps=input.word();out.word(steps);out.snapshot(&actor,&reset,&names);
        for _ in 0..steps {
            match input.word() {
                0=>{let dt=input.float();let action=input.map();let physical=input.physical();out.status(actor.advance(&graphs,dt,&action,physical,&mut reset));},
                1=>{let natural=input.word();let style=input.word();actor.set_customisation(natural,style);out.status(Ok(()));},
                2=>{actor.request_checkpoint_stance(input.word());out.status(Ok(()));},
                3=>{let name=input.string();let animation=input.string();let settings=input.channel();match actor.motion.animation.new_channel(&name,&animation,settings) {Ok(created)=>{out.word(1);out.word(u32::from(created));},Err(e)=>out.status(Err(e))}},
                4=>{let name=input.string();let time=input.float();let from_last=input.boolean();actor.motion.animation.channels.end_with(&name,time,from_last);out.status(Ok(()));},
                5=>{match actor.evaluate_initial_pose() {Ok(h)=>{out.word(1);out.matrices(&h);},Err(e)=>out.status(Err(e))}},
                6=>{actor.motion.animation.posture.set_profile(input.word());out.status(Ok(()));},
                7=>{actor.action_controller.end_all_behaviors(&mut actor.action);actor.motion_controller.end_all_behaviors(&mut actor.motion);out.status(Ok(()));},
                8=>{assert!(extended);input.extra_physical(&mut actor.motion);out.status(Ok(()));},
                _=>unreachable!(),
            }
            out.snapshot(&actor,&reset,&names);
        }
    }
    assert_eq!(input.at,input.data.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
