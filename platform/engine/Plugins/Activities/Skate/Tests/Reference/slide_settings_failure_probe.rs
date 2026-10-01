//! Whole unchanged original Slide stock loader appended by the checker.
use skate_core::{physics::contact::RetailContactMaterial,player::slide_state::{self,SlideSettings,SlideSurface},point_graph::PointGraph};
use std::{io::{Read,Write},path::Path};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}}
struct Output(Vec<u8>);
impl Output {
    fn word(&mut self,v:u32) {self.0.extend(v.to_le_bytes());}
    fn floats(&mut self,values:impl IntoIterator<Item=f32>) {for v in values {self.word(v.to_bits());}}
    fn string(&mut self,v:&str) {self.word(v.len() as u32);self.0.extend(v.as_bytes());}
    fn curve(&mut self,v:&PointGraph<8>) {self.floats(v.x);self.floats(v.y);}
    fn settings(&mut self,s:stock::SlideState) {
        for c in [&s.settings.input_remap,&s.settings.remap_vs_speed,&s.settings.force_vs_angle,&s.settings.force_vs_speed] {self.curve(c);}
        self.floats([s.settings.softest_wheel_force,s.settings.softest_wheel_spin,s.settings.angular_force,s.settings.force_y_offset]);
        for (surface,material) in s.surfaces {self.curve(&surface.speed_to_force);self.floats([surface.yaw_strength,surface.yaw_damping,material.static_friction,material.dynamic_friction,material.restitution]);}self.floats([s.manual_scalar]);
    }
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut input=Input{bytes,at:0};let count=input.word();let mut output=Output(Vec::new());
    for index in 0..count {let fixture=input.word();let data=skate_data::collections::Collections::load(&Path::new(&args[1]).join(fixture.to_string()))?;let result=stock::SlideState::load(&data);output.word(index);output.word(result.is_ok() as u32);match result {Ok(s)=>output.settings(s),Err(error)=>{output.string(&error);output.word(1);}}}
    assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&output.0).map_err(|e|e.to_string())?;Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
