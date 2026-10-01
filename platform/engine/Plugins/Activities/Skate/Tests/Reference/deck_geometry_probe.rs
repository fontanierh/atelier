use skate_core::{math::{Basis3,Vector3},physics::{mass::*,drive_frames::RetailAffineTransform,rigid_body::RetailBodyMassProperties}};
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=self.words[self.at];self.at+=1;v}fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn frame(&mut self)->RetailAffineTransform{RetailAffineTransform{basis:Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))},translation:self.vector()}}
 fn settings(&mut self)->DeckGeometrySettings{DeckGeometrySettings{width:self.float(),mid_length:self.float(),thickness:self.float(),back_end_size:self.float(),front_end_angle_degrees:self.float(),back_end_angle_degrees:self.float(),end_capsule_count:self.word() as i32,enable_deck_volume_collisions:self.word()!=0,enable_end_volume_collisions:self.word()!=0}}
 fn child(&mut self)->DeckChild{let kind=self.word();let p:[u32;14]=std::array::from_fn(|_|self.word());let f=|n:usize|f32::from_bits(p[n]);let shape=match kind{
  0=>DeckShape::RoundedBox{half_extents:Vector3::new(f(0),f(1),f(2)),radius:f(3)},1=>DeckShape::Capsule{radius:f(0),half_length:f(1)},2=>DeckShape::Sphere{radius:f(0)},
  3=>DeckShape::Triangle{vertices:std::array::from_fn(|n|Vector3::new(f(n*3),f(n*3+1),f(n*3+2))),fatness:f(9),edge_cosines:[f(10),f(11),f(12)],volume_flags:p[13]},_=>panic!("shape")};
  DeckChild{shape,transform:self.frame(),collision_enabled:self.word()!=0}}
}
fn floats(out:&mut Vec<u32>,values:impl IntoIterator<Item=f32>){out.extend(values.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn body(out:&mut Vec<u32>,b:RetailBodyMassProperties){for c in b.local_mass_frame.basis.columns{floats(out,c);}vector(out,b.local_mass_frame.translation);let d=b.dynamics;vector(out,d.inverse_tensor);floats(out,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
fn moments(out:&mut Vec<u32>,m:MassMoments){for c in m.columns{floats(out,c);}}
fn child(out:&mut Vec<u32>,c:DeckChild){let mut p=Vec::new();let kind=match c.shape{
 DeckShape::RoundedBox{half_extents,radius}=>{vector(&mut p,half_extents);floats(&mut p,[radius]);0},
 DeckShape::Capsule{radius,half_length}=>{floats(&mut p,[radius,half_length]);1},
 DeckShape::Sphere{radius}=>{floats(&mut p,[radius]);2},
 DeckShape::Triangle{vertices,fatness,edge_cosines,volume_flags}=>{for v in vertices{vector(&mut p,v);}floats(&mut p,[fatness]);floats(&mut p,edge_cosines);p.push(volume_flags);3}};
 p.resize(14,0);out.push(kind);out.extend(p);for axis in c.transform.basis.columns{floats(out,axis);}vector(out,c.transform.translation);out.push(c.collision_enabled as u32);moments(out,c.mass_moments());}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);
 let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();let count=i.word();
 for _ in 0..count{match i.word(){
  0=>{let stock=i.word()!=0;let mut s=i.settings();if stock{s=DeckGeometrySettings::STOCK;}let mass=i.float();let drag=i.float();
   floats(&mut out,[s.width,s.mid_length,s.thickness,s.back_end_size,s.front_end_angle_degrees,s.back_end_angle_degrees]);out.extend([s.end_capsule_count as u32,s.enable_deck_volume_collisions as u32,s.enable_end_volume_collisions as u32]);
   let d=DeckGeometry::new(s);out.push(d.children.len() as u32);for c in &d.children{child(&mut out,*c);}moments(&mut out,d.mass_moments());body(&mut out,deck_mass_properties(&d,mass,drag));},
  1=>{let c=i.child();child(&mut out,c);},
  2=>{for b in default_skateboard_mass_properties(){body(&mut out,b);}},_=>panic!("operation")}}
 assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
