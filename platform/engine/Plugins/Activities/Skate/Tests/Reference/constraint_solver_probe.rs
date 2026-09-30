// Original frozen packed solver is the oracle, with no kernel modifications.
use skate_core::physics::solver::packed::{self,Constraint,Reaction};
use std::io::{Read,Write};
struct Input { words:Vec<u32>, at:usize }
impl Input {
 fn word(&mut self)->u32 {let value=self.words[self.at];self.at+=1;value}
 fn words<const N:usize>(&mut self)->[u32;N]{std::array::from_fn(|_|self.word())}
 fn constraints<const N:usize>(&mut self,n:usize)->Vec<Constraint<N>>{(0..n).map(|_|Constraint{reaction_a:self.word() as usize,reaction_b:self.word() as usize,words:self.words()}).collect()}
}
fn main(){
 std::panic::set_hook(Box::new(|_|{}));
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);
 let mut input=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();
 let count=input.word();for _ in 0..count{
  let nr=input.word() as usize;let nc=input.word() as usize;let nj=input.word() as usize;let nd=input.word() as usize;
  let iterations=input.word();let repeat=input.word();
  let mut reactions:Vec<Reaction>=(0..nr).map(|_|input.words()).collect();
  let mut contacts=input.constraints::<64>(nc);let mut joints=input.constraints::<96>(nj);let mut drives=input.constraints::<96>(nd);
  for _ in 0..repeat {
   let ok=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||packed::solve(&mut contacts,&mut joints,&mut drives,&mut reactions,iterations))).is_ok();
   out.push(u32::from(ok));
   for c in &contacts{out.extend(c.words);}for c in &joints{out.extend(c.words);}for c in &drives{out.extend(c.words);}
   for r in &reactions{out.extend(r);}
  }
 }
 assert_eq!(input.at,input.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
