//! ATPHYS01 keeps all 28 bone words and 64-bit record offsets unchanged.
use super::{PhysicsBone, PhysicsSkeleton};
use hakuba_skate_schema::{Error, Reader};
use std::collections::BTreeSet;

pub fn from_bytes(bytes: &[u8], expected_bank: &str) -> Result<Vec<PhysicsSkeleton>, String> {
    decode(bytes, expected_bank).map_err(|e| e.to_string())
}
fn decode(bytes: &[u8], expected_bank: &str) -> Result<Vec<PhysicsSkeleton>, Error> {
    let mut r = Reader::new(bytes, b"ATPHYS01")?;
    if r.string()? != expected_bank {
        return Err(Error("physics skeleton bank identity differs from animation data".into()));
    }
    let count = r.word()? as usize;
    if count > r.remaining() / 16 {
        return Err(Error("invalid physical skeleton count".into()));
    }
    let mut skeletons = Vec::with_capacity(count);
    let mut names = BTreeSet::new();
    for _ in 0..count {
        let name = r.string()?.to_owned();
        let source_offset = r.wide()?;
        let count = r.word()? as usize;
        if !names.insert(name.clone()) || !(1..=255).contains(&count) || count > r.remaining() / 124 {
            return Err(Error("invalid physical bone count or repeated skeleton name".into()));
        }
        let mut bones = Vec::with_capacity(count);
        let mut bone_names = BTreeSet::new();
        for _ in 0..count {
            let name = r.string()?.to_owned();
            let source_offset = r.wide()?;
            let mut words = [0; 28];
            for word in &mut words {
                *word = r.word()?;
            }
            if !bone_names.insert(name.clone())
                || [8, 9, 10, 12, 13, 14, 15, 16, 17, 18].iter().any(|&i| !f32::from_bits(words[i]).is_finite())
            {
                return Err(Error("repeated physical bone or nonfinite transform".into()));
            }
            bones.push(PhysicsBone { name, source_offset, words });
        }
        skeletons.push(PhysicsSkeleton { name, source_offset, bones });
    }
    r.end()?;
    Ok(skeletons)
}
