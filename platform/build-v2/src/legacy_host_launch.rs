//! Owned lightweight scheduler child. NO capacity reservation or aggregate tree guard.
//! Native descendants retain their existing individual admission and custody monitors.
use crate::checkout_locks::{BuildGuard, ContentWriteGuard};
use crate::install_fs::{FileObservation, RootFs};
use crate::leases::ProcessIdentity;
use crate::legacy_epoch::EpochError;
use crate::legacy_epoch::selection::GuardBinding;
use serde::{Deserialize, Serialize};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::time::{Duration, Instant};

static CANCELLED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
extern "C" fn cancel(_: libc::c_int) {
    CANCELLED.store(true, std::sync::atomic::Ordering::Relaxed);
}
pub(crate) fn install_cancellation() -> io::Result<()> {
    CANCELLED.store(false, std::sync::atomic::Ordering::Relaxed);
    for signal in [libc::SIGINT, libc::SIGTERM, libc::SIGHUP] {
        if unsafe { libc::signal(signal, cancel as libc::sighandler_t) } == libc::SIG_ERR {
            return Err(io::Error::last_os_error());
        }
    }
    Ok(())
}
fn cancelled() -> bool {
    CANCELLED.load(std::sync::atomic::Ordering::Relaxed)
}
pub(crate) fn invalid(message: impl ToString) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.to_string())
}
fn duplicate(file: &File) -> io::Result<File> {
    let fd = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct LockIdentity {
    pub role: String,
    pub device: u64,
    pub inode: u64,
}
pub(crate) struct TripleCustody {
    files: [File; 3],
    writer_fs: RootFs,
    writer_path: String,
    identities: [LockIdentity; 3],
}
impl TripleCustody {
    pub(crate) fn acquire(
        build: &BuildGuard,
        write: &ContentWriteGuard,
        output: &Path,
    ) -> io::Result<Self> {
        if !build.owns_writer(write) {
            return Err(invalid("different-root build/content custody"));
        }
        // The first supported route is an explicit real output root inside this checkout.
        let root = build.root().canonicalize()?;
        let output = output.canonicalize()?;
        if !output.starts_with(&root) {
            return Err(invalid("external output root needs explicit authority"));
        }
        let writer_fs = RootFs::open(&output)?;
        writer_fs.mkdirs(".state/retention", 0o700)?;
        let writer_path = ".state/retention/writer.lock".to_string();
        let writer = writer_fs.persistent_lock_file(&writer_path)?;
        if unsafe { libc::flock(writer.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let [build, content] = build
            .duplicate_for_legacy_exec(write)
            .map_err(invalid)?
            .into_host_files();
        let files = [build, content, writer];
        let mut identities_vec = Vec::new();
        for (file, role) in files.iter().zip(["build", "content", "writer"]) {
            let m = file.metadata()?;
            identities_vec.push(LockIdentity {
                role: role.into(),
                device: m.dev(),
                inode: m.ino(),
            });
        }
        let identities: [LockIdentity; 3] = identities_vec
            .try_into()
            .map_err(|_| invalid("lock set incomplete"))?;
        let result = Self {
            files,
            writer_fs,
            writer_path,
            identities,
        };
        result.verify_writer()?;
        Ok(result)
    }
    fn verify_writer(&self) -> io::Result<()> {
        let anchored = self.writer_fs.root_metadata()?;
        let current = RootFs::open(&self.writer_fs.absolute(""))?.root_metadata()?;
        if (anchored.dev(), anchored.ino()) != (current.dev(), current.ino()) {
            return Err(invalid("writer output root replaced"));
        }
        let expected = FileObservation::from_metadata(&self.files[2].metadata()?);
        if !self
            .writer_fs
            .observe(&self.writer_path)?
            .is_some_and(|m| m.same_inode(&expected))
        {
            return Err(invalid("writer lock replaced"));
        }
        Ok(())
    }
    pub(crate) fn identities(&self) -> &[LockIdentity; 3] {
        &self.identities
    }
    fn inherited(&self) -> io::Result<[File; 3]> {
        Ok([
            duplicate(&self.files[0])?,
            duplicate(&self.files[1])?,
            duplicate(&self.files[2])?,
        ])
    }
}
/// Absolute kernel monotonic nanoseconds, not an invocation-relative timeout default.
pub(crate) fn monotonic_ns() -> io::Result<u64> {
    let mut t = std::mem::MaybeUninit::<libc::timespec>::uninit();
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, t.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let t = unsafe { t.assume_init() };
    u64::try_from(t.tv_sec)
        .ok()
        .and_then(|s| s.checked_mul(1_000_000_000))
        .and_then(|v| v.checked_add(t.tv_nsec as u64))
        .ok_or_else(|| invalid("monotonic clock outside range"))
}
pub(crate) fn deadline_instant(absolute: u64) -> io::Result<Instant> {
    let remaining = absolute
        .checked_sub(monotonic_ns()?)
        .filter(|v| *v > 0)
        .ok_or_else(|| invalid("host deadline already expired"))?;
    Instant::now()
        .checked_add(Duration::from_nanos(remaining))
        .ok_or_else(|| invalid("host deadline outside range"))
}
/// Match the existing capacity_protocol process-start/boot representation, never PID alone.
pub(crate) fn process_identity(pid: u32) -> io::Result<ProcessIdentity> {
    if pid == 0 {
        return Err(invalid("missing process identity"));
    }
    #[cfg(target_os = "linux")]
    {
        let raw = fs::read(format!("/proc/{pid}/stat"))?;
        if raw.len() > 4096 {
            return Err(invalid("oversized process identity"));
        }
        let end = raw
            .iter()
            .rposition(|b| *b == b')')
            .ok_or_else(|| invalid("malformed process stat"))?;
        let tail = std::str::from_utf8(&raw[end + 2..]).map_err(invalid)?;
        let values: Vec<_> = tail.split_whitespace().collect();
        if values.len() < 20 || ["Z", "X"].contains(&values[0]) {
            return Err(invalid("process is not live"));
        }
        let start = values[19].parse::<u64>().map_err(invalid)?;
        if start == 0 {
            return Err(invalid("unknown process start"));
        }
        let boot = fs::read_to_string("/proc/sys/kernel/random/boot_id")?
            .trim()
            .to_ascii_lowercase();
        if boot.len() != 36 {
            return Err(invalid("unknown boot identity"));
        }
        Ok(ProcessIdentity {
            pid,
            boot,
            started: start.to_string(),
        })
    }
    #[cfg(target_os = "macos")]
    {
        #[repr(C)]
        struct Usage {
            uuid: [u8; 16],
            values: [u64; 18],
        }
        #[link(name = "proc")]
        unsafe extern "C" {
            fn proc_pid_rusage(pid: i32, flavor: i32, buffer: *mut libc::c_void) -> i32;
        }
        let mut usage = Usage {
            uuid: [0; 16],
            values: [0; 18],
        };
        if unsafe { proc_pid_rusage(pid as i32, 2, &mut usage as *mut _ as *mut libc::c_void) } != 0
        {
            return Err(io::Error::last_os_error());
        }
        if usage.values[8] == 0 || usage.values[9] != 0 {
            return Err(invalid("process start unavailable/exited"));
        }
        let name = std::ffi::CString::new("kern.bootsessionuuid").unwrap();
        let mut bytes = [0u8; 128];
        let mut size = bytes.len();
        if unsafe {
            libc::sysctlbyname(
                name.as_ptr(),
                bytes.as_mut_ptr() as *mut _,
                &mut size,
                std::ptr::null_mut(),
                0,
            )
        } != 0
        {
            return Err(io::Error::last_os_error());
        }
        if size == 0 || size > bytes.len() {
            return Err(invalid("unknown boot identity"));
        }
        let boot = std::str::from_utf8(&bytes[..size])
            .map_err(invalid)?
            .trim_end_matches('\0')
            .to_ascii_lowercase();
        if boot.len() != 36 {
            return Err(invalid("unknown boot identity"));
        }
        Ok(ProcessIdentity {
            pid,
            boot,
            started: usage.values[8].to_string(),
        })
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "host identity unsupported",
        ))
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Custodian {
    schema: u32,
    monitor: ProcessIdentity,
    invocation: String,
    receipts: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Cleanup {
    schema: u32,
    invocation: String,
    boot: String,
    child: (u32, u64),
    monitor: (u32, u64),
    confirmed: bool,
    reason: Option<String>,
}
fn bounded_record<T: serde::de::DeserializeOwned>(
    fs: &RootFs,
    path: &str,
) -> Result<T, EpochError> {
    let mut f = fs.file(path)?;
    let before = FileObservation::from_metadata(&f.metadata()?);
    if before.size > 65536 {
        return Err(EpochError::Invalid);
    }
    let mut bytes = vec![];
    f.by_ref().take(65537).read_to_end(&mut bytes)?;
    if before != FileObservation::from_metadata(&f.metadata()?)
        || fs.observe(path)?.as_ref() != Some(&before)
    {
        return Err(EpochError::Changed);
    }
    let value: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|_| EpochError::Invalid)?;
    if !value.is_object() {
        return Err(EpochError::Invalid);
    }
    serde_json::from_slice(&bytes).map_err(|_| EpochError::Invalid)
}
pub(crate) fn verify_guard_start(fs: &RootFs, binding: &GuardBinding) -> Result<(), EpochError> {
    let c: Custodian = bounded_record(fs, &format!("{}/custodian.json", binding.directory))?;
    if c.schema != 1
        || c.monitor != binding.monitor
        || c.invocation != binding.invocation
        || Path::new(&c.receipts) != fs.absolute(&binding.directory)
    {
        return Err(EpochError::CleanupUnknown);
    }
    if process_identity(binding.child.pid).map_err(EpochError::Io)? != binding.child
        || process_identity(binding.monitor.pid).map_err(EpochError::Io)? != binding.monitor
    {
        return Err(EpochError::CleanupUnknown);
    }
    Ok(())
}
/// Only an exact guard-issued positive receipt counts. Child reap/absence never substitutes.
pub(crate) fn verify_guard_cleanup(fs: &RootFs, binding: &GuardBinding) -> Result<(), EpochError> {
    // Internal pressure requeues may leave several gated roots. This first profile
    // refuses archive chains rather than pretending the final PID covers them all.
    if fs
        .metadata_names(&binding.directory, 256)?
        .iter()
        .any(|n| n.starts_with("lost-offer-"))
    {
        return Err(EpochError::CleanupUnknown);
    }
    let c: Custodian = bounded_record(fs, &format!("{}/custodian.json", binding.directory))?;
    let receipt: Cleanup = bounded_record(fs, &format!("{}/cleanup.json", binding.directory))?;
    let matches =
        |pair: (u32, u64), p: &ProcessIdentity| pair.0 == p.pid && pair.1.to_string() == p.started;
    if c.schema != 1
        || c.monitor != binding.monitor
        || c.invocation != binding.invocation
        || Path::new(&c.receipts) != fs.absolute(&binding.directory)
        || receipt.schema != 1
        || receipt.invocation != binding.invocation
        || receipt.boot != binding.child.boot
        || binding.child.boot != binding.monitor.boot
        || !matches(receipt.child, &binding.child)
        || !matches(receipt.monitor, &binding.monitor)
        || !receipt.confirmed
        || receipt.reason.is_some()
    {
        return Err(EpochError::CleanupUnknown);
    }
    Ok(())
}
pub(crate) fn read_cleanup_binding(
    fs: &RootFs,
    directory: &str,
    invocation: &str,
) -> Result<GuardBinding, EpochError> {
    let receipt: Cleanup = bounded_record(fs, &format!("{directory}/cleanup.json"))?;
    let binding = GuardBinding {
        invocation: invocation.into(),
        directory: directory.into(),
        child: ProcessIdentity {
            pid: receipt.child.0,
            boot: receipt.boot.clone(),
            started: receipt.child.1.to_string(),
        },
        monitor: ProcessIdentity {
            pid: receipt.monitor.0,
            boot: receipt.boot,
            started: receipt.monitor.1.to_string(),
        },
    };
    verify_guard_cleanup(fs, &binding)?;
    Ok(binding)
}

pub(crate) struct SchedulerChild {
    child: Child,
    identity: ProcessIdentity,
    pub requests: std::io::PipeReader,
    pub replies: Option<std::io::PipeWriter>,
    custody: TripleCustody,
    deadline: Instant,
    reaped: bool,
}
impl SchedulerChild {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn spawn(
        interpreter: &Path,
        bootstrap: &Path,
        manifest: &Path,
        checkout: &Path,
        log: &Path,
        custody: TripleCustody,
        deadline: Instant,
    ) -> io::Result<Self> {
        if Instant::now() >= deadline {
            return Err(invalid("host deadline expired"));
        }
        custody.verify_writer()?;
        let (command_reader, command_writer) = std::io::pipe()?;
        let (reply_reader, reply_writer) = std::io::pipe()?;
        let locks = custody.inherited()?;
        let inherited = [
            command_writer.as_raw_fd(),
            reply_reader.as_raw_fd(),
            locks[0].as_raw_fd(),
            locks[1].as_raw_fd(),
            locks[2].as_raw_fd(),
        ];
        let stdout = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(log)?;
        let stderr = stdout.try_clone()?;
        let mut command = Command::new(interpreter);
        command.args(["-I", "-S"]).arg(bootstrap);
        for (name, fd) in [
            "--command-fd",
            "--reply-fd",
            "--build-fd",
            "--content-fd",
            "--writer-fd",
        ]
        .iter()
        .zip(inherited)
        {
            command.arg(name).arg(fd.to_string());
        }
        command
            .arg("--startup-manifest")
            .arg(manifest)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .current_dir(checkout)
            .stdin(Stdio::null())
            .stdout(stdout)
            .stderr(stderr);
        let maximum = unsafe { libc::sysconf(libc::_SC_OPEN_MAX) };
        if maximum < 0 || maximum > 1_048_576 {
            return Err(invalid("cannot bound inherited descriptor closure"));
        }
        // SAFETY: child-only async-signal-safe descriptor flag updates; no parent flags change.
        unsafe {
            command.pre_exec(move || {
                for fd in 3..maximum as RawFd {
                    if !inherited.contains(&fd) {
                        let flags = libc::fcntl(fd, libc::F_GETFD);
                        if flags >= 0
                            && libc::fcntl(fd, libc::F_SETFD, flags | libc::FD_CLOEXEC) < 0
                        {
                            return Err(io::Error::last_os_error());
                        }
                    }
                }
                for fd in inherited {
                    if libc::fcntl(fd, libc::F_SETFD, 0) < 0 {
                        return Err(io::Error::last_os_error());
                    }
                }
                Ok(())
            });
        }
        let mut child = command.spawn()?;
        drop(command_writer);
        drop(reply_reader);
        drop(locks);
        let identity = match process_identity(child.id()) {
            Ok(v) => v,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e);
            }
        };
        Ok(Self {
            child,
            identity,
            requests: command_reader,
            replies: Some(reply_writer),
            custody,
            deadline,
            reaped: false,
        })
    }
    pub(crate) fn identity(&self) -> &ProcessIdentity {
        &self.identity
    }
    pub(crate) fn close_permission_channel(&mut self) {
        self.replies.take();
    }
    pub(crate) fn verify_custody(&self) -> io::Result<()> {
        self.custody.verify_writer()
    }
    pub(crate) fn locks(&self) -> &[LockIdentity; 3] {
        self.custody.identities()
    }
    pub(crate) fn wait(&mut self) -> io::Result<Option<ExitStatus>> {
        if let Some(status) = self.child.try_wait()? {
            self.reaped = true;
            return Ok(Some(status));
        }
        Ok(None)
    }
    pub(crate) fn stop_owned(&mut self) -> io::Result<()> {
        if self.wait()?.is_some() {
            return Ok(());
        }
        // Child handle is unreaped, so this PID cannot be reused. Never signal its group.
        self.child.kill()?;
        Ok(())
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.deadline
    }
}
impl Drop for SchedulerChild {
    fn drop(&mut self) {
        if !self.reaped {
            // Retain original custody while the owned child may still live. No Drop success
            // or guessed cleanup: leaking these FDs on uncertainty is conservative until exit.
            if self.child.try_wait().ok().flatten().is_none() {
                for file in &self.custody.files {
                    if let Ok(copy) = duplicate(file) {
                        std::mem::forget(copy);
                    }
                }
            }
        }
    }
}
/// Deadline-bounded exact pipe reads/writes; no reader thread outlives the authority scope.
pub(crate) fn read_exact(fd: RawFd, bytes: &mut [u8], deadline: Instant) -> io::Result<()> {
    let mut offset = 0;
    while offset < bytes.len() {
        if cancelled() {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "legacy authority cancelled",
            ));
        }
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "host read deadline"))?;
        let ms = remaining.as_millis().min(i32::MAX as u128).max(1) as i32;
        let mut p = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut p, 1, ms) };
        if result < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if result == 0 {
            continue;
        }
        let n = unsafe {
            libc::read(
                fd,
                bytes[offset..].as_mut_ptr() as *mut _,
                bytes.len() - offset,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if n == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "authority channel closed",
            ));
        }
        offset += n as usize;
    }
    Ok(())
}
pub(crate) fn write_all(fd: RawFd, bytes: &[u8], deadline: Instant) -> io::Result<()> {
    let mut offset = 0;
    while offset < bytes.len() {
        if cancelled() {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "legacy authority cancelled",
            ));
        }
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "host write deadline"))?;
        let mut p = libc::pollfd {
            fd,
            events: libc::POLLOUT,
            revents: 0,
        };
        let result = unsafe {
            libc::poll(
                &mut p,
                1,
                remaining.as_millis().min(i32::MAX as u128).max(1) as i32,
            )
        };
        if result < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }
        if result == 0 {
            continue;
        }
        let n = unsafe {
            libc::write(
                fd,
                bytes[offset..].as_ptr() as *const _,
                bytes.len() - offset,
            )
        };
        if n <= 0 {
            return Err(io::Error::last_os_error());
        }
        offset += n as usize;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkout_locks::CheckoutLocks;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    fn root() -> PathBuf {
        let root = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-host-launch-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        fs::create_dir(root.join("out")).unwrap();
        root
    }
    #[test]
    fn triple_custody_duplicates_keep_all_same_descriptions_locked_and_cloexec() {
        let root = root();
        let locks = CheckoutLocks::open(&root).unwrap();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let custody = TripleCustody::acquire(&build, &write, &root.join("out")).unwrap();
        let retained = custody.inherited().unwrap();
        for file in &retained {
            assert_ne!(
                unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
                0
            );
        }
        let writer = OpenOptions::new()
            .read(true)
            .write(true)
            .open(root.join("out/.state/retention/writer.lock"))
            .unwrap();
        assert_ne!(
            unsafe { libc::flock(writer.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(custody);
        drop(write);
        drop(build);
        assert!(locks.try_build_exclusive().is_err());
        assert_ne!(
            unsafe { libc::flock(writer.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(retained);
        let build = locks.try_build_exclusive().unwrap();
        assert_eq!(
            unsafe { libc::flock(writer.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        drop(writer);
        drop(build);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn guard_receipt_requires_unique_correlated_cleanup_and_refuses_pressure_archive_chain() {
        let root = root();
        fs::create_dir(root.join("guard")).unwrap();
        let fs = RootFs::open(&root).unwrap();
        let binding = GuardBinding {
            invocation: "0123456789abcdef0123456789abcdef".into(),
            directory: "guard".into(),
            child: ProcessIdentity {
                pid: 11,
                boot: "boot".into(),
                started: "100".into(),
            },
            monitor: ProcessIdentity {
                pid: 12,
                boot: "boot".into(),
                started: "200".into(),
            },
        };
        assert!(verify_guard_cleanup(&fs, &binding).is_err());
        let custodian = serde_json::json!({"schema":1,"monitor":binding.monitor,"invocation":binding.invocation,"receipts":root.join("guard")});
        let cleanup = serde_json::json!({"schema":1,"invocation":binding.invocation,"boot":"boot","child":[11,100],"monitor":[12,200],"confirmed":true,"reason":null});
        std::fs::write(
            root.join("guard/custodian.json"),
            serde_json::to_vec(&custodian).unwrap(),
        )
        .unwrap();
        std::fs::write(
            root.join("guard/cleanup.json"),
            serde_json::to_vec(&cleanup).unwrap(),
        )
        .unwrap();
        verify_guard_cleanup(&fs, &binding).unwrap();
        assert_eq!(
            read_cleanup_binding(&fs, "guard", &binding.invocation).unwrap(),
            binding
        );
        std::fs::create_dir(root.join("guard/lost-offer-known-1")).unwrap();
        assert!(verify_guard_cleanup(&fs, &binding).is_err());
        std::fs::remove_dir(root.join("guard/lost-offer-known-1")).unwrap();
        let mut wrong = cleanup.clone();
        wrong["monitor"] = serde_json::json!([13, 200]);
        std::fs::write(
            root.join("guard/cleanup.json"),
            serde_json::to_vec(&wrong).unwrap(),
        )
        .unwrap();
        assert!(verify_guard_cleanup(&fs, &binding).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn exact_identity_and_expired_absolute_deadline_never_become_fixture_authority() {
        let identity = process_identity(std::process::id()).unwrap();
        assert_eq!(identity.pid, std::process::id());
        assert!(!identity.started.is_empty());
        assert_eq!(identity.boot.len(), 36);
        assert!(process_identity(0).is_err());
        assert!(deadline_instant(1).is_err());
    }
}
