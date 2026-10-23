//! Durable write claims and the shared metadata mutex used by publication and future GC.
//! This module never signals processes, expires leases by age, or deletes payload trees.
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);
pub const LEASE_VERSION: u32 = 1;

/// PID alone is insufficient because it can be reused. The lifecycle adapter supplies
/// and probes the same boot/start identity; unavailable identity/liveness stays Unknown.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProcessIdentity {
    pub pid: u32,
    pub boot: String,
    pub started: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Liveness {
    Alive,
    Dead,
    Unknown,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LeaseRecord {
    pub version: u32,
    pub id: String,
    /// Store-relative, exclusively owned namespace; protected before it is created.
    pub staging: String,
    pub owner: ProcessIdentity,
    pub workers: Vec<ProcessIdentity>,
    pub result_keys: BTreeSet<String>,
    pub object_digests: BTreeSet<String>,
    /// Per-unit claims were released only after the required durable root callback.
    /// The process/staging lease still protects unknown or live writers.
    pub rooted: bool,
}

impl LeaseRecord {
    pub fn may_reclaim(&self, mut probe: impl FnMut(&ProcessIdentity) -> Liveness) -> bool {
        // No timestamp participates: even one unknown worker prevents reclamation.
        std::iter::once(&self.owner)
            .chain(self.workers.iter())
            .all(|process| probe(process) == Liveness::Dead)
    }
}

#[derive(Clone, Debug)]
pub struct LeaseStore {
    root: PathBuf,
}

/// Hold this same mutex while inspecting leases and deciding/mutating GC eligibility.
/// Open independently per acquisition: shared File clones do not provide thread exclusion.
pub struct MetadataGuard {
    root: PathBuf,
    _file: File,
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn occupied(path: &Path) -> io::Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error),
    }
}

pub(crate) fn directory(path: &Path) -> io::Result<()> {
    match fs::create_dir(path) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error),
    }
    if !fs::symlink_metadata(path)?.is_dir() {
        return Err(invalid("metadata directory is not a real directory"));
    }
    Ok(())
}

pub(crate) fn sync_dir(path: &Path) -> io::Result<()> {
    File::open(path)?.sync_all()
}

/// Caller owns this namespace and holds the metadata mutex. Atomic replacement is for
/// mutable lease metadata only; immutable result records use exclusive publication.
pub(crate) fn replace_json(path: &Path, value: &impl Serialize) -> io::Result<()> {
    let serial = NEXT.fetch_add(1, Ordering::Relaxed);
    let temporary = path.with_extension(format!("{}-{serial}.tmp", std::process::id()));
    let bytes = serde_json::to_vec(value)?;
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    let result = (|| {
        file.write_all(&bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
        sync_dir(path.parent().unwrap())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

impl LeaseStore {
    /// Root must be the same trusted canonical store root as ObjectStore.
    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref().canonicalize()?;
        directory(&root.join("leases"))?;
        directory(&root.join("staging"))?;
        Ok(Self { root })
    }

    pub fn lock(&self) -> io::Result<MetadataGuard> {
        let mut options = OpenOptions::new();
        options.read(true).write(true).create(true).truncate(false);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600).custom_flags(libc::O_NOFOLLOW);
        }
        let file = options.open(self.root.join("metadata.lock"))?;
        if !file.metadata()?.is_file() {
            return Err(invalid("metadata mutex is not a regular file"));
        }
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            loop {
                if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } == 0 {
                    break;
                }
                let error = io::Error::last_os_error();
                if error.kind() != io::ErrorKind::Interrupted {
                    return Err(error);
                }
            }
        }
        #[cfg(not(unix))]
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "metadata locking requires Unix",
        ));
        Ok(MetadataGuard {
            root: self.root.clone(),
            _file: file,
        })
    }

    /// @cc [owner:fontanierh,label:correctness] lease-before-staging
    /// Begin MUST persist and fsync a unique staging claim before creating any payload
    /// namespace. Unknown digests MUST remain covered by that claim. No time-only expiry
    /// may release it while an owner/worker is alive or unknown. See tests/results.rs.
    pub(crate) fn begin(
        &self,
        result_keys: BTreeSet<String>,
        owner: ProcessIdentity,
        workers: Vec<ProcessIdentity>,
    ) -> io::Result<LeaseRecord> {
        let guard = self.lock()?;
        let id = loop {
            let serial = NEXT.fetch_add(1, Ordering::Relaxed);
            let id = format!("{}-{serial}", std::process::id());
            if !occupied(&guard.path(&id))? && !occupied(&self.root.join("staging").join(&id))? {
                break id;
            }
        };
        let record = LeaseRecord {
            version: LEASE_VERSION,
            staging: format!("staging/{id}"),
            id,
            owner,
            workers,
            result_keys,
            object_digests: BTreeSet::new(),
            rooted: false,
        };
        guard.save(&record)?;
        fs::create_dir(self.root.join(&record.staging))?;
        sync_dir(&self.root.join("staging"))?;
        Ok(record)
    }
}

impl MetadataGuard {
    fn path(&self, id: &str) -> PathBuf {
        self.root.join("leases").join(format!("{id}.json"))
    }

    pub(crate) fn save(&self, record: &LeaseRecord) -> io::Result<()> {
        replace_json(&self.path(&record.id), record)
    }

    /// Enumerate only small lease records under the mutex, never output directories.
    /// Malformed/unknown records fail closed; GC must abort rather than ignore them.
    pub fn leases(&self) -> io::Result<Vec<LeaseRecord>> {
        let mut records = vec![];
        for entry in fs::read_dir(self.root.join("leases"))? {
            let entry = entry?;
            if entry
                .path()
                .extension()
                .is_none_or(|extension| extension != "json")
            {
                continue;
            }
            if !entry.file_type()?.is_file() {
                return Err(invalid("lease is not a regular file"));
            }
            let record: LeaseRecord = serde_json::from_slice(&fs::read(entry.path())?)?;
            if record.version != LEASE_VERSION
                || record.id.is_empty()
                || !record
                    .id
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || byte == b'-')
                || record.staging != format!("staging/{}", record.id)
                || entry.path() != self.path(&record.id)
                || std::iter::once(&record.owner)
                    .chain(record.workers.iter())
                    .any(|identity| {
                        identity.pid == 0 || identity.boot.is_empty() || identity.started.is_empty()
                    })
                || record
                    .result_keys
                    .iter()
                    .chain(record.object_digests.iter())
                    .any(|value| crate::store::ObjectDigest::from_hex(value).is_err())
                || (record.rooted
                    && (!record.result_keys.is_empty() || !record.object_digests.is_empty()))
            {
                return Err(invalid("unsupported or malformed lease"));
            }
            records.push(record);
        }
        records.sort_by(|a, b| a.id.cmp(&b.id));
        Ok(records)
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn dangling_lease_and_staging_names_remain_occupied() {
        use std::os::unix::fs::symlink;
        let serial = NEXT.fetch_add(1, Ordering::Relaxed);
        let root = std::env::temp_dir().join(format!(
            "atelier-v2-lease-names-{}-{serial}",
            std::process::id()
        ));
        let objects = crate::store::ObjectStore::open(&root).unwrap();
        let leases = LeaseStore::open(objects.root()).unwrap();
        let candidate = format!("{}-{}", std::process::id(), NEXT.load(Ordering::Relaxed));
        let lease_path = root.join("leases").join(format!("{candidate}.json"));
        let staging_path = root.join("staging").join(&candidate);
        let missing = root.join("foreign-missing-target");
        symlink(&missing, &lease_path).unwrap();
        symlink(&missing, &staging_path).unwrap();
        assert!(occupied(&lease_path).unwrap());
        assert!(occupied(&staging_path).unwrap());
        let owner = ProcessIdentity {
            pid: 1,
            boot: "boot".into(),
            started: "start".into(),
        };
        let lease = leases
            .begin(BTreeSet::from(["a".repeat(64)]), owner, vec![])
            .unwrap();
        assert_ne!(lease.id, candidate);
        assert_eq!(fs::read_link(&lease_path).unwrap(), missing);
        assert_eq!(fs::read_link(&staging_path).unwrap(), missing);
        fs::remove_dir_all(root).unwrap();
    }
}
