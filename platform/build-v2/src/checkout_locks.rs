//! Checkout-specific nonblocking build and content locks. Callers own waits/deadlines.
//! Persistent lock inodes are never removed, including during journal cleanup.
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::sync::Arc;

pub const INSTALL_METADATA: &str = "build/build-v2/install";
pub(crate) const LEGACY_EPOCH: &str = "build/build-v2/install/legacy-epoch.json";

/// Presence is intentionally stronger than parsing: foreign, linked or damaged epochs fence.
pub(crate) fn require_no_legacy_epoch(checkout: &Path) -> Result<(), LockError> {
    if crate::install_fs::RootFs::open(checkout)?.occupied(LEGACY_EPOCH)? {
        return Err(LockError::LegacyEpochIncomplete);
    }
    Ok(())
}

#[derive(Debug)]
pub enum LockError {
    Busy,
    RecoveryRequired,
    LegacyEpochIncomplete,
    Io(io::Error),
}
impl fmt::Display for LockError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Busy => formatter.write_str("checkout lock is busy"),
            Self::RecoveryRequired => {
                formatter.write_str("checkout install journal requires exclusive recovery")
            }
            Self::LegacyEpochIncomplete => {
                formatter.write_str("legacy epoch requires same-scope repair")
            }
            Self::Io(error) => error.fmt(formatter),
        }
    }
}
impl std::error::Error for LockError {}
impl From<io::Error> for LockError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

#[derive(Clone, Debug)]
pub struct CheckoutLocks {
    checkout: PathBuf,
    metadata: PathBuf,
    scope: Arc<File>,
}

struct HeldLock {
    checkout: PathBuf,
    metadata: PathBuf,
    file: File,
    scope: Arc<File>,
}

impl HeldLock {
    fn current_identity(&self, name: &str) -> io::Result<bool> {
        let fs = crate::install_fs::RootFs::open(&self.checkout)?;
        let anchored = self.scope.metadata()?;
        let current = fs.root_metadata()?;
        if (anchored.dev(), anchored.ino()) != (current.dev(), current.ino()) {
            return Ok(false);
        }
        let held = self.file.metadata()?;
        Ok(fs
            .observe(&format!("{INSTALL_METADATA}/{name}"))?
            .is_some_and(|now| (now.device, now.inode) == (held.dev(), held.ino())))
    }
    fn duplicate(&self) -> io::Result<File> {
        #[cfg(unix)]
        {
            use std::os::fd::{AsRawFd, FromRawFd};
            let descriptor =
                unsafe { libc::fcntl(self.file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 0) };
            if descriptor < 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(unsafe { File::from_raw_fd(descriptor) })
        }
        #[cfg(not(unix))]
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "checkout custody requires Unix",
        ))
    }
}

/// One build owns a checkout until this guard and every explicitly duplicated
/// custodian descriptor close. No explicit LOCK_UN may invalidate a live custodian.
pub struct BuildGuard(HeldLock);

/// Shared content custody must last through every owned reader's lifetime.
pub struct ContentReadGuard(HeldLock);

pub(crate) struct ContentWriteGuard {
    _lock: HeldLock,
}

/// Private fresh-exec exception only. No caller here changes inheritable flags or launches.
pub(crate) struct LegacyExecCustody {
    build: File,
    content: File,
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn directory(path: &Path) -> io::Result<()> {
    match fs::create_dir(path) {
        Ok(()) => {}
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
        Err(error) => return Err(error),
    }
    if !fs::symlink_metadata(path)?.is_dir() {
        return Err(invalid(
            "checkout metadata ancestor is not a real directory",
        ));
    }
    Ok(())
}

fn acquire(
    checkout: &Path,
    metadata: &Path,
    scope: &Arc<File>,
    name: &str,
    shared: bool,
) -> Result<HeldLock, LockError> {
    let fs = crate::install_fs::RootFs::open(checkout)?;
    let original = scope.metadata()?;
    let current = fs.root_metadata()?;
    if (original.dev(), original.ino()) != (current.dev(), current.ino()) {
        return Err(invalid("checkout root changed after opening locks").into());
    }
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(true).truncate(false);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600).custom_flags(libc::O_NOFOLLOW);
    }
    let file = options.open(metadata.join(name))?;
    if !file.metadata()?.is_file() {
        return Err(invalid("checkout lock is not a regular file").into());
    }
    #[cfg(unix)]
    {
        use std::os::fd::AsRawFd;
        let operation = if shared { libc::LOCK_SH } else { libc::LOCK_EX } | libc::LOCK_NB;
        loop {
            if unsafe { libc::flock(file.as_raw_fd(), operation) } == 0 {
                break;
            }
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if error.kind() == io::ErrorKind::WouldBlock {
                return Err(LockError::Busy);
            }
            return Err(error.into());
        }
    }
    #[cfg(not(unix))]
    return Err(
        io::Error::new(io::ErrorKind::Unsupported, "checkout locking requires Unix").into(),
    );
    let held = HeldLock {
        checkout: checkout.into(),
        metadata: metadata.into(),
        file,
        scope: scope.clone(),
    };
    if !held.current_identity(name)? {
        return Err(invalid("checkout lock identity changed during acquisition").into());
    }
    Ok(held)
}

impl CheckoutLocks {
    pub fn open(checkout: impl AsRef<Path>) -> Result<Self, LockError> {
        if !fs::symlink_metadata(checkout.as_ref())?.is_dir() {
            return Err(invalid("checkout root is not a real directory").into());
        }
        let checkout = checkout.as_ref().canonicalize()?;
        let scope = Arc::new(
            OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&checkout)?,
        );
        let mut metadata = checkout.clone();
        for component in INSTALL_METADATA.split('/') {
            metadata.push(component);
            directory(&metadata)?;
        }
        Ok(Self {
            checkout,
            metadata,
            scope,
        })
    }

    pub fn try_build_exclusive(&self) -> Result<BuildGuard, LockError> {
        Ok(BuildGuard(acquire(
            &self.checkout,
            &self.metadata,
            &self.scope,
            "build.lock",
            false,
        )?))
    }

    /// @cc [owner:fontanierh,label:correctness] checkout-reader-admission
    /// Reader admission MUST acquire shared content custody before checking the journal.
    /// Dirty or malformed install state MUST block readers until exclusive recovery.
    /// No waiting, process launch, install-state mutation or reader-to-writer upgrade is hidden
    /// in admission. See tests/checkout_locks.rs and tests/installs.rs.
    pub fn try_read_content(&self) -> Result<ContentReadGuard, LockError> {
        let lock = acquire(
            &self.checkout,
            &self.metadata,
            &self.scope,
            "content.lock",
            true,
        )?;
        require_no_legacy_epoch(&self.checkout)?;
        match fs::symlink_metadata(self.metadata.join("journal.json")) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(ContentReadGuard(lock)),
            Err(error) => Err(error.into()),
            Ok(_) => Err(LockError::RecoveryRequired),
        }
    }

    pub(crate) fn root(&self) -> &Path {
        &self.checkout
    }
    pub(crate) fn metadata(&self) -> &Path {
        &self.metadata
    }
}

impl BuildGuard {
    pub(crate) fn root(&self) -> &Path {
        &self.0.checkout
    }
    pub(crate) fn metadata(&self) -> &Path {
        &self.0.metadata
    }
    pub(crate) fn try_write_content(&self) -> Result<ContentWriteGuard, LockError> {
        let writer = self.try_legacy_write_content()?;
        require_no_legacy_epoch(self.root())?;
        Ok(writer)
    }

    // Acquiring exclusion is not authority to interpret or mutate an existing epoch.
    // Only legacy_epoch's exact-record verification can issue that authority.
    pub(crate) fn try_legacy_write_content(&self) -> Result<ContentWriteGuard, LockError> {
        Ok(ContentWriteGuard {
            _lock: acquire(
                self.root(),
                self.metadata(),
                &self.0.scope,
                "content.lock",
                false,
            )?,
        })
    }

    pub(crate) fn owns_writer(&self, writer: &ContentWriteGuard) -> bool {
        self.root() == writer._lock.checkout
            && self.metadata() == writer._lock.metadata
            && Arc::ptr_eq(&self.0.scope, &writer._lock.scope)
            && self.0.current_identity("build.lock").unwrap_or(false)
            && writer
                ._lock
                .current_identity("content.lock")
                .unwrap_or(false)
    }

    pub(crate) fn matches_current_root(&self, root: &fs::Metadata) -> bool {
        self.0
            .scope
            .metadata()
            .is_ok_and(|original| (original.dev(), original.ino()) == (root.dev(), root.ino()))
            && self.0.current_identity("build.lock").unwrap_or(false)
    }

    /// @cc [owner:fontanierh,label:safety] legacy-exec-same-description-pair
    /// The private fresh-exec pair MUST require real same-checkout build and EX guards,
    /// atomically duplicate BOTH same open descriptions with CLOEXEC and never unlock,
    /// adopt a raw FD or change inheritable flags. No bootstrap is implemented here.
    /// See legacy_epoch::tests and checkout_locks::tests::legacy_exec_pair_is_same_ofd_and_cloexec.
    pub(crate) fn duplicate_for_legacy_exec(
        &self,
        writer: &ContentWriteGuard,
    ) -> Result<LegacyExecCustody, LockError> {
        if !self.owns_writer(writer) {
            return Err(invalid("legacy writer belongs to another checkout").into());
        }
        Ok(LegacyExecCustody {
            build: self.0.duplicate()?,
            content: writer._lock.duplicate()?,
        })
    }

    /// Explicit custody duplicate: F_DUPFD_CLOEXEC shares the SAME open file description
    /// and sets CLOEXEC. These are BSD flock locks, not fcntl record locks. Guards never
    /// call LOCK_UN: exclusion ends only when the last descriptor for that description
    /// closes. Pass explicitly only to C7's existing monitor/custodian, never workers,
    /// shared services, environment or op inputs. This accessor does not prove C7 custody.
    pub fn duplicate_for_custodian(&self) -> io::Result<File> {
        self.0.duplicate()
    }
}

impl LegacyExecCustody {
    // Only the owned legacy-host launcher consumes this private pair. Never expose it
    // as an ordinary worker pass_fds or raw-guard-adoption constructor.
    pub(crate) fn into_host_files(self) -> [File; 2] {
        [self.build, self.content]
    }
}

impl ContentReadGuard {
    /// Same open file description, CLOEXEC set, and no manual LOCK_UN on guard drop.
    /// The existing monitor must retain the duplicate while any owned reader is alive
    /// or cleanup identity is unknown; ordinary worker processes must not inherit it.
    pub fn duplicate_for_custodian(&self) -> io::Result<File> {
        self.0.duplicate()
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::fd::AsRawFd;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    /// A child spawn briefly duplicates every open descriptor, including a lock one just
    /// released, until exec closes it. Spawning tests hold the write side; tests that assert
    /// an immediate re-acquire hold the read side and can still run in parallel with each other.
    static SPAWN_GATE: std::sync::RwLock<()> = std::sync::RwLock::new(());
    fn spawn_gate_read() -> std::sync::RwLockReadGuard<'static, ()> {
        SPAWN_GATE.read().unwrap_or_else(|error| error.into_inner())
    }
    fn spawn_gate_write() -> std::sync::RwLockWriteGuard<'static, ()> {
        SPAWN_GATE
            .write()
            .unwrap_or_else(|error| error.into_inner())
    }
    struct OwnedChild(std::process::Child);
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
    struct Workspace(PathBuf);
    impl Workspace {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "atelier-v2-locks-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
        fn locks(&self) -> CheckoutLocks {
            CheckoutLocks::open(&self.0).unwrap()
        }
    }
    impl Drop for Workspace {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn checkout_build_and_content_locks_have_independent_lifetimes() {
        let _gate = spawn_gate_read();
        let workspace = Workspace::new();
        let first = workspace.locks();
        let second = workspace.locks();
        let build = first.try_build_exclusive().unwrap();
        assert!(matches!(second.try_build_exclusive(), Err(LockError::Busy)));
        let reader1 = first.try_read_content().unwrap();
        let reader2 = second.try_read_content().unwrap();
        assert!(matches!(build.try_write_content(), Err(LockError::Busy)));
        drop(reader1);
        assert!(matches!(build.try_write_content(), Err(LockError::Busy)));
        drop(reader2);
        let writer = build.try_write_content().unwrap();
        assert!(matches!(first.try_read_content(), Err(LockError::Busy)));
        drop(writer);
        first.try_read_content().unwrap();
        drop(build);
        second.try_build_exclusive().unwrap();
    }
    #[test]
    fn explicit_custody_duplicate_keeps_same_description_and_cloexec() {
        let _gate = spawn_gate_read();
        let workspace = Workspace::new();
        let locks = workspace.locks();
        let build = locks.try_build_exclusive().unwrap();
        let custody = build.duplicate_for_custodian().unwrap();
        assert_ne!(
            unsafe { libc::fcntl(custody.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
        drop(build);
        assert!(matches!(locks.try_build_exclusive(), Err(LockError::Busy)));
        drop(custody);
        let build = locks.try_build_exclusive().unwrap();
        let reader = locks.try_read_content().unwrap();
        let custody = reader.duplicate_for_custodian().unwrap();
        drop(reader);
        assert!(matches!(build.try_write_content(), Err(LockError::Busy)));
        drop(custody);
        build.try_write_content().unwrap();
    }
    #[test]
    fn any_journal_entry_blocks_readers_without_touching_lock_inodes() {
        let _gate = spawn_gate_read();
        let workspace = Workspace::new();
        let locks = workspace.locks();
        let journal = locks.metadata.join("journal.json");
        fs::write(&journal, b"malformed").unwrap();
        assert!(matches!(
            locks.try_read_content(),
            Err(LockError::RecoveryRequired)
        ));
        fs::remove_file(&journal).unwrap();
        std::os::unix::fs::symlink("missing", &journal).unwrap();
        assert!(matches!(
            locks.try_read_content(),
            Err(LockError::RecoveryRequired)
        ));
        fs::remove_file(&journal).unwrap();
        locks.try_read_content().unwrap();
        assert!(locks.metadata.join("content.lock").is_file());
    }
    #[test]
    fn legacy_exec_pair_is_same_ofd_and_cloexec() {
        use std::os::fd::AsRawFd;
        use std::os::unix::fs::MetadataExt;
        let workspace = Workspace::new();
        let locks = workspace.locks();
        let build = locks.try_build_exclusive().unwrap();
        let writer = build.try_legacy_write_content().unwrap();
        let pair = build.duplicate_for_legacy_exec(&writer).unwrap();
        for (original, duplicate) in [
            (&build.0.file, &pair.build),
            (&writer._lock.file, &pair.content),
        ] {
            assert_eq!(
                original.metadata().unwrap().ino(),
                duplicate.metadata().unwrap().ino()
            );
            let flags = unsafe { libc::fcntl(duplicate.as_raw_fd(), libc::F_GETFD) };
            assert!(flags >= 0 && flags & libc::FD_CLOEXEC != 0);
        }
        let foreign = Workspace::new();
        let foreign_locks = foreign.locks();
        let foreign_build = foreign_locks.try_build_exclusive().unwrap();
        let foreign_write = foreign_build.try_legacy_write_content().unwrap();
        assert!(build.duplicate_for_legacy_exec(&foreign_write).is_err());
        drop(writer);
        drop(build);
        assert!(matches!(locks.try_build_exclusive(), Err(LockError::Busy)));
        assert!(matches!(locks.try_read_content(), Err(LockError::Busy)));
        // No immediate post-close acquisition assertion: unrelated concurrent forks may
        // transiently retain CLOEXEC copies, as the separate spawn contract documents.
        drop(pair);

        // Real guards retain their original root anchor, not just its pathname.
        let workspace = Workspace::new();
        let locks = workspace.locks();
        let cloned = locks.clone();
        let build = cloned.try_build_exclusive().unwrap();
        let flags = unsafe { libc::fcntl(build.0.scope.as_raw_fd(), libc::F_GETFD) };
        assert!(flags >= 0 && flags & libc::FD_CLOEXEC != 0);
        let writer = build.try_legacy_write_content().unwrap();
        assert!(build.duplicate_for_legacy_exec(&writer).is_ok());
        let displaced = workspace.0.with_extension("displaced");
        fs::rename(&workspace.0, &displaced).unwrap();
        fs::create_dir(&workspace.0).unwrap();
        assert!(build.duplicate_for_legacy_exec(&writer).is_err());
        assert!(!build.matches_current_root(&fs::metadata(&workspace.0).unwrap()));
        assert!(locks.try_build_exclusive().is_err());
        fs::remove_dir(&workspace.0).unwrap();
        fs::rename(&displaced, &workspace.0).unwrap();
        for name in ["build.lock", "content.lock"] {
            let original = locks.metadata.join(name);
            let displaced = locks.metadata.join(format!("saved-{name}"));
            fs::rename(&original, &displaced).unwrap();
            fs::write(&original, b"replacement lock inode").unwrap();
            assert!(build.duplicate_for_legacy_exec(&writer).is_err());
            fs::remove_file(&original).unwrap();
            fs::rename(&displaced, &original).unwrap();
        }
        assert!(build.duplicate_for_legacy_exec(&writer).is_ok());
    }

    #[test]
    fn real_process_shared_reader_excludes_checkout_writer() {
        let _gate = spawn_gate_write();
        use std::io::{BufRead, BufReader, Write};
        use std::process::{Command, Stdio};
        let workspace = Workspace::new();
        let locks = workspace.locks();
        let build = locks.try_build_exclusive().unwrap();
        let path = locks.metadata.join("content.lock");
        let mut child=OwnedChild(Command::new("python3").args(["-c","import fcntl,signal,sys; signal.alarm(2); f=open(sys.argv[1],'a+'); fcntl.flock(f,fcntl.LOCK_SH); print('held',flush=True); sys.stdin.readline()"])
            .arg(path).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap());
        let mut output = BufReader::new(child.0.stdout.take().unwrap());
        let mut line = String::new();
        output.read_line(&mut line).unwrap();
        assert_eq!(line, "held\n");
        let refused = matches!(build.try_write_content(), Err(LockError::Busy));
        child
            .0
            .stdin
            .take()
            .unwrap()
            .write_all(b"release\n")
            .unwrap();
        assert!(child.0.wait().unwrap().success());
        assert!(refused);
        build.try_write_content().unwrap();
    }
}
