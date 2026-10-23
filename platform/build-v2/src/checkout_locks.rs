//! Checkout-specific nonblocking build and content locks. Callers own waits/deadlines.
//! Persistent lock inodes are never removed, including during journal cleanup.
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};

pub const INSTALL_METADATA: &str = "build/build-v2/install";

#[derive(Debug)]
pub enum LockError {
    Busy,
    RecoveryRequired,
    Io(io::Error),
}
impl fmt::Display for LockError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Busy => formatter.write_str("checkout lock is busy"),
            Self::RecoveryRequired => {
                formatter.write_str("checkout install journal requires exclusive recovery")
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
}

struct HeldLock {
    checkout: PathBuf,
    metadata: PathBuf,
    file: File,
}

impl HeldLock {
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
    name: &str,
    shared: bool,
) -> Result<HeldLock, LockError> {
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
    Ok(HeldLock {
        checkout: checkout.into(),
        metadata: metadata.into(),
        file,
    })
}

impl CheckoutLocks {
    pub fn open(checkout: impl AsRef<Path>) -> Result<Self, LockError> {
        if !fs::symlink_metadata(checkout.as_ref())?.is_dir() {
            return Err(invalid("checkout root is not a real directory").into());
        }
        let checkout = checkout.as_ref().canonicalize()?;
        let mut metadata = checkout.clone();
        for component in INSTALL_METADATA.split('/') {
            metadata.push(component);
            directory(&metadata)?;
        }
        Ok(Self { checkout, metadata })
    }

    pub fn try_build_exclusive(&self) -> Result<BuildGuard, LockError> {
        Ok(BuildGuard(acquire(
            &self.checkout,
            &self.metadata,
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
        let lock = acquire(&self.checkout, &self.metadata, "content.lock", true)?;
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
        Ok(ContentWriteGuard {
            _lock: acquire(self.root(), self.metadata(), "content.lock", false)?,
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
