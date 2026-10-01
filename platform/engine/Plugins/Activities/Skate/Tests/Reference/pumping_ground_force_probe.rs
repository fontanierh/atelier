//! Actual frozen pumping geometry/control/state and ground/pump-force kernels.
//! stock-bindings.rs contains hashed verbatim original loader methods; its
//! shell exposes only their returned values and replaces no runtime callback.
use std::{io::{Read,Write},path::Path};
use skate_core::riding::{ground_force::{self,GroundForceSettings,GroundForceInput},pumping::{self,
    controller::{self,PumpingGeometry,PumpingSample},geometry::NativePumpingGeometry,state::PumpingState}};
use skate_data::collections::Collections;
mod stock_bindings {include!("../../../stock-bindings.rs");}
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let w=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;w}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn sample(&mut self)->PumpingSample {PumpingSample{position:self.vector(),normal:self.vector(),com_to_deck_world:self.vector(),deck_angle:self.float(),intentional_pumping:self.word() as u8}}
    fn state(&mut self)->PumpingState {PumpingState{previous_position:self.vector(),previous_normal:self.vector(),smoothed_height_change:self.float(),pumping_time:self.float(),previous_height:self.float(),pumping:self.float(),pump_acceleration:self.float(),angular_speed:self.float(),absorption:self.float(),ground_normal_absorption:self.float(),minimum_crouch:self.float(),deck_angle_absorption:self.float(),reset_only_scalar:self.float(),record_valid:self.word()!=0,intentional_pumping:self.word() as u8}}
    fn ground(&mut self)->GroundForceInput {GroundForceInput{argument_1:self.float(),application_z:self.float(),argument_3:self.float(),argument_4:self.float(),balance:self.float(),surface_speed:self.float(),axis_384:self.vector(),velocity_400:self.vector(),axis_544:self.vector()}}
    fn ground_settings(&mut self)->GroundForceSettings {GroundForceSettings{range_1220:self.float(),speed_scale_1224:self.float(),scale_1228:self.float(),normal_threshold:self.vector()}}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,w:u32) {self.0.extend(w.to_le_bytes());}
    fn float(&mut self,f:f32) {self.word(f.to_bits());}
    fn string(&mut self,s:&str) {self.word(s.len() as u32);self.0.extend(s.as_bytes());}
    fn floats(&mut self,v:&[f32]) {for f in v {self.float(*f);}}
    fn state(&mut self,s:&PumpingState) {
        self.floats(&s.previous_position);self.floats(&s.previous_normal);for f in [s.smoothed_height_change,s.pumping_time,s.previous_height,s.pumping,s.pump_acceleration,s.angular_speed,s.absorption,s.ground_normal_absorption,s.minimum_crouch,s.deck_angle_absorption,s.reset_only_scalar] {self.float(f);}self.word(u32::from(s.record_valid));self.word(s.intentional_pumping as u32);
        let p=s.physics_output();for f in [p.compression,p.absorption,p.ground_normal_absorption,p.minimum_crouch,p.deck_angle_absorption,p.pump_acceleration] {self.float(f);}self.word(p.intentional_pumping as u32);
    }
    fn settings(&mut self,c:&stock_bindings::pumping::GroundPumping,g:&GroundForceSettings) {
        self.word(118);let s=&c.settings;for curve in [&s.pump_vs_speed,&s.pump_vs_time,&s.min_crouch_vs_ground_angle,&s.compression_vs_ground_angle,&s.compression_vs_deck_angle] {self.floats(&curve.x);self.floats(&curve.y);}for f in [s.height_change_damping,s.minimum_height_change,s.maximum_height_change,s.ground_compression_scale,s.deck_compression_scale,s.angular_speed_damping] {self.float(f);}
        for m in c.modes {for f in [m.controller.maximum_absorption_per_second,m.controller.maximum_acceleration_per_second,m.controller.absorption_factor,m.controller.acceleration_factor,m.unintentional_scalar] {self.float(f);}}
        for f in [g.range_1220,g.speed_scale_1224,g.scale_1228] {self.float(f);}self.floats(&g.normal_threshold);
    }
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=Collections::load(Path::new(&args[1]))?;let c=stock_bindings::pumping::GroundPumping::load(&data)?;let g=stock_bindings::ground_force(&data)?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{data:bytes,at:0};let mut out=Output(Vec::new());out.settings(&c,&g);let count=input.word();out.word(count);let mut state=PumpingState::reset_state();
    for index in 0..count {
        let op=input.word();let mut payload=Output(Vec::new());let mut result=Ok(());
        match op {
            0=>{state=input.state();state.reset();payload.state(&state);},
            1=>{let ground=input.word()!=0;let mode=input.word();let dt=input.float();let sample=input.sample();match c.mode(mode) {Err(e)=>result=Err(e),Ok(m)=>{if ground {controller::update_ground(&mut state,&c.settings,m.controller,sample,&mut NativePumpingGeometry).unwrap();}else {controller::update(&mut state,&c.settings,m.controller,sample,dt,&mut NativePumpingGeometry).unwrap();}payload.state(&state);}}},
            2=>{let dt=input.float();let sample=input.sample();payload.float(controller::calculate(&mut state,&c.settings,&sample,dt,&mut NativePumpingGeometry).unwrap());payload.state(&state);},
            3=>{let i=pumping::PumpForceInput{flags_2476:input.word(),mode_multiplier:input.float(),pumping_scalar:input.float(),input_scalar_2660:input.float(),timestep:input.float(),direction_432:input.vector(),normal_threshold:input.vector()};payload.floats(&pumping::calculate(&i));},
            4=>{let i=input.ground();payload.floats(&ground_force::calculate(&g,&i));},
            5=>{let s=input.ground_settings();let i=input.ground();payload.floats(&ground_force::calculate(&s,&i));},
            6=>{let position=input.vector();let normal=input.vector();let sample=input.sample();let dt=input.float();let mut geometry=NativePumpingGeometry;payload.float(geometry.height(sample.normal,sample.com_to_deck_world).unwrap());payload.float(geometry.speed(position,sample.position,dt).unwrap());payload.float(geometry.angular_speed(position,normal,&sample,dt).unwrap());payload.float(geometry.inclination_radians(sample.normal[1]).unwrap());},
            7=>match c.mode(input.word()) {Err(e)=>result=Err(e),Ok(m)=>for f in [m.controller.maximum_absorption_per_second,m.controller.maximum_acceleration_per_second,m.controller.absorption_factor,m.controller.acceleration_factor,m.unintentional_scalar] {payload.float(f);}},
            8=>{state=input.state();payload.state(&state);},
            _=>return Err("Invalid probe operation".into()),
        }
        out.word(index);out.word(op);match result {Err(e)=>{out.word(0);out.string(&e);},Ok(())=>{out.word(1);out.word((payload.0.len()/4) as u32);out.0.extend(payload.0);}}
    }
    assert_eq!(input.at,input.data.len());std::io::stdout().write_all(&out.0).unwrap();Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
