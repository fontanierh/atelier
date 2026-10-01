#![allow(non_snake_case)]
use skate_core::player::post_input::*;
use std::io::{Read,Write};
struct Input{bytes:Vec<u8>,at:usize}
impl Input{fn word(&mut self)->u32{let w=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;w}fn float(&mut self)->f32{f32::from_bits(self.word())}}
struct Output{words:Vec<u32>}
impl Output{fn word(&mut self,w:u32){self.words.push(w)}fn float(&mut self,f:f32){self.word(f.to_bits())}}
// GENERATED_PROTOCOL
struct Services{valid:u8,heading:f32,calls:Vec<u32>}
impl PostInputServices for Services{
 fn update_grind_manager_82d8ab08(&mut self){self.calls.push(1)}
 fn update_trajectory_selector_82d68800(&mut self)->u8{self.calls.push(2);self.valid}
 fn calculate_scalar_2740_82db5e10(&mut self)->f32{self.calls.push(3);self.heading}
 fn register_candidate_82762ab0(&mut self,r:CandidateRegistration){self.calls.push(match r{CandidateRegistration::First1888=>4,CandidateRegistration::Second2176=>5})}
}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{bytes,at:0};let mut o=Output{words:vec![]};let cases=i.word();o.word(cases);
 for c in 0..cases{
  let mut player=read_PostInputPlayerFields(&mut i);let mut processed=read_PostInputProcessedFields(&mut i);let mut output=read_PostInputPhysOutFields(&mut i);let mut candidates=read_CandidatePublicationFields(&mut i);let count=i.word();o.word(c);o.word(count);
  for _ in 0..count{
   let op=i.word();o.word(op);
   match op{
    0=>{
     processed.flags_2468=i.word();processed.flags_2472=i.word();processed.flags_2480=i.word();processed.flags_2484=i.word();processed.current_state_2508=i.word();
     output=read_PostInputPhysOutFields(&mut i);candidates=read_CandidatePublicationFields(&mut i);let mut services=Services{valid:i.word()as u8,heading:i.float(),calls:vec![]};
     run_post_input(PostInputContext{player:&mut player,processed:&mut processed,phys_out:&mut output,candidates:&mut candidates},&mut services);
     o.word(services.calls.len()as u32);for call in services.calls{o.word(call)}
     observe_PostInputPlayerFields(&mut o,&player);observe_PostInputProcessedFields(&mut o,&processed);observe_PostInputPhysOutFields(&mut o,&output);observe_CandidatePublicationFields(&mut o,&candidates);
    },
    1=>{let mut destination=std::array::from_fn(|_|i.word());let source=std::array::from_fn(|_|i.word());copy_grab_record_82762ab0(&mut destination,&source);for w in destination{o.word(w)}},
    _=>panic!("opcode")
   }
  }
 }
 assert_eq!(i.at,i.bytes.len());let mut out=std::io::stdout().lock();for w in o.words{out.write_all(&w.to_le_bytes()).unwrap();}
}
