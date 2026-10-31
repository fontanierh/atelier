//! ATGEST01 sets preserve authored set, pattern and point order, including names.
use crate::core::input::gesture::{Pattern, Recognizer};
use hakuba_skate_schema::{Error, Reader};

#[derive(Clone, Debug, PartialEq)]
pub struct GestureSet {
    pub name: String,
    pub stick: usize,
    pub patterns: Vec<Pattern>,
}
pub fn from_bytes(bytes: &[u8]) -> Result<Vec<GestureSet>, String> {
    decode(bytes).map_err(|e| e.to_string())
}
fn decode(bytes: &[u8]) -> Result<Vec<GestureSet>, Error> {
    let mut r = Reader::new(bytes, b"ATGEST01")?;
    let count = r.word()? as usize;
    if count > r.remaining() / 12 {
        return Err(Error("invalid gesture set count".into()));
    }
    let mut sets = Vec::with_capacity(count);
    for _ in 0..count {
        let name = r.string()?.to_owned();
        let stick = r.word()? as usize;
        let count = r.word()? as usize;
        if stick > 1 || count > r.remaining() / 12 {
            return Err(Error("invalid gesture stick or pattern count".into()));
        }
        let mut patterns = Vec::with_capacity(count);
        for _ in 0..count {
            let name = r.string()?.to_owned();
            let tolerance_squared = r.float()?;
            let count = r.word()? as usize;
            if !(2..=15).contains(&count) || count > r.remaining() / 8 {
                return Err(Error("invalid gesture point count".into()));
            }
            let mut points = Vec::with_capacity(count);
            for _ in 0..count {
                points.push([r.float()?, r.float()?]);
            }
            patterns.push(Pattern { name, points, tolerance_squared });
        }
        Recognizer::new(patterns.clone()).map_err(Error)?;
        sets.push(GestureSet { name, stick, patterns });
    }
    r.end()?;
    Ok(sets)
}
