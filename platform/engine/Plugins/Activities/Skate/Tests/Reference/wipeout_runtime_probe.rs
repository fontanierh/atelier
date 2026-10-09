use std::io::{Read,Write};
use skate_core::player::wipeout::{self,Requests};
use skate_core::physics::skeleton_animation_record::AnimationPartTransform;
use skate_core::point_graph::PointGraph;
type WipeoutFrame=wipeout::Frame;
type WipeoutMode=wipeout::Mode;
type WipeoutSettings=wipeout::Settings;
type WipeoutGroundSettings=wipeout::GroundSettings;
type WipeoutAirSettings=wipeout::AirSettings;
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
 fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}
 fn floats<const N:usize>(&mut self)->[f32;N]{std::array::from_fn(|_|self.float())}
 fn matrix(&mut self)->AnimationPartTransform{std::array::from_fn(|_|self.floats())}
 fn curve<const N:usize>(&mut self)->PointGraph<N>{PointGraph{x:self.floats(),y:self.floats()}}
}
struct Output{words:Vec<u32>}
impl Output{
 fn word(&mut self,w:u32){self.words.push(w)}
 fn float(&mut self,v:f32){self.word(v.to_bits())}
 fn words<const N:usize>(&mut self,w:[u32;N]){self.words.extend(w)}
 fn floats<const N:usize>(&mut self,v:[f32;N]){self.words.extend(v.map(f32::to_bits))}
 fn text(&mut self,s:&str){self.word(s.len()as u32);self.words.extend(s.bytes().map(u32::from))}
}
// GENERATED_PROTOCOL
// ORIGINAL_SETTINGS
fn requests(o:&mut Output,s:&Requests){o.words(s.reasons.map(u32::from));o.floats(s.values);o.words([s.count,s.cooldown.to_bits(),s.contact_frames as u32,s.balance.to_bits(),s.mode])}
fn seed(i:&mut Input,s:&mut Requests){s.reasons=std::array::from_fn(|_|i.word()!=0);s.values=i.floats();s.count=i.word();s.cooldown=i.float();s.contact_frames=i.word()as i32;s.balance=i.float();s.mode=i.word();}
fn main(){
 let args:Vec<_>=std::env::args().collect();let data=skate_data::collections::Collections::load(std::path::Path::new(&args[1])).unwrap();let mut o=Output{words:vec![]};
 match original_settings::load(&data){
  Err(e)=>{o.word(0);o.text(&e)},
  Ok((settings,modes))=>{
   o.word(1);o.text("");observe_WipeoutSettings(&mut o,&settings);for m in &modes{observe_WipeoutMode(&mut o,m)}let mut initial=Requests::new();initial.initialize_player();requests(&mut o,&initial);
   if args.len()==2{
    let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let count=i.word();o.word(count);
    for _ in 0..count{let mut s=initial.clone();let mode=i.word()as usize;let commands=i.word();o.word(mode as u32);o.word(commands);
     for _ in 0..commands{let op=i.word();o.word(op);
      if op<=4{let f=read_WipeoutFrame(&mut i);let scalar=i.float();match op{0=>wipeout::check_ground(&mut s,&settings,&modes[mode],&f),1=>wipeout::check_air(&mut s,&settings,&modes[mode],&f,scalar!=0.0),2=>wipeout::check_air_collision(&mut s,&settings,&modes[mode],&f),3=>wipeout::check_plant(&mut s,&settings,&f),4=>wipeout::check_ground_animation(&mut s,&settings,&modes[mode],&f,scalar),_=>unreachable!()};let p=wipeout::RequestInput{flags_2468:f.flags_2468,flags_2476:f.flags_2476,flags_2480:f.flags_2480,flags_2484:f.flags_2484,animation_up_y:f.animation_up[1],category:f.category};o.words([s.requests_runout(&p)as u32,s.requests_wipeout(&p)as u32]);}
      else{match op{5=>seed(&mut i,&mut s),6=>s.clear_after_selection(),7=>s.initialize_player(),8=>s.teleport(),9=>s.reset_systems(),_=>panic!("Unknown wipeout operation")}}requests(&mut o,&s);
     }
    }assert_eq!(i.at,i.words.len());
   }
  }
 }
 let mut output=std::io::BufWriter::new(std::io::stdout().lock());for w in o.words{output.write_all(&w.to_le_bytes()).unwrap()}
}
