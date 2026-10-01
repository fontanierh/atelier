//! Unchanged public steering/truck/wobble core, with verbatim stock bindings appended.
use skate_core::{point_graph::PointGraph,riding::{steering::{self,SteeringInput,SteeringSettings,TruckSteeringState},speed_wobble::{self,SpeedWobbleInput,SpeedWobbleSettings,SpeedWobbleState}}};
use std::io::{Read,Write};
struct Input {bytes:Vec<u8>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
    fn curve(&mut self)->PointGraph<8> {PointGraph{x:core::array::from_fn(|_|self.float()),y:core::array::from_fn(|_|self.float())}}
    fn steering(&mut self)->SteeringSettings {SteeringSettings{hard_turn_increase:self.float(),damping:self.float(),speed_graph_max_speed:self.float(),push_scalar_increment:self.float(),push_scalar_decrement:self.float(),push_scalar_min:self.float(),manual_scalar:self.float(),general_scalar:self.float(),tight_trucks_scalar:self.float(),speed_graph:self.curve(),input_graph:self.curve(),tilt_blending:self.float()}}
    fn wobble(&mut self)->SpeedWobbleSettings {SpeedWobbleSettings{frequency_time:self.curve(),frequency_speed:self.curve(),amplitude_time:self.curve(),amplitude_speed:self.curve(),tightness_threshold:self.float(),time_range:self.float(),speed_range:self.float(),frequency_scale:self.float(),amplitude_scale:self.float(),crouch_threshold:self.float(),height_min:self.float(),height_max:self.float()}}
}
fn floats(output:&mut Vec<u32>,values:impl IntoIterator<Item=f32>) {output.extend(values.into_iter().map(f32::to_bits));}
fn curve(output:&mut Vec<u32>,value:&PointGraph<8>) {floats(output,value.x);floats(output,value.y);}
fn steering(output:&mut Vec<u32>,s:&SteeringSettings) {floats(output,[s.hard_turn_increase,s.damping,s.speed_graph_max_speed,s.push_scalar_increment,s.push_scalar_decrement,s.push_scalar_min,s.manual_scalar,s.general_scalar,s.tight_trucks_scalar]);curve(output,&s.speed_graph);curve(output,&s.input_graph);floats(output,[s.tilt_blending]);}
fn wobble(output:&mut Vec<u32>,s:&SpeedWobbleSettings) {curve(output,&s.frequency_time);curve(output,&s.frequency_speed);curve(output,&s.amplitude_time);curve(output,&s.amplitude_speed);floats(output,[s.tightness_threshold,s.time_range,s.speed_range,s.frequency_scale,s.amplitude_scale,s.crouch_threshold,s.height_min,s.height_max]);}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;let stock_steering=stock::steering(&data)?;let stock_wobble=stock::wobble(&data)?;
    let modes=["easy","normal","hardcore","motorized","test"].map(|name|stock::mode(&data,name)).into_iter().collect::<Result<Vec<_>,_>>()?;
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;assert_eq!(&bytes[..8],b"ATSTWB01");let mut i=Input{bytes,at:8};let count=i.word();let mut output=Vec::new();
    for c in 0..count {let op=i.word();output.extend([c,op,0]);let mark=output.len()-1;match op {
        0=>{steering(&mut output,&stock_steering);wobble(&mut output,&stock_wobble);for mode in &modes {floats(&mut output,*mode);}},
        1=>{let s=if i.word()!=0 {stock_steering}else {i.steering()};let mut push=i.float();let mut damped=i.float();let steps=i.word();for _ in 0..steps {let mask=i.word();let input=SteeringInput{turn:i.float(),hard_turn:i.float(),absolute_body_speed:i.float(),flipped_controls_scalar:i.float(),balance:i.float(),truck_tightness:i.float(),pushing:i.word()!=0};let result=steering::calculate_tilt(&s,input,(mask&1!=0).then_some(&mut push),(mask&2!=0).then_some(&mut damped));floats(&mut output,[result,push,damped]);}},
        2=>{let mut state=TruckSteeringState{deck_tilt:i.float(),targets:core::array::from_fn(|_|i.float()),activation_time:core::array::from_fn(|_|i.float())};let steps=i.word();for _ in 0..steps {let target=i.float();let blend=i.float();let flags_a=i.word();let flags_b=i.word();state.update(target,blend,flags_a,flags_b);floats(&mut output,[state.deck_tilt,state.targets[0],state.targets[1],state.activation_time[0],state.activation_time[1]]);}},
        3=>{let s=if i.word()!=0 {stock_wobble}else {i.wobble()};let mut state=SpeedWobbleState(core::array::from_fn(|_|i.word()));let steps=i.word();for _ in 0..steps {if i.word()!=0 {state.reset();}let input=SpeedWobbleInput{tilt:i.float(),speed:i.float(),center_of_mass_height:i.float(),truck_tightness:i.float(),activation_threshold:i.float(),amplitude_multiplier:i.float()};floats(&mut output,[speed_wobble::calculate(&mut state,&s,input)]);output.extend(state.0);}},
        _=>panic!("Unknown steering/wobble operation"),
    }output[mark]=(output.len()-mark-1) as u32;}assert_eq!(i.at,i.bytes.len());let mut out=std::io::BufWriter::new(std::io::stdout().lock());for word in output {out.write_all(&word.to_le_bytes()).map_err(|e|e.to_string())?;}Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
