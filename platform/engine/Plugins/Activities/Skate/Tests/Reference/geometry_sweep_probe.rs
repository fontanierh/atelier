//! Temporary frozen-source oracle for the complete triangle-segment dispatcher.
use std::io::{Read,Write};
use math::Vector3;
use physics::triangle_query::{TriangleLineHit,triangle_segment};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let word=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;word}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->Vector3 {Vector3::new(self.scalar(),self.scalar(),self.scalar())}
}
fn word(out:&mut Vec<u8>,value:u32) {out.extend(value.to_le_bytes());}
fn scalar(out:&mut Vec<u8>,value:f32) {word(out,value.to_bits());}
fn vector(out:&mut Vec<u8>,value:Vector3) {scalar(out,value.x);scalar(out,value.y);scalar(out,value.z);}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();
    let mut reader=Reader{bytes,at:0};let count=reader.word();let mut out=Vec::new();
    for index in 0..count {
        let mut result=TriangleLineHit{position:reader.vector(),normal:reader.vector(),fraction:reader.scalar(),
            volume_parameter:std::array::from_fn(|_|reader.scalar())};
        let start=reader.vector();let direction=reader.vector();let vertices=std::array::from_fn(|_|reader.vector());
        let line_radius=reader.scalar();let triangle_fatness=reader.scalar();
        let found=triangle_segment(&mut result,start,direction,vertices,line_radius,triangle_fatness);
        word(&mut out,index);word(&mut out,u32::from(found));vector(&mut out,result.position);vector(&mut out,result.normal);
        scalar(&mut out,result.fraction);for lane in result.volume_parameter {scalar(&mut out,lane);}
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&out).unwrap();
}
