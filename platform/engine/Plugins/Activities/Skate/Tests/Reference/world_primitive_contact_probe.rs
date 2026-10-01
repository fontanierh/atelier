//! Public original typed primitive contacts and transformed Volume geometry.
use std::io::{Read,Write};
use math::{Basis3,Vector3};
use physics::collision::{Sphere,Triangle,WorldContactSettings,world_separation_limit};
use physics::world_contact::{ContactPrimitive,triangle_from_volume,transform_triangle_volume,primitive_triangle_world_contacts};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->Vector3 {Vector3::new(self.scalar(),self.scalar(),self.scalar())}
    fn basis(&mut self)->Basis3 {Basis3{columns:std::array::from_fn(|_|std::array::from_fn(|_|self.scalar()))}}
    fn triangle(&mut self,transformed:bool)->Triangle {
        let vertices=std::array::from_fn(|_|self.vector());let fatness=self.scalar();let cosines=std::array::from_fn(|_|self.scalar());let flags=self.word();
        if transformed {let basis=self.basis();let translation=self.vector();transform_triangle_volume(vertices,fatness,cosines,flags,basis,translation)}
        else {triangle_from_volume(vertices,fatness,cosines,flags)}
    }
    fn primitive(&mut self)->ContactPrimitive {
        match self.word() {
            0=>ContactPrimitive::Sphere(Sphere{center:self.vector(),radius:self.scalar()}),
            1=>ContactPrimitive::Capsule{center:self.vector(),axis:self.vector(),half_length:self.scalar(),radius:self.scalar()},
            2=>ContactPrimitive::Triangle(self.triangle(true)),
            3=>ContactPrimitive::RoundedBox{center:self.vector(),basis:self.basis(),half_extents:self.vector(),radius:self.scalar()},
            _=>panic!("Invalid contact primitive"),
        }
    }
    fn settings(&mut self)->WorldContactSettings {WorldContactSettings{volume_padding:self.scalar(),maximum_separating_distance:self.scalar(),edge_cos_bend_normal_threshold:self.scalar(),convexity_epsilon:self.scalar(),is_object:self.word()!=0}}
}
fn vector(out:&mut Vec<u32>,v:Vector3) {out.extend([v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}
fn triangle(out:&mut Vec<u32>,t:Triangle) {
    for v in t.vertices {vector(out,v);}vector(out,t.feature.normal);for e in t.feature.edges {vector(out,e);}out.push(t.feature.flags);
    out.extend(t.feature.edge_cosines.map(f32::to_bits));out.extend(t.edge_lengths.map(f32::to_bits));out.push(t.fatness.to_bits());
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut out=Vec::new();
    for index in 0..count {
        let op=reader.word();out.extend([index,op]);
        match op {
            0=>{let velocity=reader.vector();let normal=reader.vector();let padding=reader.scalar();let maximum=reader.scalar();out.push(world_separation_limit(velocity,normal,padding,maximum).to_bits());},
            1=>triangle(&mut out,reader.triangle(true)),
            2=>{
                let primitive=reader.primitive();let t=reader.triangle(false);let velocity=reader.vector();let settings=reader.settings();
                let result=primitive_triangle_world_contacts(primitive,t,velocity,settings);out.push(result.is_some() as u32);
                if let Some(result)=result {vector(&mut out,result.normal);out.push(result.count as u32);for pair in result.points {vector(&mut out,pair.a);vector(&mut out,pair.b);}}
                else {out.extend([0;100]);}
            },
            _=>panic!("Invalid primitive contact operation"),
        }
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&out.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
