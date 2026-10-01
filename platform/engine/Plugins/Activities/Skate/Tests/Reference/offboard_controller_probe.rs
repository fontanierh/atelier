#![allow(dead_code,unused_imports,non_snake_case)]
mod offboard_settings;
use skate_core::player::offboard::{controller,movement_intent,movement_velocity,surface_frame,ground_motion,contact_correction,slide,position_output,cadence};
use skate_data::{collections::Collections,animation_banks::AnimationBanks};
use std::io::{Read,Write};
struct Input{bytes:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let w=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;w}
    fn float(&mut self)->f32{f32::from_bits(self.word())}
}
struct Output{words:Vec<u32>}
impl Output{
    fn word(&mut self,w:u32){self.words.push(w)}fn float(&mut self,f:f32){self.word(f.to_bits())}
    fn status(&mut self,okay:bool,error:&str){self.word(okay as u32);self.word(error.len()as u32);for c in error.bytes(){self.word(c as u32)}}
    fn curve<const N:usize>(&mut self,g:&skate_core::point_graph::PointGraph<N>){for f in g.x{self.float(f)}for f in g.y{self.float(f)}}
}
// GENERATED_PROTOCOL
fn settings_out(o:&mut Output,s:&offboard_settings::Settings){
    let i=&s.controller.movement_intent;for g in[&i.sprint_blend,&i.slide_steering]{o.curve(g)}o.curve(&i.sprint_speed);o.curve(&i.normal_speed);o.float(i.sprint_time_cap);
    let v=&s.controller.movement_velocity;for g in[&v.slope_speed_scalar,&v.slope_mode_speed,&v.turn_vs_speed,&v.turn_delta_vs_speed,&s.controller.slide_vs_slope,&s.controller.slide_vs_speed]{o.curve(g)}
    for metric in s.metrics{o.word(metric.is_some()as u32);if let Some(m)=metric{o.float(m.translation_z);o.float(m.end_time)}}
    for value in[s.board.extent_0,s.board.extent_16,s.board.offset_32]{for f in value{o.float(f)}}
    for f in[s.board.angle_436,s.board.angle_440,s.board.margin_444,s.board.angle_452,s.board.angle_456]{o.float(f)}
    o.curve(&s.movement_vs_stick_angle);o.curve(&s.turn_vs_stick_angle);o.float(s.air_launch.jump_speed_scalar);o.float(s.air_launch.jump_height);
}
// ORIGINAL_OUTPUT_FORWARDING
fn snapshot(o:&mut Output,c:&controller::Controller){let at=o.words.len();o.word(0);observe_BipedControllerState(o,&c.state);observe_BipedGroundResult(o,&output_bridge::export(&c.state));o.words[at]=(o.words.len()-at-1)as u32;}
fn run()->Result<(),String>{
    let args:Vec<_>=std::env::args().collect();let assets=std::path::Path::new(&args[1]);let metadata=AnimationBanks::load(assets)?.metadata()?;let data=Collections::load(assets)?;
    let mut settings=offboard_settings::Settings::load(&data,&metadata)?;let mut o=Output{words:Vec::new()};o.status(true,"");settings_out(&mut o,&settings);
    if args.len()==3{match offboard_settings::Settings::load(&Collections::load(std::path::Path::new(&args[2]))?,&metadata){Ok(next)=>{settings=next;o.status(true,"")},Err(error)=>o.status(false,&error)}settings_out(&mut o,&settings);}
    else{
        let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{bytes,at:0};let count=i.word();o.word(count);
        for c in 0..count{
            let settings=offboard_settings::Settings::load(&data,&metadata)?;let mut owner=controller::Controller::new(settings.controller,settings.metrics);let n=i.word();o.word(c);o.word(n);snapshot(&mut o,&owner);
            for _ in 0..n{
                let op=i.word();o.word(op);match op{
                    0=>{owner.step_ground(&read_BipedGroundJob(&mut i));},1=>owner.place(read_BipedPlacementInput(&mut i)),2=>owner.reset(),
                    3=>{owner.state.motion.correction_576=std::array::from_fn(|_|i.float());owner.state.correction_target_592=std::array::from_fn(|_|i.float());owner.state.motion.correction_enabled_711=i.word()!=0;owner.state.cadence.phase=read_BipedPhase(&mut i);owner.state.cadence.locomotion_index=i.word();},
                    4=>owner.state.cadence.phase.advance(),_=>return Err("invalid command".into())
                }snapshot(&mut o,&owner);
            }
        }assert_eq!(i.at,i.bytes.len());
    }
    for w in o.words{std::io::stdout().write_all(&w.to_le_bytes()).unwrap()}Ok(())
}
fn main(){if let Err(error)=run(){eprintln!("{error}");std::process::exit(2)}}
