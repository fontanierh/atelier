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
use std::path::Path;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::time::Duration;

static CANCELLED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
extern "C" fn cancel(_: libc::c_int) {
    CANCELLED.store(true, std::sync::atomic::Ordering::Relaxed);
}
pub(crate) fn install_cancellation() -> io::Result<()> {
    CANCELLED.store(false, std::sync::atomic::Ordering::Relaxed);
    if unsafe { libc::signal(libc::SIGCHLD, libc::SIG_DFL) } == libc::SIG_ERR {
        return Err(io::Error::last_os_error());
    }
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
/// Fixed operational output directory needed ONLY to acquire the third lock. No
/// arbitrary missing-root creation, discovery import, stamp, Content or payload write.
pub(crate) fn prepare_default_output(
    build: &BuildGuard,
    write: &ContentWriteGuard,
    output: &Path,
    project: &str,
) -> io::Result<()> {
    if !build.owns_writer(write)
        || project.is_empty()
        || project.len() > 128
        || !project
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b"_-".contains(&b))
    {
        return Err(invalid(
            "invalid captured original project/output authority",
        ));
    }
    let fs = RootFs::open(build.root())?;
    let root = build.root().canonicalize()?;
    let relative = output
        .strip_prefix(&root)
        .map_err(|_| invalid("external output root unsupported"))?;
    let relative = relative
        .to_str()
        .ok_or_else(|| invalid("output root must be UTF-8"))?;
    crate::paths::relative_path(relative, true).map_err(invalid)?;
    let default = format!("build/{project}");
    match fs.directory_identity(relative) {
        Ok(Some(_)) => {
            if output.canonicalize()? != output {
                return Err(invalid("aliased output root"));
            }
        }
        Ok(None) => {
            if relative != default {
                return Err(invalid("only a missing default output can be initialized"));
            }
            fs.mkdirs(relative, 0o700)?;
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            if relative != default {
                return Err(invalid("missing output override unsupported"));
            }
            fs.mkdirs(relative, 0o700)?;
        }
        Err(e) => return Err(e),
    }
    if !build.owns_writer(write)
        || root != build.root().canonicalize()?
        || fs.directory_identity(relative)?.is_none()
    {
        return Err(invalid(
            "output root changed during operational initialization",
        ));
    }
    Ok(())
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
pub(crate) const CLOCK_DOMAIN: &str = "posix-clock-monotonic-v1";
/// Shared absolute kernel clock. Never cache a conversion into std::time::Instant:
/// Python time.monotonic uses another numeric origin on Darwin and Instant may differ
/// across suspend. Every remaining-time calculation samples this SAME kernel clock.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Deadline {
    absolute_ns: u64,
}
impl Deadline {
    pub(crate) fn new(absolute_ns: u64, domain: &str) -> io::Result<Self> {
        let value = Self { absolute_ns };
        value.remaining_at(monotonic_ns()?, domain)?;
        Ok(value)
    }
    fn remaining_at(&self, now: u64, domain: &str) -> io::Result<Duration> {
        if domain != CLOCK_DOMAIN {
            return Err(invalid("incompatible absolute clock domain"));
        }
        self.absolute_ns
            .checked_sub(now)
            .filter(|v| *v > 0)
            .map(Duration::from_nanos)
            .ok_or_else(|| {
                io::Error::new(io::ErrorKind::TimedOut, "legacy absolute deadline expired")
            })
    }
    pub(crate) fn remaining(&self) -> io::Result<Duration> {
        self.remaining_at(monotonic_ns()?, CLOCK_DOMAIN)
    }
    pub(crate) fn expired(&self) -> bool {
        self.remaining().is_err()
    }
    pub(crate) fn cap(&self, budget_ns: u64) -> io::Result<Self> {
        if budget_ns == 0 {
            return Err(invalid("zero deadline budget"));
        }
        let absolute_ns = monotonic_ns()?
            .checked_add(budget_ns)
            .ok_or_else(|| invalid("absolute deadline overflow"))?
            .min(self.absolute_ns);
        Self::new(absolute_ns, CLOCK_DOMAIN)
    }
    #[cfg(test)]
    pub(crate) fn after(duration: Duration) -> Self {
        let ns = u64::try_from(duration.as_nanos()).unwrap();
        Self::new(
            monotonic_ns().unwrap().checked_add(ns).unwrap(),
            CLOCK_DOMAIN,
        )
        .unwrap()
    }
}
pub(crate) fn deadline_absolute(absolute: u64) -> io::Result<Deadline> {
    Deadline::new(absolute, CLOCK_DOMAIN)
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
fn raw_guard_record(
    fs: &RootFs,
    path: &str,
    digest: &str,
) -> Result<serde_json::Value, EpochError> {
    let mut file = fs.file(path)?;
    let before = FileObservation::from_metadata(&file.metadata()?);
    if before.size > 65536 {
        return Err(EpochError::Invalid);
    }
    let mut bytes = Vec::new();
    file.by_ref().take(65537).read_to_end(&mut bytes)?;
    if crate::source_hashes::sha256(&bytes) != digest
        || before != FileObservation::from_metadata(&file.metadata()?)
        || fs.observe(path)?.as_ref() != Some(&before)
    {
        return Err(EpochError::Changed);
    }
    crate::py_data::validate_py_data_payload("JsonData", "guard-observation.json", &bytes)
        .map_err(|_| EpochError::Invalid)?;
    let value: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|_| EpochError::Invalid)?;
    if !value.is_object() {
        return Err(EpochError::Invalid);
    }
    Ok(value)
}
fn raw_pair(value: &serde_json::Value) -> Option<(u32, u64)> {
    let a = value.as_array()?;
    if a.len() != 2 {
        return None;
    }
    let pid = u32::try_from(a[0].as_u64()?).ok()?;
    let started = a[1].as_u64()?;
    if pid == 0 || started == 0 {
        return None;
    }
    Some((pid, started))
}
fn matches_pair(value: &serde_json::Value, identity: &ProcessIdentity) -> bool {
    raw_pair(value)
        .is_some_and(|(pid, start)| pid == identity.pid && start.to_string() == identity.started)
}
fn empty(value: &serde_json::Value) -> bool {
    value.as_array().is_some_and(Vec::is_empty)
}
/// Wrapper cleanup/custodian JSON and optional timing diagnostics issue NO authority.
/// Normal-return close is a separate captured-provider attestation, accepted only
/// by FrozenIssuer; here the actual independent raw guard files must agree.
pub(crate) fn verify_raw_guard(
    fs: &RootFs,
    binding: &GuardBinding,
    locks: &[LockIdentity],
    controller: &ProcessIdentity,
) -> Result<(), EpochError> {
    if fs
        .metadata_names(&binding.directory, 256)?
        .iter()
        .any(|n| n.starts_with("lost-offer-"))
    {
        return Err(EpochError::CleanupUnknown);
    }
    let process = raw_guard_record(
        fs,
        &format!("{}/memory-health.json", binding.directory),
        &binding.process_digest,
    )?;
    let tree = raw_guard_record(
        fs,
        &format!("{}/memory-health-tree.json", binding.directory),
        &binding.tree_digest,
    )?;
    let child = &binding.child;
    if binding.monitor.pid == child.pid
        || binding.monitor.boot != child.boot
        || controller.boot != child.boot
        || process["pid"].as_u64() != Some(child.pid as u64)
        || process["process_start"]
            .as_u64()
            .map(|s| s.to_string())
            .as_deref()
            != Some(child.started.as_str())
        || tree["owner"].as_u64() != Some(child.pid as u64)
        || tree["owner_started"]
            .as_u64()
            .map(|s| s.to_string())
            .as_deref()
            != Some(child.started.as_str())
        || !matches_pair(&tree["monitor"], &binding.monitor)
        || !matches_pair(&tree["controller"], controller)
        || tree["cleanup_complete"] != true
        || tree.get("error").is_some()
        || tree.get("termination_reason").is_some()
        || process.get("error").is_some()
        || !matches!(
            process["state"].as_str(),
            Some("running" | "memory_limit" | "test_duration")
        )
        || process["limit_bytes"].as_u64().is_none_or(|n| n == 0)
        || tree["limit_bytes"].as_u64() != process["limit_bytes"].as_u64()
    {
        return Err(EpochError::CleanupUnknown);
    }
    match tree["state"].as_str() {
        Some("child_exited") => {
            if !empty(&tree["processes"])
                || tree["footprint_bytes"].as_u64() != Some(0)
                || tree.get("cleanup_processes").is_some()
                || tree.get("cleanup_footprint_bytes").is_some()
            {
                return Err(EpochError::CleanupUnknown);
            }
        }
        Some("memory_limit" | "test_duration" | "terminated" | "controller_exited") => {
            if !empty(&tree["cleanup_processes"])
                || tree["cleanup_footprint_bytes"].as_u64() != Some(0)
            {
                return Err(EpochError::CleanupUnknown);
            }
        }
        _ => return Err(EpochError::CleanupUnknown),
    }
    if let Some(late) = tree.get("late_reporters") {
        if late["scan_failed"] != false
            || !empty(&late["unresolved"])
            || !empty(&late["unresolved_pids"])
        {
            return Err(EpochError::CleanupUnknown);
        }
    }
    let custody = &tree["custody"];
    if custody["held"] != false || custody["released"] != "cleanup_complete" {
        return Err(EpochError::CleanupUnknown);
    }
    let actual = custody["lock_files"]
        .as_array()
        .ok_or(EpochError::CleanupUnknown)?;
    let mut actual_files = std::collections::BTreeSet::new();
    for item in actual {
        let a = item.as_array().ok_or(EpochError::CleanupUnknown)?;
        if a.len() != 2 {
            return Err(EpochError::CleanupUnknown);
        }
        let pair = (
            a[0].as_u64().ok_or(EpochError::CleanupUnknown)?,
            a[1].as_u64().ok_or(EpochError::CleanupUnknown)?,
        );
        if !actual_files.insert(pair) {
            return Err(EpochError::CleanupUnknown);
        }
    }
    let expected: std::collections::BTreeSet<_> =
        locks.iter().map(|l| (l.device, l.inode)).collect();
    if expected.len() != 3 || actual_files != expected {
        return Err(EpochError::CleanupUnknown);
    }
    Ok(())
}
/// Persisted facts can only be rechecked against the original independently bound
/// controller/lock set. The record stores those below, not a self-derived wrapper.
pub(crate) fn verify_persisted_guard(
    fs: &RootFs,
    binding: &GuardBinding,
) -> Result<(), EpochError> {
    verify_raw_guard(fs, binding, &binding.locks, &binding.controller)
}

/// The production entry is the standalone private binary mode, never an arbitrary
/// threaded embedding. Signal handlers store only an atomic flag and open no FDs.
fn require_single_thread() -> io::Result<()> {
    #[cfg(target_os = "linux")]
    {
        if fs::read_dir("/proc/self/task")?
            .take(2)
            .collect::<io::Result<Vec<_>>>()?
            .len()
            != 1
        {
            return Err(invalid(
                "legacy host requires its standalone single-thread entry",
            ));
        }
    }
    #[cfg(target_os = "macos")]
    {
        #[repr(C)]
        struct TaskInfo {
            times: [u64; 6],
            values: [i32; 12],
        }
        #[link(name = "proc")]
        unsafe extern "C" {
            fn proc_pidinfo(
                pid: i32,
                flavor: i32,
                arg: u64,
                buffer: *mut libc::c_void,
                size: i32,
            ) -> i32;
        }
        let mut info = TaskInfo {
            times: [0; 6],
            values: [0; 12],
        };
        let size = std::mem::size_of::<TaskInfo>();
        if unsafe {
            proc_pidinfo(
                std::process::id() as i32,
                4,
                0,
                &mut info as *mut _ as *mut _,
                size as i32,
            )
        } != size as i32
            || info.values[9] != 1
        {
            return Err(invalid(
                "legacy host requires its standalone single-thread entry",
            ));
        }
    }
    Ok(())
}
#[cfg(any(target_os = "macos", test))]
#[derive(Clone, Copy, Default)]
#[repr(C)]
struct ProcFd {
    fd: i32,
    kind: u32,
}
#[cfg(any(target_os = "macos", test))]
fn validate_fd_inventory(entries: &[ProcFd], bytes: i32) -> io::Result<Vec<RawFd>> {
    let capacity = std::mem::size_of_val(entries);
    let width = std::mem::size_of::<ProcFd>();
    if bytes <= 0 || bytes as usize >= capacity || (bytes as usize) % width != 0 {
        return Err(invalid("incomplete/truncated descriptor inventory"));
    }
    let mut seen = std::collections::BTreeSet::new();
    let mut result = vec![];
    for entry in &entries[..bytes as usize / width] {
        if entry.fd < 0 || !seen.insert(entry.fd) {
            return Err(invalid("invalid/duplicate descriptor inventory"));
        }
        result.push(entry.fd);
    }
    Ok(result)
}
fn parent_fd_inventory(deadline: Deadline) -> io::Result<Vec<RawFd>> {
    deadline.remaining()?;
    require_single_thread()?;
    #[cfg(target_os = "linux")]
    {
        Ok(vec![])
    } // child close_range(CLOEXEC) atomically covers the complete table.
    #[cfg(target_os = "macos")]
    {
        #[link(name = "proc")]
        unsafe extern "C" {
            fn proc_pidinfo(
                pid: i32,
                flavor: i32,
                arg: u64,
                buffer: *mut libc::c_void,
                size: i32,
            ) -> i32;
        }
        let mut capacity = 256usize;
        loop {
            deadline.remaining()?;
            let mut entries = vec![ProcFd::default(); capacity];
            let bytes = std::mem::size_of_val(entries.as_slice());
            let returned = unsafe {
                proc_pidinfo(
                    std::process::id() as i32,
                    1,
                    0,
                    entries.as_mut_ptr() as *mut _,
                    bytes as i32,
                )
            };
            if returned > 0 && returned as usize == bytes {
                capacity = capacity
                    .checked_mul(2)
                    .filter(|n| *n <= 65536)
                    .ok_or_else(|| invalid("descriptor inventory capacity exceeded"))?;
                continue;
            }
            let result = validate_fd_inventory(&entries, returned)?;
            require_single_thread()?;
            return Ok(result);
        }
    }
}
/// Child-only sanitization leaves the Rust spawn error pipe open until exec (CLOEXEC).
/// No soft-limit fallback, close_range(flags=0), UNSHARE or swallowed unknown error.
unsafe fn sanitize_child_fds(inherited: &[RawFd], snapshot: &[RawFd]) -> io::Result<()> {
    #[cfg(target_os = "linux")]
    {
        if unsafe { libc::syscall(libc::SYS_close_range, 3u32, u32::MAX, 1u32 << 2) } != 0 {
            return Err(io::Error::last_os_error());
        }
    }
    #[cfg(target_os = "macos")]
    {
        for fd in snapshot.iter().copied().filter(|fd| *fd >= 3) {
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
            if flags < 0 {
                let e = io::Error::last_os_error();
                if e.raw_os_error() == Some(libc::EBADF) {
                    continue;
                }
                return Err(e);
            }
            if unsafe { libc::fcntl(fd, libc::F_SETFD, flags | libc::FD_CLOEXEC) } < 0 {
                return Err(io::Error::last_os_error());
            }
        }
    }
    #[cfg(target_os = "linux")]
    let _ = snapshot;
    for fd in inherited {
        if unsafe { libc::fcntl(*fd, libc::F_SETFD, 0) } < 0 {
            return Err(io::Error::last_os_error());
        }
    }
    Ok(())
}

pub(crate) struct SchedulerChild {
    child: Child,
    identity: ProcessIdentity,
    pub requests: std::io::PipeReader,
    pub replies: Option<std::io::PipeWriter>,
    custody: TripleCustody,
    deadline: Deadline,
    reaped: bool,
}
pub(crate) fn isolated_command(
    interpreter_role: &Path,
    bootstrap: &Path,
    environment: &crate::legacy_host::OperationalEnvironment,
) -> io::Result<Command> {
    let mut command = Command::new(interpreter_role);
    command.args(["-I", "-S"]).arg(bootstrap);
    environment.apply(&mut command)?;
    Ok(command)
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
        deadline: Deadline,
        environment: &crate::legacy_host::OperationalEnvironment,
    ) -> io::Result<Self> {
        if deadline.expired() {
            return Err(invalid("host deadline expired"));
        }
        custody.verify_writer()?;
        let (command_reader, command_writer) = std::io::pipe()?;
        let (reply_reader, reply_writer) = std::io::pipe()?;
        for fd in [command_reader.as_raw_fd(), reply_writer.as_raw_fd()] {
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
            if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0
            {
                return Err(io::Error::last_os_error());
            }
        }

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
        let mut command = isolated_command(interpreter, bootstrap, environment)?;
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
            .current_dir(checkout)
            .stdin(Stdio::null())
            .stdout(stdout)
            .stderr(stderr);
        // Snapshot AFTER all application pipe/custody/log/config setup. This process
        // has one thread/no FD-creating signal callback; std spawn creates only CLOEXEC
        // internal descriptors afterward. Darwin std pipe's set_cloexec startup window
        // is not claimed atomic and relies on this restricted callgraph.
        let inventory = parent_fd_inventory(deadline)?;
        // SAFETY: child-only syscall/fcntl operations; no allocation or parent flag changes.
        unsafe {
            command.pre_exec(move || sanitize_child_fds(&inherited, &inventory));
        }
        let mut child = command.spawn()?;
        drop(command_writer);
        drop(reply_reader);
        drop(locks);
        let identity = match process_identity(child.id()) {
            Ok(v) => v,
            Err(e) => {
                let _ = child.kill();
                if child.try_wait().ok().flatten().is_none() {
                    std::mem::forget(custody);
                }
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
    pub(crate) fn begin_drain(&mut self, cleanup_budget_ns: u64) -> Deadline {
        begin_permission_drain(&mut self.replies, self.deadline, cleanup_budget_ns)
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
    pub(crate) fn deadline(&self) -> Deadline {
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
/// On ambiguity no second frame can repair a partial ACK. Close permission FIRST,
/// then start actual reserved shutdown; never spend cleanup time draining this pipe.
fn begin_permission_drain(
    pipe: &mut Option<std::io::PipeWriter>,
    overall: Deadline,
    cleanup_budget_ns: u64,
) -> Deadline {
    pipe.take();
    overall.cap(cleanup_budget_ns).unwrap_or(overall)
}

/// Deadline-bounded exact pipe reads/writes; no reader thread outlives the authority scope.
pub(crate) fn read_exact(fd: RawFd, bytes: &mut [u8], deadline: Deadline) -> io::Result<()> {
    let mut offset = 0;
    while offset < bytes.len() {
        if cancelled() {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "legacy authority cancelled",
            ));
        }
        let remaining = deadline.remaining()?;
        let ms = remaining.as_millis().min(100).max(1) as i32;
        let mut p = libc::pollfd {
            fd,
            events: libc::POLLIN,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut p, 1, ms) };
        if result < 0 {
            let e = io::Error::last_os_error();
            if [io::ErrorKind::Interrupted, io::ErrorKind::WouldBlock].contains(&e.kind()) {
                continue;
            }
            return Err(e);
        }
        if result == 0 {
            continue;
        }
        deadline.remaining()?;
        let n = unsafe {
            libc::read(
                fd,
                bytes[offset..].as_mut_ptr() as *mut _,
                bytes.len() - offset,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if [io::ErrorKind::Interrupted, io::ErrorKind::WouldBlock].contains(&e.kind()) {
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
pub(crate) fn write_all(fd: RawFd, bytes: &[u8], deadline: Deadline) -> io::Result<()> {
    let mut offset = 0;
    while offset < bytes.len() {
        if cancelled() {
            return Err(io::Error::new(
                io::ErrorKind::Interrupted,
                "legacy authority cancelled",
            ));
        }
        let remaining = deadline.remaining()?;
        let mut p = libc::pollfd {
            fd,
            events: libc::POLLOUT,
            revents: 0,
        };
        let result = unsafe { libc::poll(&mut p, 1, remaining.as_millis().min(100).max(1) as i32) };
        if result < 0 {
            let e = io::Error::last_os_error();
            if [io::ErrorKind::Interrupted, io::ErrorKind::WouldBlock].contains(&e.kind()) {
                continue;
            }
            return Err(e);
        }
        if result == 0 {
            continue;
        }
        deadline.remaining()?;
        let n = unsafe {
            libc::write(
                fd,
                bytes[offset..].as_ptr() as *const _,
                bytes.len() - offset,
            )
        };
        if n < 0 {
            let e = io::Error::last_os_error();
            if [io::ErrorKind::Interrupted, io::ErrorKind::WouldBlock].contains(&e.kind()) {
                continue;
            }
            return Err(e);
        }
        if n == 0 {
            return Err(io::Error::new(
                io::ErrorKind::WriteZero,
                "legacy reply pipe stopped",
            ));
        }
        offset += n as usize;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::checkout_locks::CheckoutLocks;
    use std::path::PathBuf;
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
        let anchored = RootFs::open(&root).unwrap();
        let child = ProcessIdentity {
            pid: 11,
            boot: "boot".into(),
            started: "100".into(),
        };
        let monitor = ProcessIdentity {
            pid: 12,
            boot: "boot".into(),
            started: "200".into(),
        };
        let controller = ProcessIdentity {
            pid: 13,
            boot: "boot".into(),
            started: "300".into(),
        };
        let locks = vec![
            LockIdentity {
                role: "build".into(),
                device: 1,
                inode: 1,
            },
            LockIdentity {
                role: "content".into(),
                device: 1,
                inode: 2,
            },
            LockIdentity {
                role: "writer".into(),
                device: 1,
                inode: 3,
            },
        ];
        let process =
            serde_json::json!({"pid":11,"process_start":100,"limit_bytes":4096,"state":"running"});
        let tree = serde_json::json!({"owner":11,"owner_started":100,"monitor":[12,200],"controller":[13,300],"limit_bytes":4096,"cleanup_complete":true,"state":"child_exited","processes":[],"footprint_bytes":0,"custody":{"held":false,"released":"cleanup_complete","lock_files":[[1,1],[1,2],[1,3]]}});
        let raw_process = serde_json::to_vec(&process).unwrap();
        let raw_tree = serde_json::to_vec(&tree).unwrap();
        let binding = GuardBinding {
            directory: "guard".into(),
            invocation: "0123456789abcdef0123456789abcdef".into(),
            child,
            monitor,
            controller: controller.clone(),
            locks: locks.clone(),
            controller_source: crate::source_hashes::sha256(b"controller"),
            issuer_source: crate::source_hashes::sha256(b"issuer"),
            request_digest: crate::source_hashes::sha256(b"request"),
            returncode: 0,
            process_digest: crate::source_hashes::sha256(&raw_process),
            tree_digest: crate::source_hashes::sha256(&raw_tree),
        };
        assert!(verify_raw_guard(&anchored, &binding, &locks, &controller).is_err());
        // A wrapper's selfassertion is insufficient without BOTH independent raw guards.
        fs::write(root.join("guard/cleanup.json"), br#"{"confirmed":true}"#).unwrap();
        assert!(verify_raw_guard(&anchored, &binding, &locks, &controller).is_err());
        fs::write(root.join("guard/memory-health.json"), &raw_process).unwrap();
        fs::write(root.join("guard/memory-health-tree.json"), &raw_tree).unwrap();
        verify_raw_guard(&anchored, &binding, &locks, &controller).unwrap();
        fs::create_dir(root.join("guard/lost-offer-known-1")).unwrap();
        assert!(verify_raw_guard(&anchored, &binding, &locks, &controller).is_err());
        fs::remove_dir(root.join("guard/lost-offer-known-1")).unwrap();
        let mut wrong = tree;
        wrong["custody"]["lock_files"] = serde_json::json!([[1, 1], [1, 2]]);
        fs::write(
            root.join("guard/memory-health-tree.json"),
            serde_json::to_vec(&wrong).unwrap(),
        )
        .unwrap();
        assert!(verify_raw_guard(&anchored, &binding, &locks, &controller).is_err());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn exact_identity_and_expired_absolute_deadline_never_become_fixture_authority() {
        let identity = process_identity(std::process::id()).unwrap();
        assert_eq!(identity.pid, std::process::id());
        assert!(!identity.started.is_empty());
        assert_eq!(identity.boot.len(), 36);
        assert!(process_identity(0).is_err());
        assert!(deadline_absolute(1).is_err());
    }
    #[test]
    fn absolute_clock_domain_refuses_mach_origin_and_rechecks_after_elapsed_sleep() {
        let deadline = Deadline { absolute_ns: 1_000 };
        assert_eq!(
            deadline.remaining_at(900, CLOCK_DOMAIN).unwrap(),
            Duration::from_nanos(100)
        );
        // Distinguishable numeric origins cannot silently manufacture another 950ns.
        assert!(
            deadline
                .remaining_at(50, "python-mach-absolute-time-v1")
                .is_err()
        );
        assert!(deadline.remaining_at(1_001, CLOCK_DOMAIN).is_err());
        assert!(Deadline::new(u64::MAX, "unknown-clock").is_err());
        let mut t = std::mem::MaybeUninit::<libc::timespec>::uninit();
        assert_eq!(
            unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, t.as_mut_ptr()) },
            0
        );
        let before = unsafe { t.assume_init() };
        let before = before.tv_sec as u64 * 1_000_000_000 + before.tv_nsec as u64;
        let sampled = monotonic_ns().unwrap();
        assert_eq!(
            unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, t.as_mut_ptr()) },
            0
        );
        let after = unsafe { t.assume_init() };
        let after = after.tv_sec as u64 * 1_000_000_000 + after.tv_nsec as u64;
        assert!(before <= sampled && sampled <= after);
    }
    #[test]
    fn fresh_default_output_needs_no_plan_and_refuses_aliases_or_missing_overrides() {
        let root = root();
        let locks = CheckoutLocks::open(&root).unwrap();
        let build = locks.try_build_exclusive().unwrap();
        let write = build.try_legacy_write_content().unwrap();
        let output = root.join("build/fixture");
        assert!(!output.exists());
        prepare_default_output(&build, &write, &output, "fixture").unwrap();
        assert!(output.is_dir());
        assert!(fs::read_dir(&output).unwrap().next().is_none());
        for path in ["Content", "stamps", "cache", ".state"] {
            assert!(!output.join(path).exists());
        }
        let missing = root.join("missing/override");
        assert!(prepare_default_output(&build, &write, &missing, "fixture").is_err());
        assert!(!root.join("missing").exists());
        fs::create_dir(root.join("target")).unwrap();
        std::os::unix::fs::symlink(root.join("target"), root.join("build/alias")).unwrap();
        assert!(
            prepare_default_output(&build, &write, &root.join("build/alias"), "alias").is_err()
        );
        assert!(
            prepare_default_output(&build, &write, &root.join("build/../escape"), "fixture")
                .is_err()
        );
        assert!(fs::read_dir(root.join("target")).unwrap().next().is_none());
        drop(write);
        drop(build);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn fd_inventory_rejects_full_truncated_duplicate_and_unknown_rows() {
        let entries = [
            ProcFd { fd: 0, kind: 1 },
            ProcFd { fd: 4096, kind: 1 },
            ProcFd::default(),
        ];
        assert_eq!(validate_fd_inventory(&entries, 16).unwrap(), vec![0, 4096]);
        assert!(validate_fd_inventory(&entries, 24).is_err());
        assert!(validate_fd_inventory(&entries, 15).is_err());
        assert!(validate_fd_inventory(&entries, 0).is_err());
        let duplicate = [
            ProcFd { fd: 3, kind: 1 },
            ProcFd { fd: 3, kind: 1 },
            ProcFd::default(),
        ];
        assert!(validate_fd_inventory(&duplicate, 16).is_err());
    }
    #[cfg(target_os = "linux")]
    #[test]
    fn child_sanitizer_covers_high_inheritable_fd_above_lowered_limit_and_preserves_exec_error() {
        let file = File::open("/dev/null").unwrap();
        let mut original = std::mem::MaybeUninit::<libc::rlimit>::uninit();
        assert_eq!(
            unsafe { libc::getrlimit(libc::RLIMIT_NOFILE, original.as_mut_ptr()) },
            0
        );
        let original = unsafe { original.assume_init() };
        let target = (original.rlim_cur / 2).min(4096) as i32;
        assert!(target >= 64);
        let high = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD_CLOEXEC, target) };
        assert!(high >= target);
        let high = unsafe { File::from_raw_fd(high) };
        let sentinel = high.as_raw_fd();
        let mut command = Command::new("/bin/sh");
        command.args(["-c", &format!("test ! -e /proc/self/fd/{sentinel}")]);
        unsafe {
            command.pre_exec(move || {
                if libc::fcntl(sentinel, libc::F_SETFD, 0) < 0 {
                    return Err(io::Error::last_os_error());
                }
                let mut limits = std::mem::MaybeUninit::<libc::rlimit>::uninit();
                if libc::getrlimit(libc::RLIMIT_NOFILE, limits.as_mut_ptr()) != 0 {
                    return Err(io::Error::last_os_error());
                }
                let mut limits = limits.assume_init();
                limits.rlim_cur = ((target / 2) as libc::rlim_t).min(limits.rlim_cur);
                if libc::setrlimit(libc::RLIMIT_NOFILE, &limits) != 0 {
                    return Err(io::Error::last_os_error());
                }
                sanitize_child_fds(&[], &[])
            });
        }
        assert!(command.status().unwrap().success());
        let mut missing = Command::new("/definitely-missing/atelier-legacy-exec-error-probe");
        unsafe {
            missing.pre_exec(|| sanitize_child_fds(&[], &[]));
        }
        assert!(missing.spawn().is_err());
        assert_ne!(
            unsafe { libc::fcntl(sentinel, libc::F_GETFD) } & libc::FD_CLOEXEC,
            0
        );
    }
    #[test]
    fn nonblocking_reply_pipe_stopped_reader_cannot_cross_absolute_deadline() {
        let (reader, writer) = std::io::pipe().unwrap();
        let flags = unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_GETFL) };
        assert_eq!(
            unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK) },
            0
        );
        let chunk = [1u8; 4096];
        loop {
            let n =
                unsafe { libc::write(writer.as_raw_fd(), chunk.as_ptr() as *const _, chunk.len()) };
            if n < 0 {
                assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
                break;
            }
        }
        let deadline = Deadline::after(Duration::from_millis(20));
        assert!(write_all(writer.as_raw_fd(), &[0u8; 65536], deadline).is_err());
        assert!(deadline.expired());
        drop(reader);
    }
    #[test]
    fn partial_ack_closes_permission_before_reserved_drain_without_second_frame() {
        let (mut reader, writer) = std::io::pipe().unwrap();
        let flags = unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_GETFL) };
        assert_eq!(
            unsafe { libc::fcntl(writer.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK) },
            0
        );
        let fill = [1u8; 4096];
        let mut queued = 0usize;
        loop {
            let n =
                unsafe { libc::write(writer.as_raw_fd(), fill.as_ptr() as *const _, fill.len()) };
            if n < 0 {
                assert_eq!(io::Error::last_os_error().kind(), io::ErrorKind::WouldBlock);
                break;
            }
            queued += n as usize;
        }
        let mut room = [0u8; 4096];
        reader.read_exact(&mut room).unwrap();
        queued -= room.len();
        let overall = Deadline::after(Duration::from_secs(5));
        let work = overall.cap(20_000_000).unwrap();
        let mut permission = Some(writer);
        // Actual maximum frame plus length header: at least part reaches the stopped
        // reader, then the OWNED nonblocking write hits its WORK deadline.
        assert!(
            write_all(
                permission.as_ref().unwrap().as_raw_fd(),
                &[2u8; 65540],
                work
            )
            .is_err()
        );
        assert!(work.expired());
        let drain = begin_permission_drain(&mut permission, overall, 4_000_000_000);
        assert!(permission.is_none());
        assert!(drain.remaining().is_ok());
        let mut retained = Vec::new();
        reader.read_to_end(&mut retained).unwrap();
        assert!(retained.len() > queued);
        assert!(retained.len() < queued + 65540);
        assert!(overall.remaining().is_ok());
    }
}
