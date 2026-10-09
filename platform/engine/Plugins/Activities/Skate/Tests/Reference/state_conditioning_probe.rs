pub use skate_core::{animation,physics,point_graph};
use skate_core::animation::output::attributes::AttributeName;
use std::io::{Read,Write};
mod filtered {
// ORIGINAL_FILTERED
    pub fn cache(s:&FilteredState)->GrindState{s.cached_grind}
    pub fn seed(s:&mut FilteredState,raw:[u32;9],grind:GrindState){
        s.cached_grind=grind;s.category=category(raw[0]);s.previous_category=category(raw[1]);s.previous_physics_state=raw[2] as i32;s.air_count=raw[3] as i32;s.nonspecific_count=raw[4] as i32;s.nonspecific_collision_free_count=raw[5] as i32;s.nonspecific_collision_count=raw[6] as i32;s.frames_since_ground_stairs=raw[7] as i32;s.must_change=raw[8]!=0;
    }
    fn category(v:u32)->FilteredCategory{match v{0=>FilteredCategory::Invalid,1=>FilteredCategory::Ground,2=>FilteredCategory::Air,3=>FilteredCategory::Grind,4=>FilteredCategory::Wipeout,5=>FilteredCategory::Teleport,6=>FilteredCategory::Offboard,7=>FilteredCategory::OffboardAir,_=>panic!("bad fixture category")}}
}
use skate_core::animation::landing_quality as landing;
mod loader {
// ORIGINAL_LOADER
}
struct Input{bytes:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn float(&mut self)->f32{f32::from_bits(self.word())}
    fn vector(&mut self)->[f32;4]{std::array::from_fn(|_|self.float())}
    fn name(&mut self)->AttributeName{AttributeName(std::array::from_fn(|_|self.word()))}
    fn guid(&mut self)->u64{let low=self.word();u64::from(low)|(u64::from(self.word())<<32)}
    fn grind(&mut self)->filtered::GrindState{filtered::GrindState{kind:self.word() as i32,scorable_id:self.word() as i32,name:self.name(),scoring_name:self.name(),on_front:self.word()!=0,crouch:self.float(),pathed_guid:self.guid(),local_guid:self.guid()}}
    fn settings(&mut self)->landing::Settings{let mut graph=||point_graph::PointGraph{x:std::array::from_fn(|_|self.float()),y:std::array::from_fn(|_|self.float())};landing::Settings{twist_spin:graph(),side_speed:graph()}}
}
#[derive(Default)]struct Output(Vec<u8>);
impl Output{
    fn word(&mut self,v:u32){self.0.extend(v.to_le_bytes())}fn float(&mut self,v:f32){self.word(v.to_bits())}
    fn string(&mut self,v:&str){self.word(v.len() as u32);self.0.extend(v.bytes());while self.0.len()%4!=0{self.0.push(0)}}
    fn grind(&mut self,g:filtered::GrindState){self.word(g.kind as u32);self.word(g.scorable_id as u32);for x in g.name.0{self.word(x)}for x in g.scoring_name.0{self.word(x)}self.word(g.on_front as u32);self.float(g.crouch);self.word(g.pathed_guid as u32);self.word((g.pathed_guid>>32) as u32);self.word(g.local_guid as u32);self.word((g.local_guid>>32) as u32)}
    fn settings(&mut self,s:&landing::Settings){for g in [&s.twist_spin,&s.side_speed]{for x in g.x{self.float(x)}for y in g.y{self.float(y)}}}
    fn landing(&mut self,l:&landing::Output){self.float(l.landing_adjust_80);self.float(l.sideways_speed_84);self.float(l.forward_speed_88);self.float(l.spin_92);self.word(l.landing_type_96);self.word(l.landing_data_167 as u32)}
    fn state(&mut self,s:&filtered::FilteredState){for w in [s.category as u32,s.previous_category as u32,s.previous_physics_state as u32,s.air_count as u32,s.nonspecific_count as u32,s.nonspecific_collision_free_count as u32,s.nonspecific_collision_count as u32,s.frames_since_ground_stairs as u32,s.must_change as u32]{self.word(w)}self.grind(filtered::cache(s))}
    fn filtered(&mut self,f:Option<filtered::FilteredStateOutput>){self.word(f.is_some() as u32);if let Some(s)=f{self.word(s.category as u32);self.word(s.previous_category as u32);self.word(s.grinding as u32);self.grind(s.grind);self.float(s.last_grind_distance)}}
}
fn main()->Result<(),String>{
    let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1]))?;
    let mut settings=landing::Settings{twist_spin:point_graph::PointGraph{x:[-0.731,-0.317,0.137,0.731],y:[0.517,0.113,-0.137,0.317]},side_speed:point_graph::PointGraph{x:[-0.731,-0.317,0.137,0.731],y:[0.517,0.113,-0.137,0.317]}};
    let mut out=Output::default();match loader::load(&data){Ok(s)=>{settings=landing::Settings{twist_spin:s.twist_spin,side_speed:s.side_speed};out.word(1);out.string("")},Err(e)=>{out.word(0);out.string(&e)}}out.settings(&settings);
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).map_err(|e|e.to_string())?;let mut i=Input{bytes,at:0};let programs=i.word();out.word(programs);
    for p in 0..programs{let mut state=filtered::FilteredState::default();let mut publication=None;let mut landing=landing::Output::default();let mut current=settings;let count=i.word();for n in 0..count{let op=i.word();match op{
        0=>{state.reset();publication=None},
        1=>{let raw=std::array::from_fn(|_|i.word());let grind=i.grind();filtered::seed(&mut state,raw,grind)},
        2=>{let input=filtered::FilteredStateInput{physics_category:i.word() as i32,physics_state:i.word() as i32,anything_in_contact:i.word()!=0,physics_surface_type:i.word() as i32,wall_ride_exit:i.word()!=0,targeting_grind:i.word()!=0,offboard_has_landed:i.word()!=0,offboard_on_deck:i.word()!=0,grind:i.grind(),last_grind_distance:i.float()};publication=Some(state.update(input))},
        3=>landing=landing::Output{landing_adjust_80:i.float(),sideways_speed_84:i.float(),forward_speed_88:i.float(),spin_92:i.float(),landing_type_96:i.word(),landing_data_167:i.word()!=0},
        4=>{let input=landing::Input{previous_filtered_state:i.word(),filtered_state:i.word(),ground_normal:i.vector(),deck_velocity:i.vector(),flipped:i.word()!=0,reckoning_forward:i.vector(),air_spin:i.float()};landing.update(input,&current)},
        5=>current=i.settings(),6=>landing=landing::Output::default(),_=>return Err("invalid opcode".into())
    }out.word(p);out.word(n);out.word(op);out.state(&state);out.filtered(publication);out.landing(&landing);out.settings(&current)}}
    if i.at!=i.bytes.len(){return Err("unconsumed input".into())}std::io::stdout().write_all(&out.0).map_err(|e|e.to_string())
}
