// SPDX-License-Identifier: Apache-2.0
use std::io::{Read,Write};
use skate_core::player::wipeout::{Requests,RequestInput};
struct Input {words:Vec<u32>,at:usize}
impl Input {
    fn word(&mut self)->u32 {let w=self.words[self.at];self.at+=1;w}
    fn float(&mut self)->f32 {f32::from_bits(self.word())}
}
fn snapshot(out:&mut Vec<u32>,s:&Requests) {
    out.extend(s.reasons.map(u32::from));out.extend(s.values.map(f32::to_bits));
    out.extend([s.count,s.cooldown.to_bits(),s.contact_frames as u32,s.balance.to_bits(),s.mode]);
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();
    let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};
    let mut out=Vec::new();let count=i.word();out.push(count);
    for _ in 0..count {
        let mut s=Requests::new();snapshot(&mut out,&s);let commands=i.word();out.push(commands);
        for _ in 0..commands {
            let op=i.word();out.push(op);match op {
                0=>{s.reasons=std::array::from_fn(|_|i.word()!=0);s.values=std::array::from_fn(|_|i.float());
                    s.count=i.word();s.cooldown=i.float();s.contact_frames=i.word() as i32;s.balance=i.float();s.mode=i.word();},
                1=>s.initialize_player(),2=>s.teleport(),3=>s.enter_ground(),
                4=>{let index=i.word() as usize;let value=i.float();s.request(index,value);},
                5=>s.clear_after_selection(),6=>s.reset_systems(),
                7=>{let f=RequestInput{flags_2468:i.word(),flags_2476:i.word(),flags_2480:i.word(),flags_2484:i.word(),animation_up_y:i.float(),category:i.word()};
                    out.extend([u32::from(s.requests_runout(&f)),u32::from(s.requests_wipeout(&f))]);},
                _=>panic!("Invalid request program")
            };snapshot(&mut out,&s);
        }
    }
    assert_eq!(i.at,i.words.len());let mut o=std::io::BufWriter::new(std::io::stdout().lock());
    for w in out {o.write_all(&w.to_le_bytes()).unwrap();}
}
