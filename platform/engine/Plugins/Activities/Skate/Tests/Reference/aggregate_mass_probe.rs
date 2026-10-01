use skate_core::{math::{Basis3,Vector3},physics::{mass::*,rigid_body::{RetailBodyMassProperties,RetailLocalMassFrame}}};
use std::io::{Read,Write};
struct Input{words:Vec<u32>,at:usize}
impl Input{
 fn word(&mut self)->u32{let v=self.words[self.at];self.at+=1;v}fn float(&mut self)->f32{f32::from_bits(self.word())}
 fn vector(&mut self)->Vector3{Vector3::new(self.float(),self.float(),self.float())}
 fn basis(&mut self)->Basis3{Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn moments(&mut self)->MassMoments{MassMoments{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.float()))}}
 fn shape(&mut self)->MassShape{let kind=self.word();let radius=self.float();let half_length=self.float();let padding=self.float();let half_extents=self.vector();match kind{0=>MassShape::Sphere{radius},1=>MassShape::Capsule{radius,half_length},2=>MassShape::RoundedBox{radius,half_extents},3=>MassShape::Cylinder{radius,half_length,padding},_=>MassShape::Unsupported}}
}
fn floats(out:&mut Vec<u32>,values:impl IntoIterator<Item=f32>){out.extend(values.into_iter().map(f32::to_bits));}
fn vector(out:&mut Vec<u32>,v:Vector3){floats(out,[v.x,v.y,v.z]);}
fn frame(out:&mut Vec<u32>,f:RetailLocalMassFrame){for c in f.basis.columns{floats(out,c);}vector(out,f.translation);}
fn body(out:&mut Vec<u32>,b:RetailBodyMassProperties){frame(out,b.local_mass_frame);let d=b.dynamics;vector(out,d.inverse_tensor);floats(out,[d.inverse_mass,d.spherical,d.maximum_linear_velocity,d.maximum_angular_velocity,d.linear_drag,d.angular_drag]);}
fn moments(out:&mut Vec<u32>,m:MassMoments){for c in m.columns{floats(out,c);}}
fn main(){
 let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();assert_eq!(bytes.len()%4,0);
 let mut i=Input{words:bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect(),at:0};let mut out=Vec::new();
 let count=i.word();for _ in 0..count{match i.word(){
  0=>{let input=PartMassInput{shape:i.shape(),requested_mass:i.float()};let velocity=i.float();let drag=i.float();
   if let Some(p)=forward_mass_properties(input){out.push(1);vector(&mut out,p.primitive.moments_per_unit_mass);floats(&mut out,[p.primitive.volume,p.mass]);vector(&mut out,p.principal_moments);}else{out.push(0);}
   if let Some(b)=primitive_mass_properties(input,velocity,drag){out.push(1);body(&mut out,b);}else{out.push(0);}
  },
  1=>{let mut total=MassMoments::ZERO;let children=i.word();for _ in 0..children{let shape=i.shape();let basis=i.basis();let translation=i.vector();let mut child=MassMoments::from_primitive(primitive_mass(shape).unwrap());moments(&mut out,child);child.transform(basis,translation);moments(&mut out,child);total.add(child);moments(&mut out,total);}
   let mass=i.float();let velocity=i.float();let drag=i.float();let mut reduced=total;let p=reduced.principal_properties();moments(&mut out,reduced);floats(&mut out,[p.volume]);frame(&mut out,p.local_mass_frame);vector(&mut out,p.moments_per_unit_mass);body(&mut out,aggregate_mass_properties(total,mass,velocity,drag));
  },
  2=>{let mut m=i.moments();let basis=i.basis();let translation=i.vector();let child=i.moments();m.transform(basis,translation);moments(&mut out,m);m.add(child);moments(&mut out,m);},
  3=>{let stock=i.word()!=0;let mut wheel=WheelMassSettings{radius:i.float(),mass:i.float(),mass_factor:i.float()};let mut truck=TruckMassSettings{wheel_radius:i.float(),wheel_x_distance:i.float(),radius_scalar:i.float(),half_height_scalar:i.float(),mass:i.float(),mass_factor:i.float()};if stock{wheel=WheelMassSettings::STOCK;truck=TruckMassSettings::STOCK;}
   floats(&mut out,[wheel.radius,wheel.mass,wheel.mass_factor,truck.wheel_radius,truck.wheel_x_distance,truck.radius_scalar,truck.half_height_scalar,truck.mass,truck.mass_factor]);let w=wheel_mass_input(wheel);let t=truck_mass_input(truck);
   if let MassShape::Sphere{radius}=w.shape{floats(&mut out,[radius,w.requested_mass]);}else{panic!("wheel shape");}if let MassShape::Capsule{radius,half_length}=t.shape{floats(&mut out,[radius,half_length,t.requested_mass]);}else{panic!("truck shape");}
   body(&mut out,wheel_mass_properties(wheel));body(&mut out,truck_mass_properties(truck));
  },_=>panic!("operation")
 }}assert_eq!(i.at,i.words.len());let mut stdout=std::io::BufWriter::new(std::io::stdout().lock());for word in out{stdout.write_all(&word.to_le_bytes()).unwrap();}
}
