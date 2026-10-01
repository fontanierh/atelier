//! Verbatim frozen host stock binding functions/expressions are appended.
use skate_core::{physics::manual::settings::{ManualSettings,ManualGains,ManualMode},point_graph::PointGraph,riding::{grounded::propulsion::GroundPropulsionSettings,braking::{BrakeSettings,LinearDragSettings},speed_model::SpeedModelSettings,ground_contact_response::WallRideSettings}};
use skate_data::collections::Collections;
use std::{collections::BTreeMap,io::{Read,Write},path::Path};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let value=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn string(&mut self)->String {let count=self.word() as usize;let value=String::from_utf8(self.bytes[self.at..self.at+count].to_vec()).unwrap();self.at+=count;value}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,value:u32) {self.0.extend(value.to_le_bytes());}
    fn float(&mut self,value:f32) {self.word(value.to_bits());}
    fn string(&mut self,value:&str) {self.word(value.len() as u32);self.0.extend(value.as_bytes());}
    fn floats(&mut self,values:impl IntoIterator<Item=f32>) {for v in values {self.float(v);}}
    fn curve(&mut self,value:&PointGraph<8>) {self.floats(value.x);self.floats(value.y);}
    fn manual(&mut self,s:ManualSettings) {self.curve(&s.noise_vs_speed);self.floats([s.torque_scale_without_contact,s.torque_bleed_without_contact,s.start_torque_scale,s.procedural_noise_scale,s.procedural_noise_frequency,s.powerslide.proportional,s.powerslide.integral,s.powerslide.derivative,s.manual.proportional,s.manual.integral,s.manual.derivative,s.maximum_tilt_degrees,s.maximum_angle_error,s.derivative_limit,s.brake_tilt_degrees,s.animation_noise_scale]);}
    fn manual_mode(&mut self,s:ManualMode) {self.float(s.correction_angular_speed_threshold);self.word(s.corrective_force_enabled as u32);}
    fn propulsion(&mut self,s:GroundPropulsionSettings) {self.floats([s.braking.input_force,s.braking.override_force,s.braking.minimum_speed,s.maximum_pushable_speed,s.mode_speed_changes[0],s.mode_speed_changes[1]]);}
    fn drag(&mut self,s:LinearDragSettings) {self.floats([s.brake_speed,s.balance_speed,s.comparison_threshold,s.balance_drag]);}
    fn speed(&mut self,s:SpeedModelSettings) {self.floats([s.negative_gain,s.maximum_gravity_acceleration,s.gravity,s.positive_gain,s.coffin_acceleration,s.speed_error_bound]);self.curve(&s.surface_friction);self.floats([s.manual_acceleration,s.negative_manual_angle_limit,s.manual_angle_limit,s.no_input_delay]);self.curve(&s.no_input_friction);self.curve(&s.manual_friction);self.word(s.override_enabled as u32);self.float(s.override_speed);self.floats(s.normal_threshold);self.floats(s.override_direction_threshold);}
    fn wallride(&mut self,s:WallRideSettings) {self.curve(&s.anti_gravity_vs_time);self.floats([s.max_dot_floor_wall,s.foot_force_time,s.auto_jump_height,s.max_time,s.velocity_time_to_consider,s.auto_jump_y_down_scalar,s.auto_jump_force]);}
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut input=Input{bytes,at:0};let count=input.word();let mut fixtures=BTreeMap::new();let mut output=Output(Vec::new());
    for index in 0..count {let op=input.word();let fixture=input.word();let mode=input.string();let surface=input.string();let surface_id=input.word();if !fixtures.contains_key(&fixture) {fixtures.insert(fixture,Collections::load(&Path::new(&args[1]).join(fixture.to_string()))?);}let data=&fixtures[&fixture];let mut payload=Output(Vec::new());let result=match op {
        0=>stock::manual(data).map(|s|payload.manual(s)),
        1=>stock::manual_mode(data,&mode).map(|s|payload.manual_mode(s)),
        2=>stock::propulsion(data,&mode).map(|s|payload.propulsion(s)),
        3=>stock::drag(data).map(|s|payload.drag(s)),
        4=>stock::speed(data,&mode,&surface).map(|s|payload.speed(s)),
        5=>stock_wall::wallride(data).map(|s|payload.wallride(s)),
        6=>stock_surface::surface_key(surface_id).map(|s|payload.string(s)),
        _=>return Err("Unknown ground settings operation".into()),
    };output.word(index);output.word(op);output.word(result.is_ok() as u32);match result {Ok(())=>output.0.extend(payload.0),Err(error)=>output.string(&error)};}
    assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&output.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
