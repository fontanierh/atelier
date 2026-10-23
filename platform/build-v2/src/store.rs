//! Immutable content objects only. B2 owns leases, result records and transactions.
//! Store roots are trusted caller-owned directories; sources and object names are checked.
use sha2::{Digest, Sha256};
use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

pub const OBJECT_ALGORITHM: &str = "sha256";
pub const OBJECT_FORMAT_VERSION: u32 = 1;
static NEXT_STAGE: AtomicU64 = AtomicU64::new(0);

/// SHA-256 bytes encoded as exactly 64 lowercase hexadecimal characters.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct ObjectDigest(String);

impl ObjectDigest {
    pub fn from_hex(value: &str) -> Result<Self, StoreError> {
        if value.len() != 64
            || !value
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err(StoreError::InvalidDigest);
        }
        Ok(Self(value.into()))
    }
    pub fn as_hex(&self) -> &str {
        &self.0
    }
}
impl fmt::Display for ObjectDigest {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

#[derive(Debug)]
pub enum StoreError {
    InvalidDigest,
    InvalidFile(&'static str),
    WrongStore,
    Io(io::Error),
    /// There is deliberately no byte-copy fallback for any clone failure.
    Clone(io::Error),
}
impl fmt::Display for StoreError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidDigest => {
                formatter.write_str("object digest must be 64 lowercase SHA-256 hex characters")
            }
            Self::InvalidFile(reason) => write!(formatter, "invalid object file: {reason}"),
            Self::WrongStore => formatter.write_str("prepared object belongs to another store"),
            Self::Io(error) => write!(formatter, "object store: {error}"),
            Self::Clone(error) => {
                write!(formatter, "APFS clone failed (no copy fallback): {error}")
            }
        }
    }
}
impl std::error::Error for StoreError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) | Self::Clone(error) => Some(error),
            _ => None,
        }
    }
}
impl From<io::Error> for StoreError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

#[derive(Clone, Debug)]
pub struct ObjectStore {
    root: PathBuf,
}

/// Unforgeable, single-use frozen snapshot. Dropping it removes only its own staging file.
/// Neither the staged path nor a constructor is public; it cannot certify a caller's digest claim.
#[derive(Debug)]
pub struct PreparedObject {
    root: PathBuf,
    staging: PathBuf,
    staging_dir: PathBuf,
    digest: ObjectDigest,
    size: u64,
    source_mode: u32,
}
impl PreparedObject {
    pub fn digest(&self) -> &ObjectDigest {
        &self.digest
    }
    pub fn size(&self) -> u64 {
        self.size
    }
    pub fn source_mode(&self) -> u32 {
        self.source_mode
    }
}
impl Drop for PreparedObject {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.staging);
        let _ = fs::remove_dir(&self.staging_dir);
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PublishOutcome {
    Published,
    Existing,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PublishedObject {
    pub digest: ObjectDigest,
    pub size: u64,
    /// Payload permissions are metadata, not object identity. B2/B3 must retain and install them.
    pub source_mode: u32,
    pub outcome: PublishOutcome,
}

fn directory(path: &Path) -> Result<(), StoreError> {
    match fs::create_dir(path) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error.into()),
    }
    if !fs::symlink_metadata(path)?.is_dir() {
        return Err(StoreError::InvalidFile(
            "store directory is not a real directory",
        ));
    }
    Ok(())
}

fn immutable(path: &Path) -> Result<fs::Metadata, StoreError> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() {
        return Err(StoreError::InvalidFile("not a regular file"));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o222 != 0 {
            return Err(StoreError::InvalidFile("stored object is writable"));
        }
    }
    Ok(metadata)
}

impl ObjectStore {
    pub fn open(root: impl AsRef<Path>) -> Result<Self, StoreError> {
        fs::create_dir_all(root.as_ref())?;
        if !fs::symlink_metadata(root.as_ref())?.is_dir() {
            return Err(StoreError::InvalidFile(
                "store root is not a real directory",
            ));
        }
        let root = root.as_ref().canonicalize()?;
        directory(&root.join("objects"))?;
        directory(&root.join("objects").join(OBJECT_ALGORITHM))?;
        directory(&root.join("staging"))?;
        Ok(Self { root })
    }
    pub fn root(&self) -> &Path {
        &self.root
    }
    fn object_path(&self, digest: &ObjectDigest) -> PathBuf {
        self.root
            .join("objects")
            .join(OBJECT_ALGORITHM)
            .join(digest.as_hex())
    }

    /// @cc [owner:fontanierh,label:correctness] verified-object-snapshot
    /// Preparation MUST clone the source into an independent owned staging file, freeze it read-only,
    /// and hash those exact frozen bytes once before yielding a publication token. It MUST reject
    /// non-regular sources and clone failures without copying bytes or modifying the source.
    pub fn prepare(&self, source: impl AsRef<Path>) -> Result<PreparedObject, StoreError> {
        let source = source.as_ref();
        let metadata = fs::symlink_metadata(source)?;
        if !metadata.is_file() {
            return Err(StoreError::InvalidFile("source is not a regular file"));
        }
        // Reserve a private directory first, so even a partially failed clone has
        // unambiguous cleanup ownership. Stale or foreign names are never removed.
        let staging_dir = loop {
            let serial = NEXT_STAGE.fetch_add(1, Ordering::Relaxed);
            let path = self
                .root
                .join("staging")
                .join(format!("{}-{serial}", std::process::id()));
            match fs::create_dir(&path) {
                Ok(()) => break path,
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error.into()),
            }
        };
        let mut prepared = PreparedObject {
            root: self.root.clone(),
            staging: staging_dir.join("payload"),
            staging_dir,
            digest: ObjectDigest("0".repeat(64)),
            size: 0,
            source_mode: 0,
        };
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&prepared.staging_dir, fs::Permissions::from_mode(0o700))?;
        }
        native::clone_file(source, &prepared.staging).map_err(StoreError::Clone)?;
        let cloned = fs::symlink_metadata(&prepared.staging)?;
        if !cloned.is_file() {
            return Err(StoreError::InvalidFile(
                "cloned source is not a regular file",
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            prepared.source_mode = cloned.permissions().mode() & 0o777;
            fs::set_permissions(&prepared.staging, fs::Permissions::from_mode(0o444))?;
        }
        #[cfg(not(unix))]
        {
            let mut permissions = fs::metadata(&prepared.staging)?.permissions();
            permissions.set_readonly(true);
            fs::set_permissions(&prepared.staging, permissions)?;
        }
        let mut file = File::open(&prepared.staging)?;
        let mut hasher = Sha256::new();
        let mut buffer = [0; 64 * 1024];
        loop {
            let count = file.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            hasher.update(&buffer[..count]);
            prepared.size += count as u64;
        }
        prepared.digest = ObjectDigest(format!("{:x}", hasher.finalize()));
        file.sync_all()?;
        Ok(prepared)
    }

    /// @cc [owner:fontanierh,label:correctness] first-object-wins
    /// Publication MUST accept only this store's prepared token and atomically publish without
    /// replacing any existing entry. Existing entries MUST be regular and read-only. Neither
    /// publication nor a clone hit may rehash previously verified bytes or scan output folders.
    pub fn publish(&self, prepared: PreparedObject) -> Result<PublishedObject, StoreError> {
        if prepared.root != self.root {
            return Err(StoreError::WrongStore);
        }
        let destination = self.object_path(&prepared.digest);
        let outcome = match native::publish_exclusive(&prepared.staging, &destination) {
            Ok(()) => {
                File::open(destination.parent().unwrap())?.sync_all()?;
                PublishOutcome::Published
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                if immutable(&destination)?.len() != prepared.size {
                    return Err(StoreError::InvalidFile(
                        "existing object has incorrect size",
                    ));
                }
                PublishOutcome::Existing
            }
            Err(error) => return Err(error.into()),
        };
        Ok(PublishedObject {
            digest: prepared.digest.clone(),
            size: prepared.size,
            source_mode: prepared.source_mode,
            outcome,
        })
    }

    /// Clone a trusted recorded object directly. Verification/auditing is a separate B7 operation.
    /// The new file remains read-only; B3 installs permissions from the result metadata explicitly.
    pub fn clone_to(
        &self,
        digest: &ObjectDigest,
        destination: impl AsRef<Path>,
    ) -> Result<(), StoreError> {
        let source = self.object_path(digest);
        immutable(&source)?;
        native::clone_file(&source, destination.as_ref()).map_err(StoreError::Clone)
    }
}

#[cfg(target_os = "macos")]
mod native {
    use std::{ffi::CString, io, os::unix::ffi::OsStrExt, path::Path};
    fn path(path: &Path) -> io::Result<CString> {
        CString::new(path.as_os_str().as_bytes())
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "path contains NUL"))
    }
    pub fn clone_file(source: &Path, destination: &Path) -> io::Result<()> {
        let source = path(source)?;
        let destination = path(destination)?;
        // CLONE_NOFOLLOW prevents a source race from following a replacement symlink.
        let result =
            unsafe { libc::clonefile(source.as_ptr(), destination.as_ptr(), libc::CLONE_NOFOLLOW) };
        if result == 0 {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }
    pub fn publish_exclusive(source: &Path, destination: &Path) -> io::Result<()> {
        let source = path(source)?;
        let destination = path(destination)?;
        let result =
            unsafe { libc::renamex_np(source.as_ptr(), destination.as_ptr(), libc::RENAME_EXCL) };
        if result == 0 {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }
}
#[cfg(not(target_os = "macos"))]
mod native {
    use std::{io, path::Path};
    pub fn clone_file(_: &Path, _: &Path) -> io::Result<()> {
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "APFS clone requires macOS",
        ))
    }
    pub fn publish_exclusive(_: &Path, _: &Path) -> io::Result<()> {
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "exclusive APFS publication requires macOS",
        ))
    }
}
