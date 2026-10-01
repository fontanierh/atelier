
use crate::{math::{Vector3,Basis3},physics::{rigid_body::{RetailBodyRates,RetailQuaternion},deck_angular_correction::*}};
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
fn word(&mut self)->u32{let w=self.words[self.at];self.at+=1;w}
fn float(&mut self)->f32{f32::from_bits(self.word())}
fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
fn body(&mut self)->RetailBodyRates{RetailBodyRates{orientation:RetailQuaternion{x:self.float(),y:self.float(),z:self.float(),w:self.float()},basis:self.basis(),world_inverse_inertia:self.basis(),position:self.vector(),linear_velocity:self.vector(),angular_velocity:self.vector(),force_acceleration:self.vector(),torque_acceleration:self.vector(),kinetic_energy:self.float(),cool_down:self.word()}}
}
fn vector(out:&mut Vec<u32>,v:Vector3){out.extend([v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}
fn basis(out:&mut Vec<u32>,b:Basis3){for c in b.columns{out.extend(c.map(f32::to_bits));}}
fn body(out:&mut Vec<u32>,b:RetailBodyRates){out.extend([b.orientation.x,b.orientation.y,b.orientation.z,b.orientation.w].map(f32::to_bits));basis(out,b.basis);basis(out,b.world_inverse_inertia);for v in [b.position,b.linear_velocity,b.angular_velocity,b.force_acceleration,b.torque_acceleration]{vector(out,v);}out.extend([b.kinetic_energy.to_bits(),b.cool_down]);}
fn main(){
let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut i=Input{words:bytes.chunks_exact(4).map(|v|u32::from_le_bytes(v.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
for index in 0..count{let mut b=i.body();let n=i.word();out.extend([index,n,0]);let mark=out.len()-1;let start=out.len();body(&mut out,b);
for _ in 0..n{let op=i.word();out.push(op);match op{0=>apply_axis_displacement(&mut b,i.vector()),1=>apply_limited_displacement(&mut b,i.vector()),2=>apply_angular_displacement(&mut b,i.vector()),3=>apply_ground_body_torque(&mut b),4=>b.angular_velocity=i.vector(),5=>{b.torque_acceleration=i.vector();b.cool_down=i.word();},6=>b.world_inverse_inertia=i.basis(),7=>b.basis=i.basis(),_=>panic!("Deck operation")};body(&mut out,b);}out[mark]=(out.len()-start) as u32;}
assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for w in out{stdout.write_all(&w.to_le_bytes()).unwrap();}}
