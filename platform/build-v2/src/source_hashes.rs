//! Hash hints for already-frozen source versions. No live filesystem I/O.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Snapshot-provider stat token. No field participates in semantic unit identity.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileVersion {
    pub device: u64,
    pub inode: u64,
    pub size: u64,
    pub mtime_ns: i64,
    pub ctime_ns: i64,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct HashStats {
    pub versions_hashed: u64,
    pub bytes_hashed: u64,
    pub memo_hits: u64,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub enum LoadStatus {
    #[default]
    Empty,
    Restored,
    Discarded,
}

#[derive(Default)]
pub struct SourceHashCache {
    entries: BTreeMap<ViewVersion, String>,
    pub stats: HashStats,
    pub load_status: LoadStatus,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct CacheEntry {
    version: ViewVersion,
    digest: String,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ViewVersion {
    file: FileVersion,
    selector: Option<String>,
    encoding_version: u32,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Payload {
    schema: u32,
    entries: Vec<CacheEntry>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    payload: Payload,
    checksum: String,
}

impl SourceHashCache {
    /// @cc [owner:fontanierh,label:correctness] source-version-hash-hints
    /// Hints MUST match device, inode, size and nanosecond mtime/ctime, not mtime alone.
    /// Missing hints MUST hash the frozen bytes. Stat tokens MUST NOT enter semantic
    /// keys. Providers MUST bind tokens to those same frozen bytes; A6 owns live
    /// edit revalidation. See tests/keys.rs.
    pub fn digest(
        &mut self,
        version: Option<&FileVersion>,
        bytes: &[u8],
    ) -> Result<String, String> {
        if let Some(version) = version {
            if version.size != bytes.len() as u64 {
                return Err("source version size differs from frozen bytes".into());
            }
        }
        Ok(self.digest_view(
            version.map(|file| ViewVersion {
                file: file.clone(),
                selector: None,
                encoding_version: 0,
            }),
            bytes,
        ))
    }

    pub fn digest_selected(
        &mut self,
        version: Option<&FileVersion>,
        source_size: u64,
        selector: &str,
        encoding_version: u32,
        bytes: &[u8],
    ) -> Result<String, String> {
        if version.is_some_and(|version| version.size != source_size) {
            return Err("source version size differs from frozen selector source".into());
        }
        Ok(self.digest_view(
            version.map(|file| ViewVersion {
                file: file.clone(),
                selector: Some(selector.into()),
                encoding_version,
            }),
            bytes,
        ))
    }

    fn digest_view(&mut self, version: Option<ViewVersion>, bytes: &[u8]) -> String {
        if let Some(digest) = version
            .as_ref()
            .and_then(|version| self.entries.get(version))
        {
            self.stats.memo_hits = self.stats.memo_hits.saturating_add(1);
            return digest.clone();
        }
        let digest = sha256(bytes);
        self.stats.versions_hashed = self.stats.versions_hashed.saturating_add(1);
        self.stats.bytes_hashed = self.stats.bytes_hashed.saturating_add(bytes.len() as u64);
        if let Some(version) = version {
            self.entries.insert(version, digest.clone());
        }
        digest
    }

    pub fn to_bytes(&self) -> Vec<u8> {
        let payload = Payload {
            schema: 1,
            entries: self
                .entries
                .iter()
                .map(|(version, digest)| CacheEntry {
                    version: version.clone(),
                    digest: digest.clone(),
                })
                .collect(),
        };
        let checksum = sha256(&serde_json::to_vec(&payload).expect("finite source-cache metadata"));
        serde_json::to_vec(&Record { payload, checksum }).expect("finite source-cache metadata")
    }

    /// A missing/corrupt hint index becomes an empty cache, never an invented hit.
    /// Checksums detect damaged records; they are not a hostile-input trust boundary.
    pub fn from_bytes(bytes: Option<&[u8]>) -> Self {
        let Some(bytes) = bytes else {
            return Self::default();
        };
        let restore = || -> Option<BTreeMap<ViewVersion, String>> {
            let record: Record = serde_json::from_slice(bytes).ok()?;
            if record.payload.schema != 1
                || sha256(&serde_json::to_vec(&record.payload).ok()?) != record.checksum
            {
                return None;
            }
            let mut entries = BTreeMap::new();
            for entry in record.payload.entries {
                if !valid_digest(&entry.digest)
                    || entries.insert(entry.version, entry.digest).is_some()
                {
                    return None;
                }
            }
            Some(entries)
        };
        match restore() {
            Some(entries) => Self {
                entries,
                load_status: LoadStatus::Restored,
                ..Self::default()
            },
            None => Self {
                load_status: LoadStatus::Discarded,
                ..Self::default()
            },
        }
    }
}
