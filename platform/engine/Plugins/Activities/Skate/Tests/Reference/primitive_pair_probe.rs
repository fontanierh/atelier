// Appended to the frozen crate root; all original numerical modules unchanged.
use std::io::{Read,Write};
use math::{Basis3,Vector3};
use physics::collision::Sphere;
use physics::world_contact::{ContactPrimitive,transform_triangle_volume,PrimitivePairSettings,primitive_pair_contacts};
struct Reader{bytes:Vec<u8>,at:usize}
impl Reader{
 fn word(&mut self)->u32{let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
 fn scalar(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.scalar(),self.scalar(),self.scalar())}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.scalar()))}}
 fn primitive(&mut self)->ContactPrimitive{match self.word(){
  0=>ContactPrimitive::Sphere(Sphere{center:self.vector(),radius:self.scalar()}),
  1=>ContactPrimitive::Capsule{center:self.vector(),axis:self.vector(),half_length:self.scalar(),radius:self.scalar()},
  2=>{let vertices=std::array::from_fn(|_|self.vector());let fat=self.scalar();let cosines=std::array::from_fn(|_|self.scalar());let flags=self.word();let basis=self.basis();let position=self.vector();ContactPrimitive::Triangle(transform_triangle_volume(vertices,fat,cosines,flags,basis,position))},
  3=>ContactPrimitive::RoundedBox{center:self.vector(),basis:self.basis(),half_extents:self.vector(),radius:self.scalar()},_=>panic!("Primitive pair kind")}}
 fn settings(&mut self)->PrimitivePairSettings{PrimitivePairSettings{padding_a:self.scalar(),padding_b:self.scalar(),additional_padding:self.scalar(),edge_cos_bend_normal_threshold:self.scalar(),convexity_epsilon:self.scalar()}}
}
fn vector(out:&mut Vec<u32>,v:Vector3){out.extend([v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Reader{bytes,at:0};let mut out=Vec::new();let n=i.word();
 for index in 0..n{let op=i.word();out.extend([index,op]);match op{
  0=>{let s=PrimitivePairSettings::skater_self_collision();out.extend([s.padding_a,s.padding_b,s.additional_padding,s.edge_cos_bend_normal_threshold,s.convexity_epsilon].map(f32::to_bits));},
  1=>{let a=i.primitive();let b=i.primitive();let s=i.settings();let hit=primitive_pair_contacts(a,b,s);out.push(hit.is_some() as u32);if let Some(r)=hit{vector(&mut out,r.normal);out.push(r.count as u32);for p in r.points{vector(&mut out,p.a);vector(&mut out,p.b);}}else{out.extend([0;100]);}},_=>panic!("Primitive pair operation")}}
 assert_eq!(i.at,i.bytes.len());std::io::stdout().write_all(&out.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
