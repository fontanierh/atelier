//! Public prism callbacks; all frozen numerical modules remain unchanged.
use std::io::{Read,Write};
use physics::world_contact::{closest_feature_segment,intersect_point_face,clamp_point_to_feature,clip_segment_to_feature,
    intersect_feature_segments,intersect_segment_face,intersect_feature_corner_edge,find_feature_intersection_prism};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};
    let count=reader.word();let mut out=Vec::new();
    for index in 0..count {
        let op=reader.word();out.extend([index,op]);
        match op {
            0=>{let segment=reader.words();let mut point=reader.words();out.push(closest_feature_segment(&segment,&mut point));out.extend(point);},
            2=>{let face=reader.words();let normal=reader.words();let mut point=reader.words();out.push(clamp_point_to_feature(&face,normal,&mut point));out.extend(point);},
            3=>{
                let face=reader.words();let segment=reader.words();let normal=reader.words();let mut interval=reader.words();let mut outside=reader.words();
                out.push(clip_segment_to_feature(&face,&segment,normal,&mut interval,&mut outside));out.extend(interval);out.extend(outside);
            },
            1|4|5|6|7=>{
                let mut output=reader.words();let mut a=reader.words();let mut b=reader.words();let normal=reader.words();
                let result=match op {
                    1=>intersect_point_face(&mut output,&mut a,&b,normal,reader.word()!=0),
                    4=>intersect_feature_segments(&mut output,&mut a,&mut b,normal,reader.word()!=0),
                    5=>intersect_segment_face(&mut output,&mut a,&mut b,normal,reader.word()!=0),
                    6=>{let corner=reader.word() as usize;let edge=reader.word() as usize;intersect_feature_corner_edge(&mut output,&mut a,&mut b,corner,edge,reader.word()!=0)},
                    7=>find_feature_intersection_prism(&mut output,&mut a,&mut b,normal),
                    _=>unreachable!(),
                };
                out.push(result);out.extend(output);out.extend(a);out.extend(b);
            },
            _=>panic!("Invalid prism operation"),
        }
    }
    assert_eq!(reader.at,reader.bytes.len());
    std::io::stdout().write_all(&out.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
