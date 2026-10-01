//! Original public classification/fixup, including all mutated and inactive contact slots.
use std::io::{Read,Write};
use math::Vector3;
use physics::collision::{TriangleFeature,TriangleFixup,ContactPair,fix_up_triangle};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->Vector3 {Vector3::new(self.scalar(),self.scalar(),self.scalar())}
    fn feature(&mut self)->TriangleFeature {TriangleFeature{normal:self.vector(),edges:std::array::from_fn(|_|self.vector()),flags:self.word(),edge_cosines:std::array::from_fn(|_|self.scalar())}}
}
fn vector(out:&mut Vec<u32>,v:Vector3) {out.extend([v.x.to_bits(),v.y.to_bits(),v.z.to_bits()]);}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut out=Vec::new();
    for index in 0..count {
        let op=reader.word();let feature=reader.feature();let mut normal=reader.vector();out.extend([index,op]);
        match op {
            0=>out.push(feature.classify(normal) as u32),
            1=>{
                let settings=TriangleFixup{reverse:reader.word()!=0,edge_cos_bend_normal_threshold:reader.scalar(),convexity_epsilon:reader.scalar(),is_object:reader.word()!=0};
                let n=reader.word() as usize;let mut contacts:[ContactPair;16]=std::array::from_fn(|_|ContactPair{a:reader.vector(),b:reader.vector()});
                out.push(fix_up_triangle(feature,&mut normal,&mut contacts[..n],settings) as u32);vector(&mut out,normal);
                for pair in contacts {vector(&mut out,pair.a);vector(&mut out,pair.b);}
            },
            _=>panic!("Invalid fixup operation"),
        }
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&out.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
