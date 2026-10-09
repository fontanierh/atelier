use std::io::{Read,Write};
use skate_core::player::wipeout::{Frame,Requests,Settings};
mod original{use crate::Frame;
// ORIGINAL_FORCE
}
fn main(){
 let mut bytes=vec![];std::io::stdin().read_to_end(&mut bytes).unwrap();
 let mut words=bytes.chunks_exact(4).map(|v|u32::from_le_bytes(v.try_into().unwrap()));
 let count=words.next().unwrap();let mut output=std::io::BufWriter::new(std::io::stdout().lock());
 for _ in 0..count{
  // Only regions_force is consumed by force; the full original Frame type is
  // retained, with valid zero representations for every unconsumed field.
  let mut frame:Frame=unsafe{std::mem::zeroed()};
  frame.regions_force=std::array::from_fn(|_|f32::from_bits(words.next().unwrap()));
  let body=f32::from_bits(words.next().unwrap());let arms=f32::from_bits(words.next().unwrap());
  output.write_all(&(original::force(&frame,body,arms)as u32).to_le_bytes()).unwrap();
 }
 assert!(words.next().is_none());
}
