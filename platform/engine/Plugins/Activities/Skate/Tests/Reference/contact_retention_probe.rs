//! Public original contact buffer, geometric reduction and ordered material combine.
use std::io::{Read,Write};
use physics::world_contact::{ContactBuffer,ContactRecord,coplanar_contacts,select_contact_points};
use physics::contact::{RetailContactMaterial,combine_contact_materials};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->[f32;3] {std::array::from_fn(|_|self.scalar())}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn material(&mut self)->RetailContactMaterial {RetailContactMaterial{static_friction:self.scalar(),dynamic_friction:self.scalar(),restitution:self.scalar()}}
}
fn state(out:&mut Vec<u32>,b:&ContactBuffer) {out.extend([b.count,b.flushed,b.capacity,b.dropped,b.distance_squared_threshold.to_bits(),b.allow_flush as u32,b.deferred_reduction as u32,b.full as u32]);}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut result=Vec::new();
    for index in 0..count {
        let op=reader.word();let mut out=Vec::new();
        match op {
            0=>{let a=reader.words();let b=reader.words();out.push(coplanar_contacts(&a,&b) as u32);},
            1=>{
                let n=reader.word();let a:Vec<_>=(0..n).map(|_|reader.vector()).collect();let b:Vec<_>=(0..n).map(|_|reader.vector()).collect();let normal=reader.vector();let mut selected=reader.words();
                out.push(select_contact_points(&a,&b,normal,&mut selected) as u32);out.extend(selected);
            },
            2=>{
                let mut buffer=ContactBuffer{count:reader.word(),flushed:reader.word(),capacity:reader.word(),dropped:reader.word(),distance_squared_threshold:reader.scalar(),allow_flush:reader.word() as u8,deferred_reduction:reader.word() as u8,full:reader.word() as u8,records:std::array::from_fn(|_|reader.words())};
                let mut chunks:Vec<Vec<ContactRecord>>=Vec::new();let mut sink=|rows:&[ContactRecord]|chunks.push(rows.to_vec());let n=reader.word();out.push(n);
                for _ in 0..n {
                    let command=reader.word();let mut slot=None;let mut duplicate=false;
                    match command {
                        0=>{let row=reader.words();let test=reader.word()!=0;slot=buffer.allocate(&mut sink);if let Some(i)=slot {buffer.records[i]=row;if test && buffer.last_is_duplicate() {duplicate=true;buffer.count-=1;}}},
                        1=>buffer.reduce(),2=>buffer.flush(&mut sink),_=>panic!("Invalid retention command"),
                    }
                    out.extend([command,slot.is_some() as u32,slot.map_or(u32::MAX,|i|i as u32),duplicate as u32]);state(&mut out,&buffer);
                }
                state(&mut out,&buffer);for row in buffer.records {out.extend(row);}out.push(chunks.len() as u32);
                for chunk in chunks {out.push(chunk.len() as u32);for row in chunk {out.extend(row);}}
            },
            3=>{let a=reader.material();let b=reader.material();let m=combine_contact_materials(a,b);out.extend([m.static_friction.to_bits(),m.dynamic_friction.to_bits(),m.restitution.to_bits()]);},
            _=>panic!("Invalid retention operation"),
        }
        result.extend([index,op,out.len() as u32]);result.extend(out);
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&result.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
