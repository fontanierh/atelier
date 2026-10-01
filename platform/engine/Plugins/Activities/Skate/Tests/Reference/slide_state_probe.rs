//! Unchanged original Slide core and whole original stock loader appended.
use skate_core::{math::Vector3,physics::contact::RetailContactMaterial,player::slide_state::{self,SlideSettings,SlideSurface,SlideInput},point_graph::PointGraph};
use std::io::{Read,Write};
struct Input {words:Vec<u32>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let word=self.words[self.at];self.at+=1;word}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn four(&mut self)->[f32;4] {std::array::from_fn(|_|self.float())}
    fn curve(&mut self)->PointGraph<8> {PointGraph{x:std::array::from_fn(|_|self.float()),y:std::array::from_fn(|_|self.float())}}
    fn settings(&mut self)->SlideSettings {SlideSettings{input_remap:self.curve(),remap_vs_speed:self.curve(),force_vs_angle:self.curve(),force_vs_speed:self.curve(),softest_wheel_force:self.float(),softest_wheel_spin:self.float(),angular_force:self.float(),force_y_offset:self.float()}}
    fn surface(&mut self)->SlideSurface {SlideSurface{speed_to_force:self.curve(),yaw_strength:self.float(),yaw_damping:self.float()}}
    fn frame(&mut self)->SlideInput {SlideInput{velocity:self.four(),normal:self.four(),side:self.four(),effective_forward:self.four(),reference_forward:self.four(),angular_velocity:self.four(),absolute_speed:self.float(),surface_speed:self.float(),slide:self.float(),elapsed:self.float(),wheel_hardness:self.float()}}
}
fn floats(out:&mut Vec<u32>,values:impl IntoIterator<Item=f32>) {out.extend(values.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3) {floats(out,[v.x,v.y,v.z]);}
fn curve(out:&mut Vec<u32>,p:&PointGraph<8>) {floats(out,p.x);floats(out,p.y);}
fn state(out:&mut Vec<u32>,s:&slide_state::SlideState) {floats(out,[s.start_speed,s.steering_push,s.damped_turn]);out.extend([s.flag48 as u32,s.wall_riding as u32]);}
fn settings(out:&mut Vec<u32>,s:&SlideSettings) {curve(out,&s.input_remap);curve(out,&s.remap_vs_speed);curve(out,&s.force_vs_angle);curve(out,&s.force_vs_speed);floats(out,[s.softest_wheel_force,s.softest_wheel_spin,s.angular_force,s.force_y_offset]);}
fn surface(out:&mut Vec<u32>,s:&SlideSurface) {curve(out,&s.speed_to_force);floats(out,[s.yaw_strength,s.yaw_damping]);}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let stock=stock::SlideState::load(&data)?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let count=i.word();let mut out=Vec::new();
    for c in 0..count {let op=i.word();out.extend([c,op,0]);let mark=out.len()-1;match op {
        0=>{state(&mut out,&stock.state);settings(&mut out,&stock.settings);for (s,m) in &stock.surfaces {surface(&mut out,s);floats(&mut out,[m.static_friction,m.dynamic_friction,m.restitution]);}floats(&mut out,[stock.manual_scalar]);},
        1=>{let mut s=slide_state::SlideState{start_speed:i.float(),steering_push:i.float(),damped_turn:i.float(),flag48:i.word()!=0,wall_riding:i.word()!=0};let steps=i.word();for _ in 0..steps {let action=i.word();let value=i.float();match action {0=>s=slide_state::SlideState::new(),1=>s.enter(value),2=>s.exit(),_=>return Err("Invalid lifecycle".into())};state(&mut out,&s);}},
        2=>{let selected=i.word();let s=if selected==0 {i.settings()}else {stock.settings.clone()};let surface=if selected==0 {i.surface()}else {stock.surfaces[selected as usize-1].0.clone()};let steps=i.word();for _ in 0..steps {let input=i.frame();floats(&mut out,slide_state::angular_correction(&s,&surface,input));let force=slide_state::sliding_force(&s,&surface,input);out.push(force.tag);vector(&mut out,force.force_world);vector(&mut out,force.point_body);}},
        _=>return Err("Invalid Slide command".into()),
    }out[mark]=(out.len()-mark-1) as u32;}assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out {stdout.write_all(&word.to_le_bytes()).map_err(|e|e.to_string())?;}Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
