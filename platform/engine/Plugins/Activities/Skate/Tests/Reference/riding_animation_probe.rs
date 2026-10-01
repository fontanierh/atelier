//! Original core riding animation owners, ground conditioning and feedback.
#[path="../../crates/skate-host/src/graph_host/crouching_settings.rs"] mod stock_crouch;
#[path="../../crates/skate-host/src/graph_host/pumping_settings.rs"] mod stock_pump;
#[path="../../crates/skate-host/src/graph_host/turning_settings.rs"] mod stock_turn;
#[path="../../crates/skate-host/src/physics/animation_feedback_settings.rs"] mod stock_feedback;
use std::io::{Read,Write};
use skate_core::{animation::{crouching,body_tilt,riding_fakie,pumping_channel,ground_acceleration,physical_feedback},
    input::{set_turning,turn_conditioner},point_graph::PointGraph,math::{Vector3,Basis3},
    physics::board_motion_output::BoardMotionOutput,riding::{pumping::state::PumpingState,speed_wobble::SpeedWobbleState}};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn boolean(&mut self)->bool {self.word()!=0}
    fn optional(&mut self)->Option<f32> {self.boolean().then(||self.float())}
    fn vector(&mut self)->[f32;4] {core::array::from_fn(|_|self.float())}
    fn position(&mut self)->Vector3 {Vector3::new(self.float(),self.float(),self.float())}
    fn matrix(&mut self)->[[f32;4];4] {core::array::from_fn(|_|self.vector())}
    fn curve<const N:usize>(&mut self)->PointGraph<N> {PointGraph{x:core::array::from_fn(|_|self.float()),y:core::array::from_fn(|_|self.float())}}
    fn crouch_settings(&mut self)->crouching::Settings {crouching::Settings{maximum_height:self.curve(),absorption_upforce:self.curve(),pump_maxspeed:self.curve(),minimum_height:self.float(),maximum_ratio:self.float(),maximum_delta_delta:self.float(),maximum_delta:self.float(),input_blend:self.float(),pump_vertical_speed:self.float(),maximum_crouch_from_deck:self.float(),skateboard_damping:self.float(),maximum_force:self.float(),maximum_ground_force:self.float(),absorption_factor:self.float(),auto_pump:crouching::AutoPumpSettings{maximum_crouch:self.curve(),sufficient_crouch:self.float(),standing_threshold:self.float(),rise_speed:self.float(),pump_speed:self.float(),potential_threshold:self.float(),potential_blend:self.float(),intent_magnitude_start:self.float(),intent_angle_region:self.float(),crouch_time:self.float(),crouch_speed:self.float()}}}
    fn crouch_physical(&mut self)->crouching::Physical {crouching::Physical{body_84:self.float(),body_164:self.float(),body_188:self.float(),force_516:self.float(),ground_force_520:self.float(),minimum_crouch_528:self.float(),deck_angle_532:self.float(),animation_height_72:self.float()}}
    fn crouch_intents(&mut self)->crouching::Intents {crouching::Intents{auto_pump_angle:self.optional(),auto_pump_magnitude:self.optional(),crouch:self.optional(),hard_turn_crouch:self.optional(),manual:self.optional(),motion_flag_108:self.boolean()}}
    fn tilt_settings(&mut self)->body_tilt::Settings {body_tilt::Settings{body_spin_factor:self.curve(),ground_velocity:self.float(),ground_acceleration:self.float(),air_velocity:self.float(),air_acceleration:self.float()}}
    fn fakie_settings(&mut self)->riding_fakie::Settings {riding_fakie::Settings{high_speed:self.float(),low_speed:self.float(),slowly_backwards_seconds:self.float(),after_teleport_seconds:self.float()}}
    fn fakie_physical(&mut self)->riding_fakie::Physical {riding_fakie::Physical{category:self.word(),grind_state:self.word(),doing_trick:self.boolean(),board_axis:self.vector(),deck_velocity:self.vector(),external_velocity:self.vector(),ground_projected_speed:self.float()}}
    fn pump_settings(&mut self)->pumping_channel::Settings {pumping_channel::Settings{amplify:self.curve(),input_blend:self.float(),maximum_physics_pump:self.float(),new_pump_threshold:self.float(),blend_in:self.float(),blend_out:self.float()}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn float(&mut self,v:f32) {self.word(v.to_bits());}
    fn optional(&mut self,v:Option<f32>) {self.word(u32::from(v.is_some()));if let Some(v)=v {self.float(v);}}
    fn floats<const N:usize>(&mut self,values:[f32;N]) {for f in values {self.float(f);}}
    fn curve<const N:usize>(&mut self,p:&PointGraph<N>) {self.floats(p.x);self.floats(p.y);}
    fn crouch(&mut self,s:&crouching::Settings) {self.curve(&s.maximum_height);self.curve(&s.absorption_upforce);self.curve(&s.pump_maxspeed);self.floats([s.minimum_height,s.maximum_ratio,s.maximum_delta_delta,s.maximum_delta,s.input_blend,s.pump_vertical_speed,s.maximum_crouch_from_deck,s.skateboard_damping,s.maximum_force,s.maximum_ground_force,s.absorption_factor]);let a=&s.auto_pump;self.curve(&a.maximum_crouch);self.floats([a.sufficient_crouch,a.standing_threshold,a.rise_speed,a.pump_speed,a.potential_threshold,a.potential_blend,a.intent_magnitude_start,a.intent_angle_region,a.crouch_time,a.crouch_speed]);}
    fn tilt(&mut self,s:&body_tilt::Settings) {self.curve(&s.body_spin_factor);self.floats([s.ground_velocity,s.ground_acceleration,s.air_velocity,s.air_acceleration]);}
    fn pump(&mut self,s:&pumping_channel::Settings) {self.curve(&s.amplify);self.floats([s.input_blend,s.maximum_physics_pump,s.new_pump_threshold,s.blend_in,s.blend_out]);}
    fn turning(&mut self,s:&set_turning::Settings) {for r in &s.remaps {self.curve(&r.magnitude);self.curve(&r.angle);self.float(r.angle_offset);}self.curve(&s.speed_tuck);self.curve(&s.blend);self.floats([s.speed_threshold,s.maximum_delta,s.override_turn]);}
    fn feedback(&mut self,s:&turn_conditioner::Settings) {for c in s.filter_coefficients {self.floats(c);}self.curve(&s.input_curve);self.curve(&s.quickness_curve);self.curve(&s.speed_curve);self.curve(&s.smoothing_curve);self.floats(s.parameters);}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let stock_crouch=stock_crouch::load(&data)?;let stock_tilt=body_tilt_settings(&data)?;let stock_pump=stock_pump::load(&data)?;let stock_turn=stock_turn::load(&data)?;let stock_feedback=stock_feedback::load(&data)?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{bytes,at:8};let count=input.word();let mut out=Output(Vec::new());
    for _ in 0..count {match input.word() {
        0=>{out.crouch(&stock_crouch);out.tilt(&stock_tilt);out.pump(&stock_pump);out.turning(&stock_turn);out.feedback(&stock_feedback);out.float(data.float("anim_motion","bumps","scale_x_acc")?);out.float(data.float("anim_motion","bumps","min_bump_mag")?);},
        1=>{let settings=if input.boolean() {stock_crouch.clone()}else {input.crouch_settings()};let physical=input.crouch_physical();let mut state=crouching::State::begin(physical,&settings);out.float(state.fraction);for _ in 0..input.word() {let p=input.crouch_physical();let intents=input.crouch_intents();let r=state.update(p,intents,input.float(),&settings);out.float(r.height);out.word(u32::from(r.new_auto_pump));out.word(u32::from(r.player_controlled_pump));out.float(state.fraction);}},
        2=>{let settings=if input.boolean() {stock_tilt.clone()}else {input.tilt_settings()};let mut state=body_tilt::State::default();for _ in 0..input.word() {let action=input.word();if action==2 {state.disable();out.optional(None);}else {let mirrored=input.boolean();let p=body_tilt::Physical{lateral_tilt:input.float(),body_spin_speed:input.float(),filtered_category:input.word()};out.optional(state.update(action!=0,mirrored,p,&settings));}}},
        3=>{let settings=input.fakie_settings();let mut state=riding_fakie::State::default();for _ in 0..input.word() {let p=input.fakie_physical();let r=state.update(p,input.float(),settings);out.word(u32::from(r.is_some()));if let Some(v)=r {out.word(u32::from(v));}}},
        4=>{let settings=if input.boolean() {stock_pump.clone()}else {input.pump_settings()};let mut state=pumping_channel::State::default();for _ in 0..input.word() {let pump=input.float();let occupied=core::array::from_fn(|_|input.boolean());let r=state.update(pump,occupied,&settings);out.word(u32::from(r.start.is_some()));if let Some(i)=r.start {out.word(i as u32);}out.word(u32::from(r.influence.is_some()));if let Some((i,v))=r.influence {out.word(i as u32);out.float(v);}}},
        5=>{let settings=ground_acceleration::Settings{scale_x_acc:input.float(),min_bump_mag:input.float()};let p=ground_acceleration::Input{deck:input.matrix(),ground:input.matrix(),world_acceleration:input.vector()};let r=ground_acceleration::publish(p,&settings);out.floats(r.acceleration);out.word(u32::from(r.bumped));},
        6=>{
            let mut state=turn_conditioner::State{history:core::array::from_fn(|_|input.float()),filters:core::array::from_fn(|_|core::array::from_fn(|_|input.float()))};
            for _ in 0..input.word() {
                let speed=input.float();let forward_speed=input.float();let ground_speed=input.float();let linear_y=input.float();
                // Only speed/forward/ground/linear-Y are read by the untouched
                // physical-feedback publisher. Other completed record fields
                // have explicit fixture sentinels and no callback substitutes.
                let motion=BoardMotionOutput{angular_velocity:Vector3::new(0.137,0.317,0.731),linear_velocity:Vector3::new(0.137,linear_y,0.731),ground_velocity:Vector3::new(0.137,0.317,0.731),speed,ground_speed,forward_speed,effective_basis:Basis3{columns:[[0.137,0.317,0.731];3]}};
                let mut pumping=PumpingState::reset_state();pumping.pumping=input.float();pumping.absorption=input.float();pumping.ground_normal_absorption=input.float();pumping.minimum_crouch=input.float();pumping.deck_angle_absorption=input.float();pumping.pump_acceleration=input.float();
                let mut wobble=SpeedWobbleState([0;8]);wobble.0[5]=input.float().to_bits();let reckoning=physical_feedback::ReckoningFeedback{system_position:input.position(),system_up:input.position(),board_position:input.position(),target_lean_angle:input.float()};let controls=physical_feedback::ControlFeedback{processed_flags:input.word(),turn:input.float(),animation_mirrored:input.boolean()};let acceleration=ground_acceleration::Output{acceleration:input.vector(),bumped:input.boolean()};
                let r=physical_feedback::publish(&mut state,&stock_feedback,&motion,&pumping,&wobble,reckoning,controls,acceleration);let t=r.turning;out.floats([t.field_32,t.field_36,t.field_52,t.field_56,t.field_60,t.body_168]);let c=r.crouching;out.floats([c.body_84,c.body_164,c.body_188,c.force_516,c.ground_force_520,c.minimum_crouch_528,c.deck_angle_532,c.animation_height_72]);out.float(r.pumping_acceleration);out.floats(r.ground_acceleration);out.word(u32::from(r.bumped));out.floats(r.conditioned_turn);out.floats(state.history);for c in state.filters {out.floats(c);}
            }
        },
        _=>unreachable!(),
    }}assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
