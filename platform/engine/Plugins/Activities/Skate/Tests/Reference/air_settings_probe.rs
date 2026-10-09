use skate_data::collections::Collections;
use std::io::Write;
// The entire original input.rs module is a byte-identical staged alias. The
// unused owner shapes below bind its other function declarations only; this
// proof calls no physical, selector, or launch facade.
// GENERATED_OWNER_TYPES
#[derive(Default)]struct Output(Vec<u32>);
impl Output {
    fn word(&mut self,v:u32){self.0.push(v)}
    fn float(&mut self,v:f32){self.word(v.to_bits())}
    fn string(&mut self,s:&str){self.word(s.len()as u32);for chunk in s.as_bytes().chunks(4){let mut word=[0u8;4];word[..chunk.len()].copy_from_slice(chunk);self.word(u32::from_le_bytes(word))}}
    fn status(&mut self,error:Option<String>){match error{None=>self.word(1),Some(error)=>{self.word(0);self.string(&error)}}}
    fn settings(&mut self,s:&bindings::input::AirSettings){for v in s.state.body_spin_over_time_320.x{self.float(v)}for v in s.state.body_spin_over_time_320.y{self.float(v)}for v in[s.state.landing_normal_blend_388,s.state.body_spin_scale_428,s.state.landing_normal_angle_limit_444,s.steering_blend]{self.float(v)}for v in s.grind_lock_distance{self.float(v)}}
}
fn main(){
    let args:Vec<_>=std::env::args().collect();
    let stock=Collections::load(std::path::Path::new(&args[1])).unwrap();
    let variant=Collections::load(std::path::Path::new(&args[2])).unwrap();
    let mut settings=bindings::input::AirSettings::load(&stock).unwrap();let mut out=Output::default();out.settings(&settings);
    for _ in 0..2{let error=match bindings::input::AirSettings::load(&variant){Ok(next)=>{settings=next;None},Err(error)=>Some(error)};out.status(error);out.settings(&settings)}
    let error=match bindings::input::AirSettings::load(&stock){Ok(next)=>{settings=next;None},Err(error)=>Some(error)};out.status(error);out.settings(&settings);
    let bytes:Vec<_>=out.0.into_iter().flat_map(u32::to_le_bytes).collect();std::io::stdout().write_all(&bytes).unwrap();
}
