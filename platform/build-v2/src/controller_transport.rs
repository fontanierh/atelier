//! Private caller handoff. Startup/liveness is control, never semantic job input.
use crate::controller::{
    self, ControllerRequest, ExecutionContext, ExecutionObservation, MAX_CONTROL_BYTES,
};
use crate::failure_policy::Limits;
use crate::guard_adapter::GuardedLauncher;
use crate::leases::ProcessIdentity;
use crate::scheduler::Control;
use crate::schema::Provenance;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, RawFd};
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

static CANCELLED: AtomicBool = AtomicBool::new(false);
struct Cancellation {
    parent: RawFd,
}
impl Control for Cancellation {
    fn cancelled(&self) -> bool {
        if CANCELLED.load(Ordering::Relaxed) {
            return true;
        }
        // After the one startup byte the live parent sends no further data. EOF,
        // an extra byte or a broken provider is a persistent cancellation fact.
        let mut poll = libc::pollfd {
            fd: self.parent,
            events: libc::POLLIN,
            revents: 0,
        };
        if unsafe { libc::poll(&mut poll, 1, 0) } != 0 {
            CANCELLED.store(true, Ordering::Relaxed);
        }
        CANCELLED.load(Ordering::Relaxed)
    }
}
extern "C" fn cancel(_: libc::c_int) {
    CANCELLED.store(true, Ordering::Relaxed);
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Invocation {
    pub version: u32,
    pub nonce: String,
    pub controller_source: String,
    pub request: ControllerRequest,
    pub execution: ExecutionSettings,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionSettings {
    pub cache_root: PathBuf,
    pub interpreter: PathBuf,
    pub owner: ProcessIdentity,
    pub provenance: Provenance,
    pub worktree_id: String,
    pub memory_gib: u32,
    pub job_seconds: u64,
    pub cleanup_seconds: u64,
    pub overall_seconds: u64,
}

#[derive(Serialize)]
pub struct Report {
    pub version: u32,
    pub nonce: String,
    pub controller_source: String,
    pub observation: ExecutionObservation,
}

struct Handoff {
    request: File,
    report: File,
    liveness: File,
}

fn same(left: &std::fs::Metadata, right: &std::fs::Metadata) -> bool {
    (
        left.dev(),
        left.ino(),
        left.uid(),
        left.mode(),
        left.len(),
        left.mtime(),
        left.mtime_nsec(),
        left.ctime(),
        left.ctime_nsec(),
        left.nlink(),
    ) == (
        right.dev(),
        right.ino(),
        right.uid(),
        right.mode(),
        right.len(),
        right.mtime(),
        right.mtime_nsec(),
        right.ctime(),
        right.ctime_nsec(),
        right.nlink(),
    )
}

impl Handoff {
    /// @cc [owner:fontanierh,label:safety] normal-controller-owned-fd-handoff
    /// Startup MUST consume distinct owned capabilities: private unique regular request/report
    /// files with correct access and an empty report, plus a read-only parent pipe. Every
    /// descriptor MUST regain CLOEXEC before any worker can start. Only the caller owns the
    /// pipe writer; no path lookup may replace these supplied capabilities. See
    /// tests::handoff_rejects_wrong_access_public_alias_and_occupied_report and
    /// tests::startup_release_and_parent_eof_are_observed_before_dispatch.
    fn open(inherited: [File; 3]) -> Result<Self, String> {
        let fds = inherited.each_ref().map(AsRawFd::as_raw_fd);
        if fds.iter().any(|fd| *fd < 3) || fds[0] == fds[1] || fds[0] == fds[2] || fds[1] == fds[2]
        {
            return Err("invalid handoff descriptors".into());
        }
        let mut files = vec![];
        for (index, file) in inherited.into_iter().enumerate() {
            let fd = file.as_raw_fd();
            let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
            let access = if index == 1 {
                libc::O_WRONLY
            } else {
                libc::O_RDONLY
            };
            if flags < 0 || flags & libc::O_ACCMODE != access {
                return Err("invalid handoff descriptor access".into());
            }
            if unsafe { libc::fcntl(fd, libc::F_SETFD, libc::FD_CLOEXEC) } < 0 {
                return Err("cannot close handoff descriptors across worker exec".into());
            }
            let metadata = file
                .metadata()
                .map_err(|_| "cannot observe handoff descriptor")?;
            if index < 2 {
                if metadata.uid() != unsafe { libc::geteuid() }
                    || !metadata.is_file()
                    || metadata.mode() & 0o077 != 0
                    || metadata.nlink() != 1
                {
                    return Err("handoff control file is not private regular unique data".into());
                }
                if metadata.len() > MAX_CONTROL_BYTES as u64 || (index == 1 && metadata.len() != 0)
                {
                    return Err("handoff control file has invalid size".into());
                }
            } else if !metadata.file_type().is_fifo() {
                return Err("parent liveness is not a pipe".into());
            }
            files.push(file);
        }
        let liveness = files.pop().unwrap();
        let report = files.pop().unwrap();
        let request = files.pop().unwrap();
        let a = request.metadata().map_err(|_| "cannot observe request")?;
        let b = report.metadata().map_err(|_| "cannot observe report")?;
        if a.dev() == b.dev() && a.ino() == b.ino() {
            return Err("request/report alias".into());
        }
        Ok(Self {
            request,
            report,
            liveness,
        })
    }

    fn await_parent(&mut self) -> Result<(), String> {
        let until = Instant::now() + Duration::from_secs(30);
        while Instant::now() < until && !CANCELLED.load(Ordering::Relaxed) {
            let mut poll = libc::pollfd {
                fd: self.liveness.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            let result = unsafe { libc::poll(&mut poll, 1, 100) };
            if result < 0 {
                if std::io::Error::last_os_error().kind() == std::io::ErrorKind::Interrupted {
                    continue;
                }
                return Err("startup pipe observation failed".into());
            }
            if result > 0 {
                let mut byte = [0];
                if self
                    .liveness
                    .read(&mut byte)
                    .map_err(|_| "startup pipe read failed")?
                    == 1
                    && byte == [b'G']
                {
                    return Ok(());
                }
                return Err("parent lost or invalid startup release".into());
            }
        }
        Err("startup cancelled or deadline reached".into())
    }

    fn invocation(&mut self) -> Result<Invocation, String> {
        let before = self
            .request
            .metadata()
            .map_err(|_| "cannot observe request")?;
        if before.uid() != unsafe { libc::geteuid() }
            || before.mode() & 0o077 != 0
            || before.nlink() != 1
        {
            return Err("request lost private ownership before release".into());
        }
        if before.len() > MAX_CONTROL_BYTES as u64 {
            return Err("request exceeds bound".into());
        }
        let mut bytes = vec![];
        (&mut self.request)
            .take(MAX_CONTROL_BYTES as u64 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| "cannot read request")?;
        let after = self
            .request
            .metadata()
            .map_err(|_| "cannot reobserve request")?;
        if !same(&before, &after) || bytes.len() != before.len() as usize {
            return Err("request changed during handoff".into());
        }
        crate::py_data::validate_py_data_payload("JsonData", "invocation.json", &bytes)
            .map_err(|_| "invalid invocation JSON")?;
        let invocation: Invocation =
            serde_json::from_slice(&bytes).map_err(|_| "invalid invocation shape")?;
        if invocation.version != controller::CONTROL_VERSION
            || invocation.nonce.len() != 32
            || !invocation
                .nonce
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
            || Some(invocation.controller_source.as_str()) != controller::source_identity()
            || invocation.execution.owner.pid != std::process::id()
        {
            return Err("invocation identity mismatch".into());
        }
        invocation.request.check()?;
        Ok(invocation)
    }

    fn write_report(&mut self, report: &Report) -> Result<(), String> {
        let raw = serde_json::to_vec(report).map_err(|_| "cannot encode controller report")?;
        if raw.len() > MAX_CONTROL_BYTES {
            return Err("controller report exceeds bound".into());
        }
        let before = self
            .report
            .metadata()
            .map_err(|_| "cannot observe report")?;
        if before.len() != 0
            || before.uid() != unsafe { libc::geteuid() }
            || before.mode() & 0o077 != 0
            || before.nlink() != 1
        {
            return Err("report changed before publication".into());
        }
        self.report
            .write_all(&raw)
            .and_then(|_| self.report.sync_all())
            .map_err(|_| "cannot persist controller report")?;
        let after = self
            .report
            .metadata()
            .map_err(|_| "cannot reobserve report")?;
        if after.uid() != before.uid()
            || after.mode() != before.mode()
            || after.nlink() != 1
            || after.len() != raw.len() as u64
        {
            return Err("report changed during publication".into());
        }
        Ok(())
    }
}

/// Start/boot authority is the live parent's OS probe and owned private handoff;
/// our self-PID comparison alone does not certify those metadata fields.
pub fn run(inherited: [File; 3]) -> Result<(), String> {
    if controller::source_identity().is_none() {
        return Err("controller distribution identity unavailable".into());
    }
    for signal in [libc::SIGTERM, libc::SIGHUP, libc::SIGINT] {
        if unsafe { libc::signal(signal, cancel as libc::sighandler_t) } == libc::SIG_ERR {
            return Err("cannot install cancellation handler".into());
        }
    }
    let mut handoff = Handoff::open(inherited)?;
    handoff.await_parent()?;
    let control = Cancellation {
        parent: handoff.liveness.as_raw_fd(),
    };
    let invocation = handoff.invocation()?;
    let execution = invocation.execution;
    let launcher = GuardedLauncher {
        bridge: vec![
            execution.interpreter.clone().into_os_string(),
            "-m".into(),
            "atelier.build_v2.guarded_worker".into(),
        ],
    };
    let observation = controller::execute(
        &invocation.request,
        ExecutionContext {
            cache_root: execution.cache_root,
            interpreter: execution.interpreter,
            owner: execution.owner,
            provenance: execution.provenance,
            worktree_id: execution.worktree_id,
            memory_gib: execution.memory_gib,
            limits: Limits {
                job: Duration::from_secs(execution.job_seconds),
                cleanup: Duration::from_secs(execution.cleanup_seconds),
                overall: Some(Duration::from_secs(execution.overall_seconds)),
            },
        },
        launcher,
        &control,
    )?;
    handoff.write_report(&Report {
        version: controller::CONTROL_VERSION,
        nonce: invocation.nonce,
        controller_source: invocation.controller_source,
        observation,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs::{self, OpenOptions};
    use std::os::fd::FromRawFd;
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
    use std::sync::atomic::AtomicU64;
    static NEXT: AtomicU64 = AtomicU64::new(0);
    struct Space(PathBuf);
    impl Space {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "atelier-controller-fd-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&root).unwrap();
            Self(root)
        }
    }
    impl Drop for Space {
        fn drop(&mut self) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
    fn inherited(space: &Space) -> ([File; 3], File) {
        let request = space.0.join("request.json");
        fs::write(&request, b"{}").unwrap();
        fs::set_permissions(&request, fs::Permissions::from_mode(0o600)).unwrap();
        let request = File::open(request).unwrap();
        let report = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(space.0.join("report.json"))
            .unwrap();
        let mut pipe = [-1; 2];
        assert_eq!(unsafe { libc::pipe(pipe.as_mut_ptr()) }, 0);
        // pipe() returned two fresh descriptors owned only by this fixture.
        let (reader, writer) = unsafe { (File::from_raw_fd(pipe[0]), File::from_raw_fd(pipe[1])) };
        ([request, report, reader], writer)
    }

    #[test]
    fn handoff_rejects_wrong_access_public_alias_and_occupied_report() {
        for fault in ["access", "public", "alias", "occupied"] {
            let space = Space::new();
            let (mut files, _writer) = inherited(&space);
            match fault {
                "access" => {
                    files[0] = OpenOptions::new()
                        .read(true)
                        .write(true)
                        .open(space.0.join("request.json"))
                        .unwrap()
                }
                "public" => fs::set_permissions(
                    space.0.join("report.json"),
                    fs::Permissions::from_mode(0o644),
                )
                .unwrap(),
                "alias" => {
                    fs::hard_link(space.0.join("request.json"), space.0.join("extra-link")).unwrap()
                }
                "occupied" => fs::write(space.0.join("report.json"), b"existing evidence").unwrap(),
                _ => unreachable!(),
            }
            assert!(Handoff::open(files).is_err(), "accepted {fault}");
            assert_eq!(fs::read(space.0.join("request.json")).unwrap(), b"{}");
            if fault == "occupied" {
                assert_eq!(
                    fs::read(space.0.join("report.json")).unwrap(),
                    b"existing evidence"
                );
            }
        }
        let space = Space::new();
        let (files, _writer) = inherited(&space);
        let mut handoff = Handoff::open(files).unwrap();
        fs::set_permissions(
            space.0.join("request.json"),
            fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        assert!(
            handoff
                .invocation()
                .err()
                .unwrap()
                .contains("private ownership")
        );
    }

    #[test]
    fn startup_release_and_parent_eof_are_observed_before_dispatch() {
        CANCELLED.store(false, Ordering::Relaxed);
        let space = Space::new();
        let (files, mut writer) = inherited(&space);
        let mut handoff = Handoff::open(files).unwrap();
        for file in [&handoff.request, &handoff.report, &handoff.liveness] {
            assert_ne!(
                unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC,
                0
            );
        }
        writer.write_all(b"G").unwrap();
        handoff.await_parent().unwrap();
        let control = Cancellation {
            parent: handoff.liveness.as_raw_fd(),
        };
        assert!(!control.cancelled());
        drop(writer);
        assert!(control.cancelled());
        assert_eq!(fs::metadata(space.0.join("report.json")).unwrap().len(), 0);
        CANCELLED.store(false, Ordering::Relaxed);

        let other = Space::new();
        let (files, writer) = inherited(&other);
        let mut handoff = Handoff::open(files).unwrap();
        drop(writer);
        assert!(
            handoff.await_parent().is_err(),
            "lost parent released startup"
        );
        assert_eq!(fs::metadata(other.0.join("report.json")).unwrap().len(), 0);
    }
}
