//! Current project binary settings reader; reflected payload bytes retain big-endian word order.
use super::*;
use hakuba_skate_schema::Reader;
impl Collections {
    pub(crate) fn from_bytes(bytes: &[u8]) -> Result<Self, String> {
        fn decode(bytes: &[u8]) -> Result<Collections, hakuba_skate_schema::Error> {
            let mut r = Reader::new(bytes, b"ATATTR01")?;
            let ns = r.word()? as usize;
            let count = r.word()? as usize;
            if ns > r.remaining() / 4 || count > r.remaining() / 16 {
                return Err(hakuba_skate_schema::Error("Settings dimensions exceed bytes".into()));
            }
            let strings = (0..ns).map(|_| r.string().map(str::to_owned)).collect::<Result<Vec<_>, _>>()?;
            let mut collections = Vec::new();
            let mut identities = std::collections::BTreeSet::new();
            for _ in 0..count {
                let class_name = strings
                    .get(r.word()? as usize)
                    .ok_or_else(|| hakuba_skate_schema::Error("Settings string index".into()))?
                    .clone();
                let key = strings
                    .get(r.word()? as usize)
                    .ok_or_else(|| hakuba_skate_schema::Error("Settings key index".into()))?
                    .clone();
                let parent = strings
                    .get(r.word()? as usize)
                    .ok_or_else(|| hakuba_skate_schema::Error("Settings parent index".into()))?
                    .clone();
                if !identities.insert((
                    crate::data::attrib_hash::numeric_name(&class_name),
                    crate::data::attrib_hash::numeric_name(&key),
                )) {
                    return Err(hakuba_skate_schema::Error("Duplicate settings collection identity".into()));
                }
                let n = r.word()?;
                if n as usize > r.remaining() / 16 {
                    return Err(hakuba_skate_schema::Error("Settings field count exceeds bytes".into()));
                }
                let mut fields = BTreeMap::new();
                for _ in 0..n {
                    let name = strings
                        .get(r.word()? as usize)
                        .ok_or_else(|| hakuba_skate_schema::Error("Settings field index".into()))?
                        .clone();
                    let type_name = strings
                        .get(r.word()? as usize)
                        .ok_or_else(|| hakuba_skate_schema::Error("Settings type index".into()))?
                        .clone();
                    let encoding = r.word()?;
                    let size = r.word()? as usize;
                    let data = if encoding == 1 {
                        String::from_utf8(r.take(size)?.to_vec())
                            .map_err(|_| hakuba_skate_schema::Error("Settings text encoding".into()))?
                    } else if encoding == 0 {
                        let mut bytes = Vec::new();
                        for i in 0..size.div_ceil(4) {
                            let word = r.word()?.to_be_bytes();
                            let n = if i == size / 4 && size % 4 != 0 { size % 4 } else { 4 };
                            bytes.extend_from_slice(&word[4 - n..]);
                        }
                        bytes.iter().map(|b| format!("{b:02x}")).collect()
                    } else {
                        return Err(hakuba_skate_schema::Error("Settings field encoding".into()));
                    };
                    if fields.insert(name, Field { type_name, data }).is_some() {
                        return Err(hakuba_skate_schema::Error("Duplicate settings field".into()));
                    }
                }
                collections.push(Collection {
                    class_name,
                    key,
                    parent,
                    fields,
                    source: String::new(),
                    sha256: String::new(),
                });
            }
            r.end()?;
            Ok(Collections { version: 1, collections })
        }
        decode(bytes).map_err(|e| e.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn byte_and_full_word_fields_retain_payload_endianness() {
        fn word(b: &mut Vec<u8>, w: u32) {
            b.extend(w.to_le_bytes());
        }
        fn text(b: &mut Vec<u8>, s: &str) {
            word(b, s.len() as u32);
            b.extend(s.as_bytes());
        }
        let mut b = b"ATATTR01".to_vec();
        let strings = ["", "EA::Reflection::Bool", "EA::Reflection::Float", "class", "flag", "key", "value"];
        word(&mut b, strings.len() as u32);
        word(&mut b, 1);
        for s in strings {
            text(&mut b, s);
        }
        for w in [3, 5, 0, 2, 4, 1, 0, 1, 1, 6, 2, 0, 4, 0x3f800000] {
            word(&mut b, w);
        }
        let c = Collections::from_bytes(&b).unwrap();
        assert!(c.boolean("class", "key", "flag").unwrap());
        assert_eq!(c.float("class", "key", "value").unwrap().to_bits(), 1f32.to_bits());
        b.pop();
        assert!(Collections::from_bytes(&b).is_err());
    }
}
