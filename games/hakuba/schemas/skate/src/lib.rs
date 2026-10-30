//! Bounds-checked little-endian simulation data and an indexed, immutable payload archive.

use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fmt, ops::Range};

pub const PACKAGE_MAGIC: &[u8; 8] = b"ATSKPK01";
pub const PACKAGE_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error(pub String);
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}
impl std::error::Error for Error {}
type Result<T> = std::result::Result<T, Error>;
fn error(message: &str) -> Error {
    Error(message.into())
}

/// A reader never changes float words; `float` merely interprets their IEEE-754 bits.
#[derive(Clone)]
pub struct Reader<'a> {
    data: &'a [u8],
    at: usize,
}
impl<'a> Reader<'a> {
    pub fn new(data: &'a [u8], magic: &[u8; 8]) -> Result<Self> {
        if data.get(..8) != Some(magic.as_slice()) {
            return Err(error("simulation magic differs"));
        }
        Ok(Self { data, at: 8 })
    }
    pub fn take(&mut self, size: usize) -> Result<&'a [u8]> {
        let end = self.at.checked_add(size).ok_or_else(|| error("simulation range overflow"))?;
        let bytes = self.data.get(self.at..end).ok_or_else(|| error("truncated simulation data"))?;
        self.at = end;
        Ok(bytes)
    }
    pub fn word(&mut self) -> Result<u32> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    pub fn int(&mut self) -> Result<i32> {
        Ok(self.word()? as i32)
    }
    pub fn wide(&mut self) -> Result<u64> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }
    pub fn float(&mut self) -> Result<f32> {
        Ok(f32::from_bits(self.word()?))
    }
    pub fn string(&mut self) -> Result<&'a str> {
        let size = self.word()? as usize;
        std::str::from_utf8(self.take(size)?).map_err(|_| error("invalid simulation UTF-8"))
    }
    pub fn position(&self) -> usize {
        self.at
    }
    pub fn remaining(&self) -> usize {
        self.data.len() - self.at
    }
    pub fn end(&self) -> Result<()> {
        if self.at != self.data.len() {
            return Err(error("trailing simulation bytes"));
        }
        Ok(())
    }
}

/// One UTF-8 relative file name, with no implicit normalization or filesystem access.
pub fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && !path.contains(['\\', ':', '\0'])
        && path.split('/').all(|part| !part.is_empty() && part != "." && part != "..")
}

/// Index ranges refer to the original byte allocation, not separately allocated payloads.
#[derive(Debug)]
pub struct Package<'a> {
    bytes: &'a [u8],
    index: BTreeMap<&'a str, Range<usize>>,
}
impl<'a> Package<'a> {
    pub fn parse(bytes: &'a [u8]) -> Result<Self> {
        let mut r = Reader::new(bytes, PACKAGE_MAGIC)?;
        if r.word()? != PACKAGE_VERSION {
            return Err(error("unsupported simulation package version"));
        }
        let count = r.word()? as usize;
        // Every index entry needs a length word, a nonempty path, two u64s and a digest.
        if count == 0 || count > r.remaining() / 53 {
            return Err(error("invalid simulation package count"));
        }
        let mut raw = Vec::with_capacity(count);
        let mut previous = "";
        for _ in 0..count {
            let name = r.string()?;
            if !safe_path(name) || name <= previous {
                return Err(error("simulation paths must be safe, unique and sorted"));
            }
            previous = name;
            let offset = usize::try_from(r.wide()?).map_err(|_| error("package offset too large"))?;
            let size = usize::try_from(r.wide()?).map_err(|_| error("package payload too large"))?;
            let checksum: [u8; 32] = r.take(32)?.try_into().unwrap();
            raw.push((name, offset, size, checksum));
        }
        let mut next = r.position();
        let mut index = BTreeMap::new();
        for (name, offset, size, checksum) in raw {
            if offset != next || size == 0 {
                return Err(error("package payload ranges must be contiguous and nonempty"));
            }
            let end = offset.checked_add(size).ok_or_else(|| error("package range overflow"))?;
            let payload = bytes.get(offset..end).ok_or_else(|| error("truncated package payload"))?;
            if Sha256::digest(payload).as_slice() != checksum {
                return Err(Error(format!("simulation checksum differs: {name}")));
            }
            index.insert(name, offset..end);
            next = end;
        }
        if next != bytes.len() {
            return Err(error("trailing package bytes"));
        }
        Ok(Self { bytes, index })
    }
    pub fn get(&self, path: &str) -> Result<&'a [u8]> {
        self.index
            .get(path)
            .map(|range| &self.bytes[range.clone()])
            .ok_or_else(|| Error(format!("missing simulation payload: {path}")))
    }
    /// The validated absolute payload range in the original archive allocation.
    pub fn range(&self, path: &str) -> Result<Range<usize>> {
        self.index.get(path).cloned().ok_or_else(|| Error(format!("missing simulation payload: {path}")))
    }
    pub fn entries(&self) -> impl Iterator<Item = (&'a str, &'a [u8])> + '_ {
        self.index.iter().map(|(&name, range)| (name, &self.bytes[range.clone()]))
    }
    pub fn len(&self) -> usize {
        self.index.len()
    }
    pub fn is_empty(&self) -> bool {
        self.index.is_empty()
    }
}

/// Archive format: magic, version/count u32; sorted (string, absolute offset/size u64, SHA-256), payload bytes.
pub fn encode(entries: &BTreeMap<String, Vec<u8>>) -> Result<Vec<u8>> {
    if entries.is_empty() {
        return Err(error("empty simulation package"));
    }
    let count = u32::try_from(entries.len()).map_err(|_| error("too many simulation payloads"))?;
    let mut offset: usize = 16;
    for (name, bytes) in entries {
        if !safe_path(name) || bytes.is_empty() {
            return Err(error("invalid simulation payload"));
        }
        u32::try_from(name.len()).map_err(|_| error("payload name too large"))?;
        offset = offset.checked_add(52 + name.len()).ok_or_else(|| error("package index overflow"))?;
    }
    let mut out = Vec::new();
    out.extend(PACKAGE_MAGIC);
    out.extend(PACKAGE_VERSION.to_le_bytes());
    out.extend(count.to_le_bytes());
    for (name, bytes) in entries {
        out.extend((name.len() as u32).to_le_bytes());
        out.extend(name.as_bytes());
        out.extend((offset as u64).to_le_bytes());
        out.extend((bytes.len() as u64).to_le_bytes());
        out.extend(Sha256::digest(bytes));
        offset = offset.checked_add(bytes.len()).ok_or_else(|| error("package size overflow"))?;
    }
    out.reserve(offset - out.len());
    for bytes in entries.values() {
        out.extend(bytes);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn archive_borrows_exact_payloads_and_rejects_corruption() {
        let entries = BTreeMap::from([("a/one".into(), vec![0, 1, 2]), ("b".into(), vec![255, 128])]);
        let bytes = encode(&entries).unwrap();
        let package = Package::parse(&bytes).unwrap();
        assert_eq!(package.len(), 2);
        for (name, data) in &entries {
            assert_eq!(package.get(name).unwrap(), data);
            assert_eq!(&bytes[package.range(name).unwrap()], data);
        }
        let mut corrupt = bytes.clone();
        *corrupt.last_mut().unwrap() ^= 1;
        assert!(Package::parse(&corrupt).is_err());
        assert!(Package::parse(&bytes[..bytes.len() - 1]).is_err());
        let mut trailing = bytes;
        trailing.push(0);
        assert!(Package::parse(&trailing).is_err());
    }
    #[test]
    fn reader_preserves_float_words_and_checks_boundaries() {
        let mut bytes = b"ATTEST01".to_vec();
        bytes.extend(0x80000000u32.to_le_bytes());
        bytes.extend(0x7fc01234u32.to_le_bytes());
        let mut reader = Reader::new(&bytes, b"ATTEST01").unwrap();
        assert_eq!(reader.float().unwrap().to_bits(), 0x80000000);
        assert_eq!(reader.float().unwrap().to_bits(), 0x7fc01234);
        reader.end().unwrap();
        assert!(reader.word().is_err());
    }
    #[test]
    fn unsafe_paths_are_not_normalized() {
        for path in ["", "/a", "a/", "a//b", "../a", "a/./b", "a:b", "a\\b"] {
            assert!(!safe_path(path));
        }
    }
}
