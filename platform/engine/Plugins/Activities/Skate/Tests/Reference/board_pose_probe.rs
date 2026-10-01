//! Original public board/part pose operations with optional live records and all carry lanes.
use std::io::{Read,Write};
use physics::board_pose::{PartPose,orthonormalize_rotation,orthonormalize_part_basis,part_transform,set_part_transform,set_board_transform};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn part(&mut self)->PartPose {let mask=self.word();let transform=self.words();let local=self.words();let body=self.words();let inertia=self.words();PartPose{transform,local_mass_frame:(mask&1!=0).then_some(local),body:(mask&2!=0).then_some(body),inertia:(mask&4!=0).then_some(inertia)}}
}
fn part(out:&mut Vec<u32>,p:&PartPose) {out.push(p.local_mass_frame.is_some() as u32|((p.body.is_some() as u32)<<1)|((p.inertia.is_some() as u32)<<2));out.extend(p.transform);out.extend(p.local_mass_frame.unwrap_or([0;16]));out.extend(p.body.unwrap_or([0;44]));out.extend(p.inertia.unwrap_or([0;10]));}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut result=Vec::new();
    for index in 0..count {
        let op=reader.word();let mut out=Vec::new();
        match op {
            0=>out.extend(orthonormalize_rotation(reader.words())),1=>out.extend(orthonormalize_part_basis(reader.words())),
            2=>{let mut p=reader.part();out.extend(part_transform(&p));let n=reader.word();out.push(n);for _ in 0..n{set_part_transform(&mut p,reader.words());part(&mut out,&p);out.extend(part_transform(&p));}},
            3=>{let mut parts:[PartPose;7]=std::array::from_fn(|_|reader.part());let mut hook=reader.part();let n=reader.word();out.push(n);for _ in 0..n{set_board_transform(&mut parts,&mut hook,reader.words());for p in &parts{part(&mut out,p);out.extend(part_transform(p));}part(&mut out,&hook);out.extend(part_transform(&hook));}},
            _=>panic!("Invalid board pose operation"),
        }
        result.extend([index,op,out.len() as u32]);result.extend(out);
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&result.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
