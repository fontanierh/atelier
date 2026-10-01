//! Untouched four grounded kernels, retained heading history and hashed stock bindings.
use std::{io::{Read,Write},path::Path};
use skate_core::riding::{slide_friction::{self,SlideFrictionInput},straighten::{self,StraightenInput},heading::{self,HeadingInput},anti_flip::{self,AntiFlipInput}};
use skate_data::collections::Collections;
mod stock_bindings {include!("../../../ground-torque-stock-bindings.rs");}
struct Input {data:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let w=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;w}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn matrix(&mut self)->[[f32;4];4] {std::array::from_fn(|_|self.vector())}
}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,w:u32) {self.0.extend(w.to_le_bytes());}
    fn float(&mut self,f:f32) {self.word(f.to_bits());}
    fn floats(&mut self,v:&[f32]) {for f in v {self.float(*f);}}
    fn curve<const N:usize>(&mut self,c:&skate_core::point_graph::PointGraph<N>) {self.floats(&c.x);self.floats(&c.y);}
    fn settings(&mut self,s:&stock_bindings::GroundTorqueSettings) {
        self.word(228);self.curve(&s.slide.angle_response);self.curve(&s.slide.speed_response);self.curve(&s.slide.time_response);for f in [s.slide.scalar_516,s.slide.heading_time_limit,s.slide.friction] {self.float(f);}
        self.curve(&s.straighten.time_response);for f in [s.straighten.opposite_turn_limit,s.straighten.time_scalar,s.straighten.heading_time_limit,s.straighten.strength] {self.float(f);}
        for f in [s.heading.manual_wrong_wheel_scalar,s.heading.manual_damping,s.heading.speed_max,s.heading.heading_strength,s.heading.turn_strength] {self.float(f);}self.curve(&s.heading.angular_response);self.curve(&s.heading.manual_response);self.curve(&s.heading.inclination_response);self.curve(&s.heading.speed_response);self.floats(&s.heading.normal_threshold);
        self.curve(&s.anti_flip.axis_96_response);self.curve(&s.anti_flip.axis_64_response);self.floats(&s.anti_flip.normal_threshold);
    }
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=Collections::load(Path::new(&args[1]))?;let mut settings=Vec::new();for key in ["smooth","rough","slow","slippery","veryslow"] {settings.push(stock_bindings::load(&data,key)?);}
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{data:bytes,at:0};let mut out=Output(Vec::new());out.word(5);for s in &settings {out.settings(s);}let count=input.word();out.word(count);let mut previous=0.;
    for index in 0..count {
        let op=input.word();let profile=input.word() as usize;let s=&settings[profile];let mut payload=Output(Vec::new());
        match op {
            0=>{let i=SlideFrictionInput{heading_time:input.float(),normal:input.vector(),velocity:input.vector(),side_axis:input.vector(),surface_speed:input.float(),scalar_2764:input.float()};payload.floats(&slide_friction::calculate(&s.slide,&i));},
            1=>{let i=StraightenInput{heading_time:input.float(),scalar_2764:input.float(),turn:input.float(),forward:input.vector(),velocity:input.vector(),normal:input.vector()};payload.floats(&straighten::calculate(&s.straighten,&i));},
            2=>{let i=HeadingInput{balance:input.float(),manual_turn:input.float(),flags_2472:input.word(),timestep:input.float(),signed_speed:input.float(),manual_curve_input:input.float(),turn_2712:input.float(),scalar_2740:input.float(),velocity:input.vector(),normal:input.vector(),angular_velocity:input.vector(),transform:input.matrix()};payload.floats(&heading::calculate(&s.heading,&i,&mut previous));payload.float(previous);},
            3=>{let i=AntiFlipInput{flags_2468:input.word(),balance:input.float(),axis_96:input.vector(),axis_64:input.vector(),projection_axis_544:input.vector()};payload.floats(&anti_flip::calculate(&s.anti_flip,&i));},
            4=>{previous=input.float();payload.float(previous);},
            _=>return Err("Invalid probe operation".into()),
        }
        out.word(index);out.word(op);out.word((payload.0.len()/4) as u32);out.0.extend(payload.0);
    }
    assert_eq!(input.at,input.data.len());std::io::stdout().write_all(&out.0).unwrap();Ok(())
}
fn main() {if let Err(e)=run() {eprintln!("{e}");std::process::exit(2);}}
