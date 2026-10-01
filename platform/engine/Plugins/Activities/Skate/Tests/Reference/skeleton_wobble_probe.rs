pub mod point_graph{pub use skate_core::point_graph::*;}
pub mod trigonometry{pub use skate_core::trigonometry::*;}
pub mod physics{pub use skate_core::physics::*;}
mod wobble{
// ORIGINAL_CORE
impl Wobble{pub fn selected_curves(&self)->bool{self.selected_landing_curves}}
}
use physics::skeleton_animation_record::AnimationPartTransform as Matrix;
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn matrix(&mut self)->Matrix{std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}
 fn settings(&mut self)->wobble::Settings{
  let mut curve=||point_graph::PointGraph{x:std::array::from_fn(|_|self.float()),y:std::array::from_fn(|_|self.float())};
  wobble::Settings{takeoff_tilt:curve(),landing_tilt:curve(),takeoff_squish:curve(),landing_squish:curve(),maximum_time:self.float()}
 }
}
fn observe(o:&mut Vec<u32>,s:&wobble::Wobble,out:wobble::Output,board:Matrix){
 o.extend([s.active as u32,s.landing as u32,s.time.to_bits(),s.amplitude.to_bits(),s.direction.to_bits(),s.selected_curves() as u32,out.sampled as u32,out.tilt.to_bits(),out.squish.to_bits(),out.remains_active as u32]);for c in board{o.extend(c.map(f32::to_bits));}
}
fn main(){
 let args=std::env::args().collect::<Vec<_>>();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1])).unwrap();
 let curve=|key|{let words=data.words::<20>("physics_deck_wobble","default",key).unwrap().map(f32::from_bits);point_graph::PointGraph{x:words[4..12].try_into().unwrap(),y:words[12..20].try_into().unwrap()}};
 let stock=wobble::Settings{takeoff_tilt:curve("TiltVsTimeTakeOff"),landing_tilt:curve("TiltVsTimeLanding"),takeoff_squish:curve("SquishVsTimeTakeOff"),landing_squish:curve("SquishVsTimeLanding"),maximum_time:data.float("physics_deck_wobble","default","MaxTime").unwrap()};
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|w|u32::from_le_bytes(w.try_into().unwrap())).collect(),at:0};let mut o=Vec::new();let count=i.word();o.push(count);
 for c in 0..count{
  let variant=i.word();let settings=if variant!=0{i.settings()}else{wobble::Settings{takeoff_tilt:stock.takeoff_tilt,landing_tilt:stock.landing_tilt,takeoff_squish:stock.takeoff_squish,landing_squish:stock.landing_squish,maximum_time:stock.maximum_time}};
  let mut state=wobble::Wobble::default();let mut board=i.matrix();o.push(c);for curve in [settings.takeoff_tilt,settings.landing_tilt,settings.takeoff_squish,settings.landing_squish]{o.extend(curve.x.map(f32::to_bits));o.extend(curve.y.map(f32::to_bits));}o.push(settings.maximum_time.to_bits());observe(&mut o,&state,Default::default(),board);
  let commands=i.word();o.push(commands);
  for _ in 0..commands{
   let op=i.word();let mut result=Default::default();match op{
    0=>state=Default::default(),1=>state.trigger(i.word()!=0,i.word()!=0),
    2=>{result=state.update(&settings);wobble::apply(result,&mut board);},
    3=>{state.active=i.word()!=0;state.landing=i.word()!=0;state.time=i.float();state.amplitude=i.float();state.direction=i.float();},
    4=>board=i.matrix(),
    5=>{state.time=0.;state.amplitude=0.;state.direction=1.;state.active=false;state.landing=false;},
    _=>panic!("Unknown wobble command"),
   }o.push(op);observe(&mut o,&state,result,board);
  }
 }
 assert_eq!(i.at,i.words.len());let mut out=std::io::BufWriter::new(std::io::stdout().lock());for word in o{out.write_all(&word.to_le_bytes()).unwrap();}
}
